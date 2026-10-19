#!/usr/bin/env python3
"""Download the NanGate 45nm Liberty files (typical, slow and fast corners).

The files come from the OpenSTA repository's examples and are unpacked to
lib/nangate45_{typ,slow,fast}.lib (they are not committed to this repository).
"""
import gzip
import os
import urllib.request

BASE = "https://raw.githubusercontent.com/The-OpenROAD-Project/OpenSTA/master/examples/"
CORNERS = ("typ", "slow", "fast")


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.makedirs(os.path.join(root, "lib"), exist_ok=True)
    for corner in CORNERS:
        dst = os.path.join(root, "lib", "nangate45_%s.lib" % corner)
        if os.path.exists(dst):
            print("already present: " + dst)
            continue
        url = BASE + "nangate45_%s.lib.gz" % corner
        print("downloading " + url)
        with urllib.request.urlopen(url) as r:
            data = gzip.decompress(r.read())
        with open(dst, "wb") as f:
            f.write(data)
        print("wrote %s (%.1f MB)" % (dst, len(data) / 1e6))


if __name__ == "__main__":
    main()
