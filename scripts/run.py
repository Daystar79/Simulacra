#!/usr/bin/env python3
"""
OS-aware tool launcher for Simulacra.

Detects Windows vs Unix-like hosts and runs the matching platform wrapper
(or falls back to the shared Python cores). Prefer this entry point for agents.

Usage:
  python scripts/run.py deploy [target]
  python scripts/run.py lint <path> [--ext .md,.txt]
  python scripts/run.py golem --card <card.yaml> --stimulus <json_or_path>
  python scripts/run.py migrate

Environment:
  CM_FORCE_OS=windows|unix   Override auto-detection (for testing).
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent

TOOLS: tuple[str, ...] = ("deploy", "lint", "validate", "validate_state", "validate-state", "migrate", "golem")


def detect_family() -> str:
    """Detect OS family (windows or unix)."""
    forced = os.environ.get("CM_FORCE_OS", "").strip().lower()
    if forced in ("windows", "win", "win32"):
        return "windows"
    if forced in ("unix", "linux", "darwin", "posix"):
        return "unix"
    system = platform.system().lower()
    if system == "windows" or sys.platform.startswith("win"):
        return "windows"
    return "unix"


def find_python() -> list[str]:
    """Return argv prefix that invokes Python 3 on this host."""
    if detect_family() == "windows":
        for candidate in (
            [sys.executable],
            ["py", "-3"],
            ["python"],
            ["python3"],
        ):
            if candidate[0] == sys.executable and sys.executable:
                return candidate
            if candidate[0] != sys.executable and shutil.which(candidate[0]):
                return candidate
        return [sys.executable or "python"]
    # Unix
    if sys.executable:
        return [sys.executable]
    for name in ("python3", "python"):
        if shutil.which(name):
            return [name]
    return ["python3"]


def wrapper_path(family: str, tool: str) -> Path | None:
    """Get the path to a platform wrapper script."""
    canonical = "validate" if tool in ("validate_state", "validate-state") else tool
    if family == "windows":
        ps1 = SCRIPTS / "windows" / f"{canonical}.ps1"
        return ps1 if ps1.is_file() else None
    sh = SCRIPTS / "unix" / f"{canonical}.sh"
    return sh if sh.is_file() else None


def python_core(tool: str) -> Path:
    """Get the path to a Python core script."""
    if tool == "deploy":
        return ROOT / "deploy_framework.py"
    if tool == "lint":
        return ROOT / "Framework" / "linter.py"
    if tool in ("validate", "validate_state", "validate-state"):
        return ROOT / "scripts" / "validate_state.py"
    if tool == "migrate":
        return ROOT / "migrate_optimized.py"
    if tool == "golem":
        return ROOT / "scripts" / "golem.py"
    raise KeyError(tool)


def run_windows_wrapper(ps1: Path, args: list[str]) -> int:
    """Run a Windows PowerShell wrapper script."""
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if not powershell:
        # Fall back to pure Python core
        return run_python_core(ps1.stem, args)
    cmd = [
        powershell,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(ps1),
        *args,
    ]
    print(f"[run] OS=windows → {ps1.relative_to(ROOT)}", flush=True)
    return subprocess.call(cmd, cwd=str(ROOT))


def run_unix_wrapper(sh: Path, args: list[str]) -> int:
    """Run a Unix shell wrapper script."""
    bash = shutil.which("bash") or shutil.which("sh")
    if not bash:
        return run_python_core(sh.stem, args)
    cmd = [bash, str(sh), *args]
    print(f"[run] OS=unix → {sh.relative_to(ROOT)}", flush=True)
    return subprocess.call(cmd, cwd=str(ROOT))


def run_python_core(tool: str, args: list[str]) -> int:
    """Run a Python core script directly."""
    if tool == "migrate":
        print("Notice: 'migrate' is retired; framework optimization is complete and active.", file=sys.stderr)
        return 0
    core = python_core(tool)
    if not core.is_file():
        if tool == "deploy":
            print("Error: 'deploy_framework.py' was not found in this repository.", file=sys.stderr)
            print("Note: Framework deployment is an upstream operation. To deploy or update a book project,", file=sys.stderr)
            print("please run the deploy command from the main 'Simulacra' repository.", file=sys.stderr)
        else:
            print(f"Error: missing core script {core}", file=sys.stderr)
        return 2
    py = find_python()
    cmd = [*py, str(core), *args]
    print(f"[run] python core → {core.relative_to(ROOT)}", flush=True)
    return subprocess.call(cmd, cwd=str(ROOT))


def usage() -> None:
    """Print usage information."""
    family = detect_family()
    print(
        f"""Simulacra — OS-aware launcher
Detected OS family: {family}

Usage:
  python scripts/run.py deploy [book_name_or_path]
  python scripts/run.py deploy --update /path/to/installation [--check]
  python scripts/run.py lint <path> [linter args...]
  python scripts/run.py validate [state_file_or_dir]
  python scripts/run.py golem --card <card.yaml> --stimulus <json_or_path>

Platform wrappers (AI: pick by OS if not using this launcher):
  Unix:    scripts/unix/deploy.sh | lint.sh | validate.sh
  Windows: scripts/windows/deploy.ps1 | lint.ps1 | validate.ps1
"""
    )


def main(argv: list[str] | None = None) -> int:
    """Main entry point for the OS-aware launcher."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        usage()
        return 0 if argv else 1

    tool = argv[0].lower()
    args = argv[1:]
    if tool not in TOOLS:
        print(f"Unknown tool: {tool}", file=sys.stderr)
        usage()
        return 2

    if tool == "migrate":
        print("Notice: 'migrate' is retired; framework optimization is complete and active.")
        return 0

    family = detect_family()
    wrapper = wrapper_path(family, tool)

    if wrapper is not None:
        if family == "windows":
            return run_windows_wrapper(wrapper, args)
        return run_unix_wrapper(wrapper, args)

    return run_python_core(tool, args)


if __name__ == "__main__":
    raise SystemExit(main())
