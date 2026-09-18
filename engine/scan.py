#!/usr/bin/env python3
"""
scan.py - project walker + fingerprint + AST symbol extraction.

This is the structure layer of DEVKIT: a single AST pass that produces, for
every Python file, its docstring, classes/methods, functions and imports, all
with line ranges. Non-Python files are listed too (for the project map).

The walker prunes ignored directories and hidden directories at the directory
level, so huge folders (miniconda, java, node_modules, .git) are never even
entered.
"""

import ast
import hashlib
import json
import os
import warnings
from datetime import datetime
from pathlib import Path

PY_EXT = ".py"


def compute_sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _decorator_names(node) -> list:
    names = []
    for d in node.decorator_list:
        try:
            names.append(ast.unparse(d))
        except Exception:
            if isinstance(d, ast.Name):
                names.append(d.id)
            elif isinstance(d, ast.Attribute):
                names.append(d.attr)
            else:
                names.append(type(d).__name__)
    return names


def _base_names(node) -> list:
    names = []
    for b in node.bases:
        try:
            names.append(ast.unparse(b))
        except Exception:
            if isinstance(b, ast.Name):
                names.append(b.id)
            elif isinstance(b, ast.Attribute):
                names.append(b.attr)
            else:
                names.append(type(b).__name__)
    return names


def _is_entry_file(tree) -> bool:
    """True when the module has an `if __name__ == "__main__":` guard."""
    for node in tree.body:
        if isinstance(node, ast.If) and isinstance(node.test, ast.Compare):
            t = node.test
            if (isinstance(t.left, ast.Name) and t.left.id == "__name__"
                    and len(t.comparators) == 1
                    and isinstance(t.comparators[0], ast.Constant)
                    and t.comparators[0].value == "__main__"):
                return True
    return False


def _module_level_imports(tree) -> set:
    """Collect imports that execute at module load time.

    Skips function/class bodies (lazy imports) and ``if TYPE_CHECKING:``
    blocks (which are false at runtime), so this reflects the imports that
    can actually cause an import-time cycle.
    """
    imports = set()

    def _add(node):
        if isinstance(node, ast.Import):
            for a in node.names:
                imports.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                imports.add(node.module)

    def _visit(stmts):
        for node in stmts:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                _add(node)
            elif isinstance(node, ast.If):
                if isinstance(node.test, ast.Name) and node.test.id == "TYPE_CHECKING":
                    continue
                _visit(node.body)
                _visit(node.orelse)
            elif isinstance(node, (ast.Try, ast.With)) or (
                hasattr(ast, "TryStar") and isinstance(node, ast.TryStar)
            ):
                _visit(node.body)
                for h in getattr(node, "handlers", []):
                    _visit(h.body)
                if hasattr(node, "orelse"):
                    _visit(node.orelse)
                if hasattr(node, "finalbody"):
                    _visit(node.finalbody)
            elif isinstance(node, (ast.For, ast.While)):
                _visit(node.body)
                _visit(node.orelse)

    _visit(tree.body)
    return imports


def _signature(node) -> str:
    args = node.args
    parts = []
    pos = list(args.posonlyargs) + list(args.args)
    defaults = [None] * (len(pos) - len(args.defaults)) + list(args.defaults)
    for a, d in zip(pos, defaults):
        s = a.arg
        if d is not None:
            try:
                s += "=" + ast.unparse(d)
            except Exception:
                s += "=..."
        parts.append(s)
    if args.vararg:
        parts.append("*" + args.vararg.arg)
    elif args.kwonlyargs:
        parts.append("*")
    for a, d in zip(args.kwonlyargs, args.kw_defaults):
        s = a.arg
        if d is not None:
            try:
                s += "=" + ast.unparse(d)
            except Exception:
                s += "=..."
        parts.append(s)
    if args.kwarg:
        parts.append("**" + args.kwarg.arg)
    ret = ""
    if node.returns is not None:
        try:
            ret = " -> " + ast.unparse(node.returns)
        except Exception:
            ret = ""
    return "(" + ", ".join(parts) + ")" + ret


