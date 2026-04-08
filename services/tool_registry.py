from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from tools.apply_patch import apply_patch
from tools.diagnostics import diagnostics
from tools.git_diff import git_diff
from tools.git_status import git_status
from tools.grep_search import grep_search
from tools.list_dir import list_dir
from tools.read import read_file
from tools.run import run_command
from tools.vector_index import query_index
from tools.write import write_file

MAX_WORKFLOW_RUN_TIMEOUT = 120
MAX_WORKFLOW_STEPS = 20


@dataclass(frozen=True)
class ToolSpec:
    name: str
    handler: Callable[[dict, bool], dict]
    workflow_enabled: bool = True
    # True = tool must be executed on the client laptop, not on the remote server
    local: bool = False


class ToolRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {
            # Client-local tools: executed on the laptop, not on the server
            "apply_patch": ToolSpec("apply_patch", self._handle_apply_patch, local=True),
            "diagnostics": ToolSpec("diagnostics", self._handle_diagnostics, local=True),
            "git_diff": ToolSpec("git_diff", self._handle_git_diff, local=True),
            "git_status": ToolSpec("git_status", self._handle_git_status, local=True),
            "grep_search": ToolSpec("grep_search", self._handle_grep_search, local=True),
            "list_dir": ToolSpec("list_dir", self._handle_list_dir, local=True),
            "read": ToolSpec("read", self._handle_read, local=True),
            "run": ToolSpec("run", self._handle_run, local=True),
            "write": ToolSpec("write", self._handle_write, local=True),
            # Server-side tools: executed on the remote server
            "query_index": ToolSpec("query_index", self._handle_query_index, local=False),
        }

    def execute(self, tool_name: str, args: dict, for_workflow: bool = False) -> dict:
        spec = self._specs.get(tool_name)
        if not spec:
            return {
                "status": "error",
                "error": f"Unsupported tool: {tool_name}",
            }
        if for_workflow and not spec.workflow_enabled:
            return {
                "status": "error",
                "error": f"Tool is not allowed in workflows: {tool_name}",
            }

        try:
            return spec.handler(dict(args or {}), for_workflow)
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "tool": tool_name,
            }

    def get_spec(self, tool_name: str) -> ToolSpec | None:
        return self._specs.get(tool_name)

    def list_workflow_tools(self) -> list[str]:
        return sorted(name for name, spec in self._specs.items() if spec.workflow_enabled)

    def list_local_tools(self) -> list[str]:
        return sorted(name for name, spec in self._specs.items() if spec.local)

    @staticmethod
    def _require(args: dict, key: str) -> str:
        value = args.get(key)
        if value is None or value == "":
            raise ValueError(f"Missing required argument: {key}")
        return str(value)

    def _handle_apply_patch(self, args: dict, _: bool) -> dict:
        return apply_patch(
            path=self._require(args, "path"),
            old_text=self._require(args, "old_text"),
            new_text=self._require(args, "new_text"),
            replace_all=bool(args.get("replace_all", False)),
            create_backup=bool(args.get("create_backup", True)),
        )

    def _handle_diagnostics(self, args: dict, _: bool) -> dict:
        return diagnostics(
            path=str(args.get("path", ".")),
            include_hidden=bool(args.get("include_hidden", False)),
        )

    def _handle_git_diff(self, args: dict, _: bool) -> dict:
        return git_diff(
            path=str(args.get("path", ".")),
            staged=bool(args.get("staged", False)),
        )

    def _handle_git_status(self, args: dict, _: bool) -> dict:
        return git_status(path=str(args.get("path", ".")))

    def _handle_grep_search(self, args: dict, for_workflow: bool) -> dict:
        max_results = int(args.get("max_results", 200))
        if for_workflow:
            max_results = min(max_results, 200)
        return grep_search(
            query=self._require(args, "query"),
            path=str(args.get("path", ".")),
            is_regex=bool(args.get("is_regex", False)),
            case_sensitive=bool(args.get("case_sensitive", False)),
            max_results=max_results,
            include_hidden=bool(args.get("include_hidden", False)),
        )

    def _handle_list_dir(self, args: dict, _: bool) -> dict:
        return list_dir(
            path=str(args.get("path", ".")),
            include_hidden=bool(args.get("include_hidden", False)),
        )

    def _handle_query_index(self, args: dict, for_workflow: bool) -> dict:
        top_k = int(args.get("top_k", 5))
        if for_workflow:
            top_k = min(top_k, 20)
        return query_index(
            query=self._require(args, "query"),
            index_name=str(args.get("index_name", "knowledge")),
            top_k=top_k,
            topic=args.get("topic"),
        )

    def _handle_read(self, args: dict, _: bool) -> dict:
        return read_file(
            path=self._require(args, "path"),
            start_line=args.get("start_line"),
            end_line=args.get("end_line"),
        )

    def _handle_run(self, args: dict, for_workflow: bool) -> dict:
        timeout = int(args.get("timeout", 30))
        if for_workflow:
            timeout = min(timeout, MAX_WORKFLOW_RUN_TIMEOUT)
        return run_command(
            command=self._require(args, "command"),
            cwd=args.get("cwd"),
            timeout=timeout,
        )

    def _handle_write(self, args: dict, _: bool) -> dict:
        return write_file(
            path=self._require(args, "path"),
            content=self._require(args, "content"),
            make_backup=bool(args.get("make_backup", True)),
            create_parents=bool(args.get("create_parents", True)),
        )


tool_registry = ToolRegistry()
