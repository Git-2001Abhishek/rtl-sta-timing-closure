`timescale 1ns/1ps
// -----------------------------------------------------------------------------
// dot2_v2 - multiply / add split
//
//   y = a*b + c*d        (unsigned, W-bit operands, 2W+1-bit result)
//
// Pipeline (latency 3):
//   [input regs] -> multipliers -> [product regs] -> adder -> [y reg]
//
// Optimization over v1: the final 2W-bit addition is moved into its own
// stage, so the critical path is only input reg -> multiplier -> product reg.
// -----------------------------------------------------------------------------
module dot2_v2 #(
    parameter int W = 16
) (
    input  logic           clk,
    input  logic           rst_n,
    input  logic           in_valid,
    input  logic [W-1:0]   a, b, c, d,
    output logic           out_valid,
    output logic [2*W:0]   y
);

    localparam int LATENCY = 3;

    // stage 0: register inputs
    logic [W-1:0] a_q, b_q, c_q, d_q;

    always_ff @(posedge clk) begin
        a_q <= a;
        b_q <= b;
        c_q <= c;
        d_q <= d;
    end

    // stage 1: multiply
    logic [2*W-1:0] ab_q, cd_q;

    always_ff @(posedge clk) begin
        ab_q <= a_q * b_q;
        cd_q <= c_q * d_q;
    end

    // stage 2: add
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
