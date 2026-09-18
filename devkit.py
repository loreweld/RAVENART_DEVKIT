#!/usr/bin/env python3
"""
DEVKIT - AI Development Support System
======================================

Project-agnostic toolchain that lets an AI (or a developer) quickly build an
accurate mental model of an unfamiliar codebase and keep that model fresh
while working on it.

Key principles:
  - Single source of truth: every piece of knowledge exists in one place.
  - Map before reading: file outlines + symbol index instead of blind reads.
  - KB files always hold the CURRENT final state; history lives only in
    DEVELOPMENT_LOG.md.
  - Headless by default; the only interactive surface is the setup wizard.
  - Zero third-party dependencies (stdlib + Tkinter only).
  - No project output is ever written under the DEVKIT home folder.

Usage:
    python devkit.py <command> [args]

Commands:
    init             Setup wizard for a new project (GUI folder picker)
    select [name]    Set the active project
    list             List registered projects
    help             Usage guide
"""

import argparse
import os
import sys

from common import load_registry, project_root, set_active_project, project_write_lock, RegistryLockError
from engine.context import DevkitError

USAGE_TEXT = """\
============================================================
DEVKIT - AI Gelistirme Destek Sistemi - Kullanim Kilavuzu
============================================================

DEVKIT, bir AI'nin (veya gelistiricinin) hic bilmedigi bir kod
mimarisini hizla anlamasini ve calisma boyunca bu bilgiyi guncel
tutmasini saglayan, projeden bagimsiz destek aletidir.

BASLANGIC (bir kez):
  1. DEVKIT.bat -> [1] Yeni Proje (Kurulum Sihirbazi)
  2. Sihirbazda:
     - Calisma klasorunu sec (Windows gezgini ile)
     - Proje hakkinda bilgi gir (ayri .txt ciktisi olur)
     - Istersen projeye ozel ek kurallar gir
     - Python env yolunu sec (python.exe)
     - Taranmayacak klasorleri isaretle (miniconda, java, .git ...)

  Bu islem sonunda:
     - Proje, devkit kayit defterine eklenir
     - <proje>/.devkit/ klasoru olusur (config, bilgi, kurallar)
     - Ileride tum tarama ve rapor ciktilari buraya yazilir

GUNLUK KULLANIM:
  DEVKIT.bat -> [2] Projeleri Listele / Sec  -> aktif projeyi degistir

MEVCUT KOMUTLAR:
  init            Yeni proje kurulum sihirbazi
  list            Kayitli projeleri listele
  select <ad>     Aktif projeyi sec
  scan            Tam yapisal tarama (data/*.json, sadece veri)
  scaffold        Proje dosyalarini garantile (.gitignore/pyproject.toml/.git)
  sync            Hizli guncelle (tarama + fark + rapor + log)
  rescan          "Taramayi Guncelle" (sifirdan tam tarama + rapor)
  report          Raporlari uret (KB/*.md)
  find <sembol>   Sembol ara (hangi dosya:satir)
  outline <dosya> Dosya anahati (satir araliklari ile)
  impact <dosya>  Degisiklik etki analizi
  check           Runtime saglik kontrolu (import testi, ok/fail per modul)
  changed         Git-diff + AST ile hangi dosya/fonksiyon degisti (son commit'e gore)
  techdebt        Teknik borc taramasi (twin/fix/callgraph + refactor onerisi)
  desc <yol> <..> Dosya/klasor ozeti ekle-goster (desc list ile listele)
  close-task      Gorev kapanis protokolu
  help            Bu kilavuz

PARALEL AI KULLANIMI (proje izolasyonu):
  Proje cozumleme sirasi: acik --project  >  calisma klasoru (cwd)  >  aktif
  proje isaretcisi. Her AI kendi proje klasoru icinden komut calistirirsa
  hedef OTOMATIK dogru projedir; iki AI birbirinin "select" yaptigini bilmez
  ve etkilenmez. En guvenceli yine acik --project vermektir.

  Her komut hedefini stderr'e yazar (yanlis hedef aninda gorunur):
      [PROJE] REMEMBER_EVA_AI -> H:\REMEMBER_EVA_AI (kaynak: calisma klasoru)
  (--json modunda bu satir bastirilmaz; stdout makine cikisi icin temizdir.)

  Projeler tamamen ayri .devkit/ klasorleri + ayri kilitler (.devkit.lock)
  kullanir; tum raporlar yalnizca hedef projenin klasorune yazilir (rapor
  sizmasi mumkun degil). Registry yazmalari da kilitli + atomiktir.

  Ornekler:
      python devkit.py sync --project "ProjeAdi"
      python devkit.py check --json --project "DigerProje"

KENDI KENDINE KESIF:
  sync/rescan her seferinde KB/INSIGHTS.md uretir: hub moduller (kim neyi
  kullaniyor), otomatik katman sirasi, base-class/polymorphic haritasi ve
  entry-point listesi. meta.yaml yoksa meta.draft.yaml otomatik taslak olur;
  AI bunu OBJECT okuyup duzenler, sifirdan yazmak zorunda kalmaz.
  Kalite skoru duzenlenebilir: 4 boyut kirilimi + oncelikli onarim listesi
  hem scan ciktisinda hem STATUS.yaml'da (top_remediation) yer alir.
  `check` artik modul bazinda ok/fail raporlar; runtime hatalarini yakalar.

ONEMLI KURAL:
  - Tum ciktilar PROJE klasorune yazilir; devkit ana klasoru
    yalnizca aletleri ve kayit defterini tutar.
============================================================
© 2026 İlker Can Karagülle · Loreweld AI (loreweld.ai)
"""


