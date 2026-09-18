#!/usr/bin/env python3
"""manual/scan.py - structural scan of an arbitrary folder (one-off tool)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.scan import run_scan


def _ignore(argv):
    if "--ignore" in argv:
        i = argv.index("--ignore")
        return [x.strip() for x in argv[i + 1].split(",") if x.strip()]
    return []


def main():
    if len(sys.argv) < 2:
        print("Kullanim: python manual/scan.py <klasor> [--ignore a,b,c]")
        return 1
    root = Path(sys.argv[1])
    if not root.is_dir():
        print("[ERROR] Klasor bulunamadi: %s" % root)
        return 1
    result = run_scan(root, _ignore(sys.argv))
    s = result["stats"]
    print("Klasor: %s" % root)
    print("  Dosya: %d (.py %d) | Satir: %d | Sinif: %d | Fonksiyon: %d"
          % (s["total_files"], s["total_py"], s["total_lines"], s["total_classes"], s["total_functions"]))
    print("  Alt sistemler: %s" % ", ".join(s["subsystems"]))
    for rel in sorted(result["files"]):
        f = result["files"][rel]
        print("  %-52s %d satir" % (rel, f["lines"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
