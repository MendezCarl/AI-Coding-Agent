from __future__ import annotations

from tools.security import is_within_agent_root, is_likely_binary, resolve_under_agent_root

MAX_BYTES = 100_000


def read_file(path: str, start_line: int | None = None, end_line: int | None = None):
    try:
        file_path = resolve_under_agent_root(path)

        if not is_within_agent_root(file_path):
            return {
                "status": "error",
                "error": f"Path not allowed: {file_path}",
            }

        if not file_path.exists():
            return {
                "status": "error",
                "error": "File does not exist",
                "path": str(file_path),
            }

        if not file_path.is_file():
            return {
                "status": "error",
                "error": "Path is not a file",
                "path": str(file_path),
            }

        raw = file_path.read_bytes()

        if len(raw) > MAX_BYTES:
            return {
                "status": "error",
                "error": f"File too large ({len(raw)} bytes). Max allowed is {MAX_BYTES} bytes.",
                "path": str(file_path),
                "size": len(raw),
            }

        if is_likely_binary(raw):
            return {
                "status": "error",
                "error": "Binary file detected; refusing to read as text.",
                "path": str(file_path),
                "size": len(raw),
            }

        text = raw.decode("utf-8", errors="replace")
        lines = text.splitlines()

        total_lines = len(lines)

        if start_line is not None or end_line is not None:
            start = 1 if start_line is None else max(1, start_line)
            end = total_lines if end_line is None else min(total_lines, end_line)

            if start > end:
                return {
                    "status": "error",
                    "error": "start_line cannot be greater than end_line",
                    "path": str(file_path),
                }

            selected = lines[start - 1:end]
            content = "\n".join(selected)
        else:
            start = 1
            end = total_lines
            content = text

        return {
            "status": "ok",
            "path": str(file_path),
            "size": len(raw),
            "start_line": start,
            "end_line": end,
            "total_lines": total_lines,
            "content": content,
        }

    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "path": path,
        }
