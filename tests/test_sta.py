"""
Unit tests for scripts/sta.py with hand-computed expectations.

Run:  python -m pytest tests -q
"""
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import sta  # noqa: E402

# -----------------------------------------------------------------------------
# A tiny library. Delays are made load- and slew-independent (2x2 tables with
# equal entries) and differ between rise and fall, so the unateness handling
# shows up in the results.
# -----------------------------------------------------------------------------
TINY_LIB = r"""
library (tiny) {
  delay_model : table_lookup;
  time_unit : "1ns";
  capacitive_load_unit (1,ff);
  lu_table_template (delay_2x2) {
    variable_1 : input_net_transition;
    variable_2 : total_output_net_capacitance;
    index_1 ("0.01, 0.1");
    index_2 ("1.0, 10.0");
  }
  lu_table_template (constraint_2x2) {
    variable_1 : constrained_pin_transition;
    variable_2 : related_pin_transition;
    index_1 ("0.01, 0.1");
    index_2 ("0.01, 0.1");
  }
  cell (INV) {
    area : 1.0;
    pin (A) { direction : input; capacitance : 2.0; }
    pin (Y) {
      direction : output;
      function : "!A";
      timing () {
        related_pin : "A";
        timing_sense : negative_unate;
        cell_rise (delay_2x2) { values ("0.10, 0.10", "0.10, 0.10"); }
        cell_fall (delay_2x2) { values ("0.05, 0.05", "0.05, 0.05"); }
        rise_transition (delay_2x2) { values ("0.02, 0.02", "0.02, 0.02"); }
        fall_transition (delay_2x2) { values ("0.02, 0.02", "0.02, 0.02"); }
      }
    }
  }
  cell (DFF) {
    area : 4.0;
    ff ("IQ", "IQN") { next_state : "D"; clocked_on : "CK"; }
    pin (D) {
      direction : input;
      capacitance : 1.0;
      timing () {
        related_pin : "CK";
        timing_type : setup_rising;
        rise_constraint (constraint_2x2) { values ("0.03, 0.03", "0.03, 0.03"); }
        fall_constraint (constraint_2x2) { values ("0.04, 0.04", "0.04, 0.04"); }
      }
      timing () {
        related_pin : "CK";
        timing_type : hold_rising;
        rise_constraint (constraint_2x2) { values ("0.01, 0.01", "0.01, 0.01"); }
        fall_constraint (constraint_2x2) { values ("0.02, 0.02", "0.02, 0.02"); }
      }
    }
    pin (CK) { direction : input; capacitance : 1.0; clock : true; }
    pin (Q) {
      direction : output;
      function : "IQ";
      timing () {
        related_pin : "CK";
        timing_type : rising_edge;
        cell_rise (delay_2x2) { values ("0.20, 0.20", "0.20, 0.20"); }
        cell_fall (delay_2x2) { values ("0.30, 0.30", "0.30, 0.30"); }
        rise_transition (delay_2x2) { values ("0.02, 0.02", "0.02, 0.02"); }
        fall_transition (delay_2x2) { values ("0.02, 0.02", "0.02, 0.02"); }
      }
    }
  }
}
"""

SDC = """
set clk_period 1.0
create_clock -name clk -period $clk_period [get_ports clk]
set_clock_uncertainty 0.05 [get_clocks clk]
set_clock_transition 0.02 [get_clocks clk]
"""


def cell(ctype, conns):
    return {"hide_name": 0, "type": ctype, "parameters": {}, "attributes": {},
            "connections": {k: [v] for k, v in conns.items()}}


@pytest.fixture
def chain(tmp_path):
    """ff1.Q -> inv1 -> inv2 -> ff2.D, both flops clocked by port clk."""
    lib_path = tmp_path / "tiny.lib"
    lib_path.write_text(TINY_LIB)
    # net ids: 2 = clk, 3 = d1 (ff1 data, from port din), 4 = q1, 5 = n1, 6 = n2, 7 = q2
    netlist = {"modules": {"top": {
        "ports": {"clk": {"direction": "input", "bits": [2]},
                  "din": {"direction": "input", "bits": [3]},
                  "dout": {"direction": "output", "bits": [7]}},
        "cells": {
            "ff1": cell("DFF", {"CK": 2, "D": 3, "Q": 4}),
            "inv1": cell("INV", {"A": 4, "Y": 5}),
            "inv2": cell("INV", {"A": 5, "Y": 6}),
            "ff2": cell("DFF", {"CK": 2, "D": 6, "Q": 7}),
        },
        "netnames": {n: {"hide_name": 0, "bits": [b]} for n, b in
                     (("clk", 2), ("din", 3), ("q1", 4), ("n1", 5), ("n2", 6), ("dout", 7))},
    }}}
    net_path = tmp_path / "net.json"
    net_path.write_text(json.dumps(netlist))
    sdc_path = tmp_path / "t.sdc"
    sdc_path.write_text(SDC)
    lib = sta.Library(str(lib_path))
    design = sta.Design(lib, str(net_path), "top")
    sdc = sta.parse_sdc(str(sdc_path), design.in_ports, design.out_ports)
    timer = sta.Timer(design, sdc)
    timer.run()
    return lib, design, timer


