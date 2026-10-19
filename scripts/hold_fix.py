#!/usr/bin/env python3
"""
hold_fix.py - hold-time ECO on a Yosys JSON netlist.

Hold is checked at the fast corner (shortest delays). For every flip-flop
data pin whose hold slack is below the margin, a delay buffer is inserted directly in
front of the pin; the netlist is re-timed and the loop repeats until hold is
met or the iteration limit is reached. Each round only touches pins that
still violate, so buffers are not added where they are not needed.

The fixed netlist is written as JSON; run_flow.py converts it to Verilog
with Yosys for gate-level simulation.

Usage
  python scripts/hold_fix.py --lib-fast liberty/nangate45_fast.lib \
      --netlist in.json --top dot2_v5 --sdc constraints/dot2.sdc \
      --out out.json [--buffer BUF_X1] [--max-iter 8]
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sta import Design, Library, Timer, parse_sdc  # noqa: E402


def hold_violations(lib, netlist_path, top, sdc_path, margin):
    design = Design(lib, netlist_path, top)
    sdc = parse_sdc(sdc_path, design.in_ports, design.out_ports)
    timer = Timer(design, sdc)
    timer.run()
    viol = [e for e in timer.worst("hold") if e["slack"] < margin and e["node"][0] is not None]
    whs = timer.worst("hold")[0]["slack"]
    return design, viol, whs


def insert_buffer(data, top, inst, pin, buf_cell, idx):
    """Insert buf_cell between the net driving inst/pin and the pin."""
    mod = data["modules"][top]
    used = [b for c in mod["cells"].values() for bits in c["connections"].values()
            for b in bits if isinstance(b, int)]
    used += [b for p in mod["ports"].values() for b in p["bits"] if isinstance(b, int)]
    new_net = max(used) + 1
    old_net = mod["cells"][inst]["connections"][pin][0]
    name = "holdfix_buf_%d" % idx
    mod["cells"][name] = {
        "hide_name": 0,
        "type": buf_cell,
        "parameters": {},
        "attributes": {},
        "port_directions": {"A": "input", "Z": "output"},
        "connections": {"A": [old_net], "Z": [new_net]},
    }
    mod["cells"][inst]["connections"][pin] = [new_net]
    mod["netnames"]["holdfix_net_%d" % idx] = {"hide_name": 0, "bits": [new_net], "attributes": {}}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lib-fast", required=True)
    ap.add_argument("--netlist", required=True)
    ap.add_argument("--top", required=True)
    ap.add_argument("--sdc", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--buffer", default="BUF_X1")
    ap.add_argument("--max-iter", type=int, default=8)
    ap.add_argument("--margin", type=float, default=0.010,
                    help="required hold slack in ns (default 0.010)")
    ap.add_argument("--log", help="append a summary line per iteration here")
    a = ap.parse_args()

    lib = Library(a.lib_fast)
    if a.buffer not in lib.cells:
        sys.exit("buffer cell %s not in library" % a.buffer)
    data = json.load(open(a.netlist))
    tmp = a.out + ".tmp"
    json.dump(data, open(tmp, "w"))

    lines = []
    added = 0
    for it in range(a.max_iter + 1):
        design, viol, whs = hold_violations(lib, tmp, a.top, a.sdc, a.margin)
        msg = "iteration %d: worst hold slack %+.4f ns, %d pins below %.3f ns margin, %d buffers so far" % (
            it, whs, len(viol), a.margin, added)
        print(msg)
        lines.append(msg)
        if not viol or it == a.max_iter:
            break
        for e in viol:
            inst, pin = e["node"]
            insert_buffer(data, a.top, inst, pin, a.buffer, added)
            added += 1
        json.dump(data, open(tmp, "w"))

    os.replace(tmp, a.out)
    if a.log:
        with open(a.log, "a") as f:
            f.write("%s: %s\n" % (a.top, lines[-1]))
    if viol:
        sys.exit("hold not closed after %d iterations" % a.max_iter)


if __name__ == "__main__":
    main()
