#!/usr/bin/env python3
"""
gui.py - Tkinter GUI for DEVKIT.

Stdlib-only (Tkinter), PyInstaller-friendly: frozen-safe paths are handled in
common.py, and every action calls the same in-process functions as the CLI.

Launch:
    python gui.py            (or)   python devkit.py gui
"""

import contextlib
import io
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import devkit
from common import DEFAULT_IGNORE_DIRS, active_project_name, load_registry, save_registry, set_active_project
from engine.context import DevkitError


class DevkitGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("DEVKIT - AI Gelistirme Destek Sistemi")
        self.root.geometry("920x680")
        self.root.minsize(760, 520)
        self.project_var = tk.StringVar()
        self.folder_var = tk.StringVar()
        self.buttons = []
        self._build_ui()
        self.refresh_projects()

    def _build_ui(self):
        top = ttk.Frame(self.root, padding=(12, 10, 12, 4))
        top.pack(fill="x")
        ttk.Label(top, text="Aktif Proje:").pack(side="left")
        self.combo = ttk.Combobox(top, textvariable=self.project_var, state="readonly", width=42)
        self.combo.pack(side="left", padx=6)
        self.combo.bind("<<ComboboxSelected>>", self._on_select)
        ttk.Button(top, text="Yeni Proje", command=self._on_new_project).pack(side="left", padx=6)
        ttk.Button(top, text="Proje Kaldir", command=self._on_remove_project).pack(side="left", padx=6)
        ttk.Button(top, text="Yardim", command=self._on_help).pack(side="right")

        acts = ttk.LabelFrame(self.root, text="Islemler", padding=10)
        acts.pack(fill="x", padx=12, pady=6)
        for text, fn in [
            ("Hizli Guncelle (sync)", lambda: self._run(devkit.cmd_sync, self._project_snapshot())),
            ("Taramayi Guncelle (tam)", lambda: self._run(devkit.cmd_rescan, self._project_snapshot())),
            ("Raporlari Uret", lambda: self._run(devkit.cmd_report, self._project_snapshot())),
            ("Saglik Kontrolu", lambda: self._run(devkit.cmd_check, self._project_snapshot())),
            ("Teknik Borc", lambda: self._run(devkit.cmd_techdebt, self._project_snapshot())),
        ]:
            b = ttk.Button(acts, text=text, command=fn)
            b.pack(side="left", padx=4)
            self.buttons.append(b)

        man = ttk.LabelFrame(self.root, text="Manuel Araclar (tek seferlik - herhangi bir klasor)", padding=10)
        man.pack(fill="x", padx=12, pady=6)
        ttk.Entry(man, textvariable=self.folder_var, width=58).pack(side="left")
        ttk.Button(man, text="Klasor Sec", command=self._on_pick_folder).pack(side="left", padx=4)
        for text, fn in [
            ("Yapi", self._man_scan),
            ("Bagimlilik", self._man_deps),
            ("Teknik Borc", self._man_techdebt),
        ]:
            b = ttk.Button(man, text=text, command=fn)
            b.pack(side="left", padx=4)
            self.buttons.append(b)

        self.status = ttk.Label(self.root, text="Hazir.", padding=(12, 2))
        self.status.pack(fill="x")

        out = ttk.LabelFrame(self.root, text="Cikti", padding=4)
        out.pack(fill="both", expand=True, padx=12, pady=(2, 4))

        ttk.Label(self.root, text="© 2026 İlker Can Karagülle · Loreweld AI (loreweld.ai)",
                  foreground="#666666", padding=(12, 0, 12, 6)).pack(fill="x")
        
        out_top = ttk.Frame(out)
        out_top.pack(fill="x", pady=(0, 4))
        ttk.Button(out_top, text="JSON olarak kopyala", command=self._copy_json).pack(side="right", padx=4)
        
        self.output = tk.Text(out, wrap="word", state="disabled", font=("Consolas", 9))
        sb = ttk.Scrollbar(out, command=self.output.yview)
        self.output.configure(yscrollcommand=sb.set)
        self.output.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

    def refresh_projects(self):
        reg = load_registry()
        names = sorted(reg.get("projects", {}))
        self.combo["values"] = names
        active = active_project_name()
        self.project_var.set(active if active in names else "")

    def _on_select(self, _event=None):
        name = self.project_var.get()
        if name:
            set_active_project(name)
            self._log("Aktif proje: %s\n" % name)

    def _on_new_project(self):
        top = tk.Toplevel(self.root)
        top.transient(self.root)
        top.grab_set()
        from wizard.setup_wizard import run_setup_wizard
        run_setup_wizard(parent=top)
        self.refresh_projects()

    def _on_remove_project(self):
        name = self.project_var.get()
        if not name:
            messagebox.showwarning("Uyari", "Once bir proje secin.")
            return
        if not messagebox.askyesno("Proje Kaldir", "Projeyi kayit defterinden silmek istiyor musunuz?\n\n%s\n\n(Proje dosyalari silinmez, sadece kayit silinir.)" % name):
            return
        reg = load_registry()
        if name in reg.get("projects", {}):
            del reg["projects"][name]
        if reg.get("active_project") == name:
            reg["active_project"] = None
        save_registry(reg)
        self.refresh_projects()
        self._log("Proje kaldirildi: %s\n" % name)

    def _on_pick_folder(self):
        p = filedialog.askdirectory(title="Klasor secin")
        if p:
            self.folder_var.set(p)

    def _project_snapshot(self):
        """Capture the currently selected project at click time so a long
        background task never ends up writing to whatever project gets
        selected in the meantime."""
        class _Args:
            pass
        a = _Args()
        a.project = self.project_var.get() or None
        return a

    def _on_help(self):
        messagebox.showinfo(
            "DEVKIT - Yardim",
            "Aktif projeyi secin, ardindan islemlerden birine tiklayin.\n\n"
            "- Hizli Guncelle: degisiklikleri tespit edip raporlari yeniler\n"
            "- Taramayi Guncelle: sifirdan tam tarama yapar\n"
            "- Raporlari Uret: KB raporlarini yeniden olusturur\n"
            "- Saglik Kontrolu: runtime import testi (dongusel import/hayalet import yakalar)\n"
            "- Teknik Borc: twin fonksiyon + FIX/TODO taramasi\n\n"
            "Manuel araclar: herhangi bir klasoru tek seferlik tarar.\n"
            "Tum ciktilar projenin .devkit/ klasorune yazilir.",
        )

    def _require_folder(self):
        folder = self.folder_var.get().strip()
        if not folder:
            raise DevkitError("Once bir klasor secin.")
        if not Path(folder).is_dir():
            raise DevkitError("Klasor bulunamadi: %s" % folder)
        return folder

    def _man_scan(self):
        self._run(self._do_man_scan)

    def _man_deps(self):
        self._run(self._do_man_deps)

    def _man_techdebt(self):
        self._run(self._do_man_techdebt)

    def _do_man_scan(self):
        from engine.scan import run_scan
        folder = self._require_folder()
        r = run_scan(Path(folder), DEFAULT_IGNORE_DIRS)
        s = r["stats"]
        print("Klasor: %s" % folder)
        print("  Dosya: %d (.py %d) | Satir: %d | Sinif: %d | Fonksiyon: %d"
              % (s["total_files"], s["total_py"], s["total_lines"], s["total_classes"], s["total_functions"]))
        print("  Alt sistemler: %s" % ", ".join(s["subsystems"]))
        for rel in sorted(r["files"]):
            print("  %-52s %d satir" % (rel, r["files"][rel]["lines"]))

    def _do_man_deps(self):
        from engine.scan import run_scan
        from engine.deps import run_deps
        folder = self._require_folder()
        scan = run_scan(Path(folder), DEFAULT_IGNORE_DIRS)
        deps = run_deps(scan)
        subs = scan["stats"]["subsystems"]
        print("Bagimlilik matrisi (satir -> sutun import eder):")
        print("| from \\ to |" + "|".join(subs) + "|")
        matrix = deps.get("matrix", {})
        for s in subs:
            row = matrix.get(s, {})
            cells = [str(row.get(t, 0) or "-") for t in subs]
            print("| %s |" % s + "|".join(cells) + "|")
        cycles = deps.get("cycles", [])
        print("")
        print("Donguler: %d" % len(cycles))
        for c in cycles:
            print("  -", " <-> ".join(c))

    def _do_man_techdebt(self):
        from engine.techdebt import run_techdebt
        folder = self._require_folder()
        r = run_techdebt(Path(folder), DEFAULT_IGNORE_DIRS)
        print("Twin fonksiyon gruplari: %d" % len(r["twin_groups"]))
        for g in r["twin_groups"][:15]:
            print("  -", ", ".join(g))
        print("")
        print("FIX/TODO etiketleri: %d" % len(r["fix_tags"]))
        for t in r["fix_tags"][:30]:
            print("  %s:%s [%s]" % (t["file"], t["line"], t["tag"]))

    def _run(self, fn, *args):
        self._set_busy(True)

        def worker():
            buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                    fn(*args)
                text = buf.getvalue()
            except DevkitError as e:
                text = str(e) + "\n"
            except SystemExit:
                text = buf.getvalue()
            except Exception as e:
                text = "[HATA] %s: %s\n" % (type(e).__name__, e)
            self.root.after(0, lambda: self._finish(text))

        threading.Thread(target=worker, daemon=True).start()

    def _finish(self, text):
        self._set_busy(False)
        self._log(text)

    def _set_busy(self, busy):
        state = "disabled" if busy else "normal"
        for b in self.buttons:
            b.configure(state=state)
        self.status.configure(text="Calisiyor..." if busy else "Hazir.")

    def _log(self, text):
        self.output.configure(state="normal")
        self.output.insert("end", text)
        self.output.see("end")
        self.output.configure(state="disabled")

    def _copy_json(self):
        """Copy output as JSON to clipboard."""
        text = self.output.get("1.0", "end-1c").strip()
        if not text:
            messagebox.showinfo("JSON Kopyala", "Cikti bos.")
            return
        import json
        try:
            # Try to parse as JSON first
            parsed = json.loads(text)
            json_str = json.dumps(parsed, indent=2, ensure_ascii=False)
        except json.JSONDecodeError:
            # If not valid JSON, wrap as string
            json_str = json.dumps({"output": text}, indent=2, ensure_ascii=False)
        
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(json_str)
            messagebox.showinfo("JSON Kopyala", "JSON cikti panoya kopyalandi.")
        except Exception as e:
            messagebox.showerror("Hata", "Panoya kopyalanamadi: %s" % e)


def main():
    root = tk.Tk()
    DevkitGUI(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    main()
