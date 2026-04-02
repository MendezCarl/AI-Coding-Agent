from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Any


@dataclass
class VectorDocument:
    id: str
    content: str
    metadata: dict[str, Any]


class VectorStoreAdapter(Protocol):
    def create_index(self, index_name: str, reset: bool = False) -> dict[str, Any]:
        ...

    def upsert_documents(self, index_name: str, documents: list[VectorDocument]) -> dict[str, Any]:
        ...

    def query_index(
        self,
        index_name: str,
        query: str,
        top_k: int,
        topic: str | None = None,
    ) -> dict[str, Any]:
        ...

    def delete_topic(self, index_name: str, topic: str) -> dict[str, Any]:
        ...
