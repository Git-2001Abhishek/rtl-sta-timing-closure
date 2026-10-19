#!/usr/bin/env python3
"""
Compare OpenSTA results (reports/<design>_opensta.rpt, written by
scripts/sta.tcl) with sta.py results (reports/summary.json, typical corner).

Prints a Markdown table (suitable for $GITHUB_STEP_SUMMARY).
Exit status is 1 if any setup or hold slack differs by more than --tol ns.
"""
import argparse
import json
import os
import re
import sys


def opensta_slacks(path):
    """report_worst_slack prints 'worst slack [max|min] <value>' (max first)."""
    text = open(path).read()
    vals = [float(v) for v in re.findall(r"worst slack(?:\s+(?:max|min))?\s+(-?[\d.]+)", text)]
    if len(vals) < 2:
        return None, None
    return vals[0], vals[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tol", type=float, default=0.05, help="allowed difference in ns")
    a = ap.parse_args()
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(root)
    rows = json.load(open("reports/summary.json"))

    out = ["## OpenSTA vs sta.py (typical corner)", "",
           "| Design | Setup slack sta.py | Setup slack OpenSTA | Diff | Hold slack sta.py "
           "| Hold slack OpenSTA | Diff |",
           "| --- | --- | --- | --- | --- | --- | --- |"]
    worst = 0.0
    missing = False
    for s in rows:
        rpt = "reports/%s_opensta.rpt" % s["design"]
        if not os.path.exists(rpt):
            out.append("| %s | %+.3f | (no report) | | %+.3f | | |" % (
                s["design"], s["worst_setup_slack"], s["whs"]))
            missing = True
            continue
        o_setup, o_hold = opensta_slacks(rpt)
        if o_setup is None:
            out.append("| %s | %+.3f | (unparsed) | | %+.3f | | |" % (
                s["design"], s["worst_setup_slack"], s["whs"]))
            missing = True
            continue
        d_setup = o_setup - s["worst_setup_slack"]
        d_hold = o_hold - s["whs"]
        worst = max(worst, abs(d_setup), abs(d_hold))
        out.append("| %s | %+.3f | %+.3f | %+.3f | %+.3f | %+.3f | %+.3f |" % (
            s["design"], s["worst_setup_slack"], o_setup, d_setup, s["whs"], o_hold, d_hold))
    out.append("")
    out.append("Largest difference: %.3f ns (tolerance %.3f ns)" % (worst, a.tol))
    print("\n".join(out))
    sys.exit(1 if missing or worst > a.tol else 0)


if __name__ == "__main__":
    main()
