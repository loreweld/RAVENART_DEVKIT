#!/usr/bin/env python3
"""
deps.py - import graph, subsystem matrix and static cycle detection.

Consumes scan.json (the structure layer) and produces deps.json with:
  - graph:     file -> list of internal files it imports
  - reverse:   file -> list of files that import it
  - matrix:    subsystem x subsystem dependency counts
  - cycles:    strongly connected components of size > 1 (static cycles)
"""


def _resolve_module_to_file(module: str, files_by_module: dict, py_paths: set):
    """Resolve an import string to a project file path, or None.
    
    Supports both regular packages (with __init__.py) and namespace packages (PEP 420, no __init__.py).
    """
    parts = module.split(".")
    for i in range(len(parts), 0, -1):
        prefix = ".".join(parts[:i])
        candidate = prefix.replace(".", "/") + ".py"
        if candidate in py_paths:
            return candidate
        pkg_init = prefix.replace(".", "/") + "/__init__.py"
        if pkg_init in py_paths:
            return pkg_init
        # PEP 420 namespace package: check if directory exists in project
        pkg_dir = prefix.replace(".", "/")
        # Check if any file exists under this directory (indicating it's a namespace package)
        for py_path in py_paths:
            if py_path.startswith(pkg_dir + "/"):
                return pkg_dir + "/__init__.py"  # virtual marker for namespace pkg
    return None


def _strongly_connected_components(graph: dict) -> list:
    index = {}
    lowlink = {}
    stack = []
    on_stack = set()
    result = []
    counter = [0]

    def connect(v):
        index[v] = lowlink[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on_stack.add(v)
        for w in graph.get(v, ()):
            if w not in index:
                connect(w)
                lowlink[v] = min(lowlink[v], lowlink[w])
            elif w in on_stack:
                lowlink[v] = min(lowlink[v], index[w])
        if lowlink[v] == index[v]:
            comp = []
            while True:
                w = stack.pop()
                on_stack.discard(w)
                comp.append(w)
                if w == v:
                    break
            result.append(comp)

    for v in graph:
        if v not in index:
            connect(v)
    return result


def _resolve_relative(rel_path: str, level: int, module: str, py_paths: set):
    """Resolve `from .x import y` (level>0) relative to rel_path."""
    # rel_path is like "pkg/sub/mod.py"
    parts = rel_path.replace("\\", "/").split("/")
    # drop filename
    pkg_parts = parts[:-1]
    if pkg_parts and pkg_parts[-1] == "__init__":
        pkg_parts = pkg_parts[:-1]
    # go up (level-1) times
    for _ in range(level - 1):
        if pkg_parts:
            pkg_parts.pop()
    base = ".".join(pkg_parts)
    if module:
        full = base + "." + module if base else module
    else:
        full = base
    if not full:
        return None
    return _resolve_module_to_file(full, None, py_paths)


def run_deps(scan: dict) -> dict:
    files = scan["files"]
    subsystems = scan["stats"]["subsystems"]
    py_paths = set(files.keys())

    graph = {}
    for rel, data in files.items():
        graph[rel] = []
        # absolute imports (existing)
        for imp in data.get("module_imports", []):
            target = _resolve_module_to_file(imp, None, py_paths)
            if target and target != rel:
                graph[rel].append(target)
        # relative imports (new: scan.py now captures level>0 via raw imports if available)
        # Fallback: scan files' raw imports include relative via scan.json "imports" + "relative_imports"
        for rimp in data.get("relative_imports", []):
            # rimp: {level, module}
            lvl = rimp.get("level", 0)
            mod = rimp.get("module", "")
            if lvl and lvl > 0:
                target = _resolve_relative(rel, lvl, mod, py_paths)
                if target and target != rel:
                    graph[rel].append(target)

    reverse = {}
    for rel, targets in graph.items():
        for t in targets:
            reverse.setdefault(t, []).append(rel)
    for rel in files:
        reverse.setdefault(rel, [])

    # subsystem matrix
    matrix = {s: {t: 0 for t in subsystems} for s in subsystems}
    def sub_of(f):
        return f.split("/")[0] if "/" in f else None
    for rel, targets in graph.items():
        src = sub_of(rel)
        if not src or src not in subsystems:
            continue
        for t in targets:
            dst = sub_of(t)
            if dst and dst in subsystems and dst != src:
                matrix[src][dst] += 1

    # Cycle detection on module files only: package __init__.py files
    # legitimately import their own submodules, so they are excluded here to
    # keep the signal focused on real module<->module cycles.
    # Note: namespace packages (PEP 420) use virtual __init__.py markers
    cycle_graph = {}
    for rel, targets in graph.items():
        if rel.endswith("__init__.py"):
            continue
        filtered = [t for t in targets if not t.endswith("__init__.py")]
        cycle_graph[rel] = filtered

    sccs = _strongly_connected_components(cycle_graph)
    cycles = [sorted(c) for c in sccs if len(c) > 1]
    cycles.sort()

    return {
        "graph": {k: sorted(set(v)) for k, v in graph.items()},
        "reverse": {k: sorted(set(v)) for k, v in reverse.items()},
        "matrix": matrix,
        "cycles": cycles,
    }


if __name__ == "__main__":
    import json
    import sys
    data = json.load(open(sys.argv[1], encoding="utf-8"))
    print(json.dumps(run_deps(data), indent=2))
