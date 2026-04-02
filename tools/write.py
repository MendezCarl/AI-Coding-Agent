from __future__ import annotations

import tempfile
from pathlib import Path

from tools.security import is_within_agent_root, resolve_under_agent_root


def write_file(
    path: str,
    content: str,
    make_backup: bool = True,
    create_parents: bool = True,
):
    try:
        file_path = resolve_under_agent_root(path)

        if not is_within_agent_root(file_path):
            return {
                "status": "error",
                "error": f"Path not allowed: {file_path}",
            }

        if create_parents:
            file_path.parent.mkdir(parents=True, exist_ok=True)

        backup_path = None
        existed_before = file_path.exists()

        if existed_before and make_backup:
            backup_path = file_path.with_suffix(file_path.suffix + ".bak")
            backup_path.write_text(file_path.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")

        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=file_path.parent,
            delete=False,
        ) as tmp:
            tmp.write(content)
            temp_name = tmp.name

        Path(temp_name).replace(file_path)

        return {
            "status": "ok",
            "path": str(file_path),
            "bytes_written": len(content.encode("utf-8")),
            "backup_path": str(backup_path) if backup_path else None,
            "existed_before": existed_before,
        }

    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "path": path,
        }
