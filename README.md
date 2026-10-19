# RTL Design, Synthesis & Static Timing Analysis

## Overview

Designed and verified a pipelined arithmetic datapath in SystemVerilog
and evaluated its timing characteristics through RTL synthesis and
static timing analysis.

The datapath is a 16-bit two-term dot product,

```text
y = a*b + c*d          a, b, c, d: 16-bit unsigned,  y: 33-bit
```

implemented in five versions. Each one is an RTL change aimed at the
critical path reported by STA for the version before it. The target is
**1 GHz** in the NanGate 45 nm open cell library.

## Flow

SystemVerilog RTL → Simulation → Synthesis (Yosys) → STA (OpenSTA) → Critical Path Analysis → RTL Optimization

```text
rtl/*.sv ──► Icarus Verilog (tb_dot2: RTL sim, 5 versions in parallel)
   │
   ▼
Yosys  synth -flatten -noabc → dfflibmap → abc -D 1000 -liberty nangate45
   │                                   (scripts/synth.ys, scripts/run_flow.py)
   ├──► gate-level netlists ──► Icarus Verilog (same testbench, -DGLS)
   ▼
STA    constraints/dot2.sdc ──► scripts/sta.py   (+ scripts/sta.tcl for OpenSTA)
   │
   ▼
reports/  setup / hold paths, WNS / TNS, Fmax, area
```

## Features

- Synthesizable SystemVerilog RTL
- Pipelined arithmetic datapath
- SDC timing constraints
- RTL synthesis using Yosys
- Static timing analysis using OpenSTA
- Critical-path identification
- Setup/hold analysis
- Timing optimization through RTL modification
- Gate-level simulation of every synthesized netlist

## Design versions

| Version | Latency | Change | Why |
| --- | --- | --- | --- |
| [`dot2_v1`](rtl/dot2_v1.sv) | 2 | Baseline: input regs → `a*b + c*d` → output reg | Reference point |
| [`dot2_v2`](rtl/dot2_v2.sv) | 3 | Register the products, add in the next stage | v1 critical path = multiplier **plus** 32-bit adder |
| [`dot2_v3`](rtl/dot2_v3.sv) | 4 | Split each multiply into two 16×8 partial products, recombine in a separate stage | v2 critical path = full 16×16 multiplier array |
| [`dot2_v4`](rtl/dot2_v4.sv) | 5 | Four 16×4 partial products per product, adder tree with a register at every level | v3 critical path = 16×8 array |
| [`dot2_v5`](rtl/dot2_v5.sv) | 4 | All 32 partial-product rows of **both** products in one Wallace-style 3:2 carry-save tree, pipelined in the middle, then one [Kogge-Stone](rtl/ks_adder.sv) prefix adder | v1–v4 all end in ripple-carry chains, so extra pipelining gave diminishing returns |

Every version has the same ports (`clk`, `rst_n`, `in_valid`, `a`..`d`,
`out_valid`, `y`). Only the valid pipeline has a reset; datapath flops
don't need one.

## Constraints

[`constraints/dot2.sdc`](constraints/dot2.sdc): 1.0 ns clock, 50 ps clock
uncertainty, 20 ps clock / input transition, 0.2 ns input and output
delays, 2 fF output load, `rst_n` false-pathed. NanGate45 typical corner
(1.1 V, 25 °C), wire-load model `5K_hvratio_1_1`.

## Timing Analysis

The initial implementation is analyzed to identify critical paths
and timing violations. RTL modifications are subsequently evaluated
through synthesis and STA to measure their impact on timing.

### What the critical paths showed

- **v1**: `b_q_reg → y_reg`, 36 gates, 2.17 ns. The path runs through the
  multiplier array and then all the way up the ripple carry of the
  final 33-bit adder.
- **v2**: removing the adder from the stage helps less than expected
  (1.89 ns). The 16×16 array itself is a long ripple structure.
- **v3 / v4**: halving the array height twice brings it down to 1.51 ns, then
  1.32 ns, but the gains shrink. Every partial product still ends in a
  carry-propagate chain (29 gates in both), and v4 needs 5 cycles of latency
  and 4.2× the flops of v1.
- **v5**: carry-save levels have a constant depth (one full adder) no matter
  how wide the operands are. So the design reduces all rows to two with no
  carry propagation at all, and resolves the carry once, in a log-depth
  prefix adder. The critical path is now 16 gates (0.894 ns) inside
  the final-adder stage, with **+20 ps slack at 1 GHz**, at the same
  4-cycle latency as v3.

### Synthesis finding: generic ABC destroys the prefix tree

With the default `synth` script, v5 only reached 883 MHz (5 violating
endpoints). The report showed the Kogge-Stone stage as a ripple-like chain
of AOI/OAI gates. Yosys' generic pre-mapping ABC pass optimizes for area
and had restructured the parallel-prefix carry network. Running
`synth -noabc` leaves all mapping to the single timing-driven
`abc -D 1000 -liberty` run, which keeps the structure, and v5 then closes
timing. The flow now uses `-noabc` for every version. The full
default-flow numbers are in
[`reports/summary_default_synth.md`](reports/summary_default_synth.md).

## Results

Target 1.000 ns, from [`reports/summary.md`](reports/summary.md):

