#!/usr/bin/env python3
"""
health.py - runtime import health check.

Imports every Python module of each subsystem in a subprocess (using the
project's configured interpreter) and reports per-module OK/FAIL. This catches
runtime-only problems that static analysis cannot see, such as circular
imports and missing dependencies.

Optimization: Uses batch import - all modules in a single subprocess
to avoid process spawn overhead for projects with many subsystems.
"""

import json
import subprocess
import sys
from pathlib import Path


def _embed(value) -> str:
    """Safely embed a Python value into generated subprocess code."""
    return json.dumps(value, ensure_ascii=True)


def run_health(root: Path, config: dict, ignore_dirs, data_dir) -> dict:
    env = config.get("env_path") or sys.executable
    if not env or not Path(env).exists():
        env = sys.executable

    from engine.scan import walk_project
    py_files = [p for p in walk_project(root, ignore_dirs) if p.suffix == ".py"]

    modules_by_sub = {}
    all_modules = []
    for p in py_files:
        rel = p.relative_to(root)
        parts = list(rel.with_suffix("").parts)
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        if not parts:
            continue
        mod = ".".join(parts)
        sub = rel.parts[0]
        modules_by_sub.setdefault(sub, []).append(mod)
        all_modules.append((sub, mod))

# Batch import: single subprocess for all modules
    # Build code that imports all modules and reports per-module status
    code_lines = [
        "import sys, json",
        "sys.path.insert(0, %s)" % _embed(str(root)),
        "import importlib",
        "results = {}",
    ]
    for sub, mod in all_modules:
        code_lines.append(
            "try:\n"
            "    importlib.import_module(%s)\n"
            "    results[%s] = ['OK', %s, %s]\n"
            "except Exception as e:\n"
            "    results[%s] = ['FAIL', %s, %s, type(e).__name__, str(e)[:200]]"
            % (_embed(mod), _embed(mod), _embed(mod), _embed(sub),
               _embed(mod), _embed(mod), _embed(sub))
        )
    code_lines.append("for mod, res in results.items():\n"
                      "    if res[0] == 'OK':\n"
                      "        print('OK', res[1], res[2])\n"
                      "    else:\n"
                      "        print('FAIL', res[1], res[2], res[3], res[4])")
    
    code = "\n".join(code_lines)

    try:
        proc = subprocess.run(
            [env, "-c", code],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(root),
        )
        lines = proc.stdout.splitlines()
        
        # Reorganize by subsystem
        results = {}
        for sub in sorted(modules_by_sub.keys()):
            results[sub] = {"returncode": 0, "lines": []}
        
        for line in lines:
            if line.startswith("OK ") or line.startswith("FAIL "):
                parts = line.split(" ", 3)
                status = parts[0]
                mod = parts[1]
                sub = parts[2]
                if sub in results:
                    results[sub]["lines"].append(line)
        
        # Handle case where some subsystems had no modules imported
        for sub in results:
            if not results[sub]["lines"]:
                results[sub]["lines"] = ["(no modules)"]
                
    except subprocess.TimeoutExpired:
        # Fallback: per-subsystem (old behavior)
        results = {}
        for sub, mods in sorted(modules_by_sub.items()):
            sub_code = (
                "import sys, json\n"
                "sys.path.insert(0, %s)\n"
                "import importlib\n"
                "mods = %s\n"
                "for m in mods:\n"
                "    try:\n"
                "        importlib.import_module(m)\n"
                "        print('OK', m)\n"
                "    except Exception as e:\n"
                "        print('FAIL', m, type(e).__name__, str(e)[:200])\n"
            ) % (_embed(str(root)), _embed(mods))
            try:
                proc = subprocess.run(
                    [env, "-c", sub_code],
                    capture_output=True,
                    text=True,
                    timeout=180,
                    cwd=str(root),
                )
                results[sub] = {
                    "returncode": proc.returncode,
                    "lines": proc.stdout.splitlines(),
                }
            except subprocess.TimeoutExpired:
                results[sub] = {"returncode": -1, "lines": ["TIMEOUT"]}
            except OSError as e:
                results[sub] = {"returncode": -1, "lines": ["ERROR %s" % e]}
    except OSError as e:
        results = {sub: {"returncode": -1, "lines": ["ERROR %s" % e]} for sub in modules_by_sub}

    summary = {"ok": 0, "fail": 0, "expected": len(all_modules)}
    for r in results.values():
        for line in r.get("lines", []):
            if line.startswith("OK"):
                summary["ok"] += 1
            elif line.startswith("FAIL"):
                summary["fail"] += 1

    reported = summary["ok"] + summary["fail"]
    if reported != summary["expected"]:
        summary["note"] = (
            "Raporlanan %d/%d modul - alt islem ciktisi kesildi veya kilitlenme oldu; "
            "yukaridakiler guvenilir, geri kalani dogrulanamadi."
            % (reported, summary["expected"])
        )

    return {"summary": summary, "by_subsystem": results, "env": str(env)}
