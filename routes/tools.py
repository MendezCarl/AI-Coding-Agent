from fastapi import APIRouter

from models.requests import (
    ApplyPatchRequest,
    ApproveProposalRequest,
    CreateIndexRequest,
    DeleteTopicRequest,
    DiagnosticsRequest,
    GitDiffRequest,
    GitStatusRequest,
    GetProposalRequest,
    GrepSearchRequest,
    ListDirRequest,
    ListProposalsRequest,
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
from tools.apply_patch import apply_patch
from tools.diagnostics import diagnostics
from tools.git_diff import git_diff
from tools.git_status import git_status
from tools.grep_search import grep_search
from tools.list_dir import list_dir
from tools.read import read_file
from tools.run import run_command
from tools.safe_fetch import safe_fetch
from tools.staging import (
    approve_proposal,
    cleanup_expired,
    get_proposal,
    list_proposals,
    refresh_proposal,
    reject_proposal,
    stage_document,
)
from tools.vector_index import create_index, delete_topic, query_index, upsert_documents
from tools.web_search import web_search
from tools.write import write_file

router = APIRouter()


@router.post("/run")
async def run(req: RunRequest):
    return run_command(
        command=req.command,
        cwd=req.cwd,
        timeout=req.timeout,
    )


@router.post("/read")
async def read(req: ReadRequest):
    return read_file(
        path=req.path,
        start_line=req.start_line,
        end_line=req.end_line,
    )


@router.post("/write")
async def write(req: WriteRequest):
    return write_file(
        path=req.path,
        content=req.content,
        make_backup=req.make_backup,
        create_parents=req.create_parents,
    )


@router.post("/list_dir")
async def list_directory(req: ListDirRequest):
    return list_dir(
        path=req.path,
        include_hidden=req.include_hidden,
    )


@router.post("/grep_search")
async def grep(req: GrepSearchRequest):
    return grep_search(
        query=req.query,
        path=req.path,
        is_regex=req.is_regex,
        case_sensitive=req.case_sensitive,
        max_results=req.max_results,
        include_hidden=req.include_hidden,
    )


@router.post("/apply_patch")
async def patch(req: ApplyPatchRequest):
    return apply_patch(
        path=req.path,
        old_text=req.old_text,
        new_text=req.new_text,
        replace_all=req.replace_all,
        create_backup=req.create_backup,
    )


@router.post("/git_status")
async def status(req: GitStatusRequest):
    return git_status(path=req.path)


@router.post("/git_diff")
async def diff(req: GitDiffRequest):
    return git_diff(
        path=req.path,
        staged=req.staged,
    )


@router.post("/diagnostics")
async def check_diagnostics(req: DiagnosticsRequest):
    return diagnostics(
        path=req.path,
        include_hidden=req.include_hidden,
    )


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
    return query_index(
        index_name=req.index_name,
        query=req.query,
        top_k=req.top_k,
        topic=req.topic,
    )


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
