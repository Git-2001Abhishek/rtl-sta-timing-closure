# -----------------------------------------------------------------------------
# OpenSTA run for one synthesized datapath version.
#
#   DESIGN=dot2_v5 sta -exit scripts/sta.tcl
#   (or: make opensta, which loops over all versions)
#
# Run from the repository root after `make flow` has produced the netlists.
# Uses the same library, wire-load model and SDC as scripts/sta.py.
# -----------------------------------------------------------------------------
if {[info exists ::env(DESIGN)]} {
    set design $::env(DESIGN)
} else {
    set design dot2_v5
}

# OpenROAD (unlike standalone OpenSTA) needs a technology before linking:
# pass the NanGate45 LEFs through TECH_LEF / MACRO_LEF when running there.
if {[info exists ::env(TECH_LEF)]} {
    read_lef $::env(TECH_LEF)
    read_lef $::env(MACRO_LEF)
}
read_liberty liberty/nangate45_typ.lib
read_verilog results/$design/${design}_netlist.v
link_design $design

set_wire_load_model -name 5K_hvratio_1_1
read_sdc constraints/dot2.sdc

set rpt reports/${design}_opensta.rpt

report_checks -path_delay max -fields {slew cap input_pins nets} -digits 3 > $rpt
report_checks -path_delay min -fields {slew cap input_pins nets} -digits 3 >> $rpt
report_wns -digits 3 >> $rpt
report_tns -digits 3 >> $rpt
report_worst_slack -max -digits 3 >> $rpt
report_worst_slack -min -digits 3 >> $rpt
report_check_types -max_slew -max_capacitance -max_fanout -violators >> $rpt

report_worst_slack -max -digits 3
report_worst_slack -min -digits 3
puts "$design: full report written to $rpt"
