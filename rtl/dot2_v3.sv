`timescale 1ns/1ps
// -----------------------------------------------------------------------------
// dot2_v3 - split multipliers into half-width partial products
//
//   y = a*b + c*d        (unsigned, W-bit operands, 2W+1-bit result)
//
// Pipeline (latency 4):
//   [input regs]
//     -> W x W/2 partial products   a*b_lo, a*b_hi, c*d_lo, c*d_hi
//   [partial-product regs]
//     -> recombine:  ab = a*b_lo + (a*b_hi << W/2),  cd likewise
//   [product regs]
//     -> final add
//   [y reg]
//
// Optimization over v2: each multiplier array is halved in height, so the
// longest register-to-register path shrinks again. Costs one extra cycle of
// latency and extra pipeline flops.
// -----------------------------------------------------------------------------
module dot2_v3 #(
    parameter int W = 16
) (
    input  logic           clk,
    input  logic           rst_n,
    input  logic           in_valid,
    input  logic [W-1:0]   a, b, c, d,
    output logic           out_valid,
    output logic [2*W:0]   y
);

    localparam int LATENCY = 4;
    localparam int H       = W / 2;      // low half width
    localparam int HH      = W - H;      // high half width (handles odd W)

    // stage 0: register inputs
    logic [W-1:0] a_q, b_q, c_q, d_q;

    always_ff @(posedge clk) begin
        a_q <= a;
        b_q <= b;
        c_q <= c;
        d_q <= d;
    end

    // stage 1: partial products
    logic [W+H-1:0]  ab_lo_q, cd_lo_q;
    logic [W+HH-1:0] ab_hi_q, cd_hi_q;

    always_ff @(posedge clk) begin
        ab_lo_q <= a_q * b_q[H-1:0];
        ab_hi_q <= a_q * b_q[W-1:H];
        cd_lo_q <= c_q * d_q[H-1:0];
        cd_hi_q <= c_q * d_q[W-1:H];
    end

    // stage 2: recombine partial products
    logic [2*W-1:0] ab_q, cd_q;

    always_ff @(posedge clk) begin
        ab_q <= (2*W)'(ab_lo_q) + ((2*W)'(ab_hi_q) << H);
        cd_q <= (2*W)'(cd_lo_q) + ((2*W)'(cd_hi_q) << H);
    end

    // stage 3: final add
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
