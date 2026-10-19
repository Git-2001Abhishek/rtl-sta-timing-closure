#!/usr/bin/env python3
"""Turn the tail of CI step logs into GitHub error annotations, so the cause
of a failure is visible on the run page without opening the full log."""
import sys

LINES = 40


def escape(text):
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


for path in sys.argv[1:]:
    try:
        lines = open(path, errors="replace").read().splitlines()
    except OSError:
        continue
    if not lines:
        continue
    tail = "\n".join(lines[-LINES:])
    print("::error title=%s (last %d lines)::%s" % (path, LINES, escape(tail)))
