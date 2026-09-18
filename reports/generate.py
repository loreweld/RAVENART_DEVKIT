#!/usr/bin/env python3
"""
generate.py - render KB/*.md reports from data/*.json + meta.yaml.

Reports produced (all under <project>/.devkit/KB/):
  QUICKREF.md        fast overview (<100 lines)
  PROJECT_MAP.md     folder/file tree with one-line summaries
  DEPENDENCIES.md    subsystem matrix + static import cycles
  SYMBOL_INDEX.md    flat symbol -> file:line lookup
  ARCHITECTURE.md    working principles (auto overview + meta.yaml)
  subsystems/*.md    per-subsystem detail (big files get line-range outlines)
  flows/*.md         runtime flows (from meta.yaml, when present)

All KB files always hold the CURRENT final state; no history is embedded.
History lives only in DEVELOPMENT_LOG.md.
"""

import json
from pathlib import Path


def _get_big_file_threshold(config: dict) -> int:
    """Get big file threshold from config, default 800."""
    return config.get("big_file_threshold", 800)


def _get_output_guard_limits(config: dict) -> tuple:
    """Get output guard limits from config, default (warn=1MB, block=5MB)."""
    return (
        config.get("output_warn_mb", 1),
        config.get("output_block_mb", 5)
    )


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _load_meta(devkit_dir: Path) -> dict:
    p = devkit_dir / "meta.yaml"
    if not p.exists():
        return {}
    try:
        import yaml
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _load_descriptions(devkit_dir: Path) -> dict:
    p = devkit_dir / "map_descriptions.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _desc(rel: str, fdata: dict, descriptions: dict) -> str:
    return descriptions.get(rel) or fdata.get("doc", "") or ""


