#!/usr/bin/env python3
"""
usage.py - dependency usage validation (pyproject.toml vs actual imports).

Consumes scan.json and the project's pyproject.toml. Produces a heuristic
report: declared dependencies that have no matching import (unused candidates)
and top-level imports that are not declared (external, undeclared).

NOTE: package-name -> import-name mapping is heuristic; results are advisory.
"""

import json
import re
import sys
from pathlib import Path

try:
    STDLIB = set(sys.stdlib_module_names)
except AttributeError:
    STDLIB = {
        "os", "sys", "json", "re", "logging", "pathlib", "typing", "datetime",
        "hashlib", "functools", "itertools", "collections", "abc", "asyncio",
        "subprocess", "math", "time", "random", "string", "enum", "dataclasses",
        "contextlib", "copy", "warnings", "io", "tempfile", "shutil", "argparse",
        "struct", "socket", "threading", "queue", "inspect", "ast", "traceback",
        "unittest", "sqlite3", "base64", "csv", "glob", "gzip", "heapq", "pickle",
        "pprint", "secrets", "statistics", "textwrap", "uuid", "xml",
    }


def _extract_dependencies(pyproject: Path):
    """Return a list of dependency names from [project].dependencies."""
    text = pyproject.read_text(encoding="utf-8", errors="replace")
    try:
        import tomllib
        data = tomllib.loads(text)
        deps = data.get("project", {}).get("dependencies", [])
        return [str(d) for d in deps]
    except Exception:
        pass

    m = re.search(r"dependencies\s*=\s*\[(.*?)\]", text, re.DOTALL)
    if not m:
        return []
    names = re.findall(r'"([^"]+)"', m.group(1))
    return names


def _normalize(name: str) -> str:
    return name.lower().replace("-", "_").replace(".", "_")


IMPORT_ALIASES = {
    "pynvml": "nvidia-ml-py",
    "docx": "python-docx",
    "yaml": "pyyaml",
    "llama_cpp": "llama-cpp-python",
    "bson": "pymongo",
    "sklearn": "scikit-learn",
    "PIL": "pillow",
    "dotenv": "python-dotenv",
    "cv2": "opencv-python",
}

PACKAGE_ALIASES = {v: k for k, v in IMPORT_ALIASES.items()}


def run_usage(root: Path, scan: dict) -> dict:
    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        return {"error": "pyproject.toml not found"}

    declared = _extract_dependencies(pyproject)
    declared_norm = {_normalize(n): n for n in declared}

    imports = set()
    for data in scan["files"].values():
        for imp in data.get("imports", []):
            imports.add(imp.split(".")[0])

    import_norm = {_normalize(i): i for i in imports}

    internal = set()
    for rel in scan["files"]:
        if "/" in rel:
            internal.add(rel.split("/")[0].lower())

    unused = []
    for norm, orig in sorted(declared_norm.items()):
        base_m = re.match(r"[A-Za-z0-9_.\-]+", orig)
        base = base_m.group(0).lower() if base_m else orig.lower()
        alias_import = PACKAGE_ALIASES.get(base, "")
        alias_import_norm = _normalize(alias_import) if alias_import else ""
        matched = any(
            norm == inorm or norm in inorm or inorm in norm
            for inorm in import_norm
        ) or (alias_import_norm in import_norm)
        if not matched:
            unused.append(orig)

    undeclared = []
    for inorm, orig in sorted(import_norm.items()):
        if inorm in ("__future__",):
            continue
        if inorm in STDLIB:
            continue
        if inorm in internal:
            continue
        alias = IMPORT_ALIASES.get(orig.lower(), "")
        alias_norm = _normalize(alias) if alias else ""
        matched = any(
            inorm == dnorm or inorm in dnorm or dnorm in inorm
            or (alias_norm and (alias_norm == dnorm or alias_norm in dnorm or dnorm in alias_norm))
            for dnorm in declared_norm
        )
        if not matched:
            undeclared.append(orig)

    return {
        "declared": sorted(declared),
        "unused_candidates": unused,
        "undeclared_imports": undeclared,
    }


if __name__ == "__main__":
    import sys
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    data = json.load(open(sys.argv[2], encoding="utf-8"))
    print(json.dumps(run_usage(root, data), indent=2))
