from __future__ import annotations

from pathlib import Path
from typing import Any

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from tools.security import AGENT_ROOT
from tools.vector_store_adapter import VectorDocument

DEFAULT_INDEX_NAME = "knowledge"
EMBED_MODEL = "all-MiniLM-L6-v2"
DB_DIR = AGENT_ROOT / ".agent_data" / "chroma"


class ChromaVectorStore:
    def __init__(self, db_dir: Path = DB_DIR, embedding_model: str = EMBED_MODEL):
        db_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(db_dir))
        self._embedding_fn: Any = SentenceTransformerEmbeddingFunction(model_name=embedding_model)

    def _collection(self, index_name: str):
        return self._client.get_or_create_collection(
            name=index_name,
            embedding_function=self._embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )

    def create_index(self, index_name: str, reset: bool = False) -> dict[str, Any]:
        if reset:
            try:
                self._client.delete_collection(index_name)
            except Exception:
                # Collection may not exist yet.
                pass

        self._collection(index_name)

        return {
            "status": "ok",
            "index_name": index_name,
            "db_dir": str(DB_DIR),
            "reset": reset,
        }

    def upsert_documents(self, index_name: str, documents: list[VectorDocument]) -> dict[str, Any]:
        if not documents:
            return {
                "status": "error",
                "error": "No documents provided",
                "index_name": index_name,
            }

        collection = self._collection(index_name)

        ids = [doc.id for doc in documents]
        texts = [doc.content for doc in documents]
        metadatas: list[dict[str, str | int | float | bool]] = []
        for doc in documents:
            clean = {
                key: value
                for key, value in doc.metadata.items()
                if isinstance(value, (str, int, float, bool))
            }
            metadatas.append(clean)

        collection.upsert(ids=ids, documents=texts, metadatas=metadatas)  # type: ignore[arg-type]

        return {
            "status": "ok",
            "index_name": index_name,
            "upserted": len(documents),
        }

    def query_index(
        self,
        index_name: str,
        query: str,
        top_k: int,
        topic: str | None = None,
    ) -> dict[str, Any]:
        collection = self._collection(index_name)

        where: Any = {"topic": topic} if topic else None
        result = collection.query(
            query_texts=[query],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        ids = result.get("ids", [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]

        hits = []
        for item_id, content, metadata, distance in zip(ids, documents, metadatas, distances):
            hits.append(
                {
                    "id": item_id,
                    "content": content,
                    "metadata": metadata or {},
                    "distance": distance,
                }
            )

        return {
            "status": "ok",
            "index_name": index_name,
            "query": query,
            "top_k": top_k,
            "topic": topic,
            "hits": hits,
            "count": len(hits),
        }

    def delete_topic(self, index_name: str, topic: str) -> dict[str, Any]:
        collection = self._collection(index_name)

        to_delete = collection.get(where={"topic": topic}, include=[])
        ids = to_delete.get("ids", [])

        if ids:
            collection.delete(ids=ids)

        return {
            "status": "ok",
            "index_name": index_name,
            "topic": topic,
            "deleted": len(ids),
        }
