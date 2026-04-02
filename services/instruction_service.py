from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tools.security import AGENT_ROOT

DOCS_DIR = AGENT_ROOT / "docs"
INSTRUCTIONS_DIR = DOCS_DIR / "instructions"
MAX_FILE_CHARS = 5000
MAX_TOTAL_CHARS = 20000
EXCLUDED_FILES = {"README.md"}


@dataclass
class _CacheState:
    signature: tuple[tuple[str, int, int], ...]
    payload: dict[str, Any]


class InstructionService:
    def __init__(self) -> None:
        self._cache: dict[str, _CacheState] = {}

    def _discover_markdown_files(self, include_legacy_docs: bool = False) -> list[Path]:
        files: set[Path] = set()

        if INSTRUCTIONS_DIR.exists() and INSTRUCTIONS_DIR.is_dir():
            for path in INSTRUCTIONS_DIR.rglob("*.md"):
                if path.name in EXCLUDED_FILES:
                    continue
                files.add(path)

        if include_legacy_docs and DOCS_DIR.exists() and DOCS_DIR.is_dir():
            for path in DOCS_DIR.rglob("*.md"):
                if path.name in EXCLUDED_FILES:
                    continue
                if path == DOCS_DIR / "README.md":
                    continue
                # Keep strict instructions as primary source; include other docs only in legacy mode.
                if INSTRUCTIONS_DIR in path.parents:
                    continue
                files.add(path)

        return sorted(files)

    def _signature(self, files: list[Path]) -> tuple[tuple[str, int, int], ...]:
        signature: list[tuple[str, int, int]] = []
        for path in files:
            stat = path.stat()
            signature.append((str(path.relative_to(AGENT_ROOT)), stat.st_mtime_ns, stat.st_size))
        return tuple(signature)

    @staticmethod
    def _is_hard_truth(filename: str) -> bool:
        stem = Path(filename).stem
        has_alpha = any(ch.isalpha() for ch in stem)
        return has_alpha and stem == stem.upper()

    @staticmethod
    def _load_file_content(path: Path) -> str:
        content = path.read_text(encoding="utf-8", errors="ignore").strip()
        if len(content) > MAX_FILE_CHARS:
            content = content[:MAX_FILE_CHARS].rstrip() + "\n\n[truncated]"
        return content

    def load(self, include_legacy_docs: bool = False) -> dict[str, Any]:
        cache_key = "legacy" if include_legacy_docs else "strict"
        files = self._discover_markdown_files(include_legacy_docs=include_legacy_docs)
        signature = self._signature(files)

        cache_state = self._cache.get(cache_key)
        if cache_state and cache_state.signature == signature:
            cached = dict(cache_state.payload)
            cached["cache_hit"] = True
            return cached

        hard_truths: list[dict[str, str]] = []
        guidance: list[dict[str, str]] = []
        used_chars = 0

        for path in files:
            content = self._load_file_content(path)
            if not content:
                continue

            remaining = MAX_TOTAL_CHARS - used_chars
            if remaining <= 0:
                break
            if len(content) > remaining:
                content = content[:remaining].rstrip() + "\n\n[truncated]"

            record = {
                "path": str(path.relative_to(AGENT_ROOT)),
                "content": content,
            }
            if self._is_hard_truth(path.name):
                hard_truths.append(record)
            else:
                guidance.append(record)
            used_chars += len(content)

        payload = {
            "hard_truths": hard_truths,
            "guidance": guidance,
            "cache_hit": False,
            "excluded_files": sorted(EXCLUDED_FILES),
            "source_policy": "docs+legacy" if include_legacy_docs else "instructions-only",
            "instructions_dir": str(INSTRUCTIONS_DIR.relative_to(AGENT_ROOT)),
            "legacy_docs_enabled": include_legacy_docs,
        }
        self._cache[cache_key] = _CacheState(signature=signature, payload=payload)
        return dict(payload)


instruction_service = InstructionService()
