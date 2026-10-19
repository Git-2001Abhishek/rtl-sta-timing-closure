# Timing summary

Target clock period **1.000 ns** (1000 MHz), NanGate45, wire-load model `5K_hvratio_1_1`, Yosys `synth (default)`. Hold fixed at the fast corner (10 ps margin) before analysis.

Corners: **slow** = SS 0.95 V 125 C, **typ** = TT 1.10 V 25 C, **fast** = FF 1.25 V 0 C.

## Setup (typical corner, the synthesis target)

| Design | Latency | Cells | Flops | Area (um^2) | Setup slack (ns) | TNS (ns) | Setup viol. | Min period (ns) | Fmax (MHz) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| dot2_v1 | 2 | 3295 | 99 | 4003.8 | -1.212 | -19.393 | 29 / 133 | 2.212 | 452 |
| dot2_v2 | 3 | 3272 | 164 | 4226.5 | -0.889 | -25.862 | 62 / 198 | 1.889 | 529 |
| dot2_v3 | 4 | 3299 | 261 | 4567.8 | -0.602 | -22.127 | 83 / 295 | 1.602 | 624 |
| dot2_v4 | 5 | 3473 | 422 | 5355.1 | -0.413 | -21.933 | 102 / 456 | 1.413 | 708 |
| dot2_v5 | 4 | 3604 | 334 | 5085.4 | -0.133 | -0.433 | 5 / 368 | 1.133 | 883 |

## All corners

| Design | Fmax slow (MHz) | Fmax typ (MHz) | Fmax fast (MHz) | Hold slack slow / typ / fast (ns) | Hold buffers added |
| --- | --- | --- | --- | --- | --- |
| dot2_v1 | 126 | 452 | 799 | +0.123 / +0.059 / +0.015 | 1 |
| dot2_v2 | 149 | 529 | 924 | +0.123 / +0.053 / +0.011 | 2 |
| dot2_v3 | 177 | 624 | 1080 | +0.123 / +0.053 / +0.011 | 39 |
| dot2_v4 | 205 | 708 | 1198 | +0.123 / +0.053 / +0.011 | 76 |
| dot2_v5 | 257 | 883 | 1511 | +0.123 / +0.053 / +0.011 | 11 |

## Critical paths (typical corner)

- **dot2_v1** (baseline: multiply + add in one stage): `b_q_reg[4]/CK (DFF_X1)` -> `y_reg[31]/D (DFF_X1)`, arrival 2.131 ns
- **dot2_v2** (multiply / add split into two stages): `c_q_reg[3]/CK (DFF_X1)` -> `cd_q_reg[30]/D (DFF_X1)`, arrival 1.806 ns
- **dot2_v3** (half-width partial products + recombine stage): `c_q_reg[1]/CK (DFF_X1)` -> `cd_lo_q_reg[22]/D (DFF_X1)`, arrival 1.520 ns
- **dot2_v4** (quarter-width partial products + registered adder tree): `a_q_reg[1]/CK (DFF_X1)` -> `ab_pp_q[1]_reg[18]/D (DFF_X1)`, arrival 1.332 ns
- **dot2_v5** (carry-save reduction tree + Kogge-Stone adder): `c_q2_reg[5]/CK (DFF_X1)` -> `y_reg[31]/D (DFF_X1)`, arrival 1.051 ns
