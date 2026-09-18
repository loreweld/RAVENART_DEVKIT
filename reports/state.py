#!/usr/bin/env python3
"""
state.py - persistent task state + generated STATE/ENVIRONMENT/ISSUES files.

state.json is the single persistent state (active task, last tasks, manual
issues). STATUS.yaml, CONTEXT.md, ENVIRONMENT.md and ISSUES.md are generated
views of that state plus the latest scan/health data.
"""

import json
from pathlib import Path


def state_path(devkit_dir: Path) -> Path:
    return devkit_dir / "state.json"


def load_state(devkit_dir: Path) -> dict:
    p = state_path(devkit_dir)
    if not p.exists():
        return {"active_task": None, "last_tasks": [], "manual_issues": []}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"active_task": None, "last_tasks": [], "manual_issues": []}
    data.setdefault("active_task", None)
    data.setdefault("last_tasks", [])
    data.setdefault("manual_issues", [])
    return data


def save_state(devkit_dir: Path, state: dict) -> None:
    state_path(devkit_dir).write_text(
        json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _failing_modules(health: dict) -> list:
    out = []
    for r in health.get("by_subsystem", {}).values():
        for line in r.get("lines", []):
            if line.startswith("FAIL"):
                out.append(line)
    return out


def generate_state(root: Path, config: dict, data_dir: Path, devkit_dir: Path) -> None:
    scan = _load(data_dir / "scan.json")
    health = _load(data_dir / "health.json")
    deps = _load(data_dir / "deps.json")
    quality = _load(data_dir / "quality.json")
    techdebt = _load(data_dir / "techdebt.json")
    state = load_state(devkit_dir)

    stats = scan.get("stats", {})
    health_sum = health.get("summary", {})
    failing = _failing_modules(health)
    cycles = deps.get("cycles", [])
    q_summary = quality.get("summary", {}) if quality else {}
    td_summary = techdebt.get("twin_groups", []) if techdebt else []

    # STATUS.yaml
    td_stats = techdebt.get("callgraph_stats", {}) if techdebt else {}
    lines = [
        "# STATUS - current state (auto section regenerated; persistent fields from state.json)",
        "meta:",
        "  project: %s" % config.get("project_name", ""),
        "  last_sync: %s" % scan.get("generated_at", ""),
        "  active_task: %s" % (state.get("active_task") or "null"),
        "metrics:",
        "  python_files: %s" % stats.get("total_py", 0),
        "  lines: %s" % stats.get("total_lines", 0),
        "  classes: %s" % stats.get("total_classes", 0),
        "  subsystems: %s" % ", ".join(stats.get("subsystems", [])),
        "health:",
        "  ok: %s" % health_sum.get("ok", "?"),
        "  fail: %s" % health_sum.get("fail", "?"),
        "quality:",
        "  avg_score: %s" % q_summary.get("avg_toplam", "?"),
        "  total_issues: %s" % q_summary.get("total_issues", "?"),
        "  kritik: %s" % q_summary.get("kritik_issues", "?"),
        "techdebt:",
        "  twin_groups: %s" % len(td_summary),
        "  fix_tags: %s" % len(techdebt.get("fix_tags", [])) if techdebt else "  fix_tags: ?",
        "  callgraph_funcs: %s" % td_stats.get("total_functions", "?"),
        "  callgraph_edges: %s" % td_stats.get("total_call_edges", "?"),
        "  avg_callees: %s" % td_stats.get("avg_callees_per_func", "?"),
    ]
    if failing:
        lines.append("  failing_modules:")
        for f in failing:
            lines.append("    - %s" % f)
    lines.append("cycles:")
    if cycles:
        for c in cycles:
            lines.append("  - %s" % " <-> ".join(c))
    else:
        lines.append("  - none")
    if q_summary:
        lines.append("quality_by_subsystem:")
        for sub, entry in (quality.get("by_subsystem", {}) or {}).items():
            lines.append("  %s: avg %s, issues %d (kritik %d)" % (sub, entry.get("avg_toplam", "?"), entry.get("issues", 0), entry.get("kritik", 0)))
        brk = q_summary.get("score_breakdown")
        if isinstance(brk, dict):
            lines.append("quality_breakdown:")
            for c, v in brk.items():
                lines.append("  %s: %s/10" % (c, v))
        top = q_summary.get("top_actions", [])
        if top:
            lines.append("top_remediation:")
            for a in top[:8]:
                lines.append("  - [%s] %s:%s %s" % (
                    a.get("severity", "?").upper(),
                    a.get("file", "?"),
                    a.get("line") or "?",
                    a.get("detail", "")))
                lines.append("      cozum: %s (iyilestirir: %s)" % (
                    a.get("cozum", "?"), a.get("iyilestirilen_skor", "?")))
    (devkit_dir / "STATUS.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # CONTEXT.md
    cl = ["# CONTEXT", "", "Last tasks (newest first):", ""]
    for t in state.get("last_tasks", []):
        cl.append("## %s - %s" % (t.get("date", ""), t.get("name", "")))
        cl.append("")
        cl.append(t.get("summary", ""))
        cl.append("")
    if not state.get("last_tasks"):
        cl.append("(none yet)")
    (devkit_dir / "CONTEXT.md").write_text("\n".join(cl) + "\n", encoding="utf-8")

    # ENVIRONMENT.md
    env = config.get("env_path", "")
    ignore = config.get("ignore_dirs", [])
    entry = [r for r in scan.get("files", {}) if "/" not in r and r.endswith(".py")]
    el = [
        "# ENVIRONMENT",
        "",
        "- Project root: %s" % root,
        "- Python env: %s" % (env or "(auto-detect)"),
        "- Ignore dirs: %s" % (", ".join(sorted(ignore)) if ignore else "-"),
        "- Entry points: %s" % (", ".join(sorted(entry)) if entry else "-"),
        "",
        "## Health",
        "",
        "- Import check: %s OK / %s FAIL" % (health_sum.get("ok", "?"), health_sum.get("fail", "?")),
    ]
    (devkit_dir / "ENVIRONMENT.md").write_text("\n".join(el) + "\n", encoding="utf-8")

    # ISSUES.md (auto-detected + manual from state.json)
    il = ["# ISSUES", "", "## Auto-detected", ""]
    if failing:
        il.append("### Failing imports (runtime health)")
        for f in failing:
            il.append("- %s" % f)
        il.append("")
    if cycles:
        il.append("### Circular imports (static)")
        for c in cycles:
            il.append("- %s" % " <-> ".join(c))
        il.append("")
    parse_errors = [rel for rel, f in scan.get("files", {}).items() if f.get("parse_error")]
    if parse_errors:
        il.append("### Unparseable files")
        for p in parse_errors:
            il.append("- %s" % p)
        il.append("")
    # quality issues
    if quality:
        q_issues = []
        for rel, entry in quality.get("by_file", {}).items():
            for iss in entry.get("issues", []):
                q_issues.append((iss.get("kritik", False), rel, iss))
        if q_issues:
            il.append("### Quality issues (by file, kritik first)")
            for kritik, rel, iss in sorted(q_issues, key=lambda x: (not x[0], x[1])):
                flag = "KRITIK" if iss.get("kritik") else iss.get("severity", "dusuk")
                il.append("- [%s] `%s` %s: %s" % (flag, rel, iss.get("type", "?"), iss.get("detail", "")))
            il.append("")
        twin_d = techdebt.get("twin_detailed", []) if techdebt else []
        if twin_d:
            il.append("### Twin groups (potential duplicates)")
            for g in twin_d[:10]:
                members = ", ".join("%s:%s" % (m["file"], m["line"]) for m in g.get("members", []))
                sim = g.get("similarity_avg", "?")
                il.append("- %s (%s, sim~%s%%): %s" % (g.get("group_id", "?"), g.get("method", "?"), sim, members))
            if len(twin_d) > 10:
                il.append("- ... (%d more groups)" % (len(twin_d) - 10))
            il.append("")
        fix_tags = techdebt.get("fix_tags", []) if techdebt else []
        if fix_tags:
            il.append("### Fix/TODO tags (%d)" % len(fix_tags))
            for t in fix_tags[:20]:
                il.append("- `%s:%s` [%s] %s" % (t["file"], t["line"], t["tag"], t["text"][:80]))
            if len(fix_tags) > 20:
                il.append("- ... (%d more)" % (len(fix_tags) - 20))
            il.append("")
    if not failing and not cycles and not parse_errors and not quality:
        il.append("- (none)")
        il.append("")
    il += ["## Manual", ""]
    for i in state.get("manual_issues", []):
        il.append("- **%s** (%s): %s" % (i.get("title", ""), i.get("severity", "?"), i.get("detail", "")))
    if not state.get("manual_issues"):
        il.append("- (none - add via state.json)")
    (devkit_dir / "ISSUES.md").write_text("\n".join(il) + "\n", encoding="utf-8")
