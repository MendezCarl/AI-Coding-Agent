from __future__ import annotations

from pathlib import Path

from tools.security import AGENT_ROOT, is_hidden, is_within_agent_root, resolve_under_agent_root

MAX_FILES = 500


def diagnostics(path: str = ".", include_hidden: bool = False):
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
                "error": "Path does not exist",
                "path": str(target),
            }

        if target.is_file():
            files = [target] if target.suffix == ".py" else []
            base = target.parent
        else:
            files = sorted(p for p in target.rglob("*.py") if p.is_file())
            base = target

        checked = 0
        errors = []

        for file_path in files:
            if checked >= MAX_FILES:
                break
            if not include_hidden and is_hidden(file_path, base):
                continue

            checked += 1

            try:
                source = file_path.read_text(encoding="utf-8", errors="replace")
                compile(source, str(file_path), "exec")
            except SyntaxError as e:
                errors.append(
                    {
                        "path": str(file_path),
                        "line": e.lineno,
                        "column": e.offset,
                        "error": e.msg,
                    }
                )

        return {
            "status": "ok",
            "agent_root": str(AGENT_ROOT),
            "path": str(target),
            "checked_files": checked,
            "max_files": MAX_FILES,
            "truncated": checked >= MAX_FILES,
            "error_count": len(errors),
            "errors": errors,
        }

    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "path": path,
        }
