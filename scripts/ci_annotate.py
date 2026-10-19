#!/usr/bin/env python3
"""Turn the tail of CI logs into GitHub annotations, so results (and the
cause of a failure) are visible on the run page without opening the full
log.  Usage: ci_annotate.py [--notice] [--lines N] file..."""
import sys

LINES = 40
LEVEL = "error"
args = sys.argv[1:]
if "--notice" in args:
    LEVEL = "notice"
    args.remove("--notice")
if "--lines" in args:
    i = args.index("--lines")
    LINES = int(args[i + 1])
    del args[i:i + 2]


def escape(text):
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


for path in args:
    try:
        lines = open(path, errors="replace").read().splitlines()
    except OSError:
        continue
    if not lines:
        continue
    tail = "\n".join(lines[-LINES:])
    print("::%s title=%s (last %d lines)::%s" % (LEVEL, path, LINES, escape(tail)))
