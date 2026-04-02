from __future__ import annotations

import re

from tools.apply_patch import apply_patch
from tools.diagnostics import diagnostics
from tools.grep_search import grep_search
from tools.run import run_command

FILE_LINE_RE = re.compile(r"(?P<path>[A-Za-z0-9_./\\-]+\.py):(?P<line>\d+)(?::(?P<column>\d+))?")
NAME_ERROR_RE = re.compile(r"name ['\"](?P<symbol>[^'\"]+)['\"] is not defined")
MODULE_ERROR_RE = re.compile(r"No module named ['\"](?P<module>[^'\"]+)['\"]")
ATTRIBUTE_ERROR_RE = re.compile(r"has no attribute ['\"](?P<attribute>[^'\"]+)['\"]")
VERIFY_TIMEOUT_CAP = 120


class FixService:
    def analyze_failure(
        self,
        error_output: str,
        path: str | None = None,
        include_hidden: bool = False,
        max_search_results: int = 20,
    ) -> dict:
        normalized = (error_output or "").strip()
        if not normalized:
            return {
                "status": "error",
                "error": "error_output cannot be empty",
            }

        error_types = self._classify_error_types(normalized)
        file_references = self._extract_file_references(normalized)
        symbol_hints = self._extract_symbol_hints(normalized)
        suggestions = self._build_suggestions(error_types, symbol_hints, path)

        related_searches = []
        for hint in symbol_hints:
            query = hint["value"]
            if not query or hint["kind"] not in {"symbol", "module", "attribute"}:
                continue
            search_result = grep_search(
                query=query,
                path=path or ".",
                is_regex=False,
                case_sensitive=True,
                max_results=min(max_search_results, 20),
                include_hidden=include_hidden,
            )
            if search_result.get("status") == "ok":
                related_searches.append(
                    {
                        "kind": hint["kind"],
                        "query": query,
                        "results": search_result.get("results", []),
                        "truncated": search_result.get("truncated", False),
                    }
                )

        diagnostics_result = None
        if path:
            diagnostics_result = diagnostics(path=path, include_hidden=include_hidden)

        return {
            "status": "ok",
            "summary": suggestions[0] if suggestions else "Review the reported failure and inspect referenced files.",
            "error_types": error_types,
            "file_references": file_references,
            "symbol_hints": symbol_hints,
            "suggestions": suggestions,
            "related_searches": related_searches,
            "diagnostics": diagnostics_result,
        }

    def assisted_fix(
        self,
        path: str,
        old_text: str,
        new_text: str,
        approved: bool,
        create_backup: bool = True,
        verify_command: str | None = None,
        verify_cwd: str | None = None,
        verify_timeout: int = 60,
    ) -> dict:
        if not approved:
            return {
                "status": "error",
                "error": "Fix application requires explicit approval (approved=true)",
                "path": path,
            }

        patch_result = apply_patch(
            path=path,
            old_text=old_text,
            new_text=new_text,
            replace_all=False,
            create_backup=create_backup,
        )
        if patch_result.get("status") != "ok":
            return {
                "status": "error",
                "error": patch_result.get("error", "Patch application failed"),
                "path": path,
                "patch": patch_result,
            }

        verification = None
        verification_succeeded = None
        if verify_command:
            verification = run_command(
                command=verify_command,
                cwd=verify_cwd,
                timeout=min(int(verify_timeout), VERIFY_TIMEOUT_CAP),
            )
            verification_succeeded = (
                verification.get("status") == "ok" and verification.get("returncode") == 0
            )

        return {
            "status": "ok",
            "approved": True,
            "patch": patch_result,
            "verification": {
                "attempted": bool(verify_command),
                "succeeded": verification_succeeded,
                "result": verification,
            },
        }

    @staticmethod
    def _classify_error_types(error_output: str) -> list[str]:
        error_types = []
        for candidate in [
            "SyntaxError",
            "NameError",
            "ModuleNotFoundError",
            "ImportError",
            "AttributeError",
            "TypeError",
            "AssertionError",
        ]:
            if candidate in error_output:
                error_types.append(candidate)
        return error_types

    @staticmethod
    def _extract_file_references(error_output: str) -> list[dict]:
        seen: set[tuple[str, int, int | None]] = set()
        refs = []
        for match in FILE_LINE_RE.finditer(error_output):
            path = match.group("path")
            line = int(match.group("line"))
            column = match.group("column")
            key = (path, line, int(column) if column else None)
            if key in seen:
                continue
            seen.add(key)
            refs.append(
                {
                    "path": path,
                    "line": line,
                    "column": int(column) if column else None,
                }
            )
        return refs

    @staticmethod
    def _extract_symbol_hints(error_output: str) -> list[dict]:
        hints = []
        name_match = NAME_ERROR_RE.search(error_output)
        if name_match:
            hints.append({"kind": "symbol", "value": name_match.group("symbol")})
        module_match = MODULE_ERROR_RE.search(error_output)
        if module_match:
            hints.append({"kind": "module", "value": module_match.group("module")})
        attribute_match = ATTRIBUTE_ERROR_RE.search(error_output)
        if attribute_match:
            hints.append({"kind": "attribute", "value": attribute_match.group("attribute")})
        return hints

    @staticmethod
    def _build_suggestions(error_types: list[str], symbol_hints: list[dict], path: str | None) -> list[str]:
        suggestions = []
        if "SyntaxError" in error_types:
            suggestions.append("Run diagnostics on the failing file or directory and inspect the reported line/column first.")
        if "NameError" in error_types:
            suggestions.append("Check whether the missing symbol needs an import, definition, or a spelling fix.")
        if "ModuleNotFoundError" in error_types or "ImportError" in error_types:
            suggestions.append("Verify the import path and dependency installation before changing unrelated code.")
        if "AttributeError" in error_types:
            suggestions.append("Inspect the object type and confirm the referenced attribute exists on the concrete value.")
        if "AssertionError" in error_types:
            suggestions.append("Compare expected and actual values in the failing test before changing production code.")
        if path:
            suggestions.append(f"Focus analysis on {path} first to keep the fix narrow.")
        if symbol_hints and not suggestions:
            suggestions.append("Search for the hinted symbol/module in the repository and trace where it should be defined.")
        if not suggestions:
            suggestions.append("Start with the first referenced file and reproduce the failure with the smallest possible command.")
        return suggestions


fix_service = FixService()
