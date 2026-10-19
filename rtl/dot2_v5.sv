`timescale 1ns/1ps
// -----------------------------------------------------------------------------
// dot2_v5 - carry-save reduction tree + parallel-prefix final adder
//
//   y = a*b + c*d        (unsigned, W-bit operands, 2W+1-bit result)
//
// Instead of building two multipliers and adding their results, all 2W
// partial-product rows of BOTH products (a & b[j]) << j and (c & d[j]) << j
// are summed together in a single Wallace-style tree of 3:2 carry-save
// compressors. Carry-save levels have no carry propagation (constant depth
// per level), so only one carry-propagate adder is needed at the very end,
// and that one is a Kogge-Stone prefix adder (log2 depth).
//
// Pipeline (latency 4, same as v3):
//   [input regs]
//     -> partial products + first SPLIT CSA levels    (2W rows -> R_MID rows)
//   [mid regs]
//     -> remaining CSA levels                          (R_MID rows -> 2 rows)
//   [sum / carry regs]
//     -> Kogge-Stone adder
//   [y reg]
// -----------------------------------------------------------------------------
module dot2_v5 #(
    parameter int W     = 16,
    parameter int SPLIT = 4          // CSA levels placed before the mid registers
) (
    input  logic           clk,
    input  logic           rst_n,
    input  logic           in_valid,
    input  logic [W-1:0]   a, b, c, d,
    output logic           out_valid,
    output logic [2*W:0]   y
);

    localparam int LATENCY = 4;
    localparam int RW      = 2*W + 1;     // row width (= result width)
    localparam int NROWS   = 2*W;         // partial-product rows

    // rows remaining after l levels of 3:2 compression
    function automatic integer rows_after(input integer l);
        integer n, k;
        begin
            n = NROWS;
            for (k = 0; k < l; k = k + 1)
                n = 2*(n/3) + n%3;
            rows_after = n;
        end
    endfunction

    // number of 3:2 levels needed to get down to two rows
    /* verilator lint_off UNUSEDSIGNAL */   // Yosys needs an argument here
    function automatic integer levels_to_two(input integer dummy);
        integer n, k, l;
        begin
            n = NROWS;
            l = 0;
            for (k = 0; k < 64; k = k + 1) begin
                if (n > 2) begin
                    n = 2*(n/3) + n%3;
                    l = l + 1;
                end
            end
            levels_to_two = l;
        end
    endfunction
    /* verilator lint_on UNUSEDSIGNAL */

    localparam int LV    = levels_to_two(0);
    localparam int R_MID = rows_after(SPLIT);

    // stage 0: register inputs
    logic [W-1:0] a_q, b_q, c_q, d_q;

    always_ff @(posedge clk) begin
        a_q <= a;
        b_q <= b;
        c_q <= c;
        d_q <= d;
    end

    // All rows of all levels in one flat vector:
    //   row r after l compression levels = rows[ROW(l, r) +: RW]
    localparam int LEVEL_BITS = NROWS * RW;
    `define ROW(l, r) (((l) * NROWS + (r)) * RW)

    // Not every row slot of every level is used (the row count shrinks
    // each level), so some bits of `rows` / `src` are intentionally unread.
    /* verilator lint_off UNUSEDSIGNAL */
    logic [(LV+1)*LEVEL_BITS-1:0] rows;
    /* verilator lint_on UNUSEDSIGNAL */
    logic [R_MID*RW-1:0]          mid_q;   // the R_MID rows left after SPLIT levels

    genvar j, l, g, p;
    generate
        // partial products of both multiplications
        for (j = 0; j < W; j++) begin : g_pp
            assign rows[`ROW(0, j)     +: RW] = RW'(a_q & {W{b_q[j]}}) << j;
            assign rows[`ROW(0, W + j) +: RW] = RW'(c_q & {W{d_q[j]}}) << j;
        end

        for (l = 0; l < LV; l++) begin : g_level
            localparam int N = rows_after(l);
            localparam int G = N / 3;

            // level input: the previous level, or the mid registers
            /* verilator lint_off UNUSEDSIGNAL */
            logic [LEVEL_BITS-1:0] src;
            /* verilator lint_on UNUSEDSIGNAL */
            if (l == SPLIT) begin : g_from_reg
                assign src = LEVEL_BITS'(mid_q);
            end else begin : g_from_comb
                assign src = rows[`ROW(l, 0) +: LEVEL_BITS];
            end

            // 3:2 carry-save compressors (full adders on every bit)
            for (g = 0; g < G; g++) begin : g_csa
                logic [RW-1:0] x0, x1, x2;
                assign x0 = src[(3*g)     * RW +: RW];
                assign x1 = src[(3*g + 1) * RW +: RW];
                assign x2 = src[(3*g + 2) * RW +: RW];
                assign rows[`ROW(l+1, 2*g)     +: RW] = x0 ^ x1 ^ x2;
                assign rows[`ROW(l+1, 2*g + 1) +: RW] = ((x0 & x1) | (x0 & x2) | (x1 & x2)) << 1;
            end
            // rows left over pass straight through
            for (p = 3*G; p < N; p++) begin : g_pass
                assign rows[`ROW(l+1, 2*G + p - 3*G) +: RW] = src[p * RW +: RW];
            end
            for (p = 2*G + N - 3*G; p < NROWS; p++) begin : g_unused
                assign rows[`ROW(l+1, p) +: RW] = '0;
            end
        end
    endgenerate

    // stage 1 -> 2: mid pipeline registers
    always_ff @(posedge clk) begin
        mid_q <= rows[`ROW(SPLIT, 0) +: R_MID*RW];
    end

    // stage 2 -> 3: final sum / carry rows
    logic [RW-1:0] s_q, c_q2;

    always_ff @(posedge clk) begin
        s_q  <= rows[`ROW(LV, 0) +: RW];
        c_q2 <= rows[`ROW(LV, 1) +: RW];
    end

    `undef ROW

    // stage 3: carry-propagate add
    logic [RW-1:0] y_next;

    ks_adder #(.N(RW)) u_add (
        .x   (s_q),
        .y   (c_q2),
        .sum (y_next)
    );

    always_ff @(posedge clk) begin
        y <= y_next;
    end

    // valid pipeline
    logic [LATENCY-1:0] vld;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) vld <= '0;
        else        vld <= {vld[LATENCY-2:0], in_valid};
    end

    assign out_valid = vld[LATENCY-1];

endmodule
