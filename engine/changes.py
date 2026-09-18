#!/usr/bin/env python3
"""
changes.py - "hangi dosya/fonksiyon degisti" tespiti.

Git deposu varsa: `git diff HEAD` hunk'lari AST sembol haritasiyla eslestirilir
ve DEGISEN FONKSIYON/CLASS/METHOD isimleri satir numaralariyla raporlanir.
Git yoksa: fingerprint(.devkit/data/fingerprint.json) ile son taramadan bu yana
degisen DOSYALAR listelenir (fonksiyon detayi yok).

Sadece statik analizdir; runtime dogrulamasi icin `check` komutu kullanilir.
"""

import ast
import json
import re
import subprocess
from pathlib import Path

_HUNK_RE = re.compile(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def _git(root: Path, *args) -> str | None:
    try:
        p = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True, text=True, timeout=30,
        )
        if p.returncode != 0:
            return None
        return p.stdout
    except (OSError, subprocess.TimeoutExpired):
        return None


def _is_git_repo(root: Path) -> bool:
    out = _git(root, "rev-parse", "--is-inside-work-tree")
    return bool(out and out.strip() == "true")


def _symbol_map(path: Path):
    """[(symbol, kind, lineno, end_lineno, cls)] for a single file, via AST."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, SyntaxError):
        return []
    syms = []
    for node in tree.body:
        if isinstance(node, (ast.ClassDef,)):
            syms.append((node.name, "class", node.lineno, node.end_lineno, None))
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    syms.append(
                        ("%s.%s" % (node.name, sub.name), "method",
                         sub.lineno, sub.end_lineno, node.name))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            syms.append((node.name, "function", node.lineno, node.end_lineno, None))
    return syms


def _enclosing_sym(syms, line):
    """Find the outermost symbol containing `line`. Returns tuple or None."""
    hit = None
    for sym in syms:
        start, end = sym[2], sym[3]
        if start <= line <= end:
            if hit is None or sym[2] >= hit[2]:
                hit = sym
    return hit


def _parse_diff(out: str) -> dict:
    """git diff --unified=0 output -> {path: [new_line_numbers, ...]}."""
    files = {}
    cur = None
    for ln in out.splitlines():
        if ln.startswith("+++ b/"):
            path = ln[6:].strip()
            if path.startswith('"') and path.endswith('"'):
                try:
                    path = json.loads(path)
                except Exception:
                    path = path[1:-1]
            else:
                path = path.replace("\\ ", " ")
            cur = path
            files.setdefault(cur, [])
        elif ln.startswith("@@ -"):
            m = _HUNK_RE.search(ln)
            if not m or cur is None:
                continue
            new_start = int(m.group(3))
            new_count = int(m.group(4) or 1)
            files[cur].extend(range(new_start, new_start + new_count))
    return files


def _git_changed_files(root: Path) -> dict:
    """('modified'|'deleted'|'new') lists from git status --porcelain."""
    out = _git(root, "status", "--porcelain", "--", "*.py")
    result = {"modified": [], "deleted": [], "new": []}
    if not out:
        return result
    for raw in out.splitlines():
        if len(raw) < 3:
            continue
        code, path = raw[:2], raw[3:]
        path = path.strip().strip('"')
        if " -> " in path:
            path = path.split(" -> ", 1)[-1].strip()
        if not path.endswith(".py") and not path.endswith(".pyw"):
            continue
        if code.startswith("??"):
            result["new"].append(path)
        elif code.startswith("D"):
            result["deleted"].append(path)
        elif code.startswith("R"):
            result["modified"].append(path)
        elif code.startswith("A"):
            result["new"].append(path)
        else:
            result["modified"].append(path)
    return result


def _fingerprint_changed(root: Path, devkit_dir: Path):
    """No-git fallback: fingerprint.json vs current scan.json shas."""
    fp_path = devkit_dir / "data" / "fingerprint.json"
    scan_path = devkit_dir / "data" / "scan.json"
    changed = []
    try:
        fp = json.loads(fp_path.read_text(encoding="utf-8"))
        scan = json.loads(scan_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    for rel, fdata in scan.get("files", {}).items():
        if not rel.endswith(".py"):
            continue
        if fp.get(rel) != fdata.get("sha256"):
            changed.append(rel)
    return changed


def run_changed(root: Path, ignore_dirs, devkit_dir: Path) -> dict:
    result = {
        "mode": "git",
        "git": False,
        "changed_files": [],
        "new_files": [],
        "deleted_files": [],
        "by_file": {},
        "note": None,
    }

    if not _is_git_repo(root):
        result["mode"] = "fingerprint"
        changed = _fingerprint_changed(root, devkit_dir)
        result["changed_files"] = sorted(changed)
        result["by_file"] = {}
        for rel in result["changed_files"]:
            result["by_file"][rel] = {"new_lines": ["?"], "symbols": []}
        result["note"] = (
            "Git deposu yok; son taramadan bu yana degisen dosyalar listelendi "
            "(fonksiyon detayi icin projeyi git'e alin, or. scaffold)."
        )
        return result

    result["git"] = True
    status = _git_changed_files(root)

    modified = status["modified"]
    new_files = status["new"]
    deleted = status["deleted"]

    changed_lines = {}
    if modified:
        diff_out = _git(root, "diff", "--unified=0", "HEAD", "--", "*.py")
        if diff_out:
            changed_lines = _parse_diff(diff_out)

    by_file = {}
    for rel in sorted(modified):
        path = root / rel
        new_lines = sorted(changed_lines.get(rel, []))
        syms = _symbol_map(path)
        changed = []
        seen = set()
        for ln in new_lines:
            s = _enclosing_sym(syms, ln)
            if s and s[0] not in seen:
                seen.add(s[0])
                changed.append({
                    "symbol": s[0], "kind": s[1], "cls": s[4],
                    "line": ln, "new": False,
                })
        by_file[rel] = {"new_lines": new_lines, "symbols": changed}

    for rel in sorted(new_files):
        path = root / rel
        syms = _symbol_map(path)
        changed = []
        for s in syms:
            changed.append({
                "symbol": s[0], "kind": s[1], "cls": s[4],
                "line": s[2], "new": True,
            })
        by_file[rel] = {"new_lines": [], "entire_file": True, "symbols": changed}

    result["changed_files"] = sorted(set(modified) | set(new_files))
    result["new_files"] = sorted(new_files)
    result["deleted_files"] = sorted(deleted)
    result["by_file"] = by_file
    return result