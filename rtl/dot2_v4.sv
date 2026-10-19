`timescale 1ns/1ps
// -----------------------------------------------------------------------------
// dot2_v4 - quarter-width partial products + registered adder tree
//
//   y = a*b + c*d        (unsigned, W-bit operands, 2W+1-bit result, W % 4 == 0)
//
// Pipeline (latency 5):
//   [input regs]
//     -> 8 partial products  a*b[q], c*d[q]   (W x W/4 each, q = 0..3)
//   [pp regs]
//     -> pairwise combine    pp0 + pp1<<Q,  pp2 + pp3<<Q
//   [pair regs]
//     -> combine pairs       ab = lo + hi<<2Q   (same for cd)
//   [product regs]
//     -> final add
//   [y reg]
//
// Optimization over v3: the partial-product arrays are halved again
// (W x W/4), and every level of the reduction tree gets its own register
// stage, so no stage contains more than one carry-propagate adder or one
// small multiplier array.
// -----------------------------------------------------------------------------
module dot2_v4 #(
    parameter int W = 16
) (
    input  logic           clk,
    input  logic           rst_n,
    input  logic           in_valid,
    input  logic [W-1:0]   a, b, c, d,
    output logic           out_valid,
    output logic [2*W:0]   y
);

    localparam int LATENCY = 5;
    localparam int Q       = W / 4;

    // stage 0: register inputs
    logic [W-1:0] a_q, b_q, c_q, d_q;

    always_ff @(posedge clk) begin
        a_q <= a;
        b_q <= b;
        c_q <= c;
        d_q <= d;
    end

    // stage 1: quarter-width partial products
    logic [W+Q-1:0] ab_pp_q [4];
    logic [W+Q-1:0] cd_pp_q [4];

    always_ff @(posedge clk) begin
        for (int i = 0; i < 4; i++) begin
            ab_pp_q[i] <= a_q * b_q[i*Q +: Q];
            cd_pp_q[i] <= c_q * d_q[i*Q +: Q];
        end
    end

    // stage 2: combine adjacent partial products
    logic [W+2*Q-1:0] ab_pair_q [2];
    logic [W+2*Q-1:0] cd_pair_q [2];

    always_ff @(posedge clk) begin
        for (int i = 0; i < 2; i++) begin
            ab_pair_q[i] <= (W+2*Q)'(ab_pp_q[2*i]) + ((W+2*Q)'(ab_pp_q[2*i+1]) << Q);
            cd_pair_q[i] <= (W+2*Q)'(cd_pp_q[2*i]) + ((W+2*Q)'(cd_pp_q[2*i+1]) << Q);
        end
    end

    // stage 3: combine pairs into full products
    logic [2*W-1:0] ab_q, cd_q;

    always_ff @(posedge clk) begin
        ab_q <= (2*W)'(ab_pair_q[0]) + ((2*W)'(ab_pair_q[1]) << (2*Q));
        cd_q <= (2*W)'(cd_pair_q[0]) + ((2*W)'(cd_pair_q[1]) << (2*Q));
    end

    // stage 4: final add
    always_ff @(posedge clk) begin
        y <= {1'b0, ab_q} + {1'b0, cd_q};
    end

    // valid pipeline
    logic [LATENCY-1:0] vld;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) vld <= '0;
        else        vld <= {vld[LATENCY-2:0], in_valid};
    end

    assign out_valid = vld[LATENCY-1];

endmodule
