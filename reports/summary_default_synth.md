# Timing summary

Target clock period **1.000 ns** (1000 MHz), NanGate45 typical corner, wire-load model `5K_hvratio_1_1`.

| Design | Latency | Cells | Flops | Area (um^2) | Setup slack (ns) | TNS (ns) | Setup viol. | Hold slack (ns) | Min period (ns) | Fmax (MHz) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| dot2_v1 | 2 | 3294 | 99 | 4003.0 | -1.212 | -19.393 | 29 / 133 | +0.035 | 2.212 | 452 |
| dot2_v2 | 3 | 3270 | 164 | 4224.9 | -0.889 | -25.862 | 62 / 198 | +0.035 | 1.889 | 529 |
| dot2_v3 | 4 | 3260 | 261 | 4536.6 | -0.602 | -22.085 | 83 / 295 | +0.031 | 1.602 | 624 |
| dot2_v4 | 5 | 3397 | 422 | 5294.5 | -0.413 | -21.886 | 101 / 456 | +0.031 | 1.413 | 708 |
| dot2_v5 | 4 | 3593 | 334 | 5076.6 | -0.133 | -0.433 | 5 / 368 | +0.031 | 1.133 | 883 |

Critical paths:

- **dot2_v1** (baseline: multiply + add in one stage): `b_q_reg[4]/CK (DFF_X1)` -> `y_reg[31]/D (DFF_X1)`, arrival 2.131 ns
- **dot2_v2** (multiply / add split into two stages): `c_q_reg[3]/CK (DFF_X1)` -> `cd_q_reg[30]/D (DFF_X1)`, arrival 1.806 ns
- **dot2_v3** (half-width partial products + recombine stage): `c_q_reg[1]/CK (DFF_X1)` -> `cd_lo_q_reg[22]/D (DFF_X1)`, arrival 1.520 ns
- **dot2_v4** (quarter-width partial products + registered adder tree): `a_q_reg[1]/CK (DFF_X1)` -> `ab_pp_q[1]_reg[18]/D (DFF_X1)`, arrival 1.332 ns
- **dot2_v5** (carry-save reduction tree + Kogge-Stone adder): `c_q2_reg[5]/CK (DFF_X1)` -> `y_reg[31]/D (DFF_X1)`, arrival 1.051 ns
