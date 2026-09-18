#!/usr/bin/env python3
"""
devkit-bootstrap.py — AI Self-Bootstrap Automation Script
=========================================================

Bu script, REHBER.md §10 "AI Kendi Kendini Hazırlama Protokolü"nü otomatikleştirir.
AI bu scripti çalıştırarak (veya adım adım komutları kopyalayarak) projeyi
anlayıp "hazır durum"a gelir.

Kullanım:
    python devkit-bootstrap.py                    # Aktif proje için
    python devkit-bootstrap.py --project MyProj   # Belirli proje için
    python devkit-bootstrap.py --json-only        # Sadece JSON çıktılar (hızlı)
    python devkit-bootstrap.py --help             # Yardım

Çıktı: Terminalde protokol adımları + özet rapor.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def run_cmd(cmd, capture=True, cwd=None):
    """Komut çalıştır, (success, stdout, stderr) döndür."""
    if cmd.startswith("python "):
        # ciplak "python" PATH'e bagimli; bootstrap'i calistiran yorumlayici kullan
        cmd = f'"{sys.executable}"' + cmd[len("python"):]
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=capture, text=True, cwd=cwd, timeout=300
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "TIMEOUT"
    except Exception as e:
        return False, "", str(e)


def print_section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def print_step(step, desc):
    print(f"  [{step}] {desc}")


def read_file(path):
    try:
        return Path(path).read_text(encoding="utf-8")
    except Exception:
        return ""


def main():
    parser = argparse.ArgumentParser(description="DEVKIT AI Self-Bootstrap")
    parser.add_argument("--project", help="Proje adı (registry'den)")
    parser.add_argument("--json-only", action="store_true", help="Sadece JSON adımları")
    parser.add_argument("--skip-rescan", action="store_true", help="rescan/sync atla (KB varsayılan)")
    parser.add_argument("--auto", action="store_true", help="Otomatik mod (prompt yok, sadece çıktı)")
    parser.add_argument("--cwd", help="Çalışma dizini (varsayılan: devkit klasörü)")
    args = parser.parse_args()

    orig_cwd = Path.cwd()
    devkit_dir = Path(args.cwd) if args.cwd else Path(__file__).resolve().parent
    os.chdir(devkit_dir)
    devkit_py = str(devkit_dir / "devkit.py")

    # Acik verilen projeyi her komuta ta (aktif projeye bagimlilik kalksin):
    # boylece iki AI farkli projelerde paralel surec baslatabilir.
    proj_arg = f' --project "{args.project}"' if args.project else ""

    # Proje belirle (paralel AI guvenli: global "aktif proje" isaretcisine
    # DOKUNMA). Cozumleme: acik --project > cagrilan klasor (cwd) > aktif.
    if args.project:
        ok, out, _ = run_cmd(f"python devkit.py current{proj_arg}")
        if not ok or "bulunamadi" in out.lower():
            print(f"[HATA] Proje bulunamadi: {args.project}")
            return 1
    else:
        ok, out, _ = run_cmd(f'python "{devkit_py}" current', cwd=str(orig_cwd))
        if not ok or "proje secilmedi" in out.lower():
            print("[HATA] Proje cozumlenemedi. --project ile belirtin veya proje klasorunden calistirin.")
            return 1
        name = out.split("->")[0].strip()
        proj_arg = f' --project "{name}"'
        print(f"[BILGI] Proje cwd'den cozuldu: {name}")

    # Proje kökünü al
    ok, out, _ = run_cmd(f"python devkit.py current{proj_arg}")
    raw = out.split("->")[-1].strip() if "->" in out else ""
    project_root = raw.split("  (kaynak")[0].strip()
    if not project_root:
        print("[HATA] Proje kökü bulunamadı.")
        return 1

    devkit_proj_dir = Path(project_root) / ".devkit"
    kb_dir = devkit_proj_dir / "KB"

    print_section("DEVKIT AI SELF-BOOTSTRAP BAŞLIYOR")
    print(f"Proje kökü: {project_root}")
    print(f".devkit:    {devkit_proj_dir}")

    # === AŞAMA 1: KB Üret / Güncelle ===
    if not args.skip_rescan:
        print_section("AŞAMA 1: Bilgi Tabanını Üret / Güncelle (rescan)")
        print_step("1", f"python devkit.py rescan{proj_arg}")
        ok, out, err = run_cmd(f"python devkit.py rescan{proj_arg}")
        print(out or err)
        if not ok:
            print("[UYARI] rescan başarısız, sync deneniyor...")
            ok, out, err = run_cmd(f"python devkit.py sync{proj_arg}")
            print(out or err)
    else:
        print_section("AŞAMA 1: ATLANDI (--skip-rescan)")

    # === AŞAMA 2: Sayısal Model (JSON) ===
    print_section("AŞAMA 2: Sayısal Model — JSON Çıktılar")
    for cmd_name, cmd in [
        ("scan", f"python devkit.py scan --json{proj_arg}"),
        ("check", f"python devkit.py check --json{proj_arg}"),
        ("techdebt", f"python devkit.py techdebt --json{proj_arg}"),
    ]:
        print_step(f"2.{['scan','check','techdebt'].index(cmd_name)+1}", cmd)
        ok, out, err = run_cmd(cmd)
        if ok and out:
            try:
                data = json.loads(out)
                # Özet bas
                if cmd_name == "scan":
                    s = data.get("stats", {})
                    print(f"    Dosya: {s.get('total_py',0)} .py, {s.get('total_non_py',0)} diger | Satir: {s.get('total_lines',0)} | Sinif: {s.get('total_classes',0)} | Fonksiyon: {s.get('total_functions',0)}")
                    print(f"    Subsistemler: {', '.join(s.get('subsystems',[]))}")
                elif cmd_name == "check":
                    s = data.get("summary", {})
                    print(f"    Health: OK={s.get('ok',0)} FAIL={s.get('fail',0)}")
                    for sub, r in data.get("by_subsystem", {}).items():
                        fails = [l for l in r.get("lines",[]) if l.startswith("FAIL")]
                        if fails:
                            print(f"    {sub}: {len(fails)} hata")
                elif cmd_name == "techdebt":
                    print(f"    Twin gruplar: {len(data.get('twin_groups',[]))}")
                    print(f"    Fix/TODO tags: {len(data.get('fix_tags',[]))}")
                    cg = data.get("callgraph", {})
                    print(f"    Callgraph: {len(cg)} dosya")
            except json.JSONDecodeError:
                print(f"    [JSON parse hatası]")
        else:
            print(f"    [HATA] {err}")

    if args.json_only:
        print_section("JSON-ONLY MODU — TAMAMLANDI")
        return 0

    # === AŞAMA 3: Mimari Haritası (Markdown) ===
    print_section("AŞAMA 3: Mimari Haritası — Markdown Raporlar")
    for fname in ["QUICKREF.md", "PROJECT_MAP.md", "ARCHITECTURE.md", "DEPENDENCIES.md"]:
        fpath = kb_dir / fname
        print_step("3", f"Okunuyor: {fname}")
        content = read_file(fpath)
        if content:
            lines = content.splitlines()
            print(f"    ({len(lines)} satir) — İlk 5 satir:")
            for l in lines[:5]:
                print(f"      {l}")
            if len(lines) > 5:
                print(f"      ... ({len(lines)-5} satir daha)")
        else:
            print(f"    [YOK VEYA BOS] — {fpath}")

    # === AŞAMA 4: Runtime Akışları ===
    print_section("AŞAMA 4: Runtime Akışları — meta.yaml + flows")
    meta_path = devkit_proj_dir / "meta.yaml"
    meta_content = read_file(meta_path)
    print_step("4.1", "meta.yaml")
    if meta_content:
        lines = meta_content.splitlines()
        print(f"    ({len(lines)} satir) — Anahtarlar:")
        for l in lines:
            if l.strip() and not l.startswith("#") and ":" in l and not l.strip().startswith("-"):
                key = l.split(":")[0].strip()
                if key and not key.startswith(" "):
                    print(f"      {key}")
    else:
        print(f"    [YOK VEYA BOS] — {meta_path}")
        print(f"    >>> ACIL: templates/meta.example.yaml kopyalayip doldurun!")

    flows_dir = kb_dir / "flows"
    if flows_dir.exists():
        for f in sorted(flows_dir.glob("*.md")):
            content = read_file(f)
            if content:
                print_step("4.2+", f"flows/{f.name} ({len(content.splitlines())} satir)")

    # === AŞAMA 5: Derinlemesine (Subsystems) ===
    print_section("AŞAMA 5: Subsystem Detayları (KB/subsystems/)")
    subs_dir = kb_dir / "subsystems"
    if subs_dir.exists():
        for f in sorted(subs_dir.glob("*.md")):
            content = read_file(f)
            if content:
                lines = content.splitlines()
                print(f"  - {f.name}: {len(lines)} satir")
                # Quality satırı ara
                for l in lines:
                    if "Quality avg" in l or "KRITIK" in l:
                        print(f"      >>> {l.strip()}")
    else:
        print("  [YOK] — subsystems klasörü bulunamadi")

    # === AŞAMA 6: Kurallar ve Bağlam ===
    print_section("AŞAMA 6: Kurallar ve Baglam")
    for fname in ["PROJECT_RULES.md", "STATUS.yaml", "CONTEXT.md", "ISSUES.md"]:
        fpath = devkit_proj_dir / fname
        content = read_file(fpath)
        print_step("6", f"{fname}")
        if content:
            lines = content.splitlines()
            print(f"    ({len(lines)} satir)")
            if fname == "ISSUES.md":
                # Kritikler
                for l in lines:
                    if "[KRITIK]" in l or "FAIL" in l:
                        print(f"      >>> {l.strip()}")
        else:
            print(f"    [YOK VEYA BOS]")

    # === ÖZET RAPOR ===
    print_section("ÖZET RAPOR — HAZIR DURUM")
    # Scan stats
    scan_path = devkit_proj_dir / "data" / "scan.json"
    if scan_path.exists():
        scan = json.loads(read_file(scan_path))
        s = scan.get("stats", {})
        print(f"Proje: {scan.get('project_root', '?')}")
        print(f"  Python dosyalari: {s.get('total_py', 0)} | Toplam satir: {s.get('total_lines', 0)}")
        print(f"  Siniflar: {s.get('total_classes', 0)} | Modul fonksiyonlari: {s.get('total_functions', 0)}")
        print(f"  Subsistemler ({len(s.get('subsystems', []))}): {', '.join(s.get('subsystems', []))}")

    # Health
    health_path = devkit_proj_dir / "data" / "health.json"
    if health_path.exists():
        health = json.loads(read_file(health_path))
        s = health.get("summary", {})
        print(f"Runtime Health: OK={s.get('ok',0)} FAIL={s.get('fail',0)}")

    # Quality
    quality_path = devkit_proj_dir / "data" / "quality.json"
    if quality_path.exists():
        quality = json.loads(read_file(quality_path))
        q = quality.get("summary", {})
        print(f"Kalite: Avg {q.get('avg_toplam', '?')}/40 | Issues: {q.get('total_issues',0)} (Kritik: {q.get('kritik_issues',0)})")

    # Techdebt
    td_path = devkit_proj_dir / "data" / "techdebt.json"
    if td_path.exists():
        td = json.loads(read_file(td_path))
        print(f"Teknik Borç: Twin gruplar={len(td.get('twin_groups',[]))} | Fix tags={len(td.get('fix_tags',[]))} | Callgraph dosya={len(td.get('callgraph',{}))}")

    # Meta.yaml durumu
    if meta_content:
        print("meta.yaml: VAR (doldurulmus)")
    else:
        print("meta.yaml: YOK/BOŞ — MUTLAKA DOLDURULMALI (templates/meta.example.yaml)")

    print("\n[SONUC] Bootstrap tamamlandi. Artik proje uzerinde guvenli calisabilirsiniz.")
    print("Sonraki adim: Kullaniciya ozet raporu ver, hangi alanda calisacaginizi sorun.")
    return 0


if __name__ == "__main__":
    sys.exit(main())