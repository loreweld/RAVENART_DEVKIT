#!/usr/bin/env python3
"""
discovery.py - otomatik kesif analizleri (statik, LLM gerektirmez).

Hedef: meta.yaml yazimindan once AI'ya proje yapisi hakkinda somut ipuclari vermek:
 - hub moduller (en cok bagimlilik alan)
 - otomatik katman tespiti (alt-sistemler arasi bagimlilik yonu)
 - polymorphic / base-class haritasi (kalitim zincirleri)
 - entry-point dosyalari
 - otomatik meta.draft.yaml uretimi (AI duzenler, sifirdan baslamaz)
"""

import json
from collections import defaultdict
from pathlib import Path


def _collect_base_classes(scan_files: dict) -> list:
    """[ {base, file, line, subclasses: [{file,name,line}]}, ... ]  (max 50)"""
    name_map = defaultdict(list)
    for rel, fdata in scan_files.items():
        for cls in fdata.get("classes", []):
            name_map[cls["name"]].append((rel, cls["lineno"]))

    base_sub_map = defaultdict(list)
    for rel, fdata in scan_files.items():
        for cls in fdata.get("classes", []):
            for b in cls.get("bases", []):
                bname = b.split(".")[-1]
                for bfile, bline in name_map.get(bname, []):
                    base_sub_map[(bfile, bname, bline)].append(
                        {"file": rel, "name": cls["name"], "line": cls["lineno"]})

    items = sorted(base_sub_map.items(), key=lambda kv: -len(kv[1]))[:50]
    return [
        {"file": bf, "name": bn, "line": bl, "subclasses": subs}
        for (bf, bn, bl), subs in items if len(subs) >= 2
    ]


def build_insights(scan: dict, deps_data: dict, devkit_dir: Path) -> dict:
    """Return a dict consumed by INSIGHTS.md and meta.draft.yaml generation."""
    graph = deps_data.get("graph", {})
    files = scan.get("files", {})

    # --- hub modules (most used by others, in-degree) ---
    reverse = deps_data.get("reverse", {})
    in_deg = {f: len(targets) for f, targets in reverse.items()}
    hubs = [{"file": f, "dependents": d}
            for f, d in sorted(in_deg.items(), key=lambda kv: -kv[1]) if d > 0][:15]

    # --- entry points ---
    entry_files = scan.get("stats", {}).get("entry_files", [])
    if not entry_files:
        entry_files = sorted(
            rel for rel, f in files.items()
            if f.get("is_entry") or ("main" in [fn["name"] for fn in f.get("functions", [])]
                                      and "/" not in rel))

    # --- subsystem layering ---
    sub_outgoing = defaultdict(set)
    for f, targets in graph.items():
        sf = f.split("/")[0]
        for t in targets:
            st = t.split("/")[0]
            if sf != st:
                sub_outgoing[sf].add(st)
    sub_imported_by = defaultdict(set)
    for s, targets in sub_outgoing.items():
        for t in targets:
            sub_imported_by[t].add(s)

    subsystem_layers = []
    subs = scan.get("stats", {}).get("subsystems", [])
    for i, s in enumerate(sorted(subs, key=lambda s: (-len(sub_imported_by.get(s, set())), len(sub_outgoing.get(s, set()))))):
        subsystem_layers.append({
            "subsystem": s,
            "level": i,
            "imported_by": len(sub_imported_by.get(s, set())),
            "imports_others": len(sub_outgoing.get(s, set())),
        })

    return {
        "hubs": hubs,
        "entry_files": entry_files,
        "base_classes": _collect_base_classes(files),
        "subsystem_layer": subsystem_layers,
    }