def _project(args):
    """Return the explicit --project value (always safe on None args)."""
    return getattr(args, "project", None)


def _add_project_arg(parser):
    parser.add_argument(
        "--project", default=None,
        help="Uzerinde islem yapilacak proje (varsayilan: aktif proje)",
    )
    return parser


def cmd_help(_args) -> int:
    print(USAGE_TEXT)
    return 0


def cmd_current(args) -> int:
    import json
    from engine.context import resolve_project_name
    name, source = resolve_project_name(getattr(args, "project", None))
    if not name:
        if getattr(args, "json", False):
            print(json.dumps({"active_project": None, "source": None}, ensure_ascii=False))
        else:
            print("(proje secilmedi)")
        return 0
    projects = load_registry().get("projects", {})
    if name not in projects:
        if getattr(args, "json", False):
            print(json.dumps({"error": "unknown_project", "message": "Unknown project: %s" % name}, ensure_ascii=False))
        else:
            print("[HATA] Kayitli proje bulunamadi: %s" % name)
        return 1
    root = projects.get(name, {}).get("root", "")
    if getattr(args, "json", False):
        print(json.dumps({"active_project": name, "root": root, "source": source}, ensure_ascii=False))
    else:
        print("%s -> %s  (kaynak: %s)" % (name, root, source))
    return 0


def cmd_gui(_args) -> int:
    from gui import main as gui_main
    return gui_main()


def cmd_list(args) -> int:
    import json
    reg = load_registry()
    active = reg.get("active_project")
    projects = reg.get("projects", {})
    if not projects:
        if getattr(args, "json", False):
            print(json.dumps({"projects": [], "active_project": None}, ensure_ascii=False))
        else:
            print("No registered projects. Run: devkit init")
        return 0
    if getattr(args, "json", False):
        out = {
            "active_project": active,
            "projects": {name: data.get("root", "") for name, data in projects.items()}
        }
        print(json.dumps(out, ensure_ascii=False))
    else:
        for name in sorted(projects):
            marker = "*" if name == active else " "
            print(" %s %-20s %s" % (marker, name, projects[name].get("root", "")))
    return 0


def cmd_select(args) -> int:
    import json
    reg = load_registry()
    projects = reg.get("projects", {})
    if not projects:
        if getattr(args, "json", False):
            print(json.dumps({"error": "no_projects", "message": "No registered projects. Run: devkit init"}, ensure_ascii=False))
        else:
            print("No registered projects. Run: devkit init")
        return 1
    name = args.name
    if not name:
        if getattr(args, "json", False):
            print(json.dumps({"error": "missing_name", "message": "Project name required"}, ensure_ascii=False))
        else:
            cmd_list(args)
            name = input("Select project name: ").strip()
    if name not in projects:
        if getattr(args, "json", False):
            print(json.dumps({"error": "unknown_project", "message": "Unknown project: %s" % name}, ensure_ascii=False))
        else:
            print("[ERROR] Unknown project: %s" % name)
        return 1
    set_active_project(name)
    root = projects[name].get("root", "")
    if getattr(args, "json", False):
        print(json.dumps({"active_project": name, "root": root}, ensure_ascii=False))
    else:
        print("[OK] Active project: %s -> %s" % (name, root))
    return 0


def cmd_init(args) -> int:
    import json
    import sys
    from wizard.setup_wizard import run_setup_wizard, run_setup_wizard_ai_driven
    
    if getattr(args, "ai_driven", False):
        # AI-driven programmatic setup
        result = run_setup_wizard_ai_driven(
            project_root=args.project_root,
            project_name=args.project_name,
            env_path=args.env_path,
            project_info=args.project_info or "",
            project_rules=args.project_rules or "",
            ignore_dirs=args.ignore_dirs,
            big_file_threshold=args.big_file_threshold,
            output_warn_mb=args.output_warn_mb,
            output_block_mb=args.output_block_mb,
            auto_confirm=args.auto_confirm,
            json_output=getattr(args, "json", False),
        )
        if getattr(args, "json", False):
            sys.stdout.write(json.dumps(result, indent=2, ensure_ascii=True) + "\n")
        # Return appropriate exit code
        if result.get("status") == "ok":
            return 0
        elif result.get("status") in ("needs_input", "needs_confirmation"):
            return 2  # Special code: needs user interaction
        else:
            return 1
    else:
        # Traditional interactive wizard
        return run_setup_wizard()


