#!/usr/bin/env python3
"""
impact.py - change impact analysis for a single file.

Consumes deps.json. For a given file reports:
  - dependents: files that import it (will be affected)
  - dependencies: files it imports
"""

import json


def load_deps(data_dir) -> dict:
    path = data_dir / "deps.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def find_file(rel: str, deps: dict) -> str:
    """Resolve a partial path to a known file key."""
    graph = deps.get("graph", {})
    keys = set(graph.keys())
    if rel in keys:
        return rel
    suffix = "/" + rel if "/" not in rel else rel
    matches = [k for k in keys if k == suffix or k.endswith("/" + rel)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        return matches[0]
    return rel


def run_impact(data_dir, file_arg: str) -> dict:
    deps = load_deps(data_dir)
    rel = find_file(file_arg, deps)
    reverse = deps.get("reverse", {})
    graph = deps.get("graph", {})
    return {
        "file": rel,
        "found": rel in graph,
        "dependents": sorted(reverse.get(rel, [])),
        "dependencies": sorted(graph.get(rel, [])),
    }


if __name__ == "__main__":
    import sys
    from pathlib import Path
    data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    file_arg = sys.argv[2] if len(sys.argv) > 2 else ""
    print(json.dumps(run_impact(data_dir, file_arg), indent=2))
