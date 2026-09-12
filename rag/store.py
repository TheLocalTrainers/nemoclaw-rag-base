"""MongoDB-backed chunk store with text-index retrieval.

All defaults come from `rag.config` (nemoclaw-rag.toml + env overrides).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pymongo import ASCENDING, MongoClient, TEXT
from pymongo.collection import Collection
from pymongo.errors import OperationFailure

from rag.chunk import Chunk
from rag.config import Config, load_config


@dataclass(frozen=True)
class Hit:
    path: str
    chunk_id: int
    text: str
    start_line: int
    end_line: int
    score: float


class RagStore:
    """Persist and retrieve Markdown chunks in MongoDB.

    Retrieval uses a MongoDB text index over `text` and a punctuation-normalized
    `search_text` copy (so hyphenated tokens such as NEON-BEACON-42 match), with
    an optional regex fallback when the text query returns nothing.
    """

    def __init__(
        self,
        uri: str | None = None,
        *,
        database: str | None = None,
        collection: str | None = None,
        config: Config | None = None,
    ) -> None:
        self.config = config or load_config()
        mongo = self.config.mongodb
        self.uri = (uri or mongo.uri).strip()
        self.database_name = (database or mongo.database).strip()
        self.collection_name = (collection or mongo.collection).strip()
        self._client = MongoClient(
            self.uri,
            serverSelectionTimeoutMS=mongo.server_selection_timeout_ms,
        )
        # Fail fast if Mongo is unreachable.
        self._client.admin.command("ping")
        self._col: Collection = self._client[self.database_name][self.collection_name]
        self._ensure_indexes()

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> RagStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _ensure_indexes(self) -> None:
        self._col.create_index(
            [("path", ASCENDING), ("chunk_id", ASCENDING)],
            unique=True,
            name="path_chunk_unique",
        )
        self._ensure_text_index()

    def _ensure_text_index(self) -> None:
        desired = [("text", TEXT), ("search_text", TEXT)]
        try:
            self._col.create_index(desired, name="chunks_text", default_language="english")
            return
        except OperationFailure:
            pass
        # MongoDB allows only one text index per collection; drop a conflicting one.
        for index in self._col.list_indexes():
            if index.get("weights"):
                self._col.drop_index(index["name"])
        self._col.create_index(desired, name="chunks_text", default_language="english")

    def clear(self) -> None:
        self._col.delete_many({})

    def upsert_chunks(self, chunks: list[Chunk]) -> int:
        if not chunks:
            return 0
        paths = {c.path for c in chunks}
        self._col.delete_many({"path": {"$in": list(paths)}})
        docs = [
            {
                "path": c.path,
                "chunk_id": c.chunk_id,
                "text": c.text,
                # Helps hyphenated tokens (NEON-BEACON-42) match via text index.
                "search_text": _normalize_for_search(c.text),
                "start_line": c.start_line,
                "end_line": c.end_line,
            }
            for c in chunks
        ]
        self._col.insert_many(docs)
        return len(chunks)

    def delete_paths_except(self, keep_paths: set[str]) -> int:
        """Remove chunks whose path is not in keep_paths (incremental sync)."""
        if not keep_paths:
            result = self._col.delete_many({})
            return int(result.deleted_count)
        result = self._col.delete_many({"path": {"$nin": list(keep_paths)}})
        return int(result.deleted_count)

    def count(self) -> int:
        return int(self._col.count_documents({}))

    def search(self, query: str, *, top_k: int | None = None) -> list[Hit]:
        retrieval = self.config.retrieval
        limit = max(1, int(top_k if top_k is not None else retrieval.top_k))
        tokens = _tokens(query, min_length=retrieval.min_token_length)
        if not tokens:
            return []

        hits: list[Hit] = []
        try:
            cursor = (
                self._col.find(
                    {"$text": {"$search": _text_search_query(tokens)}},
                    {"score": {"$meta": "textScore"}},
                )
                .sort([("score", {"$meta": "textScore"})])
                .limit(limit)
            )
            hits = [_hit_from_doc(doc, float(doc.get("score", 0.0))) for doc in cursor]
        except OperationFailure:
            hits = []

        if hits or not retrieval.regex_fallback:
            return hits

        pattern = "|".join(re.escape(t) for t in tokens)
        cursor = self._col.find({"text": {"$regex": pattern, "$options": "i"}}).limit(limit)
        return [_hit_from_doc(doc, 0.0) for doc in cursor]


def open_store(
    *,
    uri: str | None = None,
    database: str | None = None,
    collection: str | None = None,
    config: Config | None = None,
) -> RagStore:
    return RagStore(uri=uri, database=database, collection=collection, config=config)


def _hit_from_doc(doc: dict, score: float) -> Hit:
    return Hit(
        path=str(doc["path"]),
        chunk_id=int(doc["chunk_id"]),
        text=str(doc["text"]),
        start_line=int(doc["start_line"]),
        end_line=int(doc["end_line"]),
        score=score,
    )


def _normalize_for_search(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _tokens(raw: str, *, min_length: int = 2) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", raw.lower()) if len(t) >= min_length]


def _text_search_query(tokens: list[str]) -> str:
    """Build a MongoDB $text query string; tokens are quoted so operators cannot leak."""
    return " ".join(f'"{t}"' for t in tokens)
