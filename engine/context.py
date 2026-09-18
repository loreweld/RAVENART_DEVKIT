#!/usr/bin/env python3
"""
context.py - resolve the target project for DEVKIT commands.

Resolution order (parallel-AI safe):
  1. explicit --project argument    (strongest guarantee)
  2. current working directory      (cwd inside a registered project root)
  3. registry "active_project"      (legacy single-session / GUI flow)

The resolved target is announced on stderr as "[PROJE] ..." so a mis-targeted
command is immediately visible. stderr keeps stdout clean for --json output;
the announcement is suppressed entirely in --json mode (CLI sets .quiet).
"""

import sys
from typing import Optional

from common import (
    DEFAULT_IGNORE_DIRS,
    active_project_name,
    devkit_dir_for,
    load_project_config,
    project_root,
    project_root_for_cwd,
)


class DevkitError(Exception):
    """Raised when a command cannot proceed (e.g. no active project)."""


# CLI sets this to True for --json runs: no [PROJE] banner anywhere.
quiet = False


def resolve_project_name(explicit: Optional[str] = None):
    """Return (name, source) for the target project, or (None, None).

    Source is one of: "acik --project", "calisma klasoru",
    "kayit defteri (aktif proje)".
    """
    if explicit:
        return explicit, "acik --project"
    cwd_name = project_root_for_cwd()
    if cwd_name:
        return cwd_name, "calisma klasoru"
    active = active_project_name()
    if active:
        return active, "kayit defteri (aktif proje)"
    return None, None


def require_project(name: Optional[str] = None):
    """Return (root, config, ignore_dirs, data_dir) for the target project.

    Resolution order: explicit name > working directory > active selection.
    Running from inside a project folder pins the command to THAT project no
    matter which project another concurrent AI session has selected - this is
    what lets several AIs work on different projects at the same time without
    stepping on each other (or leaking reports into each other's folders).

    Raises DevkitError with a clear message when the project cannot be found.
    """
    root_name, source = resolve_project_name(name)
    root = project_root(root_name) if root_name else None
    if root is None or not root.exists():
        if root_name:
            raise DevkitError(
                "[HATA] Kayitli proje bulunamadi: %s\n"
                "       Mevcut projeleri gormek icin: devkit list" % root_name
            )
        raise DevkitError(
            "[HATA] Once bir proje secin.\n"
            "       GUI: ustteki dropdown'dan secin.\n"
            "       CLI: devkit select <ad>  (veya devkit init)\n"
            "       Not: proje klasoru icinden calisirsa hedef otomatik bulunur."
        )
    config = load_project_config(root)
    ignore = set(config.get("ignore_dirs", [])) | set(DEFAULT_IGNORE_DIRS)
    data_dir = devkit_dir_for(root) / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    if not quiet:
        print("[PROJE] %s -> %s (kaynak: %s)" % (root_name, root, source),
              file=sys.stderr)
    return root, config, ignore, data_dir
