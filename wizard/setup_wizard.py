#!/usr/bin/env python3
"""
setup_wizard.py - GUI setup wizard for DEVKIT.

Collects, via a Tkinter window:
  1. Project name + root folder (Windows folder picker)
  2. Project info (free text)        -> saved as PROJECT_INFO.txt
  3. Optional project-specific rules -> saved as PROJECT_RULES.md
  4. Python environment path (python.exe)
  5. Ignore directories (checkbox list of detected top-level dirs)

Writes into the target project:
  .devkit/config.json
  .devkit/PROJECT_INFO.txt
  .devkit/PROJECT_RULES.md   (only when rules were entered)

And registers the project in the DEVKIT registry.

Fallback: when Tkinter is unavailable (or DEVKIT_FORCE_CLI=1), a plain
command-line interview is used instead.
"""

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

_DEVKIT_DIR = Path(__file__).resolve().parent.parent
if str(_DEVKIT_DIR) not in sys.path:
    sys.path.insert(0, str(_DEVKIT_DIR))

from common import DEFAULT_IGNORE_DIRS, load_registry, register_project, save_project_config

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    TK_AVAILABLE = True
except ImportError:
    TK_AVAILABLE = False


def _ask(prompt: str, default: str = "") -> str:
    try:
        value = input(prompt).strip()
    except EOFError:
        value = ""
    return value or default


def _validate_and_normalize_path(path: str) -> Path:
    """Validate and normalize a path, return Path object or raise ValueError."""
    if not path:
        raise ValueError("Path cannot be empty")
    p = Path(path).resolve()
    if not p.is_dir():
        raise ValueError("Not a directory: %s" % path)
    return p