def _load_json(path):
    import json
    return json.loads(path.read_text(encoding="utf-8"))


def cmd_scaffold(args) -> int:
    import json
    from engine.context import require_project
    from engine.scaffold import scaffold
    root, config, ignore, data_dir = require_project(_project(args))
    name = config.get("project_name", "project")
    results = scaffold(root, name)
    if getattr(args, "json", False):
        print(json.dumps(results, ensure_ascii=False))
    else:
        for k, v in results.items():
            print("  %s: %s" % (k, v))
    return 0


def cmd_scan(_args) -> int:
    import json
    from engine.context import require_project
    import engine.scan as scan_mod
    import engine.deps as deps_mod
    import engine.api_surface as api_mod
    import engine.usage as usage_mod
    import engine.quality as quality_mod

    root, config, ignore, data_dir = require_project(_project(_args))
    use_cache = not getattr(_args, "no_cache", False)

    with project_write_lock(root):
        result = scan_mod.run_scan(root, ignore, data_dir, use_cache)
        (data_dir / "scan.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

        deps = deps_mod.run_deps(result)
        (data_dir / "deps.json").write_text(
            json.dumps(deps, indent=2, ensure_ascii=False), encoding="utf-8")

        api = api_mod.run_api(result)
        (data_dir / "api.json").write_text(
            json.dumps(api, indent=2, ensure_ascii=False), encoding="utf-8")

        usage = usage_mod.run_usage(root, result)
        (data_dir / "usage.json").write_text(
            json.dumps(usage, indent=2, ensure_ascii=False), encoding="utf-8")

        quality = quality_mod.run_quality(result)
        (data_dir / "quality.json").write_text(
            json.dumps(quality, indent=2, ensure_ascii=False), encoding="utf-8")

    s = result["stats"]
    if getattr(_args, "json", False):
        print(json.dumps({"stats": s, "quality": quality["summary"]}, indent=2, ensure_ascii=False))
    else:
        print("[OK] Tarama tamamlandi")
        print("  Dosya: %d  (.py %d, diger %d)" % (s["total_files"], s["total_py"], s["total_non_py"]))
        print("  Satir: %d | Sinif: %d | Fonksiyon: %d" % (s["total_lines"], s["total_classes"], s["total_functions"]))
        print("  Alt sistemler: %s" % ", ".join(s["subsystems"]))
        print("  Kalite: avg %s/40, issues %d (kritik %d)" % (quality["summary"]["avg_toplam"], quality["summary"]["total_issues"], quality["summary"]["kritik_issues"]))
        brk = quality["summary"].get("score_breakdown")
        if brk:
            print("    kirilim: " + ", ".join("%s %s/10" % (k, v) for k, v in brk.items()))
        top = quality["summary"].get("top_actions", [])
        if top:
            for a in top[:5]:
                print("    onarim: [%s] %s:%s %s" % (
                    a["severity"].upper(), a["file"], a.get("line") or "?",
                    (a.get("detail") or "")[:80]))
        print("  Cikti: %s" % data_dir)
    return 0


def _write_data(data_dir, result, deps, api, usage, quality=None):
    import json
    (data_dir / "scan.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    (data_dir / "deps.json").write_text(
        json.dumps(deps, indent=2, ensure_ascii=False), encoding="utf-8")
    (data_dir / "api.json").write_text(
        json.dumps(api, indent=2, ensure_ascii=False), encoding="utf-8")
    (data_dir / "usage.json").write_text(
        json.dumps(usage, indent=2, ensure_ascii=False), encoding="utf-8")
    if quality is not None:
        (data_dir / "quality.json").write_text(
            json.dumps(quality, indent=2, ensure_ascii=False), encoding="utf-8")


def _append_dev_log(devkit_dir, diff, label):
    from datetime import datetime
    p = devkit_dir / "DEVELOPMENT_LOG.md"
    if not p.exists():
        p.write_text(
            "# DEVELOPMENT_LOG\n\n"
            "(append-only changelog - history only; KB files always hold the current state)\n\n"
            "## Safe Delete Protocol\n"
            "When removing code (functions, classes, files), follow this protocol:\n"
            "1. **DeprecationWarning**: Add `@deprecated` decorator or `# DEPRECATED` comment\n"
            "2. **Wait period**: Minimum 1 week (7 days) before actual removal\n"
            "3. **Karar Matrisi**: Document decision with scoring (see below)\n"
            "4. **Archive**: Move to `archive/` folder instead of hard delete\n"
            "5. **Log entry**: Record in this log with decision rationale\n\n"
            "### Karar Matrisi (Decision Matrix) - Skorlama (0-100)\n"
            "| Kriter | Agirlik | Skor (0-10) | Not |\n"
            "|--------|---------|-------------|-----|\n"
            "| Cagri Sayisi (kac yerden cagrilir) | 30% | | |\n"
            "| Docstring var mi? | 20% | | |\n"
            "| Test coverage var mi? | 25% | | |\n"
            "| Son commit ne kadar eski? | 15% | | |\n"
            "| Guvenli alternatif var mi? | 10% | | |\n"
            "| **TOPLAM** | 100% | | |\n"
            "- **>= 70**: Guvenli silme/arsivle (Safe delete)\n"
            "- **40-69**: Dikkatli, deprecation warning + 2 hafta bekle\n"
            "- **< 40**: SILME, refactor/duzelt\n\n"
            "---\n",
            encoding="utf-8",
        )
    entry = ["", "## %s - %s" % (datetime.now().isoformat(timespec="seconds"), label), ""]
    entry.append("- Added: %d | Deleted: %d | Modified: %d | Moved: %d"
                 % (len(diff["added"]), len(diff["deleted"]), len(diff["modified"]), len(diff["moved"])))
    for a in diff["added"][:20]:
        entry.append("  + %s" % a)
    for d in diff["deleted"][:20]:
        entry.append("  - %s" % d)
    for m in diff["moved"][:20]:
        entry.append("  ~ %s -> %s" % (m[0], m[1]))
    with open(p, "a", encoding="utf-8") as f:
        f.write("\n".join(entry) + "\n")


def _report_new_code_checks(root, ignore, result, diff, prev_subsystems):
    """Anti-clutter + anti-duplication signals for newly added code."""
    added_py = [a for a in diff.get("added", []) if a.endswith(".py")]
    if not added_py:
        return

    print("[KONTROL] Yeni .py dosyalari eklendi - yerlesimini dogrula:")
    for a in added_py:
        top = a.split("/")[0] if "/" in a else "(kok)"
        mark = ""
        if top != "(kok)" and top not in prev_subsystems:
            mark = "  [YENI UST KLASOR - gerekce gerekli!]"
        print("    + %-50s (alt sistem: %s)%s" % (a, top, mark))
    print("    Kural: once ilgili scripte ekle; yeni alan kendi domain klasorunde acilir.")

    from engine.techdebt import twin_check
    twins = twin_check(root, ignore)
    added_set = set(added_py)
    existing = set(result["files"]) - added_set
    warns = []
    for group in twins:
        ma = [m for m in group if m.split(":")[0] in added_set]
        me = [m for m in group if m.split(":")[0] in existing]
        if ma and me:
            warns.append((ma, me))
    if warns:
        print("[KONTROL] Duplicate uyarisi (yeni kod mevcut koda benziyor - kontrol et):")
        for ma, me in warns[:10]:
            print("    yeni   : %s" % ", ".join(ma))
            print("      mevcut: %s" % ", ".join(me))
        if len(warns) > 10:
            print("    ... (%d grup daha)" % (len(warns) - 10))


def _run_pipeline(label, record_diff, _args=None):
    from engine.context import require_project

    root, config, ignore, data_dir = require_project(_project(_args))
    with project_write_lock(root):
        return _run_pipeline_locked(root, config, ignore, data_dir, label, record_diff, _args)


def _run_pipeline_locked(root, config, ignore, data_dir, label, record_diff, _args=None):
    from engine import scan as scan_mod, deps as deps_mod, api_surface as api_mod, usage as usage_mod
    from engine import diff as diff_mod, descriptions as desc_mod
    from engine import quality as quality_mod
    from reports import generate as gen

    devkit_dir = data_dir.parent
    use_cache = not getattr(_args, "no_cache", False) if _args else True

    result = scan_mod.run_scan(root, ignore, data_dir, use_cache)
    new_fp = {rel: f["sha256"] for rel, f in result["files"].items()}
    old_fp = diff_mod.load_fingerprint(data_dir) if record_diff else {}
    diff = diff_mod.compute_diff(old_fp, new_fp) if old_fp else {
        "added": sorted(new_fp), "deleted": [], "modified": [], "moved": []}

    desc_mod.migrate_descriptions(devkit_dir, diff["moved"])

    deps = deps_mod.run_deps(result)
    api = api_mod.run_api(result)
    usage = usage_mod.run_usage(root, result)
    quality = quality_mod.run_quality(result)
    _write_data(data_dir, result, deps, api, usage, quality)
    diff_mod.save_fingerprint(data_dir, result)

    gen.generate_all(root, config, data_dir, devkit_dir)

    from reports import state as state_mod
    state_mod.generate_state(root, config, data_dir, devkit_dir)

    if record_diff:
        _append_dev_log(devkit_dir, diff, label)

    s = result["stats"]
    print("[OK] %s tamamlandi" % label)
    print("  Dosya: %d (.py %d) | Satir: %d" % (s["total_files"], s["total_py"], s["total_lines"]))
    print("  Degisiklik: +%d -%d ~%d (modified %d)"
          % (len(diff["added"]), len(diff["deleted"]), len(diff["moved"]), len(diff["modified"])))
    for a in diff["added"][:20]:
        print("    + %s" % a)
    if len(diff["added"]) > 20:
        print("    ... (%d daha)" % (len(diff["added"]) - 20))
    for d in diff["deleted"][:20]:
        print("    - %s" % d)
    if len(diff["deleted"]) > 20:
        print("    ... (%d daha)" % (len(diff["deleted"]) - 20))
    for m in diff["moved"][:20]:
        print("    ~ %s -> %s" % (m[0], m[1]))
    if len(diff["moved"]) > 20:
        print("    ... (%d daha)" % (len(diff["moved"]) - 20))

    if old_fp:
        prev_subsystems = {k.split("/")[0] for k in old_fp if "/" in k}
        _report_new_code_checks(root, ignore, result, diff, prev_subsystems)
    return 0


def cmd_report(_args):
    from engine.context import require_project
    from reports import generate as gen
    root, config, ignore, data_dir = require_project(_project(_args))
    with project_write_lock(root):
        ok = gen.generate_all(root, config, data_dir, data_dir.parent)
        if not ok:
            print("[ERROR] data/scan.json yok. Once 'devkit sync' veya 'devkit rescan' calistirin.")
            return 1
        print("[OK] Raporlar uretildi: %s" % (data_dir.parent / "KB"))
    return 0


def cmd_sync(_args):
    return _run_pipeline("sync", True, _args)


def cmd_rescan(_args):
    return _run_pipeline("full rescan", True, _args)


def _log_entry(devkit_dir, title, body):
    from datetime import datetime
    p = devkit_dir / "DEVELOPMENT_LOG.md"
    if not p.exists():
        p.write_text(
            "# DEVELOPMENT_LOG\n\n"
            "(append-only changelog - history only; KB files always hold the current state)\n\n"
            "## Safe Delete Protocol\n"
            "When removing code (functions, classes, files), follow this protocol:\n"
            "1. **DeprecationWarning**: Add `@deprecated` decorator or `# DEPRECATED` comment\n"
            "2. **Wait period**: Minimum 1 week (7 days) before actual removal\n"
            "3. **Karar Matrisi**: Document decision with scoring (see below)\n"
            "4. **Archive**: Move to `archive/` folder instead of hard delete\n"
            "5. **Log entry**: Record in this log with decision rationale\n\n"
            "### Karar Matrisi (Decision Matrix) - Skorlama (0-100)\n"
            "| Kriter | Agirlik | Skor (0-10) | Not |\n"
            "|--------|---------|-------------|-----|\n"
            "| Cagri Sayisi (kac yerden cagrilir) | 30% | | |\n"
            "| Docstring var mi? | 20% | | |\n"
            "| Test coverage var mi? | 25% | | |\n"
            "| Son commit ne kadar eski? | 15% | | |\n"
            "| Guvenli alternatif var mi? | 10% | | |\n"
            "| **TOPLAM** | 100% | | |\n"
            "- **>= 70**: Guvenli silme/arsivle (Safe delete)\n"
            "- **40-69**: Dikkatli, deprecation warning + 2 hafta bekle\n"
            "- **< 40**: SILME, refactor/duzelt\n\n"
            "---\n",
            encoding="utf-8",
        )
    lines = ["", "## %s - %s" % (datetime.now().isoformat(timespec="seconds"), title), ""] + body
    with open(p, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def cmd_close_task(args):
    import json
    from datetime import datetime
    from engine.context import require_project
    from reports import state as state_mod

    root, config, ignore, data_dir = require_project(_project(args))
    devkit_dir = data_dir.parent

    name = args.name or input("Gorev adi: ").strip()
    summary = args.summary or input("Gorev ozeti: ").strip()
    if not name:
        if getattr(args, "json", False):
            print(json.dumps({"error": "missing_name", "message": "Gorev adi bos olamaz."}, ensure_ascii=False))
        else:
            print("[ERROR] Gorev adi bos olamaz.")
        return 1

    with project_write_lock(root):
        state = state_mod.load_state(devkit_dir)
        task = {"name": name, "date": datetime.now().isoformat(timespec="seconds"), "summary": summary}
        state["last_tasks"] = [task] + state.get("last_tasks", [])
        state["last_tasks"] = state["last_tasks"][:3]
        state["active_task"] = None
        state_mod.save_state(devkit_dir, state)
        state_mod.generate_state(root, config, data_dir, devkit_dir)

        _log_entry(devkit_dir, "task closed: %s" % name, ["- %s" % summary])

    if getattr(args, "json", False):
        print(json.dumps({"task_closed": name, "summary": summary}, ensure_ascii=False))
    else:
        print("[OK] Gorev kapatildi: %s" % name)
        print("  STATUS.yaml / CONTEXT.md / ISSUES.md / ENVIRONMENT.md guncellendi.")
    return 0


def cmd_find(args) -> int:
    import json as _json
    from engine.context import require_project
    root, config, ignore, data_dir = require_project(_project(args))
    sp = data_dir / "scan.json"
    if not sp.exists():
        print("[ERROR] Once tarama yapin: devkit scan")
        return 1
    data = _load_json(sp)
    name = args.symbol
    exact = []
    partial = []
    for rel, fdata in data["files"].items():
        for c in fdata.get("classes", []):
            if c["name"] == name:
                exact.append((rel, c["lineno"], "class", c["name"]))
            elif name in c["name"]:
                partial.append((rel, c["lineno"], "class", c["name"]))
            for m in c.get("methods", []):
                if m["name"] == name:
                    exact.append((rel, m["lineno"], "method", "%s.%s" % (c["name"], m["name"])))
                elif name in m["name"]:
                    partial.append((rel, m["lineno"], "method", "%s.%s" % (c["name"], m["name"])))
        for fn in fdata.get("functions", []):
            if fn["name"] == name:
                exact.append((rel, fn["lineno"], "function", fn["name"]))
            elif name in fn["name"]:
                partial.append((rel, fn["lineno"], "function", fn["name"]))
    rows = exact if exact else partial
    if getattr(args, "json", False):
        out = [{"file": r[0], "line": r[1], "kind": r[2], "symbol": r[3]} for r in sorted(rows)]
        print(_json.dumps({"symbol": name, "count": len(out), "results": out}, indent=2, ensure_ascii=False))
        return 0
    if not rows:
        print("[NOT FOUND] Sembol bulunamadi: %s" % name)
        return 0
    print("Sembol: %s  (%d eslesme)" % (name, len(rows)))
    for rel, line, kind, sym in sorted(rows):
        print("  %-8s %-46s %s:%s" % (kind, sym, rel, line))
    return 0


def cmd_outline(args) -> int:
    import json as _json
    from engine.context import require_project
    root, config, ignore, data_dir = require_project(_project(args))
    sp = data_dir / "scan.json"
    if not sp.exists():
        print("[ERROR] Once tarama yapin: devkit scan")
        return 1
    data = _load_json(sp)
    files = data["files"]
    rel = args.file
    if rel not in files:
        matches = [k for k in files if k == rel or k.endswith("/" + rel)]
        if len(matches) == 1:
            rel = matches[0]
        elif len(matches) > 1:
            if getattr(args, "json", False):
                print(_json.dumps({"error": "ambiguous", "matches": matches}, indent=2, ensure_ascii=False))
                return 1
            print("[BULANIK] Birden fazla dosya eslesti:")
            for m in matches:
                print("   ", m)
            return 1
        else:
            print("[NOT FOUND] Dosya bulunamadi: %s" % args.file)
            return 1
    fdata = files[rel]
    if getattr(args, "json", False):
        print(_json.dumps({"file": rel, "data": fdata}, indent=2, ensure_ascii=False))
        return 0
    print("Dosya: %s (%d satir)" % (rel, fdata["lines"]))
    if fdata.get("doc"):
        print("  Ozet: %s" % fdata["doc"])
    for fn in fdata.get("functions", []):
        print("  fn   %-40s %s-%s %s" % (fn["name"], fn["lineno"], fn["end_lineno"], fn["sig"]))
    for c in fdata.get("classes", []):
        print("  cls  %-40s %s-%s" % (c["name"], c["lineno"], c["end_lineno"]))
        for m in c.get("methods", []):
            print("       def %-36s %s-%s %s" % (m["name"], m["lineno"], m["end_lineno"], m["sig"]))
    return 0


def cmd_impact(args) -> int:
    import json as _json
    from engine.context import require_project
    from engine.impact import run_impact
    root, config, ignore, data_dir = require_project(_project(args))
    if not (data_dir / "deps.json").exists():
        print("[ERROR] Once tarama yapin: devkit scan")
        return 1
    r = run_impact(data_dir, args.file)
    if getattr(args, "json", False):
        print(_json.dumps(r, indent=2, ensure_ascii=False))
        return 0
    print("Dosya: %s" % r["file"])
    if not r.get("found"):
        print("[WARN] Dosya projede bulunamadi (tam yol verin veya devkit scan calistirin).")
        return 0
    print("  Bunu import edenler (etkilenecekler): %d" % len(r["dependents"]))
    for d in r["dependents"]:
        print("    -", d)
    print("  Bu dosyanin bagimli olduklari: %d" % len(r["dependencies"]))
    for d in r["dependencies"]:
        print("    -", d)
    return 0


def cmd_check(_args) -> int:
    import json
    from engine.context import require_project
    from engine.health import run_health
    root, config, ignore, data_dir = require_project(_project(_args))
    result = run_health(root, config, ignore, data_dir)
    s = result["summary"]
    is_json = getattr(_args, "json", False)
    if is_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("[HEALTH] ok=%d fail=%d" % (s["ok"], s["fail"]))
        if s.get("note"):
            print("  [UYARI] " + s["note"])
        for sub, r in sorted(result["by_subsystem"].items()):
            lines = r.get("lines", [])
            fails = [l for l in lines if l.startswith("FAIL")]
            oks = [l for l in lines if l.startswith("OK")]
            print("  %-20s %d modul (ok=%d, hata=%d)" % (sub, len(lines), len(oks), len(fails)))
            for f in fails:
                print("       " + f)
    with project_write_lock(root):
        (data_dir / "health.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

        from reports import state as state_mod
        state_mod.generate_state(root, config, data_dir, data_dir.parent)
    return 0


def cmd_desc(args):
    import json
    from engine.context import require_project
    from engine.descriptions import load_descriptions, save_descriptions
    root, config, ignore, data_dir = require_project(_project(args))
    devkit_dir = data_dir.parent
    data = load_descriptions(devkit_dir)

    if args.path == "list":
        if getattr(args, "json", False):
            print(json.dumps(data, ensure_ascii=False))
        else:
            if not data:
                print("(bos)")
            for k in sorted(data):
                print("  %s: %s" % (k, data[k]))
        return 0

    if args.text:
        data[args.path] = " ".join(args.text)
        with project_write_lock(root):
            save_descriptions(devkit_dir, data)
        if getattr(args, "json", False):
            print(json.dumps({args.path: data[args.path]}, ensure_ascii=False))
        else:
            print("[OK] %s -> %s" % (args.path, data[args.path]))
    else:
        if args.path in data:
            if getattr(args, "json", False):
                print(json.dumps({args.path: data[args.path]}, ensure_ascii=False))
            else:
                print("%s: %s" % (args.path, data[args.path]))
        else:
            if getattr(args, "json", False):
                print(json.dumps({"error": "not_found", "path": args.path}, ensure_ascii=False))
            else:
                print("(tanim yok) %s" % args.path)
    return 0


def cmd_techdebt(_args) -> int:
    import json
    import sys
    from engine.context import require_project
    from engine.techdebt import run_techdebt
    root, config, ignore, data_dir = require_project(_project(_args))
    result = run_techdebt(root, ignore)
    with project_write_lock(root):
        (data_dir / "techdebt.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    if getattr(_args, "json", False):
        # Use ensure_ascii=True for stdout to avoid encoding issues
        sys.stdout.write(json.dumps(result, indent=2, ensure_ascii=True) + "\n")
        return 0
    print("[OK] Teknik borc taramasi tamamlandi")
    print("  Twin gruplar: %d (detayli %d)" % (len(result["twin_groups"]), len(result.get("twin_detailed", []))))
    print("  Fix/TODO etiketleri: %d" % len(result["fix_tags"]))
    print("  Callgraph: %d dosya" % len(result.get("callgraph", {})))
    return 0


def cmd_changed(_args) -> int:
    import json
    from engine.changes import run_changed
    from engine.context import require_project
    root, config, ignore, data_dir = require_project(_project(_args))
    devkit_dir = data_dir.parent
    result = run_changed(root, ignore, devkit_dir)
    if getattr(_args, "json", False):
        sys.stdout.write(json.dumps(result, indent=2, ensure_ascii=True) + "\n")
        return 0
    n_sym = sum(len(v.get("symbols", [])) for v in result["by_file"].values())
    print("[CHANGED] %s | dosyalar: %d | fonksiyon/class: %d"
          % (result["mode"], len(result["changed_files"]), n_sym))
    for rel in sorted(result["by_file"]):
        info = result["by_file"][rel]
        syms = info.get("symbols", [])
        if info.get("entire_file"):
            print("  %s  (TUM DOSYA YENi, %d sembol)" % (rel, len(syms)))
        else:
            print("  %s  (%d degisen satir, %d sembol)" % (rel, len(info.get("new_lines", [])), len(syms)))
        for s in syms[:20]:
            mark = "  [YENI DOSYA]" if s.get("new") else ""
            print("      %s  %s:%s%s" % (s["symbol"], rel, s["line"], mark))
        if len(syms) > 20:
            print("      ... +%d sembol daha" % (len(syms) - 20))
    if result["deleted_files"]:
        print("  [SILINEN] " + ", ".join(result["deleted_files"]))
    if result.get("note"):
        print("  [NOT] " + result["note"])
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="devkit",
        description="AI Development Support System",
    )
    sub = parser.add_subparsers(dest="cmd")

    p_init = sub.add_parser("init", help="setup wizard for a new project")
    p_init.add_argument("--ai-driven", action="store_true", help="AI-driven programmatic setup (non-interactive)")
    p_init.add_argument("--project-root", help="Project root directory (required for --ai-driven)")
    p_init.add_argument("--project-name", help="Project name (defaults to folder name)")
    p_init.add_argument("--env-path", help="Python executable path")
    p_init.add_argument("--project-info", help="Project description")
    p_init.add_argument("--project-rules", help="Project-specific rules")
    p_init.add_argument("--ignore-dirs", nargs="*", default=[], help="Directories to ignore")
    p_init.add_argument("--big-file-threshold", type=int, default=800, help="Big file threshold in lines")
    p_init.add_argument("--output-warn-mb", type=int, default=1, help="Output warning limit in MB")
    p_init.add_argument("--output-block-mb", type=int, default=5, help="Output block limit in MB")
    p_init.add_argument("--auto-confirm", action="store_true", help="Skip confirmation prompt (for --ai-driven)")
    p_init.add_argument("--json", action="store_true", help="output as JSON")
    p_init.set_defaults(func=cmd_init)

    p_gui = sub.add_parser("gui", help="launch the Tkinter GUI")
    p_gui.set_defaults(func=cmd_gui)

    p_list = sub.add_parser("list", help="list registered projects")
    p_list.add_argument("--json", action="store_true", help="output as JSON")
    p_list.set_defaults(func=cmd_list)

    p_current = sub.add_parser("current", help="show the active (or given) project")
    p_current.add_argument("--json", action="store_true", help="output as JSON")
    _add_project_arg(p_current)
    p_current.set_defaults(func=cmd_current)

    p_help = sub.add_parser("help", help="usage guide")
    p_help.set_defaults(func=cmd_help)

    p_select = sub.add_parser("select", help="set the active project")
    p_select.add_argument("name", nargs="?", default=None)
    p_select.add_argument("--json", action="store_true", help="output as JSON")
    p_select.set_defaults(func=cmd_select)

    p_scan = sub.add_parser("scan", help="full structural scan (data only)")
    p_scan.add_argument("--json", action="store_true", help="output scan stats as JSON")
    p_scan.add_argument("--no-cache", action="store_true", help="disable AST cache")
    _add_project_arg(p_scan)
    p_scan.set_defaults(func=cmd_scan)

    p_scaffold = sub.add_parser("scaffold", help="ensure .gitignore/pyproject.toml/.git exist")
    p_scaffold.add_argument("--json", action="store_true", help="output as JSON")
    _add_project_arg(p_scaffold)
    p_scaffold.set_defaults(func=cmd_scaffold)

    p_report = sub.add_parser("report", help="render KB reports from data")
    _add_project_arg(p_report)
    p_report.set_defaults(func=cmd_report)

    p_sync = sub.add_parser("sync", help="incremental update (scan + diff + report + log)")
    p_sync.add_argument("--no-cache", action="store_true", help="disable AST cache")
    _add_project_arg(p_sync)
    p_sync.set_defaults(func=cmd_sync)

    p_rescan = sub.add_parser("rescan", help="full fresh scan + report + log")
    p_rescan.add_argument("--no-cache", action="store_true", help="disable AST cache")
    _add_project_arg(p_rescan)
    p_rescan.set_defaults(func=cmd_rescan)

    p_close = sub.add_parser("close-task", help="task close protocol")
    p_close.add_argument("--name", default=None)
    p_close.add_argument("--summary", default=None)
    p_close.add_argument("--json", action="store_true", help="output as JSON")
    _add_project_arg(p_close)
    p_close.set_defaults(func=cmd_close_task)

    p_find = sub.add_parser("find", help="locate a symbol (file:line)")
    p_find.add_argument("symbol")
    p_find.add_argument("--json", action="store_true", help="output as JSON")
    _add_project_arg(p_find)
    p_find.set_defaults(func=cmd_find)

    p_outline = sub.add_parser("outline", help="print a file outline (line ranges)")
    p_outline.add_argument("file")
    p_outline.add_argument("--json", action="store_true", help="output as JSON")
    _add_project_arg(p_outline)
    p_outline.set_defaults(func=cmd_outline)

    p_impact = sub.add_parser("impact", help="change impact for a file")
    p_impact.add_argument("file")
    p_impact.add_argument("--json", action="store_true", help="output as JSON")
    _add_project_arg(p_impact)
    p_impact.set_defaults(func=cmd_impact)

    p_check = sub.add_parser("check", help="runtime import health check")
    p_check.add_argument("--json", action="store_true", help="output as JSON")
    _add_project_arg(p_check)
    p_check.set_defaults(func=cmd_check)

    p_techdebt = sub.add_parser("techdebt", help="technical debt scan")
    p_techdebt.add_argument("--json", action="store_true", help="output as JSON")
    _add_project_arg(p_techdebt)
    p_techdebt.set_defaults(func=cmd_techdebt)

    p_desc = sub.add_parser("desc", help="set/show a file/folder description")
    p_desc.add_argument("path")
    p_desc.add_argument("text", nargs="*", default=[])
    p_desc.add_argument("--json", action="store_true", help="output as JSON")
    _add_project_arg(p_desc)
    p_desc.set_defaults(func=cmd_desc)

    p_changed = sub.add_parser("changed", help="show files/functions changed since last commit/scan (git diff + AST)")
    p_changed.add_argument("--json", action="store_true", help="output as JSON")
    _add_project_arg(p_changed)
    p_changed.set_defaults(func=cmd_changed)

    args = parser.parse_args(argv)
    if not getattr(args, "cmd", None):
        parser.print_help()
        return 0
    if getattr(args, "json", False):
        # machine output: suppress the [PROJE] banner (it already goes to
        # stderr, but keep even stderr clean for strict JSON pipelines)
        try:
            import engine.context as _ctx
            _ctx.quiet = True
        except ImportError:
            pass
    try:
        return args.func(args)
    except DevkitError as e:
        print(e, file=sys.stderr)
        return 1
    except (RegistryLockError, OSError, TimeoutError) as e:
        print("[HATA] %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