# ------------------------------------------------------------------ tables
def test_table_bilinear_and_extrapolation(tmp_path):
    lib_text = TINY_LIB.replace('values ("0.10, 0.10", "0.10, 0.10")',
                                'values ("0.10, 0.20", "0.30, 0.40")')
    p = tmp_path / "t.lib"
    p.write_text(lib_text)
    tbl = sta.Library(str(p)).cells["INV"].pins["Y"].arcs[0].delay[sta.RISE]
    # grid points
    assert tbl.lookup(input_slew=0.01, load=1.0) == pytest.approx(0.10)
    assert tbl.lookup(input_slew=0.1, load=10.0) == pytest.approx(0.40)
    # centre of the cell: mean of the four corners
    assert tbl.lookup(input_slew=0.055, load=5.5) == pytest.approx(0.25)
    # linear extrapolation beyond the last load point
    assert tbl.lookup(input_slew=0.01, load=19.0) == pytest.approx(0.30)


# ------------------------------------------------------------ propagation
def test_arrival_rise_fall_through_inverters(chain):
    _, _, t = chain
    d = ("ff2", "D")
    # Q rise 0.20 -> inv1 fall +0.05 -> inv2 rise +0.10 = 0.35 (D rises)
    # Q fall 0.30 -> inv1 rise +0.10 -> inv2 fall +0.05 = 0.45 (D falls)
    assert t.at_max[d][sta.RISE] == pytest.approx(0.35)
    assert t.at_max[d][sta.FALL] == pytest.approx(0.45)
    assert t.at_min[d][sta.RISE] == pytest.approx(0.35)
    assert t.at_min[d][sta.FALL] == pytest.approx(0.45)


def test_setup_slack(chain):
    _, design, t = chain
    worst = t.worst("setup")[0]
    assert worst["node"] == ("ff2", "D")
    # falling data is the late one: 1.0 - 0.05 unc - 0.04 setup - 0.45
    assert worst["slack"] == pytest.approx(0.46)


def test_hold_slack(chain):
    _, _, t = chain
    holds = {e["node"]: e for e in t.worst("hold")}
    # rising data is the early one: 0.35 - (0.01 hold + 0.05 unc)
    assert holds[("ff2", "D")]["slack"] == pytest.approx(0.29)


def test_load_and_path_trace(chain):
    _, design, t = chain
    # q1 drives inv1/A only: 2.0 fF (no wire-load model in this library)
    assert t.load[4] == pytest.approx(2.0)
    path = t.trace(("ff2", "D"), sta.FALL, "max")
    pins = [n for n, _, _ in path]
    assert pins == [("ff1", "CK"), ("ff1", "Q"), ("inv1", "A"), ("inv1", "Y"),
                    ("inv2", "A"), ("inv2", "Y"), ("ff2", "D")]


# --------------------------------------------------------------------- SDC
def test_sdc_bus_matching_and_variables(tmp_path):
    p = tmp_path / "x.sdc"
    p.write_text("""
set p 2.0
create_clock -name clk -period $p [get_ports clk]
set ins [get_ports {en a}]
set_input_delay 0.3 -clock clk $ins
set_output_delay 0.1 -clock clk [all_outputs]
set_false_path -from [get_ports rst_n]
""")
    ins = ["clk", "rst_n", "en", "a[0]", "a[1]", "abc"]
    outs = ["y[0]", "y[1]"]
    c = sta.parse_sdc(str(p), ins, outs)
    assert c.period == 2.0
    # "a" matches the whole bus but not "abc", and never the clock
    assert sorted(c.input_delay) == ["a[0]", "a[1]", "en"]
    assert sorted(c.output_delay) == ["y[0]", "y[1]"]
    assert c.false_from == {"rst_n"}


# ------------------------------------------------- real library spot check
NANGATE = os.path.join(ROOT, "liberty", "nangate45_typ.lib")


@pytest.mark.skipif(not os.path.exists(NANGATE), reason="run `make lib` first")
def test_nangate_dff_clk_to_q_matches_hand_interpolation():
    lib = sta.Library(NANGATE)
    arc = [a for a in lib.cells["DFF_X1"].pins["Q"].arcs if a.type == "rising_edge"][0]
    # hand interpolation of the cell_rise table at 0.02 ns slew, 49.94 fF
    # (rows 0.0171859 / 0.0409838, columns 30.365 / 60.73) gives 0.2057 ns
    assert arc.delay[sta.RISE].lookup(input_slew=0.02, load=49.94) == pytest.approx(0.2057, abs=5e-4)
