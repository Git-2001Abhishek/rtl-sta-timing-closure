# RTL Design, Synthesis & Static Timing Analysis

## Overview

Designed and verified a pipelined arithmetic datapath in SystemVerilog
and evaluated its timing characteristics through RTL synthesis and
static timing analysis.

## Flow

SystemVerilog RTL → Simulation → Synthesis (Yosys) → STA (OpenSTA) → Critical Path Analysis → RTL Optimization

## Features

- Synthesizable SystemVerilog RTL
- Pipelined arithmetic datapath
- SDC timing constraints
- RTL synthesis using Yosys
- Static timing analysis using OpenSTA
- Critical-path identification
- Setup/hold analysis
- Timing optimization through RTL modification

## Timing Analysis

The initial implementation is analyzed to identify critical paths
and timing violations. RTL modifications are subsequently evaluated
through synthesis and STA to measure their impact on timing.

## Results



## Tools

- SystemVerilog
- Yosys
- OpenSTA
- GTKWave

## Repository Structure

rtl/          - RTL source
tb/           - Testbench
constraints/  - SDC constraints
scripts/      - Synthesis and STA scripts
reports/      - Timing reports
results/      - Results and figures