| Design | Latency | Cells | Flops | Area (µm²) | Setup slack (ns) | TNS (ns) | Setup viol. | Hold slack (ns) | Min period (ns) | Fmax (MHz) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| dot2_v1 | 2 | 3276 | 99 | 3999.3 | -1.251 | -20.926 | 29 / 133 | +0.035 | 2.251 | 444 |
| dot2_v2 | 3 | 3253 | 164 | 4220.1 | -0.974 | -28.495 | 63 / 198 | +0.035 | 1.974 | 507 |
| dot2_v3 | 4 | 3294 | 261 | 4590.4 | -0.592 | -22.690 | 87 / 295 | +0.031 | 1.592 | 628 |
| dot2_v4 | 5 | 3358 | 422 | 5255.1 | -0.402 | -17.732 | 101 / 456 | +0.031 | 1.402 | 713 |
| **dot2_v5** | **4** | 3585 | 334 | 5142.0 | **+0.020** | **0.000** | **0 / 368** | +0.031 | **0.980** | **1021** |

![Timing comparison](results/timing_comparison.png)

- **2.3× Fmax** from v1 to v5 (444 → 1021 MHz) for +29 % area.
- v5 is faster than v4 with **one cycle less latency** and fewer flops:
  architecture beat brute-force pipelining.
- No hold violations in any version. The worst hold paths are
  flop-to-flop shift registers (`vld_reg`), which still have 31–35 ps of
  margin even with an ideal clock and 50 ps uncertainty.

Excerpt of the v5 critical path ([full report](reports/dot2_v5_timing.rpt)):

```text
Startpoint: s_q_reg[5]/CK (DFF_X1)
Endpoint:   y_reg[31]/D (DFF_X1)
 Load(fF)      Slew    Delay     Time   Description
     8.80     0.023    0.108    0.108 ^ s_q_reg[5]/Q (DFF_X1)
     6.32     0.043    0.073    0.181 ^ g311/Z (XOR2_X1)        propagate
     3.99     0.017    0.070    0.251 ^ g314/ZN (AND4_X1)       group P
      ...       ...      ...      ...   AOI211 / OAI211 prefix network
     1.45     0.014    0.040    0.894 v g483/ZN (XNOR2_X1)      sum[31]
                                0.894   data arrival time
                      -0.050    0.950   clock uncertainty
                      -0.036    0.914   library setup time
                                0.020   slack (MET)
```

### Verification

- **RTL** ([`results/sim.log`](results/sim.log)): all five versions run
  side by side against a cycle-accurate reference model. The stimulus is
  corner values (0, 1, all-ones, alternating bits) plus 5000 random vectors
  with random `in_valid` bubbles and a reset in the middle of traffic.
  **TEST PASSED**, about 3,775 results checked per version.
- **Gate-level** ([`results/gls.log`](results/gls.log)): the same
  testbench on the five synthesized NanGate45 netlists (zero-delay cell
  models generated from the Liberty `function`s by
  [`scripts/lib2v.py`](scripts/lib2v.py)). **TEST PASSED**.
- Mutation check: breaking the recombine shift in v3 makes the RTL run fail
  on nearly every vector.

### About the STA engine

OpenSTA isn't available on the Windows machine this was developed on, so
the numbers above come from [`scripts/sta.py`](scripts/sta.py), a compact
static timing analyzer written for this project. It does the same
analysis OpenSTA does for a single-clock design in wire-load mode:

- reads the Liberty NLDM tables, the Yosys JSON netlist and the SDC
- propagates rise/fall arrival times and slews through unate arcs using
  bilinear table lookup (input slew × output load)
- net load = pin capacitance + wire-load-model capacitance + `set_load`
- setup and hold checks on flip-flop D pins (Liberty constraint tables) and
  output ports
- prints OpenSTA-style path reports, WNS / TNS and Fmax

Limitations: ideal clock network, no recovery/removal checks on async
reset, no wire RC delay, no CRPR or OCV. Cell delays were hand-checked
against the Liberty tables (e.g. `DFF_X1` CK→Q at 49.9 fF / 20 ps:
table interpolation gives 0.2057 ns, the report shows 0.206 ns).

[`scripts/sta.tcl`](scripts/sta.tcl) runs the same netlists, library,
wire-load model and SDC through OpenSTA (`make opensta`) on a machine
where it is installed.

## How to run

Requirements: Python 3 (+ matplotlib for the chart), Icarus Verilog 12+,
and Yosys. Any Yosys works, including the pip-installable `yowasp-yosys`.

```bash
make lib          # download lib/nangate45_typ.lib (from the OpenSTA repo)
make sim          # RTL simulation
make flow         # synthesis + STA for all versions -> reports/, results/
make gls          # gate-level simulation of the netlists
make opensta      # optional: OpenSTA cross-check
```

With `yowasp-yosys` instead of a native Yosys:

```bash
pip install yowasp-yosys
make flow YOSYS=yowasp-yosys
```

Other target periods: `python scripts/run_flow.py --period 1.25`.

## Tools

- SystemVerilog
- Yosys
- OpenSTA / Python STA engine (`scripts/sta.py`)
- Icarus Verilog
- GTKWave

## Repository Structure

```text
rtl/          - RTL source (dot2_v1 .. dot2_v5, ks_adder)
tb/           - Testbench (RTL and gate-level)
constraints/  - SDC constraints
scripts/      - Synthesis, STA, flow and helper scripts
reports/      - Timing and area reports, summary tables
results/      - Netlists, simulation logs, figures
lib/          - Liberty file (downloaded, not committed)
```
