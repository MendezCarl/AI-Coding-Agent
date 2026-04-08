from fastapi import APIRouter

from models.requests import (
    AnalyzeFailureRequest,
    ApplyPatchRequest,
    ApproveProposalRequest,
    AssistedFixRequest,
    CreateSessionRequest,
    CreateIndexRequest,
    DeleteTopicRequest,
    DiagnosticsRequest,
    ExecuteWorkflowAsyncRequest,
    ExecuteWorkflowSyncRequest,
    GetWorkflowRunRequest,
    GetSessionRequest,
    GitDiffRequest,
    GitStatusRequest,
    GetProposalRequest,
    GrepSearchRequest,
    ListDirRequest,
    ListProposalsRequest,
    ListSessionsRequest,
    OrchestrateTaskRequest,
    QueryIndexRequest,
    ReadRequest,
    RefreshProposalRequest,
    RejectProposalRequest,
    RunRequest,
    StageDocumentRequest,
    StageWebResultRequest,
    UpsertDocumentsRequest,
    WebFetchRequest,
    WebSearchRequest,
    WriteRequest,
)
from services.fix_service import fix_service
from services.orchestrator_service import WorkflowGuardError, orchestrator_service
from services.task_orchestrator_service import task_orchestrator_service
from services.tool_registry import tool_registry
from tools.safe_fetch import safe_fetch
from tools.sessions import cleanup_expired_sessions, create_session, get_session, list_sessions
from tools.staging import (
    approve_proposal,
    cleanup_expired,
    get_proposal,
    list_proposals,
    refresh_proposal,
    reject_proposal,
    stage_document,
)
from tools.vector_index import create_index, delete_topic, upsert_documents
from tools.web_search import web_search

router = APIRouter()


@router.post("/create_session")
async def create_agent_session(req: CreateSessionRequest):
    return create_session(
        ttl_hours=req.ttl_hours,
        metadata=req.metadata,
    )


@router.post("/get_session")
async def get_agent_session(req: GetSessionRequest):
    return get_session(
        session_id=req.session_id,
        include_messages=req.include_messages,
        include_turns=req.include_turns,
        limit=req.limit,
        offset=req.offset,
    )


@router.post("/list_sessions")
async def list_agent_sessions(req: ListSessionsRequest):
    return list_sessions(
        limit=req.limit,
        offset=req.offset,
        include_expired=req.include_expired,
    )


@router.post("/cleanup_expired_sessions")
async def cleanup_agent_sessions():
    return cleanup_expired_sessions()


@router.post("/execute_workflow_sync")
async def execute_workflow_sync(req: ExecuteWorkflowSyncRequest):
    try:
        return orchestrator_service.execute_sync(
            steps=[step.model_dump() for step in req.steps],
            session_id=req.session_id,
            metadata=req.metadata,
        )
    except WorkflowGuardError as e:
        return {
            "status": "error",
            "error": str(e),
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
        }


@router.post("/execute_workflow_async")
async def execute_workflow_async(req: ExecuteWorkflowAsyncRequest):
    try:
        return orchestrator_service.execute_async(
            steps=[step.model_dump() for step in req.steps],
            session_id=req.session_id,
            metadata=req.metadata,
        )
    except WorkflowGuardError as e:
        return {
            "status": "error",
            "error": str(e),
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
        }


@router.post("/get_workflow_run")
async def get_workflow_run(req: GetWorkflowRunRequest):
    return orchestrator_service.get_run(run_id=req.run_id)


@router.post("/analyze_failure")
async def analyze_failure(req: AnalyzeFailureRequest):
    return fix_service.analyze_failure(
        error_output=req.error_output,
        path=req.path,
        include_hidden=req.include_hidden,
        max_search_results=req.max_search_results,
    )


@router.post("/assisted_fix")
async def assisted_fix(req: AssistedFixRequest):
    return fix_service.assisted_fix(
        path=req.path,
        old_text=req.old_text,
        new_text=req.new_text,
        approved=req.approved,
        create_backup=req.create_backup,
        verify_command=req.verify_command,
        verify_cwd=req.verify_cwd,
        verify_timeout=req.verify_timeout,
    )


@router.post("/run")
async def run(req: RunRequest):
    return tool_registry.execute("run", req.model_dump())


@router.post("/read")
async def read(req: ReadRequest):
    return tool_registry.execute("read", req.model_dump())


