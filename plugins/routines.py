"""
Routines plugin: one phrase runs a fixed sequence of steps.

Say "start work" and JARVIS opens VS Code, a browser tab, etc.

SAFETY: the model only supplies the routine NAME. The steps come from
DEFAULT_ROUTINES below or from config/routines.json, both written by you.
The model can never inject a command or URL of its own.

To add your own routines, create config/routines.json (same shape as
DEFAULT_ROUTINES). Routines with the same name override the defaults.
Step types:
    {"type": "url",  "target": "https://github.com"}
    {"type": "app",  "target": "code", "args": ["C:/dev/myproject"]}
    {"type": "open", "target": "C:/Users/me/Documents"}   # file or folder
    {"type": "wait", "seconds": 2}
"""
import json
import os
import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

_PROJECT_DIR = Path(__file__).resolve().parent.parent

PLUGIN = {
    "name": "run_routine",
    "description": (
        "Runs a saved multi-step routine, such as opening a set of apps and "
        "websites in one go. Use when the user says things like 'start work', "
        "'work mode', or 'run my <name> routine'. Pass the routine name in "
        "'name'. If the user asks what routines exist, call with name 'list'. "
        "Do NOT use this for opening a single app or website; use the normal "
        "open-app or browser tools for that."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "name": {
                "type": "STRING",
                "description": "Routine name, e.g. 'start work'. Use 'list' to list routines.",
            },
        },
        "required": ["name"],
    },
}

DEFAULT_ROUTINES = {
    "start work": {
        "aliases": ["work mode", "begin work", "start working"],
        "steps": [
            {"type": "app", "target": "code", "args": [str(_PROJECT_DIR)]},
            {"type": "wait", "seconds": 1},
            {"type": "url", "target": "https://github.com"},
        ],
    },
}


def _load_routines() -> dict:
    routines = {k.lower(): v for k, v in DEFAULT_ROUTINES.items()}
    cfg = _PROJECT_DIR / "config" / "routines.json"
    if cfg.exists():
        try:
            data = json.loads(cfg.read_text(encoding="utf-8"))
            for k, v in data.items():
                routines[str(k).lower()] = v
        except Exception:
            pass  # bad JSON: fall back to defaults rather than crash
    return routines


def _find(routines: dict, name: str):
    name = name.strip().lower()
    if name in routines:
        return name
    for key, r in routines.items():
        if name in [a.lower() for a in r.get("aliases", [])]:
            return key
    for key, r in routines.items():  # loose match: "work" -> "start work"
        if name and (name in key or key in name):
            return key
    return None


def _run_step(step: dict) -> str:
    """Runs one step. Returns '' on success, or a short error string."""
    kind = step.get("type")
    target = str(step.get("target", ""))
    dry = os.environ.get("ROUTINES_DRY_RUN") == "1"

    if kind == "wait":
        if not dry:
            time.sleep(min(float(step.get("seconds", 1)), 10))
        return ""

    if kind == "url":
        if not target.startswith(("http://", "https://")):
            return f"skipped invalid URL {target}"
        if not dry:
            webbrowser.open(target)
        return ""

    if kind == "open":
        if not Path(target).exists():
            return f"{target} not found"
        if dry:
            return ""
        if sys.platform.startswith("win"):
            os.startfile(target)  # noqa: S606 (target comes from user config)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", target])
        else:
            subprocess.Popen(["xdg-open", target])
        return ""

    if kind == "app":
        exe = shutil.which(target) or target
        if not shutil.which(target) and not Path(target).exists():
            return f"{target} not found"
        if dry:
            return ""
        cmd = [exe] + [str(a) for a in step.get("args", [])]
        if sys.platform.startswith("win"):
            # code.cmd and similar launchers need the shell on Windows
            subprocess.Popen(subprocess.list2cmdline(cmd), shell=True)
        else:
            subprocess.Popen(cmd)
        return ""

    return f"unknown step type {kind}"


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        routines = _load_routines()
        name = str(parameters.get("name", "")).strip()

        if name.lower() in ("", "list"):
            return "Your routines are: " + ", ".join(sorted(routines)) + "."

        key = _find(routines, name)
        if key is None:
            return f"Sir, I don't have a routine called {name}. Available: " + ", ".join(sorted(routines)) + "."

        problems = []
        for step in routines[key].get("steps", []):
            err = _run_step(step)
            if err:
                problems.append(err)

        msg = f"Running {key}."
        if problems:
            msg += " Some steps failed: " + "; ".join(problems) + "."
        if player:
            try:
                player.write_log(f"JARVIS: {msg}")
            except Exception:
                pass
        return msg
    except Exception as e:
        return f"Sir, the routine failed: {e}"