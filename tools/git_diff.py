from __future__ import annotations

import subprocess

from pathlib import Path

from tools.security import AGENT_ROOT, is_within_agent_root, resolve_under_agent_root


def git_diff(path: str = ".", staged: bool = False):
    try:
        target = resolve_under_agent_root(path)

        if not is_within_agent_root(target):
            return {
                "status": "error",
                "error": f"Path not allowed: {target}",
                "agent_root": str(AGENT_ROOT),
            }

        workdir = target if target.is_dir() else target.parent

        repo_root_cmd = subprocess.run(
            ["git", "-C", str(workdir), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
        )

        if repo_root_cmd.returncode != 0:
            return {
                "status": "error",
                "error": "Not inside a git repository",
                "path": str(target),
            }

        repo_root = Path(repo_root_cmd.stdout.strip()).resolve()

        cmd = ["git", "-C", str(repo_root), "diff"]
        if staged:
            cmd.append("--staged")

        if target != repo_root:
            relative = target.relative_to(repo_root)
            cmd.extend(["--", str(relative)])

        result = subprocess.run(cmd, capture_output=True, text=True)

        return {
            "status": "ok",
            "path": str(target),
            "staged": staged,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
            "is_empty": result.stdout.strip() == "",
        }

    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "path": path,
        }
