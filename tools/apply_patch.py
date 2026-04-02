from __future__ import annotations

import tempfile

from pathlib import Path

from tools.security import AGENT_ROOT, is_within_agent_root, resolve_under_agent_root


def apply_patch(
    path: str,
    old_text: str,
    new_text: str,
    replace_all: bool = False,
    create_backup: bool = True,
):
    try:
        file_path = resolve_under_agent_root(path)

        if not is_within_agent_root(file_path):
            return {
                "status": "error",
                "error": f"Path not allowed: {file_path}",
                "agent_root": str(AGENT_ROOT),
            }

        if not file_path.exists() or not file_path.is_file():
            return {
                "status": "error",
                "error": "Path is not an existing file",
                "path": str(file_path),
            }

        if old_text == "":
            return {
                "status": "error",
                "error": "old_text cannot be empty",
                "path": str(file_path),
            }

        original = file_path.read_text(encoding="utf-8", errors="replace")
        occurrences = original.count(old_text)

        if occurrences == 0:
            return {
                "status": "error",
                "error": "old_text not found in file",
                "path": str(file_path),
            }

        if not replace_all and occurrences > 1:
            return {
                "status": "error",
                "error": "old_text appears multiple times; set replace_all=true to patch all matches",
                "path": str(file_path),
                "occurrences": occurrences,
            }

        replaced_count = occurrences if replace_all else 1
        updated = original.replace(old_text, new_text, -1 if replace_all else 1)

        backup_path = None
        if create_backup:
            backup_path = file_path.with_suffix(file_path.suffix + ".bak")
            backup_path.write_text(original, encoding="utf-8")

        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=file_path.parent,
            delete=False,
        ) as tmp:
            tmp.write(updated)
            temp_name = tmp.name

        Path(temp_name).replace(file_path)

        return {
            "status": "ok",
            "path": str(file_path),
            "replace_all": replace_all,
            "replaced_count": replaced_count,
            "backup_path": str(backup_path) if backup_path else None,
        }

    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "path": path,
        }
