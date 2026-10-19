# Timing summary

Target clock period **1.000 ns** (1000 MHz), NanGate45 typical corner, wire-load model `5K_hvratio_1_1`.

| Design | Latency | Cells | Flops | Area (um^2) | Setup slack (ns) | TNS (ns) | Setup viol. | Hold slack (ns) | Min period (ns) | Fmax (MHz) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| dot2_v1 | 2 | 3276 | 99 | 3999.3 | -1.251 | -20.926 | 29 / 133 | +0.035 | 2.251 | 444 |
| dot2_v2 | 3 | 3253 | 164 | 4220.1 | -0.974 | -28.495 | 63 / 198 | +0.035 | 1.974 | 507 |
| dot2_v3 | 4 | 3294 | 261 | 4590.4 | -0.592 | -22.690 | 87 / 295 | +0.031 | 1.592 | 628 |
| dot2_v4 | 5 | 3358 | 422 | 5255.1 | -0.402 | -17.732 | 101 / 456 | +0.031 | 1.402 | 713 |
| dot2_v5 | 4 | 3585 | 334 | 5142.0 | +0.020 | 0.000 | 0 / 368 | +0.031 | 0.980 | 1021 |

Critical paths:

- **dot2_v1** (baseline: multiply + add in one stage): `b_q_reg[3]/CK (DFF_X1)` -> `y_reg[31]/D (DFF_X1)`, arrival 2.170 ns
- **dot2_v2** (multiply / add split into two stages): `a_q_reg[1]/CK (DFF_X1)` -> `ab_q_reg[31]/D (DFF_X1)`, arrival 1.887 ns
- **dot2_v3** (half-width partial products + recombine stage): `b_q_reg[13]/CK (DFF_X1)` -> `ab_hi_q_reg[22]/D (DFF_X1)`, arrival 1.509 ns
- **dot2_v4** (quarter-width partial products + registered adder tree): `c_q_reg[3]/CK (DFF_X1)` -> `cd_pp_q[0]_reg[18]/D (DFF_X1)`, arrival 1.320 ns
- **dot2_v5** (carry-save reduction tree + Kogge-Stone adder): `s_q_reg[5]/CK (DFF_X1)` -> `y_reg[31]/D (DFF_X1)`, arrival 0.894 ns
