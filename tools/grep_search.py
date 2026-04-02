from __future__ import annotations

import re
from pathlib import Path

from tools.security import AGENT_ROOT, is_hidden, is_likely_binary, is_within_agent_root, resolve_under_agent_root

MAX_FILE_BYTES = 500_000


def grep_search(
    query: str,
    path: str = ".",
    is_regex: bool = False,
    case_sensitive: bool = False,
    max_results: int = 200,
    include_hidden: bool = False,
):
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
                "agent_root": str(AGENT_ROOT),
            }

        flags = 0 if case_sensitive else re.IGNORECASE
        pattern_text = query if is_regex else re.escape(query)

        try:
            pattern = re.compile(pattern_text, flags)
        except re.error as e:
            return {
                "status": "error",
                "error": f"Invalid regex: {e}",
                "query": query,
            }

        if target.is_file():
            files = [target]
            base = target.parent
        else:
            files = sorted(p for p in target.rglob("*") if p.is_file())
            base = target

        results: list[dict[str, object]] = []
        scanned_files = 0

        for file_path in files:
            if not include_hidden and is_hidden(file_path, base):
                continue

            raw = file_path.read_bytes()
            if len(raw) > MAX_FILE_BYTES or is_likely_binary(raw):
                continue

            scanned_files += 1
            text = raw.decode("utf-8", errors="replace")

            for line_number, line in enumerate(text.splitlines(), start=1):
                if pattern.search(line):
                    results.append(
                        {
                            "path": str(file_path),
                            "line": line_number,
                            "text": line,
                        }
                    )
                    if len(results) >= max_results:
                        return {
                            "status": "ok",
                            "agent_root": str(AGENT_ROOT),
                            "query": query,
                            "is_regex": is_regex,
                            "case_sensitive": case_sensitive,
                            "path": str(target),
                            "max_results": max_results,
                            "truncated": True,
                            "scanned_files": scanned_files,
                            "results": results,
                        }

        return {
            "status": "ok",
            "agent_root": str(AGENT_ROOT),
            "query": query,
            "is_regex": is_regex,
            "case_sensitive": case_sensitive,
            "path": str(target),
            "max_results": max_results,
            "truncated": False,
            "scanned_files": scanned_files,
            "results": results,
        }

    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "agent_root": str(AGENT_ROOT),
        }

