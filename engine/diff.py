#!/usr/bin/env python3
"""
diff.py - fingerprint diff between two scans (added/deleted/modified/moved).
"""

import json
from pathlib import Path


def load_fingerprint(data_dir: Path) -> dict:
    p = data_dir / "fingerprint.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_fingerprint(data_dir: Path, scan: dict) -> None:
    fp = {rel: f["sha256"] for rel, f in scan["files"].items()}
    (data_dir / "fingerprint.json").write_text(
        json.dumps(fp, indent=2, ensure_ascii=False), encoding="utf-8")


def compute_diff(old_fp: dict, new_fp: dict) -> dict:
    old_keys = set(old_fp)
    new_keys = set(new_fp)
    added = sorted(new_keys - old_keys)
    deleted = sorted(old_keys - new_keys)
    modified = sorted(k for k in (old_keys & new_keys) if old_fp[k] != new_fp[k])

    added_by_hash = {}
    for k in added:
        added_by_hash.setdefault(new_fp[k], []).append(k)

    moves = []
    remaining_deleted = []
    for k in deleted:
        h = old_fp[k]
        if h and added_by_hash.get(h):
            newk = added_by_hash[h].pop(0)
            moves.append((k, newk))
        else:
            remaining_deleted.append(k)

    moved_added = {new for _, new in moves}
    moved_deleted = {old for old, _ in moves}
    added = [k for k in added if k not in moved_added]
    deleted = remaining_deleted

    return {
        "added": added,
        "deleted": deleted,
        "modified": modified,
        "moved": moves,
    }
