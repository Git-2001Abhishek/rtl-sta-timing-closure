# Timing summary

Target clock period **1.000 ns** (1000 MHz), NanGate45, wire-load model `5K_hvratio_1_1`, Yosys `synth -noabc`. Hold fixed at the fast corner (10 ps margin) before analysis.

Corners: **slow** = SS 0.95 V 125 C, **typ** = TT 1.10 V 25 C, **fast** = FF 1.25 V 0 C.

## Setup (typical corner, the synthesis target)

| Design | Latency | Cells | Flops | Area (um^2) | Setup slack (ns) | TNS (ns) | Setup viol. | Min period (ns) | Fmax (MHz) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| dot2_v1 | 2 | 3277 | 99 | 4000.1 | -1.251 | -20.926 | 29 / 133 | 2.251 | 444 |
| dot2_v2 | 3 | 3255 | 164 | 4221.7 | -0.974 | -28.495 | 63 / 198 | 1.974 | 507 |
| dot2_v3 | 4 | 3332 | 261 | 4620.7 | -0.592 | -22.731 | 87 / 295 | 1.592 | 628 |
| dot2_v4 | 5 | 3432 | 422 | 5314.1 | -0.402 | -17.844 | 102 / 456 | 1.402 | 713 |
| dot2_v5 | 4 | 3596 | 334 | 5150.8 | +0.020 | 0.000 | 0 / 368 | 0.980 | 1021 |

## All corners

| Design | Fmax slow (MHz) | Fmax typ (MHz) | Fmax fast (MHz) | Hold slack slow / typ / fast (ns) | Hold buffers added |
| --- | --- | --- | --- | --- | --- |
| dot2_v1 | 124 | 444 | 789 | +0.123 / +0.059 / +0.015 | 1 |
| dot2_v2 | 144 | 507 | 886 | +0.123 / +0.053 / +0.011 | 2 |
| dot2_v3 | 180 | 628 | 1076 | +0.123 / +0.053 / +0.011 | 38 |
| dot2_v4 | 207 | 713 | 1213 | +0.123 / +0.053 / +0.011 | 74 |
| dot2_v5 | 297 | 1021 | 1733 | +0.123 / +0.053 / +0.011 | 11 |

## Critical paths (typical corner)

- **dot2_v1** (baseline: multiply + add in one stage): `b_q_reg[3]/CK (DFF_X1)` -> `y_reg[31]/D (DFF_X1)`, arrival 2.170 ns
- **dot2_v2** (multiply / add split into two stages): `a_q_reg[1]/CK (DFF_X1)` -> `ab_q_reg[31]/D (DFF_X1)`, arrival 1.887 ns
- **dot2_v3** (half-width partial products + recombine stage): `b_q_reg[13]/CK (DFF_X1)` -> `ab_hi_q_reg[22]/D (DFF_X1)`, arrival 1.509 ns
- **dot2_v4** (quarter-width partial products + registered adder tree): `c_q_reg[3]/CK (DFF_X1)` -> `cd_pp_q[0]_reg[18]/D (DFF_X1)`, arrival 1.320 ns
- **dot2_v5** (carry-save reduction tree + Kogge-Stone adder): `s_q_reg[5]/CK (DFF_X1)` -> `y_reg[31]/D (DFF_X1)`, arrival 0.894 ns
