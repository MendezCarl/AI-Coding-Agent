from __future__ import annotations

from datetime import datetime, UTC
from uuid import uuid4

from tools.vector_chroma import ChromaVectorStore, DEFAULT_INDEX_NAME
from tools.vector_store_adapter import VectorDocument

_store: ChromaVectorStore | None = None


def _get_store() -> ChromaVectorStore:
    global _store
    if _store is None:
        _store = ChromaVectorStore()
    return _store


def create_index(index_name: str = DEFAULT_INDEX_NAME, reset: bool = False):
    return _get_store().create_index(index_name=index_name, reset=reset)


def upsert_documents(index_name: str, documents: list[dict]):
    vector_docs: list[VectorDocument] = []

    for item in documents:
        content = (item.get("content") or "").strip()
        if not content:
            continue

        metadata = {
            "topic": item.get("topic"),
            "source_url": item.get("source_url"),
            "tags": ",".join(item.get("tags", [])),
            "updated_at": item.get("updated_at") or datetime.now(UTC).isoformat(),
            "ttl_days": item.get("ttl_days"),
            "confidence": item.get("confidence"),
        }

        metadata = {k: v for k, v in metadata.items() if v is not None}

        vector_docs.append(
            VectorDocument(
                id=item.get("id") or str(uuid4()),
                content=content,
                metadata=metadata,
            )
        )

    return _get_store().upsert_documents(index_name=index_name, documents=vector_docs)


def query_index(
    query: str,
    index_name: str = DEFAULT_INDEX_NAME,
    top_k: int = 5,
    topic: str | None = None,
):
    return _get_store().query_index(index_name=index_name, query=query, top_k=top_k, topic=topic)


def delete_topic(index_name: str, topic: str):
    return _get_store().delete_topic(index_name=index_name, topic=topic)
