#!/usr/bin/env python3
"""
Synthesis + hold fix + multi-corner STA flow for all datapath versions.

For each design in DESIGNS:
  1. Yosys: synthesize and map to NanGate45 at the typical corner
     (scripts/synth.ys)
  2. hold_fix.py: insert delay buffers until hold is met with margin at the
     FAST corner (shortest delays = hardest hold)
  3. sta.py: setup/hold analysis of the final netlist at the SLOW, TYPICAL
     and FAST corners against constraints/dot2.sdc
Then writes reports/summary.md, reports/summary.json and
results/timing_comparison.png.

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
LIBS = {c: "lib/nangate45_%s.lib" % c for c in ("typ", "slow", "fast")}
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


def sta(top, netlist, corner, period, tag, paths=3):
    """Run sta.py for one corner; returns its summary dict."""
    rpt = "reports/%s_timing_%s%s.rpt" % (top, corner, tag)
    js = "build/%s_sta_%s%s.json" % (top, corner, tag)
    run([sys.executable, "scripts/sta.py", "--lib", LIBS[corner], "--netlist", netlist,
         "--top", top, "--sdc", SDC, "--report", rpt, "--summary-json", js,
         "--paths", str(paths), "--period", str(period)])
    return json.load(open(js))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", type=float, help="clock period in ns (default: from SDC)")
    ap.add_argument("--synth-opts", default="-noabc",
                    help="extra options for the Yosys synth command (default: -noabc)")
    ap.add_argument("--tag", default="", help="suffix for report / summary file names")
    a = ap.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(root)
    for lib in LIBS.values():
        if not os.path.exists(lib):
            sys.exit("%s missing - run `make lib` (scripts/get_lib.py) first" % lib)
    yosys = os.environ.get("YOSYS", "yosys")
    if not shutil.which(yosys):
        sys.exit("yosys not found (set YOSYS=/path/to/yosys or yowasp-yosys)")
    period = a.period or sdc_period()
    os.makedirs("build", exist_ok=True)
    os.makedirs("reports", exist_ok=True)
    if os.path.exists("reports/hold_fix%s.log" % a.tag):
        os.remove("reports/hold_fix%s.log" % a.tag)

    rows = []
    for top, latency, desc in DESIGNS:
        # tagged (experimental) runs keep their netlists out of results/
        out = ("results/" + top) if not a.tag else ("build/%s%s" % (top, a.tag))
        os.makedirs(out, exist_ok=True)

        # 1. synthesis (typical corner)
        script = open("scripts/synth.ys").read()
        sources = " ".join(["rtl/%s.sv" % top] + EXTRA_SOURCES.get(top, []))
        script = (script.replace("{TOP}", top).replace("{SOURCES}", sources)
                  .replace("{LIB}", LIBS["typ"]).replace("{OUT}", "build")
                  .replace("{DELAY_PS}", str(int(period * 1000)))
                  .replace("{SYNTH_OPTS}", a.synth_opts))
        ys = "build/%s.ys" % top
        with open(ys, "w") as f:
            f.write(script)
        run([yosys, "-q", "-l", "build/%s_yosys.log" % top, "-s", ys])

        # 2. hold fix at the fast corner
        final_json = "%s/%s_netlist.json" % (out, top)
        hf = run([sys.executable, "scripts/hold_fix.py", "--lib-fast", LIBS["fast"],
                  "--netlist", "build/%s_synth.json" % top, "--top", top, "--sdc", SDC,
                  "--out", final_json, "--log", "reports/hold_fix%s.log" % a.tag])
        print(hf)
        buffers = int(re.findall(r"(\d+) buffers so far", hf)[-1])

        # final netlist as Verilog + area report
        run([yosys, "-q", "-p",
             "read_json %s; tee -q -o reports/%s_area%s.rpt stat -liberty %s; "
             "write_verilog -noattr -noexpr %s/%s_netlist.v"
             % (final_json, top, a.tag, LIBS["typ"], out, top)])

        # 3. multi-corner STA
        s = sta(top, final_json, "typ", period, a.tag)
        s_slow = sta(top, final_json, "slow", period, a.tag, paths=1)
        s_fast = sta(top, final_json, "fast", period, a.tag, paths=1)
        s.update(latency=latency, desc=desc, hold_buffers=buffers,
                 slow=s_slow, fast=s_fast)
        rows.append(s)

    # ---------------------------------------------------------------- summary
    L = []
    L.append("# Timing summary\n")
    L.append("Target clock period **%.3f ns** (%.0f MHz), NanGate45, wire-load model "
             "`5K_hvratio_1_1`, Yosys `synth %s`. Hold fixed at the fast corner "
             "(10 ps margin) before analysis.\n" % (period, 1000 / period, a.synth_opts or "(default)"))
    L.append("Corners: **slow** = SS 0.95 V 125 C, **typ** = TT 1.10 V 25 C, **fast** = FF 1.25 V 0 C.\n")
    L.append("## Setup (typical corner, the synthesis target)\n")
    L.append("| Design | Latency | Cells | Flops | Area (um^2) | Setup slack (ns) | TNS (ns) "
             "| Setup viol. | Min period (ns) | Fmax (MHz) |")
    L.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for s in rows:
        L.append("| %s | %d | %d | %d | %.1f | %+.3f | %.3f | %d / %d | %.3f | %.0f |" % (
            s["design"], s["latency"], s["cells"], s["flops"], s["area"], s["worst_setup_slack"],
            s["tns"], s["setup_violations"], s["endpoints"], s["min_period"], s["fmax_mhz"]))
    L.append("")
    L.append("## All corners\n")
    L.append("| Design | Fmax slow (MHz) | Fmax typ (MHz) | Fmax fast (MHz) "
             "| Hold slack slow / typ / fast (ns) | Hold buffers added |")
    L.append("| --- | --- | --- | --- | --- | --- |")
    for s in rows:
        L.append("| %s | %.0f | %.0f | %.0f | %+.3f / %+.3f / %+.3f | %d |" % (
            s["design"], s["slow"]["fmax_mhz"], s["fmax_mhz"], s["fast"]["fmax_mhz"],
            s["slow"]["whs"], s["whs"], s["fast"]["whs"], s["hold_buffers"]))
    L.append("")
    L.append("## Critical paths (typical corner)\n")
    for s in rows:
        L.append("- **%s** (%s): `%s` -> `%s`, arrival %.3f ns" % (
            s["design"], s["desc"], s["crit_start"], s["crit_end"], s["crit_arrival"]))
    with open("reports/summary%s.md" % a.tag, "w") as f:
        f.write("\n".join(L) + "\n")
    with open("reports/summary%s.json" % a.tag, "w") as f:
        json.dump(rows, f, indent=2)
    print("\n".join(L))

    # ------------------------------------------------------------------ chart
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed - skipping chart")
        return
    names = [s["design"] for s in rows]
    x = range(len(rows))
    fig, axs = plt.subplots(1, 3, figsize=(13, 3.8))
    cols = ["#d1495b" if s["worst_setup_slack"] < 0 else "#2e7d32" for s in rows]
    axs[0].bar(names, [s["min_period"] for s in rows], color=cols)
    axs[0].axhline(period, color="k", ls="--", lw=1, label="target %.2f ns" % period)
    axs[0].legend(loc="upper right", fontsize=8, frameon=False)
    axs[0].set_title("Min clock period, typical (ns)")
    for i, s in enumerate(rows):
        axs[0].text(i, s["min_period"], "%.2f" % s["min_period"], ha="center", va="bottom", fontsize=8)
    w = 0.38
    slow = [s["slow"]["fmax_mhz"] for s in rows]
    typ = [s["fmax_mhz"] for s in rows]
    axs[1].bar([i - w / 2 for i in x], slow, w, color="#9aa4b1", label="slow (SS 0.95V 125C)")
    axs[1].bar([i + w / 2 for i in x], typ, w, color="#1f6feb", label="typical (TT 1.1V 25C)")
    axs[1].set_xticks(list(x))
    axs[1].set_xticklabels(names)
    axs[1].legend(fontsize=8, frameon=False, loc="upper left")
    axs[1].set_title("Fmax (MHz)")
    for i in x:
        axs[1].text(i - w / 2, slow[i], "%.0f" % slow[i], ha="center", va="bottom", fontsize=7)
        axs[1].text(i + w / 2, typ[i], "%.0f" % typ[i], ha="center", va="bottom", fontsize=7)
    axs[2].bar(names, [s["area"] for s in rows], color="#8250df")
    axs[2].set_title("Cell area (um^2)")
    for i, s in enumerate(rows):
        axs[2].text(i, s["area"], "%.0f" % s["area"], ha="center", va="bottom", fontsize=8)
    for ax in axs:
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    fig.suptitle("dot2 datapath: timing vs. architecture (NanGate45)")
    fig.tight_layout()
    fig.savefig("results/timing_comparison%s.png" % a.tag, dpi=130)
    print("wrote results/timing_comparison%s.png" % a.tag)


if __name__ == "__main__":
    main()
