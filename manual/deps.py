#!/usr/bin/env python3
"""manual/deps.py - dependency matrix + cycles of an arbitrary folder."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.scan import run_scan
from engine.deps import run_deps


def _ignore(argv):
    if "--ignore" in argv:
        i = argv.index("--ignore")
        return [x.strip() for x in argv[i + 1].split(",") if x.strip()]
    return []


def main():
    if len(sys.argv) < 2:
        print("Kullanim: python manual/deps.py <klasor> [--ignore a,b,c]")
        return 1
    root = Path(sys.argv[1])
    if not root.is_dir():
        print("[ERROR] Klasor bulunamadi: %s" % root)
        return 1
    scan = run_scan(root, _ignore(sys.argv))
    deps = run_deps(scan)
    subs = scan["stats"]["subsystems"]
    print("Bagimlilik matrisi (satir -> sutun import eder):")
    print("| from \\ to |" + "|".join(subs) + "|")
    matrix = deps.get("matrix", {})
    for s in subs:
        row = matrix.get(s, {})
        cells = [str(row.get(t, 0) or "-") for t in subs]
        print("| %s |" % s + "|".join(cells) + "|")
    cycles = deps.get("cycles", [])
    print("")
    print("Donguler: %d" % len(cycles))
    for c in cycles:
        print("  -", " <-> ".join(c))
    return 0


if __name__ == "__main__":
    sys.exit(main())
