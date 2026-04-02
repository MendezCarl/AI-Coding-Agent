from __future__ import annotations

import subprocess

from pathlib import Path

from tools.security import AGENT_ROOT, is_within_agent_root, resolve_under_agent_root


def git_status(path: str = "."):
    try:
        target = resolve_under_agent_root(path)

        if not is_within_agent_root(target):
            return {
                "status": "error",
                "error": f"Path not allowed: {target}",
                "agent_root": str(AGENT_ROOT),
            }

        workdir = target if target.is_dir() else target.parent

        repo_check = subprocess.run(
            ["git", "-C", str(workdir), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
        )

        if repo_check.returncode != 0:
            return {
                "status": "error",
                "error": "Not inside a git repository",
                "path": str(target),
            }

        status_result = subprocess.run(
            ["git", "-C", str(workdir), "status", "--short", "--branch"],
            capture_output=True,
            text=True,
        )

        return {
            "status": "ok",
            "path": str(target),
            "stdout": status_result.stdout,
            "stderr": status_result.stderr,
            "returncode": status_result.returncode,
        }

    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "path": path,
        }