def generate_insights_md(insights: dict) -> str:
    hubs = insights.get("hubs", [])
    entries = insights.get("entry_files", [])
    bases = insights.get("base_classes", [])
    layers = insights.get("subsystem_layer", [])

    lines = [
        "# INSIGHTS",
        "",
        "Otomatik kesif sonuclari (LLM gerektirmez).",
        "",
        "## Hub moduller (en cok bagimlilik alan)",
        "",
    ]
    if hubs:
        for h in hubs[:12]:
            lines.append("- `%s`  (%d dosya tarafindan kullaniliyor)" % (h["file"], h["dependents"]))
    else:
        lines.append("- (yeterli bagimlilik verisi yok)")
    lines += ["", "## Entry-point dosyalar", ""]
    if entries:
        for e in entries:
            lines.append("- `%s`" % e)
    else:
        lines.append("- (bulunamadi)")
    lines += ["", "## Katman yapisi (subsystem)", "",
              "Seviye 0 = digerleri tarafindan en cok kullanilan (root/kutuphane); buyuk seviye = ust katman (UI/giris)."]
    if layers:
        for l in layers:
            lines.append("- **%s**  level %d  (kullanan %d alt-sistem, bagimli oldugu %d)" %
                         (l["subsystem"], l["level"], l["imported_by"], l["imports_others"]))
    else:
        lines.append("- (yeterli bagimlilik verisi yok)")
    lines += ["", "## Base-class / polymorphic harita", "",
              "En az 2 alt sinifi olan siniflar."]
    if bases:
        for b in bases[:20]:
            subs = ", ".join("%s (%s:%s)" % (s["name"], s["file"], s["line"]) for s in b["subclasses"][:5])
            lines.append("- `%s`  tanim: %s:%s  alt-siniflar: %s" % (b["name"], b["file"], b["line"], subs))
        if len(bases) > 20:
            lines.append("- ... +%d tane daha" % (len(bases) - 20))
    else:
        lines.append("- (bulunamadi)")

    return "\n".join(lines) + "\n"


def generate_meta_draft(scan: dict, insights: dict) -> dict:
    """Yarim-otomatik meta.yaml iskeleti uret. AI buna bakarak doldurur."""
    subs = scan.get("stats", {}).get("subsystems", [])
    layers = insights.get("subsystem_layer", [])
    entries = insights.get("entry_files", [])
    bases = insights.get("base_classes", [])
    hubs = insights.get("hubs", [])

    arch_layers = []
    max_level = max((ll["level"] for ll in layers), default=-1)
    for l in layers[:10]:
        role = "UI/giris katmani" if l["level"] == max_level \
            else "Kutuphane/ortak modul" if l["imports_others"] <= 1 \
            else "Ust-yapi/konfigurasyon" if l["imported_by"] == 0 \
            else "Servis/is mantigi"
        arch_layers.append({
            "name": l["subsystem"],
            "responsibility": role,
            "level": l["level"],
        })

    patterns = []
    for b in bases[:8]:
        patterns.append({
            "name": "inheritance_%s" % b["name"],
            "type": "inheritance",
            "note": "Temel sinif %s -> %d alt sinif (%s)" % (
                b["name"], len(b["subclasses"]),
                ", ".join(s["name"] for s in b["subclasses"][:3])),
        })

    return {
        "_auto_generated": True,
        "_note": "Bu dosya otomatik uretilmistir. AI bunu starter olarak duzenlemeli; yorumlari silip calistigi gibi birakmamalidir.",
        "architecture": {"layers": arch_layers},
        "entry_points": [{"name": Path(e).stem, "file": e, "type": "main"} for e in entries[:10]],
        "design_patterns": patterns,
        "dependencies": {
            "hub_files": [h["file"] for h in hubs[:10]],
            "note": "Hub dosyalari refactor icin oncelikli hedef; buyuk degisiklikler onlari etkiler.",
        },
    }


def write_discovery_output(devkit_dir: Path, scan: dict, deps_data: dict):
    """INSIGHTS.md ve meta.draft.yaml yaz; doner insights dict."""
    insights = build_insights(scan, deps_data, devkit_dir)

    kb_dir = devkit_dir / "KB"
    kb_dir.mkdir(parents=True, exist_ok=True)
    (kb_dir / "INSIGHTS.md").write_text(generate_insights_md(insights), encoding="utf-8")

    draft = generate_meta_draft(scan, insights)
    # Mevcut bir meta.draft.yaml'i asla ezme - AI duzenlemis olabilir.
    draft_path = devkit_dir / "meta.draft.yaml"
    if not draft_path.exists():
        draft_path.write_text(
            "# Otomatik uretim - AI bu dosyayi duzenlemeli\n"
            + json.dumps(draft, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8")
    return insights