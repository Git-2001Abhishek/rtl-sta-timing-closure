#!/usr/bin/env python3
"""Download the NanGate 45nm typical-corner Liberty file used by the flow.

The file is taken from the OpenSTA repository's examples and unpacked to
lib/nangate45_typ.lib (it is not committed to this repository).
"""
import gzip
import os
import urllib.request

URL = ("https://raw.githubusercontent.com/The-OpenROAD-Project/OpenSTA/"
       "master/examples/nangate45_typ.lib.gz")


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dst = os.path.join(root, "lib", "nangate45_typ.lib")
    if os.path.exists(dst):
        print("already present: " + dst)
        return
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    print("downloading " + URL)
    with urllib.request.urlopen(URL) as r:
        data = gzip.decompress(r.read())
    with open(dst, "wb") as f:
        f.write(data)
    print("wrote %s (%.1f MB)" % (dst, len(data) / 1e6))


if __name__ == "__main__":
    main()
