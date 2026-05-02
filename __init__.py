# ============================================================
#  Blender AI Assistant — __init__.py
#  Blender 4.5 / Python 3.11
# ============================================================

bl_info = {
    "name":        "AI Assistant",
    "author":      "Your Name",
    "version":     (1, 0, 0),
    "blender":     (4, 5, 0),
    "location":    "View3D › Sidebar › AI Assistant",
    "description": "Real-time AI guidance and mesh generation via Claude / OpenAI",
    "category":    "3D View",
    "doc_url":     "",
    "tracker_url": "",
}

# ------------------------------------------------------------------
# Dependency bootstrap
# Blender ships its own Python (3.11) with no pip-installed packages.
# We install missing deps into a per-user site-packages on first run.
# ------------------------------------------------------------------
import importlib
import importlib.util
import subprocess
import sys
import os

REQUIRED_PACKAGES = {
    "requests":    "requests",
    "jsonschema":  "jsonschema",
}

def _ensure_deps():
    missing = [pkg for mod, pkg in REQUIRED_PACKAGES.items()
               if importlib.util.find_spec(mod) is None]
    if not missing:
        return True
    try:
        python = sys.executable
        for pkg in missing:
            subprocess.check_call(
                [python, "-m", "pip", "install", "--user", pkg],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        importlib.invalidate_caches()
        return True
    except Exception as exc:
        print(f"[AI Assistant] Could not install dependencies: {exc}")
        return False

_deps_ok = _ensure_deps()

# ------------------------------------------------------------------
# Sub-module imports (deferred so Blender can still register the add-on
# even when deps are missing — user sees an error in the panel instead
# of a hard crash).
# ------------------------------------------------------------------
if _deps_ok:
    from . import (
        operators,
        panels,
        preferences,
    )
    _modules = [operators, panels, preferences]
else:
    _modules = []

import bpy

def register():
    # Always register preferences so the user can set their API key
    from . import preferences as prefs_mod
    prefs_mod.register()

    if not _deps_ok:
        print("[AI Assistant] Missing dependencies — limited functionality.")
        return

    for mod in _modules:
        if mod is not __import__(__name__ + ".preferences",
                                  fromlist=["preferences"]):
            mod.register()

def unregister():
    for mod in reversed(_modules):
        try:
            mod.unregister()
        except Exception:
            pass