def _gen_quickref(scan, config, info, kb_dir):
    stats = scan["stats"]
    lines = [
        "# QUICKREF",
        "",
        "- Project: %s" % config.get("project_name", ""),
        "- Root: %s" % scan.get("project_root", ""),
        "- Generated: %s" % scan.get("generated_at", ""),
        "",
    ]
    if info:
        lines += ["## What is this project?", "", info.strip(), ""]
    lines += [
        "## Numbers",
        "",
        "- Python files: %d" % stats["total_py"],
        "- Other files: %d" % stats["total_non_py"],
        "- Lines: %d" % stats["total_lines"],
        "- Classes: %d" % stats["total_classes"],
        "- Module functions: %d" % stats["total_functions"],
        "",
        "## Subsystems",
        "",
    ]
    for s in stats["subsystems"]:
        cnt = sum(1 for r in scan["files"] if r.split("/")[0] == s)
        lines.append("- %s (%d files)" % (s, cnt))
    lines += ["", "## Entry points", ""]
    for r in sorted(scan["files"]):
        if "/" not in r and r.endswith(".py"):
            lines.append("- %s" % r)
    (kb_dir / "QUICKREF.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _gen_project_map(scan, descriptions, kb_dir):
    root = {}
    for rel, fdata in scan["files"].items():
        parts = rel.split("/")
        node = root
        for i, p in enumerate(parts):
            if i == len(parts) - 1:
                node.setdefault(p, {})["_file"] = fdata
            else:
                node = node.setdefault(p, {})
    for entry in scan.get("non_py_files", []):
        parts = entry["path"].split("/")
        node = root
        for i, p in enumerate(parts):
            if i == len(parts) - 1:
                node.setdefault(p, {})["_file"] = {"path": entry["path"], "doc": "", "lines": 0}
            else:
                node = node.setdefault(p, {})

    lines = ["# Project Map", "", "Every folder and file with a one-line summary.", ""]

    def render(name, node, depth):
        ind = "  " * depth
        if "_file" in node:
            f = node["_file"]
            d = descriptions.get(f["path"]) or f.get("doc", "")
            suffix = "  (%d lines)" % f["lines"] if f.get("lines") else ""
            base = "%s%s%s" % (ind, name, suffix)
            lines.append("%s — %s" % (base, d) if d else base)
        else:
            lines.append("%s%s/" % (ind, name))
            for child in sorted(node.keys()):
                if child != "_file":
                    render(child, node[child], depth + 1)

    for name in sorted(root.keys()):
        render(name, root[name], 0)
    (kb_dir / "PROJECT_MAP.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _gen_dependencies(scan, deps, kb_dir):
    subs = scan["stats"]["subsystems"]
    lines = ["# Dependencies", "", "## Subsystem matrix (rows import columns)", ""]
    lines.append("| from \\ to |" + "|".join(subs) + "|")
    lines.append("|---|" + "---|" * len(subs))
    matrix = deps.get("matrix", {})
    for s in subs:
        row = matrix.get(s, {})
        cells = [str(row.get(t, 0) or "-") for t in subs]
        lines.append("| %s |" % s + "|".join(cells) + "|")
    lines += ["", "## Circular imports (static)", ""]
    cycles = deps.get("cycles", [])
    if cycles:
        for c in cycles:
            lines.append("- %s" % " <-> ".join(c))
    else:
        lines.append("- none detected")
    (kb_dir / "DEPENDENCIES.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _gen_symbol_index(scan, kb_dir):
    rows = []
    for rel, fdata in scan["files"].items():
        for c in fdata.get("classes", []):
            rows.append((c["name"], "class", rel, c["lineno"]))
            for m in c.get("methods", []):
                rows.append(("%s.%s" % (c["name"], m["name"]), "method", rel, m["lineno"]))
        for fn in fdata.get("functions", []):
            rows.append((fn["name"], "function", rel, fn["lineno"]))
    rows.sort(key=lambda r: r[0].lower())
    lines = ["# Symbol Index", "", "Flat lookup: symbol -> file:line.", ""]
    for name, kind, rel, line in rows:
        lines.append("%-70s %-8s %s:%s" % (name, kind, rel, line))
    (kb_dir / "SYMBOL_INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _gen_subsystems(scan, descriptions, kb_dir, quality=None, config=None):
    threshold = _get_big_file_threshold(config) if config else 800
    subs_dir = kb_dir / "subsystems"
    subs_dir.mkdir(parents=True, exist_ok=True)
    files = scan["files"]
    by_file = (quality or {}).get("by_file", {})
    for sub in scan["stats"]["subsystems"]:
        sf = {rel: f for rel, f in files.items() if rel.split("/")[0] == sub}
        if not sf:
            continue
        total_lines = sum(f["lines"] for f in sf.values())
        # subsystem avg
        sub_avg = (quality or {}).get("by_subsystem", {}).get(sub, {})
        lines = [
            "# %s" % sub,
            "",
            "Files: %d | Lines: %d" % (len(sf), total_lines),
            "",
        ]
        if sub_avg:
            lines.append("Quality avg (0-40): **%s** | Issues: %d (kritik %d)" % (
                sub_avg.get("avg_toplam", "?"), sub_avg.get("issues", 0), sub_avg.get("kritik", 0)))
            lines.append("")
        for rel in sorted(sf):
            f = sf[rel]
            d = _desc(rel, f, descriptions)
            q = by_file.get(rel, {})
            scores = q.get("scores", {})
            issues = q.get("issues", [])
            lines.append("## %s" % rel)
            if d:
                lines += ["", "> %s" % d, ""]
            if scores:
                lines.append("- Quality: Aktiflik %s | Gereklilik %s | Kod Kalitesi %s | Butunluk %s | **Toplam %s/40**" % (
                    scores.get("Aktiflik", "?"), scores.get("Gereklilik", "?"),
                    scores.get("Kod Kalitesi", "?"), scores.get("Butunluk", "?"),
                    scores.get("Toplam", "?")))
            if issues:
                for iss in issues:
                    flag = "KRITIK" if iss.get("kritik") else iss.get("severity", "")
                    lines.append("  - [%s] %s: %s -> %s" % (flag, iss.get("type", "?"), iss.get("detail", ""), iss.get("cozum", "")))
            if f.get("lines", 0) >= threshold:
                lines += ["(%d lines - outline)" % f["lines"], "", "```"]
                for fn in f.get("functions", []):
                    lines.append("fn  %-30s %s-%s %s" % (fn["name"], fn["lineno"], fn["end_lineno"], fn["sig"]))
                for c in f.get("classes", []):
                    lines.append("cls %-30s %s-%s" % (c["name"], c["lineno"], c["end_lineno"]))
                    for m in c.get("methods", []):
                        lines.append("    def %-28s %s-%s %s" % (m["name"], m["lineno"], m["end_lineno"], m["sig"]))
                lines.append("```")
            else:
                cls_names = ", ".join(c["name"] for c in f.get("classes", [])) or "-"
                fn_names = ", ".join(x["name"] for x in f.get("functions", [])) or "-"
                lines.append("- Classes: %s" % cls_names)
                lines.append("- Functions: %s" % fn_names)
            lines.append("")
        (subs_dir / ("%s.md" % sub)).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _gen_architecture(scan, meta, kb_dir):
    lines = ["# Architecture", "", "## Subsystems", ""]
    for s in scan["stats"]["subsystems"]:
        lines.append("- %s" % s)
    lines.append("")
    if not meta:
        lines.append("> Runtime principles not yet authored (meta.yaml).")
        lines.append("> Baslangic noktasi: KB/INSIGHTS.md (otomatik kesif) ve meta.draft.yaml "
                     "-> bunlari duzenleyip meta.yaml olarak kaydedin.")
    else:
        layers = meta.get("architecture", {}).get("layers", [])
        if layers:
            lines += ["## Layers", ""]
            for l in layers:
                lines.append("### %s" % l.get("name", ""))
                lines.append(l.get("responsibility", ""))
                lines.append("")
        patterns = meta.get("design_patterns", [])
        if patterns:
            lines += ["## Design patterns", ""]
            for p in patterns:
                lines.append("- **%s**: %s" % (p.get("name", ""), p.get("description") or p.get("note", "")))
            lines.append("")
        events = meta.get("events", [])
        if events:
            lines += ["## Events (%d)" % len(events), ""]
            for e in events:
                lines.append("- %s" % e.get("name", ""))
            lines.append("")
        caps = meta.get("capabilities", [])
        if caps:
            lines += ["## Capabilities", ""]
            for c in caps:
                lines.append("- %s: %s" % (c.get("capability", ""), c.get("component", "")))
            lines.append("")
    (kb_dir / "ARCHITECTURE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _md(value, level, out):
    if isinstance(value, dict):
        for k, v in value.items():
            if isinstance(v, (dict, list)) and v:
                out.append("%s**%s**" % ("  " * level, k))
                _md(v, level + 1, out)
            else:
                out.append("%s- **%s**: %s" % ("  " * level, k, v))
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                _md(item, level, out)
            else:
                out.append("%s- %s" % ("  " * level, item))
    else:
        out.append("%s- %s" % ("  " * level, value))


def _gen_flows(meta, kb_dir):
    flows_dir = kb_dir / "flows"
    flows_dir.mkdir(parents=True, exist_ok=True)
    mapping = [
        ("boot", "boot_chain"),
        ("message", "message_flow"),
        ("memory", "memory_flow"),
        ("session", "session_flow"),
        ("startup_shutdown", "startup_chain"),
    ]
    for name, key in mapping:
        data = meta.get(key)
        if not data:
            continue
        out = ["# %s" % name.replace("_", " ").title(), ""]
        _md(data, 0, out)
        (flows_dir / ("%s.md" % name)).write_text("\n".join(out) + "\n", encoding="utf-8")


def _check_output_size(text: str, label: str, config: dict = None):
    warn_mb, block_mb = _get_output_guard_limits(config) if config else (1, 5)
    size_mb = len(text.encode("utf-8")) / (1024 * 1024)
    if size_mb > block_mb:
        raise ValueError("[KB] %s %.2fMB > %dMB block limit - split the report" % (label, size_mb, block_mb))
    if size_mb > warn_mb:
        print("[KB] WARN: %s %.2fMB > %dMB" % (label, size_mb, warn_mb))


def _check_json_contract(data: dict, required_keys: list, label: str) -> list:
    missing = [k for k in required_keys if k not in data]
    if missing:
        print("[KB] WARN: %s missing keys: %s" % (label, ", ".join(missing)))
    return missing


def _validate_scan_contract(scan: dict) -> list:
    """Validate scan.json structure in detail."""
    issues = _check_json_contract(scan, ["stats", "files", "project_root", "generated_at"], "scan.json")
    if "stats" in scan:
        stats = scan["stats"]
        _check_json_contract(stats, ["total_files", "total_py", "total_lines", "total_classes", "total_functions", "subsystems"], "scan.json.stats")
    if "files" in scan:
        for rel, fdata in list(scan["files"].items())[:5]:  # sample check
            _check_json_contract(fdata, ["path", "sha256", "lines", "classes", "functions", "imports"], f"scan.json.files[{rel}]")
    return issues


def _validate_deps_contract(deps: dict) -> list:
    """Validate deps.json structure in detail."""
    issues = _check_json_contract(deps, ["graph", "reverse", "matrix", "cycles"], "deps.json")
    if "graph" in deps:
        for rel, targets in list(deps["graph"].items())[:5]:
            if not isinstance(targets, list):
                issues.append("deps.json.graph[%s] not a list" % rel)
    return issues


def _validate_quality_contract(quality: dict) -> list:
    """Validate quality.json structure in detail."""
    issues = _check_json_contract(quality, ["by_file", "by_subsystem", "summary"], "quality.json")
    if "summary" in quality:
        _check_json_contract(quality["summary"], ["total_files", "total_issues", "kritik_issues", "avg_toplam"], "quality.json.summary")
    if "by_file" in quality:
        for rel, fdata in list(quality["by_file"].items())[:5]:
            _check_json_contract(fdata, ["scores", "issues"], f"quality.json.by_file[{rel}]")
            if "scores" in fdata:
                _check_json_contract(fdata["scores"], ["Aktiflik", "Gereklilik", "Kod Kalitesi", "Butunluk", "Toplam"], f"quality.json.by_file[{rel}].scores")
    return issues


def _validate_techdebt_contract(techdebt: dict) -> list:
    """Validate techdebt.json structure in detail."""
    issues = _check_json_contract(techdebt, ["twin_groups", "twin_detailed", "fix_tags", "callgraph", "callgraph_stats"], "techdebt.json")
    if "callgraph_stats" in techdebt:
        _check_json_contract(techdebt["callgraph_stats"], ["total_functions", "total_call_edges", "total_caller_edges", "avg_callees_per_func"], "techdebt.json.callgraph_stats")
    return issues


def generate_all(root: Path, config: dict, data_dir: Path, devkit_dir: Path) -> bool:
    kb_dir = devkit_dir / "KB"
    kb_dir.mkdir(parents=True, exist_ok=True)

    # Stale-file prevention: these subdirs are fully regenerated each run;
    # remove leftovers from previous (now-invalid) subsystems/flows.
    for subdir in ("subsystems", "flows"):
        d = kb_dir / subdir
        if d.exists():
            for p in d.iterdir():
                if p.suffix == ".md":
                    try:
                        p.unlink()
                    except OSError:
                        pass

    scan = _load(data_dir / "scan.json")
    deps = _load(data_dir / "deps.json")
    quality = _load(data_dir / "quality.json")
    techdebt = _load(data_dir / "techdebt.json")
    if not scan:
        return False
    
    # Enhanced JSON contract validation
    _validate_scan_contract(scan)
    _validate_deps_contract(deps)
    if quality:
        _validate_quality_contract(quality)
    if techdebt:
        _validate_techdebt_contract(techdebt)

    descriptions = _load_descriptions(devkit_dir)
    meta = _load_meta(devkit_dir)

    info = ""
    info_path = devkit_dir / "PROJECT_INFO.txt"
    if info_path.exists():
        txt = info_path.read_text(encoding="utf-8", errors="replace")
        if "\n\n" in txt:
            info = txt.split("\n\n", 1)[1].strip()
        else:
            info = txt.strip()

    _gen_quickref(scan, config, info, kb_dir)
    _gen_project_map(scan, descriptions, kb_dir)
    _gen_dependencies(scan, deps, kb_dir)
    _gen_symbol_index(scan, kb_dir)
    _gen_subsystems(scan, descriptions, kb_dir, quality, config)
    _gen_architecture(scan, meta, kb_dir)
    _gen_flows(meta, kb_dir)
    # automatic discovery (hub/layer/entry/base-class/INSIGHTS.md + meta.draft.yaml)
    try:
        from engine.discovery import write_discovery_output
        write_discovery_output(devkit_dir, scan, deps)
    except Exception as e:
        print("[KB] WARN: kesif raporu uretilemedi: %s" % e)
    # output size guard
    for p in kb_dir.rglob("*.md"):
        try:
            _check_output_size(p.read_text(encoding="utf-8"), str(p.relative_to(kb_dir)), config)
        except ValueError as e:
            print(e)
    return True
