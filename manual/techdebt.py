#!/usr/bin/env python3
"""manual/techdebt.py - technical debt scan of an arbitrary folder."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.techdebt import run_techdebt


def _ignore(argv):
    if "--ignore" in argv:
        i = argv.index("--ignore")
        return [x.strip() for x in argv[i + 1].split(",") if x.strip()]
    return []


def main():
    if len(sys.argv) < 2:
        print("Kullanim: python manual/techdebt.py <klasor> [--ignore a,b,c]")
        return 1
    root = Path(sys.argv[1])
    if not root.is_dir():
        print("[ERROR] Klasor bulunamadi: %s" % root)
        return 1
    result = run_techdebt(root, _ignore(sys.argv))
    print("Twin fonksiyon gruplari: %d" % len(result["twin_groups"]))
    for g in result["twin_groups"][:10]:
        print("  -", ", ".join(g))
    print("")
    print("FIX/TODO etiketleri: %d" % len(result["fix_tags"]))
    for t in result["fix_tags"][:20]:
        print("  %s:%s [%s]" % (t["file"], t["line"], t["tag"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
