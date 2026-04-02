from __future__ import annotations

from pathlib import Path

# Fixed root captured when the agent process starts.
AGENT_ROOT = Path.cwd().resolve()


def is_within_agent_root(path: Path) -> bool:
    resolved = path.expanduser().resolve()
    return resolved == AGENT_ROOT or AGENT_ROOT in resolved.parents


def resolve_under_agent_root(path: str) -> Path:
    return (AGENT_ROOT / path).resolve()


def is_hidden(path: Path, base: Path) -> bool:
    try:
        relative = path.relative_to(base)
    except ValueError:
        return False
    return any(part.startswith(".") for part in relative.parts)


def is_likely_binary(data: bytes) -> bool:
    return b"\x00" in data