@router.post("/write")
async def write(req: WriteRequest):
    return tool_registry.execute("write", req.model_dump())


@router.post("/list_dir")
async def list_directory(req: ListDirRequest):
    return tool_registry.execute("list_dir", req.model_dump())


@router.post("/grep_search")
async def grep(req: GrepSearchRequest):
    return tool_registry.execute("grep_search", req.model_dump())


@router.post("/apply_patch")
async def patch(req: ApplyPatchRequest):
    return tool_registry.execute("apply_patch", req.model_dump())


@router.post("/git_status")
async def status(req: GitStatusRequest):
    return tool_registry.execute("git_status", req.model_dump())


@router.post("/git_diff")
async def diff(req: GitDiffRequest):
    return tool_registry.execute("git_diff", req.model_dump())


@router.post("/diagnostics")
async def check_diagnostics(req: DiagnosticsRequest):
    return tool_registry.execute("diagnostics", req.model_dump())


@router.post("/create_index")
async def create_vector_index(req: CreateIndexRequest):
    return create_index(
        index_name=req.index_name,
        reset=req.reset,
    )


@router.post("/upsert_documents")
async def upsert_vector_documents(req: UpsertDocumentsRequest):
    return upsert_documents(
        index_name=req.index_name,
        documents=[doc.model_dump() for doc in req.documents],
    )


@router.post("/query_index")
async def query_vector_index(req: QueryIndexRequest):
    return tool_registry.execute("query_index", req.model_dump())


@router.post("/delete_topic")
async def delete_vector_topic(req: DeleteTopicRequest):
    return delete_topic(
        index_name=req.index_name,
        topic=req.topic,
    )


@router.post("/stage_document")
async def stage_vector_document(req: StageDocumentRequest):
    return stage_document(
        index_name=req.index_name,
        document=req.document.model_dump(),
        ttl_hours=req.ttl_hours,
    )


@router.post("/list_proposals")
async def list_staged_proposals(req: ListProposalsRequest):
    return list_proposals(
        index_name=req.index_name,
        status=req.status,
        limit=req.limit,
        offset=req.offset,
    )


@router.post("/get_proposal")
async def get_staged_proposal(req: GetProposalRequest):
    return get_proposal(proposal_id=req.proposal_id)


@router.post("/approve_proposal")
async def approve_staged_proposal(req: ApproveProposalRequest):
    return approve_proposal(
        proposal_id=req.proposal_id,
        approved_by=req.approved_by,
    )


@router.post("/reject_proposal")
async def reject_staged_proposal(req: RejectProposalRequest):
    return reject_proposal(
        proposal_id=req.proposal_id,
        reason=req.reason,
    )


@router.post("/refresh_proposal")
async def refresh_staged_proposal(req: RefreshProposalRequest):
    return refresh_proposal(
        proposal_id=req.proposal_id,
        action=req.action,
        ttl_hours=req.ttl_hours,
    )


@router.post("/cleanup_expired_proposals")
async def cleanup_staged_proposals():
    return cleanup_expired()


@router.post("/web_search")
async def search_web(req: WebSearchRequest):
    return web_search(
        query=req.query,
        max_results=req.max_results,
        allowed_domains=req.allowed_domains,
        blocked_domains=req.blocked_domains,
        safe_mode=req.safe_mode,
    )


@router.post("/web_fetch")
async def fetch_web(req: WebFetchRequest):
    return safe_fetch(
        url=req.url,
        max_chars=req.max_chars,
        timeout_seconds=req.timeout_seconds,
        max_size_bytes=req.max_size_bytes,
        output_format=req.output_format,
    )


@router.post("/stage_web_result")
async def stage_web_result(req: StageWebResultRequest):
    content = req.content.strip()
    if req.title:
        content = f"# {req.title}\n\n{content}"

    document = {
        "content": content,
        "topic": req.topic,
        "source_url": req.source_url,
        "tags": req.tags,
        "ttl_days": req.ttl_days,
        "confidence": req.confidence,
    }

    return stage_document(
        index_name=req.index_name,
        document=document,
        ttl_hours=req.proposal_ttl_hours,
    )


@router.post("/orchestrate_task")
async def orchestrate_task(req: OrchestrateTaskRequest):
    try:
        return await task_orchestrator_service.orchestrate(req)
    except WorkflowGuardError as e:
        return {"status": "error", "error": str(e)}
    except Exception as e:
        return {"status": "error", "error": str(e)}
