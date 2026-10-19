# RTL -> simulation -> synthesis -> STA flow
#
#   make lib       download the NanGate45 Liberty file
#   make sim       RTL simulation of all five versions (Icarus Verilog)
#   make flow      Yosys synthesis + STA (scripts/sta.py) for all versions
#   make gls       gate-level simulation of the synthesized netlists
#   make opensta   cross-check the netlists with OpenSTA (if installed)
#   make lint      Verilator -Wall lint of all RTL
#   make test      unit tests for the STA engine (pytest)
#   make all       lib + sim + flow + gls
#
# Tools can be overridden, e.g.  make flow YOSYS=yowasp-yosys PYTHON=python3

YOSYS  ?= yosys
PYTHON ?= python3
STA    ?= sta

DESIGNS = dot2_v1 dot2_v2 dot2_v3 dot2_v4 dot2_v5
RTL     = rtl/ks_adder.sv $(addprefix rtl/,$(addsuffix .sv,$(DESIGNS)))
LIB     = lib/nangate45_typ.lib

.PHONY: all lib sim flow flow-default-synth gls opensta lint test clean

all: lib sim flow gls

# downloads whichever of the slow / typ / fast libraries are missing
lib:
	$(PYTHON) scripts/get_lib.py

$(LIB):
	$(PYTHON) scripts/get_lib.py

sim:
	mkdir -p build results
	iverilog -g2012 -Wall -o build/sim.vvp -s tb_dot2 $(RTL) tb/tb_dot2.sv
	vvp -n build/sim.vvp | tee results/sim.log
	@grep -q "TEST PASSED" results/sim.log || (echo "simulation FAILED"; exit 1)

flow: lib
	YOSYS=$(YOSYS) $(PYTHON) scripts/run_flow.py

# same flow without -noabc, to reproduce the comparison in the README
flow-default-synth: lib
	YOSYS=$(YOSYS) $(PYTHON) scripts/run_flow.py --synth-opts= --tag=_default_synth

build/cells.v: $(LIB)
	mkdir -p build
	$(PYTHON) scripts/lib2v.py $(LIB) build/cells.v

gls: build/cells.v
	iverilog -g2012 -DGLS -o build/gls.vvp -s tb_dot2 tb/tb_dot2.sv \
	    $(foreach d,$(DESIGNS),results/$(d)/$(d)_netlist.v) build/cells.v
	vvp -n build/gls.vvp | tee results/gls.log
	@grep -q "TEST PASSED" results/gls.log || (echo "simulation FAILED"; exit 1)

test:
	$(PYTHON) -m pytest tests -q

lint:
	for d in $(DESIGNS); do verilator --lint-only -Wall --top-module $$d rtl/$$d.sv rtl/ks_adder.sv || exit 1; done

opensta: $(LIB)
	for d in $(DESIGNS); do DESIGN=$$d $(STA) -exit scripts/sta.tcl; done

clean:
	rm -rf build results/*.vcd results/dot2_v*/*.json
