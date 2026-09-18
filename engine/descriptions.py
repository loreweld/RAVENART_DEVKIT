#!/usr/bin/env python3
"""
descriptions.py - persistent one-line file/folder summaries.

map_descriptions.json holds human/AI-authored one-line descriptions keyed by
project-relative path. They survive rescans and are migrated when a file is
moved (via content-hash matching in the sync step).
"""

import json
from pathlib import Path


def _path(devkit_dir: Path) -> Path:
    return devkit_dir / "map_descriptions.json"


def load_descriptions(devkit_dir: Path) -> dict:
    p = _path(devkit_dir)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_descriptions(devkit_dir: Path, data: dict) -> None:
    _path(devkit_dir).write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def migrate_descriptions(devkit_dir: Path, moves) -> None:
    """Carry descriptions over for moved files: moves = [(old_path, new_path)]."""
    if not moves:
        return
    data = load_descriptions(devkit_dir)
    changed = False
    for old, new in moves:
        if old in data and new not in data:
            data[new] = data.pop(old)
            changed = True
    if changed:
        save_descriptions(devkit_dir, data)
