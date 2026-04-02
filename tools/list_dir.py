from __future__ import annotations

from tools.security import AGENT_ROOT, is_within_agent_root, resolve_under_agent_root


def list_dir(path: str = ".", include_hidden: bool = False):
    try:
        target = resolve_under_agent_root(path)

        if not is_within_agent_root(target):
            return {
                "status": "error",
                "error": f"Path not allowed: {target}",
                "agent_root": str(AGENT_ROOT),
            }

        if not target.exists():
            return {
                "status": "error",
                "error": "Directory does not exist",
                "path": str(target),
                "agent_root": str(AGENT_ROOT),
            }

        if not target.is_dir():
            return {
                "status": "error",
                "error": "Path is not a directory",
                "path": str(target),
                "agent_root": str(AGENT_ROOT),
            }
        
        entries = []
        for p in sorted(target.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            if not include_hidden and p.name.startswith("."):
                continue
            entries.append({
                "name": p.name,
                "path": str(p),
                "is_dir": p.is_dir(),
            })

        return {
            "status": "ok",
            "agent_root": str(AGENT_ROOT),
            "path": str(target),
            "count": len(entries),
            "entries": entries,
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "agent_root": str(AGENT_ROOT),
        }