def _validate_env_path(env: str) -> str:
    """Validate python executable path, return empty string if invalid."""
    if not env:
        return ""
    p = Path(env)
    if not p.is_file():
        raise ValueError("Env path is not a file: %s" % env)
    # Quick test
    try:
        import subprocess
        result = subprocess.run([str(p), "--version"], capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            raise ValueError("Env not working (exit %s): %s" % (result.returncode, result.stderr.strip()))
    except OSError as e:
        raise ValueError("Env cannot start: %s" % e)
    return str(p)


def _normalize_ignore_dirs(ignore_dirs: list) -> list:
    """Normalize ignore directories list."""
    if not ignore_dirs:
        return []
    out = []
    for d in ignore_dirs:
        d = d.strip()
        if d and d not in out:
            out.append(d)
    return out


def _detect_suggested_ignore(root: Path) -> list:
    """Detect common ignore directories in project root."""
    common = [".git", "__pycache__", ".venv", "venv", "env", "node_modules", "dist", "build", ".pytest_cache", ".mypy_cache"]
    found = []
    try:
        for d in root.iterdir():
            if d.is_dir() and d.name in common:
                found.append(d.name)
    except OSError:
        pass
    return found


def run_setup_wizard_ai_driven(
    project_root: str,
    project_name: str = None,
    env_path: str = None,
    project_info: str = "",
    project_rules: str = "",
    ignore_dirs: list = None,
    big_file_threshold: int = 800,
    output_warn_mb: int = 1,
    output_block_mb: int = 5,
    auto_confirm: bool = False,
    json_output: bool = False,
) -> dict:
    """
    AI-driven programmatic setup wizard.
    
    Args:
        project_root: Project root directory (REQUIRED)
        project_name: Project name (optional, defaults to folder name)
        env_path: Python executable path (optional)
        project_info: Project description (optional)
        project_rules: Project-specific rules (optional)
        ignore_dirs: List of directories to ignore (optional)
        big_file_threshold: Big file threshold in lines (default 800)
        output_warn_mb: Output warning limit in MB (default 1)
        output_block_mb: Output block limit in MB (default 5)
        auto_confirm: If True, skip confirmation prompt (default False)
        json_output: If True, return JSON-serializable dict instead of printing
    
    Returns:
        dict with status and details:
        - status: "ok" | "needs_input" | "needs_confirmation" | "error"
        - missing: list of missing required fields (if needs_input)
        - config_preview: preview of config to be saved (if needs_confirmation)
        - devkit_dir: path to .devkit directory (if ok)
        - error: error message (if error)
    
    Raises:
        ValueError: for invalid inputs
    """
    # Step 1: Validate required inputs
    missing = []
    
    # project_root is required
    try:
        root = _validate_and_normalize_path(project_root)
    except ValueError as e:
        return {"status": "error", "error": "project_root: %s" % e}
    
    # project_name defaults to folder name
    if not project_name:
        project_name = root.name
    project_name = project_name.strip()
    if not project_name:
        missing.append("project_name")
    
    # env_path validation
    try:
        validated_env = _validate_env_path(env_path) if env_path else ""
    except ValueError as e:
        return {"status": "error", "error": "env_path: %s" % e}
    
    # ignore_dirs
    if ignore_dirs is None:
        # Auto-detect common ignore dirs
        ignore_dirs = _detect_suggested_ignore(root)
    validated_ignore = _normalize_ignore_dirs(ignore_dirs)
    
    # Validate numeric params
    try:
        big_file_threshold = int(big_file_threshold)
        output_warn_mb = int(output_warn_mb)
        output_block_mb = int(output_block_mb)
    except (ValueError, TypeError):
        return {"status": "error", "error": "Numeric parameters must be integers"}
    
    if missing:
        return {
            "status": "needs_input",
            "missing": missing,
            "suggestions": {
                "project_name": "Defaults to folder name: %s" % root.name,
                "env_path": "Path to python.exe (e.g. H:\\Proje\\.venv\\Scripts\\python.exe)",
                "ignore_dirs": "Auto-detected: %s" % ", ".join(_detect_suggested_ignore(root)),
            },
        }
    
    # Step 2: Prepare config preview
    config_preview = {
        "project_name": project_name,
        "project_root": str(root),
        "env_path": validated_env,
        "ignore_dirs": validated_ignore,
        "big_file_threshold": big_file_threshold,
        "output_warn_mb": output_warn_mb,
        "output_block_mb": output_block_mb,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    
    # Step 3: Check for existing registration
    from common import load_registry
    reg = load_registry()
    for other, data in reg.get("projects", {}).items():
        if other != project_name and Path(data.get("root", "")) == root:
            return {
                "status": "error",
                "error": "This root is already registered as '%s'" % other,
            }
    
    # Step 4: If not auto_confirm, return for confirmation
    if not auto_confirm:
        return {
            "status": "needs_confirmation",
            "config_preview": config_preview,
            "suggestions": {
                "env_path": validated_env or "auto-detect",
                "ignore_dirs": validated_ignore or "none",
            },
        }
    
    # Step 5: Execute setup (same as _finalize_setup)
    from common import load_registry, register_project, save_project_config
    
    save_project_config(root, config_preview)
    
    dk = root / ".devkit"
    info_text = project_info.strip() or "No project info provided yet."
    (dk / "PROJECT_INFO.txt").write_text(
        "# %s - Project Info\n\n%s\n" % (project_name, info_text), encoding="utf-8")
    
    if project_rules.strip():
        (dk / "PROJECT_RULES.md").write_text(
            "# Project-Specific Rules - %s\n\n"
            "These rules were entered during DEVKIT setup. They override the\n"
            "global DEVKIT rules (rules.md) when they conflict.\n\n"
            "## User-defined rules\n\n%s\n" % (project_name, project_rules.strip()),
            encoding="utf-8")
    
    register_project(project_name, str(root))
    
    try:
        from engine.scaffold import scaffold
        scaffold_results = scaffold(root, project_name)
    except Exception as e:
        scaffold_results = {"error": str(e)}
    
    result = {
        "status": "ok",
        "devkit_dir": str(dk),
        "config": config_preview,
        "scaffold": scaffold_results,
    }
    
    if json_output:
        return result
    else:
        print("[OK] Project '%s' registered: %s" % (project_name, root))
        print("[OK] Config written: %s" % (dk / "config.json"))
        for key, value in scaffold_results.items():
            print("[SCAFFOLD] %s: %s" % (key, value))
        if project_rules.strip():
            print("[OK] Project rules written: %s" % (dk / "PROJECT_RULES.md"))
        return result


def run_setup_wizard_cli() -> int:
    """Command-line fallback interview (used when Tkinter is unavailable)."""
    print("DEVKIT - new project setup (CLI mode)")
    name = ""
    while not name:
        name = _ask("Project name: ")
        if not name:
            print("[ERROR] Project name cannot be empty.")
    root = ""
    while not root:
        root = _ask("Project root path: ")
        if not Path(root).is_dir():
            print("[ERROR] Not a directory: %s" % root)
            root = ""
    env = _ask("Python executable path (leave empty to auto-detect): ")
    if env and not Path(env).is_file():
        print("[WARN] Env path is not a file, ignoring: %s" % env)
        env = ""
    info = _ask("Project info (optional): ")
    rules = _ask("Project-specific rules (optional): ")
    ignores = _ask("Ignore dirs, comma separated (empty = defaults): ")
    ignore_dirs = [d.strip() for d in ignores.split(",") if d.strip()]
    big_file_thresh = _ask("Big file threshold in lines (default 800): ")
    try:
        big_file_thresh = int(big_file_thresh) if big_file_thresh else 800
    except ValueError:
        big_file_thresh = 800
    output_warn = _ask("Output warn limit MB (default 1): ")
    try:
        output_warn = int(output_warn) if output_warn else 1
    except ValueError:
        output_warn = 1
    output_block = _ask("Output block limit MB (default 5): ")
    try:
        output_block = int(output_block) if output_block else 5
    except ValueError:
        output_block = 5
    
    # Inline finalize
    from common import load_registry, register_project, save_project_config
    reg = load_registry()
    for other, data in reg.get("projects", {}).items():
        if other != name and Path(data.get("root", "")) == Path(root):
            print("[WARN] This root is already registered as '%s'." % other)

    config = {
        "project_name": name,
        "project_root": str(Path(root)),
        "env_path": str(Path(env)) if env else "",
        "ignore_dirs": list(ignore_dirs),
        "big_file_threshold": big_file_thresh,
        "output_warn_mb": output_warn,
        "output_block_mb": output_block,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    save_project_config(Path(root), config)

    dk = Path(root) / ".devkit"
    info_text = info.strip() or "No project info provided yet."
    (dk / "PROJECT_INFO.txt").write_text(
        "# %s - Project Info\n\n%s\n" % (name, info_text), encoding="utf-8")

    if rules.strip():
        (dk / "PROJECT_RULES.md").write_text(
            "# Project-Specific Rules - %s\n\n"
            "These rules were entered during DEVKIT setup. They override the\n"
            "global DEVKIT rules (rules.md) when they conflict.\n\n"
            "## User-defined rules\n\n%s\n" % (name, rules.strip()),
            encoding="utf-8")

    register_project(name, str(Path(root)))
    print("[OK] Project '%s' registered: %s" % (name, root))
    print("[OK] Config written: %s" % (dk / "config.json"))

    try:
        from engine.scaffold import scaffold
        for key, result in scaffold(Path(root), name).items():
            print("[SCAFFOLD] %s: %s" % (key, result))
    except Exception as e:
        print("[SCAFFOLD] skipped: %s" % e)

    if rules.strip():
        print("[OK] Project rules written: %s" % (dk / "PROJECT_RULES.md"))
    return 0


class SetupWizardGUI:
    """Tkinter setup wizard window."""

    def __init__(self, root_window: tk.Tk):
        self.root = root_window
        self.root.title("DEVKIT - Yeni Proje Kurulumu")
        self.root.resizable(False, False)
        self.root.minsize(640, 620)

        self.project_name_var = tk.StringVar()
        self.root_var = tk.StringVar()
        self.env_var = tk.StringVar()
        self.extra_ignore_var = tk.StringVar()
        self.rules_enabled = tk.BooleanVar(value=False)
        self.ignore_vars = {}
        self.status_var = tk.StringVar(value="Hazir.")
        self.saved = False

        self._build_ui()

    def _build_ui(self) -> None:
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill="both", expand=True)

        row = 0
        ttk.Label(main, text="Proje adi:").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(main, textvariable=self.project_name_var, width=40).grid(
            row=row, column=1, sticky="we", padx=6, pady=4)
        row += 1

        ttk.Label(main, text="Calisma klasoru:").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(main, textvariable=self.root_var, width=40).grid(
            row=row, column=1, sticky="we", padx=6, pady=4)
        ttk.Button(main, text="Gezin...", command=self._pick_folder).grid(
            row=row, column=2, padx=4, pady=4)
        row += 1

        ttk.Label(main, text="Python env (python.exe):").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(main, textvariable=self.env_var, width=40).grid(
            row=row, column=1, sticky="we", padx=6, pady=4)
        ttk.Button(main, text="Sec...", command=self._pick_env).grid(
            row=row, column=2, padx=4, pady=4)
        row += 1

        ttk.Label(main, text="Proje hakkinda bilgi:").grid(row=row, column=0, sticky="nw", pady=4)
        self.info_text = tk.Text(main, height=5, width=52, wrap="word")
        self.info_text.grid(row=row, column=1, columnspan=2, sticky="we", padx=6, pady=4)
        row += 1

        ttk.Checkbutton(
            main, text="Ek kurallar ekle (proje ozel)",
            variable=self.rules_enabled, command=self._toggle_rules,
        ).grid(row=row, column=0, columnspan=3, sticky="w", pady=4)
        row += 1

        self.rules_text = tk.Text(main, height=4, width=52, wrap="word", state="disabled")
        self.rules_text.grid(row=row, column=0, columnspan=3, sticky="we", padx=6, pady=2)
        row += 1

        ignore_box = ttk.LabelFrame(main, text="Taranmayacak klasorler (ignore)")
        ignore_box.grid(row=row, column=0, columnspan=3, sticky="we", padx=2, pady=6)
        ignore_box.columnconfigure(0, weight=1)

        canvas = tk.Canvas(ignore_box, borderwidth=0, height=150)
        scrollbar = ttk.Scrollbar(ignore_box, orient="vertical", command=canvas.yview)
        self.ignore_frame = ttk.Frame(canvas)
        self.ignore_frame.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.ignore_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        scrollbar.grid(row=0, column=1, sticky="ns", pady=4)
        ttk.Label(ignore_box, text="Diger (virgulle ayrin):").grid(
            row=1, column=0, sticky="w", padx=4, pady=2)
        ttk.Entry(ignore_box, textvariable=self.extra_ignore_var, width=50).grid(
            row=2, column=0, sticky="we", padx=4, pady=(0, 6))
        row += 1

        ttk.Label(main, textvariable=self.status_var, foreground="#444").grid(
            row=row, column=0, columnspan=3, sticky="w", pady=4)
        row += 1

        # Advanced settings
        adv_box = ttk.LabelFrame(main, text="Gelişmiş ayarlar (opsiyonel)")
        adv_box.grid(row=row, column=0, columnspan=3, sticky="we", padx=2, pady=6)
        adv_box.columnconfigure(1, weight=1)

        ttk.Label(adv_box, text="Büyük dosya eşiği (satır):").grid(row=0, column=0, sticky="w", padx=4, pady=2)
        self.big_file_thresh_var = tk.StringVar(value="800")
        ttk.Entry(adv_box, textvariable=self.big_file_thresh_var, width=10).grid(row=0, column=1, sticky="w", padx=4, pady=2)

        ttk.Label(adv_box, text="Çıktı uyarı limiti (MB):").grid(row=1, column=0, sticky="w", padx=4, pady=2)
        self.output_warn_var = tk.StringVar(value="1")
        ttk.Entry(adv_box, textvariable=self.output_warn_var, width=10).grid(row=1, column=1, sticky="w", padx=4, pady=2)

        ttk.Label(adv_box, text="Çıktı bloklama limiti (MB):").grid(row=2, column=0, sticky="w", padx=4, pady=2)
        self.output_block_var = tk.StringVar(value="5")
        ttk.Entry(adv_box, textvariable=self.output_block_var, width=10).grid(row=2, column=1, sticky="w", padx=4, pady=2)
        row += 1

        buttons = ttk.Frame(main)
        buttons.grid(row=row, column=0, columnspan=3, sticky="e", pady=6)
        ttk.Button(buttons, text="Iptal", command=self.root.destroy).pack(side="right", padx=4)
        ttk.Button(buttons, text="Kaydet", command=self._save).pack(side="right", padx=4)

        main.columnconfigure(1, weight=1)

    def _toggle_rules(self) -> None:
        state = "normal" if self.rules_enabled.get() else "disabled"
        self.rules_text.configure(state=state)

    def _pick_folder(self) -> None:
        path = filedialog.askdirectory(title="Calisma klasorunu secin")
        if not path:
            return
        self.root_var.set(path)
        if not self.project_name_var.get().strip():
            self.project_name_var.set(Path(path).name)
        self._populate_ignore_list(path)
        self.status_var.set("Klasor secildi: %s" % path)

    def _populate_ignore_list(self, root_path: str) -> None:
        for child in self.ignore_frame.winfo_children():
            child.destroy()
        self.ignore_vars.clear()
        try:
            dirs = sorted(d.name for d in Path(root_path).iterdir() if d.is_dir())
        except OSError:
            dirs = []
        for d in dirs:
            var = tk.BooleanVar(value=(d in DEFAULT_IGNORE_DIRS))
            cb = tk.Checkbutton(self.ignore_frame, text=d, variable=var, anchor="w")
            cb.pack(fill="x", padx=6)
            self.ignore_vars[d] = var
        if not dirs:
            ttk.Label(self.ignore_frame, text="(alt klasor bulunamadi)").pack(anchor="w", padx=6)

    def _pick_env(self) -> None:
        path = filedialog.askopenfilename(
            title="python.exe secin",
            filetypes=[("Python", "python*.exe"), ("All files", "*.*")],
        )
        if path:
            self.env_var.set(path)

    def _validate_env(self, env: str) -> str:
        """Run the chosen interpreter to confirm it works. Returns error text or ''."""
        try:
            result = subprocess.run(
                [env, "--version"], capture_output=True, text=True, timeout=15)
            if result.returncode == 0:
                return ""
            return "env calismiyor (cikis kodu %s): %s" % (result.returncode, result.stderr.strip())
        except OSError as e:
            return "env baslatilamadi: %s" % e

    def _save(self) -> None:
        name = self.project_name_var.get().strip()
        root = self.root_var.get().strip()
        env = self.env_var.get().strip()
        info = self.info_text.get("1.0", "end").strip()
        rules = self.rules_text.get("1.0", "end").strip() if self.rules_enabled.get() else ""

        if not name:
            messagebox.showerror("Hata", "Proje adi bos olamaz.")
            return
        if not root or not Path(root).is_dir():
            messagebox.showerror("Hata", "Calisma klasoru gecerli degil.")
            return
        if env:
            error = self._validate_env(env)
            if error:
                if not messagebox.askyesno("Uyari", "%s\nYine de kaydedilsin mi?" % error):
                    return

        ignore_dirs = [d for d, var in self.ignore_vars.items() if var.get()]
        ignore_dirs += [d.strip() for d in self.extra_ignore_var.get().split(",") if d.strip()]

        # Advanced settings
        try:
            big_file_thresh = int(self.big_file_thresh_var.get().strip() or "800")
        except ValueError:
            big_file_thresh = 800
        try:
            output_warn = int(self.output_warn_var.get().strip() or "1")
        except ValueError:
            output_warn = 1
        try:
            output_block = int(self.output_block_var.get().strip() or "5")
        except ValueError:
            output_block = 5

        # Pass advanced settings via a modified _finalize_setup
        from common import save_project_config
        config = {
            "project_name": name,
            "project_root": str(Path(root)),
            "env_path": str(Path(env)) if env else "",
            "ignore_dirs": list(ignore_dirs),
            "big_file_threshold": big_file_thresh,
            "output_warn_mb": output_warn,
            "output_block_mb": output_block,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        save_project_config(Path(root), config)

        dk = Path(root) / ".devkit"
        info_text = info.strip() or "No project info provided yet."
        (dk / "PROJECT_INFO.txt").write_text(
            "# %s - Project Info\n\n%s\n" % (name, info_text), encoding="utf-8")

        if rules.strip():
            (dk / "PROJECT_RULES.md").write_text(
                "# Project-Specific Rules - %s\n\n"
                "These rules were entered during DEVKIT setup. They override the\n"
                "global DEVKIT rules (rules.md) when they conflict.\n\n"
                "## User-defined rules\n\n%s\n" % (name, rules.strip()),
                encoding="utf-8")

        from common import register_project
        register_project(name, str(Path(root)))
        print("[OK] Project '%s' registered: %s" % (name, root))
        print("[OK] Config written: %s" % (dk / "config.json"))

        try:
            from engine.scaffold import scaffold
            for key, result in scaffold(Path(root), name).items():
                print("[SCAFFOLD] %s: %s" % (key, result))
        except Exception as e:
            print("[SCAFFOLD] skipped: %s" % e)

        if rules.strip():
            print("[OK] Project rules written: %s" % (dk / "PROJECT_RULES.md"))

        self.saved = True
        messagebox.showinfo(
            "Tamam",
            "Proje kaydedildi.\n\n"
            "Ad: %s\nKlasor: %s\n\nDevKit ciktisi: %s\n" % (name, root, Path(root) / ".devkit"),
        )
        self.root.destroy()


def run_setup_wizard(parent=None) -> int:
    if os.environ.get("DEVKIT_FORCE_CLI") == "1" or not TK_AVAILABLE:
        return run_setup_wizard_cli()

    own_root = parent is None
    if own_root:
        parent = tk.Tk()
    wizard = SetupWizardGUI(parent)
    if own_root:
        parent.mainloop()
    else:
        parent.wait_window()
    return 0 if wizard.saved else 1


if __name__ == "__main__":
    sys.exit(run_setup_wizard())
