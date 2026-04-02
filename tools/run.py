from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from tools.security import AGENT_ROOT, is_within_agent_root, resolve_under_agent_root

BLOCKED_COMMAND_PREFIXES = [
    "rm -rf /",
    "sudo rm",
    "mkfs",
    "shutdown",
    "reboot",
]

DEFAULT_TIMEOUT = 30


def run_command(command: str, cwd: str | None = None, timeout: int = DEFAULT_TIMEOUT):
    try:
        stripped = command.strip()

        for blocked in BLOCKED_COMMAND_PREFIXES:
            if stripped.startswith(blocked):
                return {
                    "status": "error",
                    "error": f"Blocked dangerous command: {blocked}",
                }

        workdir = resolve_under_agent_root(cwd) if cwd else AGENT_ROOT

        if not is_within_agent_root(workdir):
            return {
                "status": "error",
                "error": f"Working directory not allowed: {workdir}",
            }

        args = shlex.split(command)

        result = subprocess.run(
            args,
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        return {
            "status": "ok",
            "command": command,
            "cwd": str(workdir),
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }

    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "error": f"Command timed out after {timeout} seconds",
            "command": command,
            "cwd": str(cwd) if cwd else str(Path.cwd()),
        }
    except FileNotFoundError:
        return {
            "status": "error",
            "error": "Command not found",
            "command": command,
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "command": command,
        }
