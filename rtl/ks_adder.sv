`timescale 1ns/1ps
// -----------------------------------------------------------------------------
// ks_adder
// N-bit Kogge-Stone parallel-prefix adder (carry-in = 0, result mod 2**N).
// Carry computation takes ceil(log2(N)) prefix levels instead of the N-stage
// chain of a ripple-carry adder.
// -----------------------------------------------------------------------------
module ks_adder #(
    parameter int N = 33
) (
    input  logic [N-1:0] x,
    input  logic [N-1:0] y,
    output logic [N-1:0] sum
);

    localparam int L = $clog2(N);

    // G[k][i] / P[k][i]: group generate / propagate of bits (i - 2**k + 1) .. i
    // P of the last level is computed by the generate loop but not needed
    /* verilator lint_off UNUSEDSIGNAL */
    logic [L:0][N-1:0] G, P;
    /* verilator lint_on UNUSEDSIGNAL */

    assign G[0] = x & y;
    assign P[0] = x ^ y;

    genvar k, i;
    generate
        for (k = 0; k < L; k++) begin : g_level
            for (i = 0; i < N; i++) begin : g_bit
                if (i >= (1 << k)) begin : g_merge
                    assign G[k+1][i] = G[k][i] | (P[k][i] & G[k][i - (1 << k)]);
                    assign P[k+1][i] = P[k][i] & P[k][i - (1 << k)];
                end else begin : g_pass
                    assign G[k+1][i] = G[k][i];
                    assign P[k+1][i] = P[k][i];
                end
            end
        end
    endgenerate

    // carry into bit i is the group generate of bits 0 .. i-1
    assign sum = P[0] ^ {G[L][N-2:0], 1'b0};

endmodule
