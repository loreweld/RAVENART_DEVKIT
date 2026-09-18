#!/usr/bin/env python3
"""
common.py - shared paths, registry and project config access for DEVKIT.

DEVKIT is project-agnostic: this module never stores project outputs under
the DEVKIT home folder. It only keeps a registry (name -> project root);
everything a project produces lives under <project_root>/.devkit/.

Concurrency: registry mutations are serialized through a lock file
(registry.json.lock) and written atomically (temp + rename with retry), so
several DEVKIT processes (e.g. different AIs working on different projects at
the same time) can register/select projects without corrupting the registry
or losing each other's entries. Writes to a given project are additionally
serialized via <project>/.devkit/.devkit.lock.
"""

import contextlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

try:
    import msvcrt
    _LOCK_KIND = "msvcrt"
except ImportError:
    try:
        import fcntl
        _LOCK_KIND = "fcntl"
    except ImportError:
        _LOCK_KIND = None


def _devkit_home() -> Path:
    """DEVKIT home dir. PyInstaller-safe: when frozen, use the exe's folder."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


DEVKIT_DIR = _devkit_home()
REGISTRY_PATH = DEVKIT_DIR / "registry.json"
REGISTRY_LOCK_PATH = DEVKIT_DIR / "registry.json.lock"

CONFIG_VERSION = 2


class RegistryLockError(Exception):
    """Raised when a concurrent registry/project lock cannot be acquired in time."""


def _lock_acquire(f, timeout: float) -> None:
    deadline = time.time() + timeout
    while True:
        try:
            if _LOCK_KIND == "msvcrt":
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            elif _LOCK_KIND == "fcntl":
                f.seek(0)
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except (OSError, IOError):
            if time.time() >= deadline:
                raise RegistryLockError(
                    "[HATA] Kilit zaman asimi (baska islem kilitli): %s" % f.name)
            time.sleep(0.05)


def _lock_release(f) -> None:
    try:
        if _LOCK_KIND == "msvcrt":
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        elif _LOCK_KIND == "fcntl":
            f.seek(0)
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except (OSError, IOError):
        pass


@contextlib.contextmanager
def file_lock(lock_path, timeout: float = 10.0):
    """Advisory cross-process lock; blocks up to `timeout` seconds."""
    lock_path = Path(lock_path)
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    with open(lock_path, "a+b") as f:
        f.seek(0, os.SEEK_END)
        if f.tell() == 0:
            f.write(b"\0")
            f.flush()
        _lock_acquire(f, timeout)
        try:
            yield
        finally:
            _lock_release(f)


def _atomic_write_text(path: Path, text: str) -> None:
    """Write via temp + rename with retry (safe against concurrent readers on Windows)."""
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    for _ in range(20):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.05)
    os.replace(tmp, path)


def project_write_lock(root) -> contextlib.AbstractContextManager:
    """Per-project lock so concurrent scans/syncs on the SAME project serialize.

    Different projects lock independently, so several AIs can work on
    different projects at the same time without blocking each other.
    """
    dk = devkit_dir_for(Path(root))
    dk.mkdir(parents=True, exist_ok=True)
    return file_lock(dk / ".devkit.lock", timeout=600.0)

DEFAULT_IGNORE_DIRS = [
    ".git",
    "__pycache__",
    ".vscode",
    ".idea",
    "node_modules",
    ".venv",
    "venv",
    "env",
    "miniconda*",
    "anaconda*",
    ".conda",
    "java",
    "dist",
    "build",
    "site-packages",
    "Lib",
    "Scripts",
    ".devkit",
    ".tox",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "__pypackages__",
]


def _read_registry() -> dict:
    """Read without locking: writers always publish atomically (temp+rename),
    so a reader can never observe a half-written registry."""
    if not REGISTRY_PATH.exists():
        return {"active_project": None, "projects": {}}
    try:
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"active_project": None, "projects": {}}
    data.setdefault("active_project", None)
    data.setdefault("projects", {})
    return data


def _write_registry(reg: dict) -> None:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(REGISTRY_PATH, json.dumps(reg, indent=2, ensure_ascii=False))


def load_registry() -> dict:
    return _read_registry()


def active_project_name() -> Optional[str]:
    return _read_registry().get("active_project")


def save_registry(reg: dict) -> None:
    with file_lock(REGISTRY_LOCK_PATH):
        _write_registry(reg)


def set_active_project(name: str) -> None:
    with file_lock(REGISTRY_LOCK_PATH):
        reg = _read_registry()
        if name not in reg.get("projects", {}):
            raise ValueError("Unknown project: %s" % name)
        reg["active_project"] = name
        _write_registry(reg)


def register_project(name: str, root: str) -> None:
    with file_lock(REGISTRY_LOCK_PATH):
        reg = _read_registry()
        reg["projects"][name] = {"name": name, "root": root}
        reg["active_project"] = name
        _write_registry(reg)


def project_root(name: Optional[str] = None) -> Optional[Path]:
    target = name or active_project_name()
    if not target:
        return None
    reg = load_registry()
    data = reg.get("projects", {}).get(target)
    if not data:
        return None
    return Path(data["root"])


def project_root_for_cwd() -> Optional[str]:
    """Registered project name whose root contains the current working dir.

    Parallel-AI support: a command launched from inside a project folder
    resolves to THAT project without consulting (or changing) the shared
    active-project pointer. The deepest (most specific) registered root wins
    when projects are nested. Returns None when cwd is not inside any
    registered project.
    """
    try:
        cwd = Path.cwd().resolve()
    except OSError:
        return None
    best_name = None
    best_depth = -1
    for name, data in _read_registry().get("projects", {}).items():
        try:
            root = Path(data.get("root", "")).resolve()
        except (OSError, ValueError):
            continue
        if cwd == root or root in cwd.parents:
            if len(root.parts) > best_depth:
                best_name = name
                best_depth = len(root.parts)
    return best_name


def devkit_dir_for(project_root: Path) -> Path:
    return Path(project_root) / ".devkit"


def load_project_config(project_root: Path) -> dict:
    path = devkit_dir_for(project_root) / "config.json"
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    # migration: add version if missing, normalize ignore_dirs (support glob patterns now)
    if "config_version" not in data:
        data["config_version"] = 1
    return data


def save_project_config(project_root: Path, config: dict) -> None:
    config = dict(config)
    config.setdefault("config_version", CONFIG_VERSION)
    dk = devkit_dir_for(project_root)
    dk.mkdir(parents=True, exist_ok=True)
    with open(dk / "config.json", "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def normalize_ignore_dirs(ignore_dirs) -> list:
    """Return cleaned list - keeps glob patterns like *.pyc, tests/* intact."""
    out = []
    for d in (ignore_dirs or []):
        d = d.strip()
        if d and d not in out:
            out.append(d)
    return out
