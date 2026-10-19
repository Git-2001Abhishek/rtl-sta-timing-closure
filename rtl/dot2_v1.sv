`timescale 1ns/1ps
// -----------------------------------------------------------------------------
// dot2_v1 - baseline
//
//   y = a*b + c*d        (unsigned, W-bit operands, 2W+1-bit result)
//
// Pipeline (latency 2):
//   [input regs] -> two multipliers + adder (one combinational stage) -> [y reg]
//
// The whole multiply-add sits between two register banks, so the critical
// path is input reg -> multiplier -> 2W-bit adder -> output reg.
// -----------------------------------------------------------------------------
module dot2_v1 #(
    parameter int W = 16
) (
    input  logic           clk,
    input  logic           rst_n,
    input  logic           in_valid,
    input  logic [W-1:0]   a, b, c, d,
    output logic           out_valid,
    output logic [2*W:0]   y
);

    localparam int LATENCY = 2;

    // stage 0: register inputs
    logic [W-1:0] a_q, b_q, c_q, d_q;

    always_ff @(posedge clk) begin
        a_q <= a;
        b_q <= b;
        c_q <= c;
        d_q <= d;
    end

    // stage 1: multiply and add in one cycle
    always_ff @(posedge clk) begin
        y <= (2*W+1)'(a_q * b_q) + (2*W+1)'(c_q * d_q);
    end

    // valid pipeline (the only state that needs a reset)
    logic [LATENCY-1:0] vld;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) vld <= '0;
        else        vld <= {vld[LATENCY-2:0], in_valid};
    end

    assign out_valid = vld[LATENCY-1];

endmodule