def walk_project(root: Path, ignore_dirs) -> list:
    """Return all files under root, pruning ignored and hidden directories.

    Supports glob patterns in ignore_dirs via fnmatch (e.g. *.pyc, tests/*).
    """
    import fnmatch
    files = []
    ignore_exact = set()
    ignore_patterns = []
    for d in (ignore_dirs or []):
        if any(c in d for c in "*?[]"):
            ignore_patterns.append(d)
        else:
            ignore_exact.add(d)

    def _ignored(name: str) -> bool:
        if name in ignore_exact:
            return True
        for pat in ignore_patterns:
            if fnmatch.fnmatch(name, pat) or fnmatch.fnmatch(name + "/", pat):
                return True
        return False

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames
            if not _ignored(d) and not d.startswith(".")
        ]
        for fn in filenames:
            # also skip ignored file patterns
            if _ignored(fn):
                continue
            files.append(Path(dirpath) / fn)
    return files


# ---- Thread-safe sha256-based disk cache (FAZ3) ----
import threading

# extraction schema degistikce artirin (eski cache kayitlari gecersiz olsun)
_CACHE_VERSION = 2

class _AstCache:
    """Thread-safe AST cache with disk persistence."""
    def __init__(self):
        self._cache = {}
        self._cache_dir = None
        self._lock = threading.RLock()
        self._dirty = False
    
    def init(self, data_dir: Path):
        with self._lock:
            self._cache_dir = Path(data_dir) / ".ast_cache"
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            idx = self._cache_dir / "_index.json"
            if idx.exists():
                try:
                    self._cache = json.loads(idx.read_text(encoding="utf-8"))
                except Exception:
                    self._cache = {}
            self._dirty = False
    
    def get(self, sha256: str, version: int = _CACHE_VERSION):
        key = "%d:%s" % (version, sha256[:16])
        with self._lock:
            cached = self._cache.get(key)
            if cached and cached.get("sha256") == sha256:
                return cached
            return None
    
    def set(self, sha256: str, value: dict, version: int = _CACHE_VERSION):
        key = "%d:%s" % (version, sha256[:16])
        with self._lock:
            self._cache[key] = value
            self._dirty = True
    
    def save(self):
        with self._lock:
            if not self._dirty or self._cache_dir is None:
                return
            try:
                # atomic write: write to temp then rename
                idx = self._cache_dir / "_index.json"
                tmp = self._cache_dir / "_index.json.tmp"
                tmp.write_text(json.dumps(self._cache, indent=2), encoding="utf-8")
                tmp.replace(idx)
                self._dirty = False
            except Exception:
                pass
    
    def stats(self):
        with self._lock:
            return {"entries": len(self._cache), "dirty": self._dirty}

_AST_CACHE = _AstCache()

def _cached_extract(path: Path, data_dir: Path = None):
    """Try cache by sha256; if hit, return cached parsed dict (with fresh sha)."""
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    sha = compute_sha256_bytes(raw)
    cached = _AST_CACHE.get(sha)
    if cached is not None:
        return cached
    # miss: parse
    result = extract_py_file(path)
    if result is not None:
        _AST_CACHE.set(sha, result)
    return result


