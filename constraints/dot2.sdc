# -----------------------------------------------------------------------------
# Timing constraints for dot2_v1 / dot2_v2 / dot2_v3
# Target: 1.0 GHz in NanGate 45nm (typical corner)
# Read by both OpenSTA (scripts/sta.tcl) and scripts/sta.py
# -----------------------------------------------------------------------------
set clk_period 1.0

create_clock -name clk -period $clk_period [get_ports clk]
set_clock_uncertainty 0.05 [get_clocks clk]
set_clock_transition 0.02 [get_clocks clk]

# Inputs come from registers in the same clock domain; outputs go to registers.
set_input_delay  0.20 -clock clk [get_ports {in_valid a* b* c* d*}]
set_output_delay 0.20 -clock clk [all_outputs]
set_input_transition 0.02 [get_ports {in_valid a* b* c* d*}]
set_load 2.0 [all_outputs]

# Asynchronous reset is not timed as a data path.
set_false_path -from [get_ports rst_n]
