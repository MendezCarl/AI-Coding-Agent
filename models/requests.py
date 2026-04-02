from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    prompt: str
    use_retrieval: bool = True
    top_k: int = Field(default=5, ge=1, le=20)
    index_name: str = "knowledge"


class RunRequest(BaseModel):
    command: str
    cwd: str | None = None
    timeout: int = 30


class ReadRequest(BaseModel):
    path: str
    start_line: int | None = None
    end_line: int | None = None


class WriteRequest(BaseModel):
    path: str
    content: str
    make_backup: bool = True
    create_parents: bool = True


class ListDirRequest(BaseModel):
    path: str = "."
    include_hidden: bool = False


class GrepSearchRequest(BaseModel):
    query: str
    path: str = "."
    is_regex: bool = False
    case_sensitive: bool = False
    max_results: int = Field(default=200, ge=1, le=2000)
    include_hidden: bool = False


class ApplyPatchRequest(BaseModel):
    path: str
    old_text: str
    new_text: str
    replace_all: bool = False
    create_backup: bool = True


class GitStatusRequest(BaseModel):
    path: str = "."


class GitDiffRequest(BaseModel):
    path: str = "."
    staged: bool = False


class DiagnosticsRequest(BaseModel):
    path: str = "."
    include_hidden: bool = False


class CreateIndexRequest(BaseModel):
    index_name: str = "knowledge"
    reset: bool = False


class UpsertDocumentInput(BaseModel):
    id: str | None = None
    content: str
    topic: str | None = None
    source_url: str | None = None
    tags: list[str] = Field(default_factory=list)
    updated_at: str | None = None
    ttl_days: int | None = Field(default=None, ge=1)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class UpsertDocumentsRequest(BaseModel):
    index_name: str = "knowledge"
    documents: list[UpsertDocumentInput]


class QueryIndexRequest(BaseModel):
    index_name: str = "knowledge"
    query: str
    top_k: int = Field(default=5, ge=1, le=20)
    topic: str | None = None


class DeleteTopicRequest(BaseModel):
    index_name: str = "knowledge"
    topic: str


class StageDocumentRequest(BaseModel):
    index_name: str = "knowledge"
    document: UpsertDocumentInput
    ttl_hours: int = Field(default=168, ge=1, le=720)


class ListProposalsRequest(BaseModel):
    index_name: str | None = None
    status: str | None = None
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class GetProposalRequest(BaseModel):
    proposal_id: str


class ApproveProposalRequest(BaseModel):
    proposal_id: str
    approved_by: str | None = None


class RejectProposalRequest(BaseModel):
    proposal_id: str
    reason: str = ""


class RefreshProposalRequest(BaseModel):
    proposal_id: str
    action: str
    ttl_hours: int = Field(default=168, ge=1, le=720)


class WebSearchRequest(BaseModel):
    query: str
    max_results: int = Field(default=5, ge=1, le=10)
    allowed_domains: list[str] = Field(default_factory=list)
    blocked_domains: list[str] = Field(default_factory=list)
    safe_mode: bool = True


class WebFetchRequest(BaseModel):
    url: str
    max_chars: int = Field(default=12000, ge=500, le=50000)
    timeout_seconds: int = Field(default=10, ge=3, le=60)
    max_size_bytes: int = Field(default=1_000_000, ge=10_000, le=5_000_000)
    output_format: str = "markdown"


class StageWebResultRequest(BaseModel):
    index_name: str = "knowledge"
    source_url: str
    content: str
    title: str | None = None
    topic: str = "web"
    tags: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    ttl_days: int = Field(default=30, ge=1, le=365)
    proposal_ttl_hours: int = Field(default=168, ge=1, le=720)


class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str | None = None
    source: str | None = None
    rank: int | None = None


class WebSearchResponse(BaseModel):
    status: str
    query: str
    results: list[SearchResult] = Field(default_factory=list)
    blocked_count: int = 0
    error: str | None = None


class Citation(BaseModel):
    url: str
    title: str | None = None
    fetched_at: str | None = None


class WebFetchResponse(BaseModel):
    status: str
    url: str
    title: str | None = None
    content: str | None = None
    content_type: str | None = None
    char_count: int = 0
    citation: Citation | None = None
    error: str | None = None