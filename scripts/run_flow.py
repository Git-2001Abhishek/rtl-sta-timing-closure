#!/usr/bin/env python3
"""
Synthesis + STA flow for all datapath versions.

For each design in DESIGNS:
  1. Yosys: synthesize and map to NanGate45 (scripts/synth.ys)
  2. sta.py: setup/hold analysis against constraints/dot2.sdc
Then writes reports/summary.md and results/timing_comparison.png.

Usage (from the repository root):
  python scripts/run_flow.py                 # uses `yosys` on PATH
  YOSYS=yowasp-yosys python scripts/run_flow.py
  python scripts/run_flow.py --period 1.25   # override the SDC clock period
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

DESIGNS = [
    ("dot2_v1", 2, "baseline: multiply + add in one stage"),
    ("dot2_v2", 3, "multiply / add split into two stages"),
    ("dot2_v3", 4, "half-width partial products + recombine stage"),
    ("dot2_v4", 5, "quarter-width partial products + registered adder tree"),
    ("dot2_v5", 4, "carry-save reduction tree + Kogge-Stone adder"),
]
# extra source files per design (besides rtl/<top>.sv)
EXTRA_SOURCES = {"dot2_v5": ["rtl/ks_adder.sv"]}
LIB = "lib/nangate45_typ.lib"
SDC = "constraints/dot2.sdc"


def sdc_period():
    for line in open(SDC):
        m = re.match(r"\s*set\s+clk_period\s+([\d.]+)", line)
        if m:
            return float(m.group(1))
    sys.exit("clk_period not found in " + SDC)


def run(cmd):
    print("+ " + " ".join(cmd), flush=True)
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if r.returncode != 0:
        print(r.stdout)
        sys.exit("command failed: " + " ".join(cmd))
    return r.stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", type=float, help="clock period in ns (default: from SDC)")
    ap.add_argument("--synth-opts", default="-noabc",
                    help="extra options for the Yosys synth command (default: -noabc)")
    ap.add_argument("--tag", default="", help="suffix for report / summary file names")
    a = ap.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(root)
    if not os.path.exists(LIB):
        sys.exit("%s missing - run scripts/get_lib.sh (or .py) first" % LIB)
    yosys = os.environ.get("YOSYS", "yosys")
    if not shutil.which(yosys):
        sys.exit("yosys not found (set YOSYS=/path/to/yosys or yowasp-yosys)")
    period = a.period or sdc_period()
    os.makedirs("build", exist_ok=True)

    rows = []
    for top, latency, desc in DESIGNS:
        out = "results/" + top
        os.makedirs(out, exist_ok=True)
        script = open("scripts/synth.ys").read()
        sources = " ".join(["rtl/%s.sv" % top] + EXTRA_SOURCES.get(top, []))
        script = (script.replace("{TOP}", top).replace("{SOURCES}", sources).replace("{LIB}", LIB)
                  .replace("{OUT}", out).replace("{DELAY_PS}", str(int(period * 1000)))
                  .replace("{SYNTH_OPTS}", a.synth_opts))
        ys = "build/%s.ys" % top
        with open(ys, "w") as f:
            f.write(script)
        log = run([yosys, "-q", "-l", "build/%s_yosys.log" % top, "-s", ys])
        rpt = "reports/%s_timing%s.rpt" % (top, a.tag)
        js = "build/%s_sta.json" % top
        cmd = [sys.executable, "scripts/sta.py", "--lib", LIB,
               "--netlist", "%s/%s_netlist.json" % (out, top), "--top", top,
               "--sdc", SDC, "--report", rpt, "--summary-json", js, "--paths", "3",
               "--period", str(period)]
        print(run(cmd))
        shutil.copy("%s/area.rpt" % out, "reports/%s_area%s.rpt" % (top, a.tag))
        s = json.load(open(js))
        s["latency"] = latency
        s["desc"] = desc
        rows.append(s)

    # ---------------------------------------------------------------- summary
    lines = []
    lines.append("# Timing summary\n")
    lines.append("Target clock period **%.3f ns** (%.0f MHz), NanGate45 typical corner, "
                 "wire-load model `5K_hvratio_1_1`.\n" % (period, 1000 / period))
    lines.append("| Design | Latency | Cells | Flops | Area (um^2) | Setup slack (ns) | TNS (ns) "
                 "| Setup viol. | Hold slack (ns) | Min period (ns) | Fmax (MHz) |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for s in rows:
        lines.append("| %s | %d | %d | %d | %.1f | %+.3f | %.3f | %d / %d | %+.3f | %.3f | %.0f |" % (
            s["design"], s["latency"], s["cells"], s["flops"], s["area"], s["worst_setup_slack"], s["tns"],
            s["setup_violations"], s["endpoints"], s["whs"], s["min_period"], s["fmax_mhz"]))
    lines.append("")
    lines.append("Critical paths:\n")
    for s in rows:
        lines.append("- **%s** (%s): `%s` -> `%s`, arrival %.3f ns" % (
            s["design"], s["desc"], s["crit_start"], s["crit_end"], s["crit_arrival"]))
    with open("reports/summary%s.md" % a.tag, "w") as f:
        f.write("\n".join(lines) + "\n")
    with open("reports/summary%s.json" % a.tag, "w") as f:
        json.dump(rows, f, indent=2)
    print("\n".join(lines))

    # ------------------------------------------------------------------ chart
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed - skipping chart")
        return
    names = [s["design"] for s in rows]
    fig, axs = plt.subplots(1, 3, figsize=(13, 3.8))
    cols = ["#d1495b" if s["wns"] < 0 else "#2e7d32" for s in rows]
    axs[0].bar(names, [s["min_period"] for s in rows], color=cols)
    axs[0].axhline(period, color="k", ls="--", lw=1, label="target %.2f ns" % period)
    axs[0].legend(loc="upper right", fontsize=8, frameon=False)
    axs[0].set_title("Minimum clock period (ns)")
    axs[1].bar(names, [s["fmax_mhz"] for s in rows], color="#1f6feb")
    axs[1].set_title("Fmax (MHz)")
    axs[2].bar(names, [s["area"] for s in rows], color="#8250df")
    axs[2].set_title("Cell area (um^2)")
    for ax, key, fmt in ((axs[0], "min_period", "%.2f"), (axs[1], "fmax_mhz", "%.0f"), (axs[2], "area", "%.0f")):
        for i, s in enumerate(rows):
            ax.text(i, s[key], fmt % s[key], ha="center", va="bottom", fontsize=8)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    fig.suptitle("dot2 datapath: timing vs. architecture (NanGate45, typical corner)")
    fig.tight_layout()
    fig.savefig("results/timing_comparison%s.png" % a.tag, dpi=130)
    print("wrote results/timing_comparison%s.png" % a.tag)


if __name__ == "__main__":
    main()
