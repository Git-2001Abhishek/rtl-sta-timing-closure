`timescale 1ns/1ps
// -----------------------------------------------------------------------------
// tb_dot2
// Drives the same stimulus into all five datapath versions and checks each
// output against a reference model delayed by that version's latency.
//
// Stimulus: corner values (0, 1, max, alternating bits) followed by random
// vectors with random in_valid bubbles. A reset is applied mid-run to check
// that out_valid clears.
// -----------------------------------------------------------------------------
module tb_dot2;

    parameter int W        = 16;
    parameter int N_RANDOM = 5000;

    localparam int MAXLAT = 5;

    logic         clk = 1'b0;
    logic         rst_n;
    logic         in_valid;
    logic [W-1:0] a, b, c, d;

    always #5 clk = ~clk;

    // Gate-level netlists have no parameters: compile with -DGLS for those.
`ifdef GLS
    `define DUT_PARAMS
`else
    `define DUT_PARAMS #(.W(W))
`endif

    logic         v1_valid, v2_valid, v3_valid, v4_valid, v5_valid;
    logic [2*W:0] v1_y, v2_y, v3_y, v4_y, v5_y;

    dot2_v1 `DUT_PARAMS u_v1 (.clk, .rst_n, .in_valid, .a, .b, .c, .d, .out_valid(v1_valid), .y(v1_y));
    dot2_v2 `DUT_PARAMS u_v2 (.clk, .rst_n, .in_valid, .a, .b, .c, .d, .out_valid(v2_valid), .y(v2_y));
    dot2_v3 `DUT_PARAMS u_v3 (.clk, .rst_n, .in_valid, .a, .b, .c, .d, .out_valid(v3_valid), .y(v3_y));
    dot2_v4 `DUT_PARAMS u_v4 (.clk, .rst_n, .in_valid, .a, .b, .c, .d, .out_valid(v4_valid), .y(v4_y));
    dot2_v5 `DUT_PARAMS u_v5 (.clk, .rst_n, .in_valid, .a, .b, .c, .d, .out_valid(v5_valid), .y(v5_y));

    // ------------------------------------------------------------------
    // Reference model: shift register of expected (valid, y)
    // ------------------------------------------------------------------
    logic         exp_v [MAXLAT+1];
    logic [2*W:0] exp_y [MAXLAT+1];

    always @(posedge clk) begin
        for (int i = MAXLAT; i > 0; i--) begin
            exp_v[i] <= exp_v[i-1];
            exp_y[i] <= exp_y[i-1];
        end
        exp_v[1] <= rst_n ? in_valid : 1'b0;
        exp_y[1] <= (2*W+1)'(a) * (2*W+1)'(b) + (2*W+1)'(c) * (2*W+1)'(d);
    end

    // clear the model's valid bits on reset, like the DUT
    always @(negedge rst_n) begin
        for (int i = 0; i <= MAXLAT; i++) exp_v[i] <= 1'b0;
    end

    int errors = 0;
    int checked [5] = '{0, 0, 0, 0, 0};

    task automatic check_out(input int idx, input int lat, input logic vld, input logic [2*W:0] y);
        if (vld !== exp_v[lat]) begin
            $error("[%0t] v%0d out_valid=%b expected %b", $time, idx + 1, vld, exp_v[lat]);
            errors++;
        end else if (vld && y !== exp_y[lat]) begin
            $error("[%0t] v%0d y=%h expected %h", $time, idx + 1, y, exp_y[lat]);
            errors++;
        end else if (vld) begin
            checked[idx]++;
        end
    endtask

    // sample just before the next rising edge
    always @(negedge clk) begin
        if (rst_n) begin
            check_out(0, 2, v1_valid, v1_y);
            check_out(1, 3, v2_valid, v2_y);
            check_out(2, 4, v3_valid, v3_y);
            check_out(3, 5, v4_valid, v4_y);
            check_out(4, 4, v5_valid, v5_y);
        end
    end

    // ------------------------------------------------------------------
    // Stimulus
    // ------------------------------------------------------------------
    task automatic drive(input logic v, input logic [W-1:0] ia, ib, ic, id);
        @(negedge clk);
        in_valid = v;
        a = ia; b = ib; c = ic; d = id;
    endtask

    localparam logic [W-1:0] MAX = '1;
    localparam logic [W-1:0] ALT = {(W/2){2'b10}};

    initial begin
        $dumpfile("results/tb_dot2.vcd");
        $dumpvars(1, tb_dot2);   // top-level signals only (keeps the dump small)

        in_valid = 1'b0;
        {a, b, c, d} = '0;
        for (int i = 0; i <= MAXLAT; i++) begin
            exp_v[i] = 1'b0;
            exp_y[i] = '0;
        end
        rst_n = 1'b0;
        repeat (3) @(posedge clk);
        @(negedge clk) rst_n = 1'b1;

        // corner cases
        drive(1, 0,   0,   0,   0);
        drive(1, 1,   1,   1,   1);
        drive(1, MAX, MAX, MAX, MAX);     // largest possible result
        drive(1, MAX, MAX, 0,   0);
        drive(1, 0,   0,   MAX, MAX);
        drive(1, ALT, ~ALT, ~ALT, ALT);
        drive(1, MAX, 1,   1,   MAX);
        drive(0, 0,   0,   0,   0);

        // random traffic with bubbles
        repeat (N_RANDOM / 2) drive($urandom_range(3) != 0, W'($urandom), W'($urandom), W'($urandom), W'($urandom));

        // reset in the middle of traffic
        @(negedge clk) rst_n = 1'b0;
        repeat (2) @(negedge clk);
        if (v1_valid || v2_valid || v3_valid || v4_valid || v5_valid) begin
            $error("out_valid not cleared by reset");
            errors++;
        end
        rst_n = 1'b1;

        repeat (N_RANDOM / 2) drive($urandom_range(3) != 0, W'($urandom), W'($urandom), W'($urandom), W'($urandom));
        drive(0, 0, 0, 0, 0);
        repeat (MAXLAT + 2) @(negedge clk);

        $display("--------------------------------------------------");
        $display("results checked: v1=%0d v2=%0d v3=%0d v4=%0d v5=%0d",
                 checked[0], checked[1], checked[2], checked[3], checked[4]);
        if (errors == 0 && checked[0] > 0 && checked[1] > 0 && checked[2] > 0 && checked[3] > 0 && checked[4] > 0)
            $display("TEST PASSED");
        else
            $display("TEST FAILED: %0d error(s)", errors);
        $display("--------------------------------------------------");
        $finish;
    end

endmodule