def extract_py_file(path: Path):
    """Parse a Python file into {sha256, lines, doc, classes, functions, imports}.

    Returns None when the file cannot be read.
    """
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    sha = compute_sha256_bytes(raw)
    source = raw.decode("utf-8-sig", errors="replace")
    lines = source.count("\n") + 1

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            tree = ast.parse(source, filename=str(path))
    except (SyntaxError, ValueError):
        return {
            "sha256": sha,
            "lines": lines,
            "doc": "",
            "parse_error": True,
            "classes": [],
            "functions": [],
            "imports": [],
            "module_imports": [],
            "relative_imports": [],
            "source_code": source,
        }

    doc = ast.get_docstring(tree) or ""
    first_line = doc.strip().splitlines()[0] if doc.strip() else ""

    imports = set()
    relative_imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                imports.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                imports.add(node.module)
            if node.level and node.level > 0:
                relative_imports.append({"level": node.level, "module": node.module or ""})

    module_imports = _module_level_imports(tree)
    # also capture relative at module level
    module_relative = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level and node.level > 0:
            # only if at module level (not inside function) — approximate via _module_level check
            module_relative.append({"level": node.level, "module": node.module or ""})

    classes = []
    functions = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            methods = []
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods.append({
                        "name": sub.name,
                        "lineno": sub.lineno,
                        "end_lineno": sub.end_lineno,
                        "async": isinstance(sub, ast.AsyncFunctionDef),
                        "sig": _signature(sub),
                        "decorators": _decorator_names(sub),
                    })
            classes.append({
                "name": node.name,
                "lineno": node.lineno,
                "end_lineno": node.end_lineno,
                "decorators": _decorator_names(node),
                "bases": _base_names(node),
                "methods": methods,
            })
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append({
                "name": node.name,
                "lineno": node.lineno,
                "end_lineno": node.end_lineno,
                "async": isinstance(node, ast.AsyncFunctionDef),
                "sig": _signature(node),
                "decorators": _decorator_names(node),
            })

    return {
        "sha256": sha,
        "lines": lines,
        "doc": first_line,
        "parse_error": False,
        "classes": classes,
        "functions": functions,
        "imports": sorted(imports),
        "module_imports": sorted(module_imports),
        "relative_imports": relative_imports,
        "is_entry": _is_entry_file(tree),
        "source_code": source,
    }


def run_scan(root: Path, ignore_dirs, data_dir: Path = None, use_cache: bool = False) -> dict:
    if use_cache and data_dir is not None:
        _AST_CACHE.init(Path(data_dir))
    files = walk_project(root, ignore_dirs)
    files_out = {}
    non_py = []
    py_count = 0
    total_lines = 0
    total_classes = 0
    total_functions = 0

    for p in files:
        rel = p.relative_to(root).as_posix()
        if p.suffix == PY_EXT:
            if use_cache:
                parsed = _cached_extract(p, data_dir)
            else:
                parsed = extract_py_file(p)
            if parsed is None:
                continue
            py_count += 1
            total_lines += parsed["lines"]
            total_classes += len(parsed["classes"])
            total_functions += len(parsed["functions"])
            files_out[rel] = {
                "path": rel,
                "size": p.stat().st_size,
                "sha256": parsed["sha256"],
                "lines": parsed["lines"],
                "doc": parsed["doc"],
                "parse_error": parsed["parse_error"],
                "classes": parsed["classes"],
                "functions": parsed["functions"],
                "imports": parsed["imports"],
                "module_imports": parsed["module_imports"],
                "relative_imports": parsed.get("relative_imports", []),
                "is_entry": parsed.get("is_entry", False),
                "source_code": parsed.get("source_code", ""),
            }
        else:
            try:
                sha = compute_sha256_bytes(p.read_bytes())
            except OSError:
                sha = ""
            non_py.append({
                "path": rel,
                "size": p.stat().st_size,
                "ext": p.suffix or "(none)",
                "sha256": sha,
            })
    if use_cache:
        _AST_CACHE.save()

    subsystems = sorted({f.split("/")[0] for f in files_out if "/" in f})
    entry_files = sorted(rel for rel, f in files_out.items() if f.get("is_entry"))
    stats = {
        "total_files": len(files),
        "total_py": py_count,
        "total_non_py": len(non_py),
        "total_lines": total_lines,
        "total_classes": total_classes,
        "total_functions": total_functions,
        "subsystems": subsystems,
        "entry_files": entry_files,
    }
    return {
        "project_root": str(root),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "stats": stats,
        "files": files_out,
        "non_py_files": non_py,
    }


if __name__ == "__main__":
    import sys
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    result = run_scan(root, [])
    print(json.dumps(result["stats"], indent=2))
