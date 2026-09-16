"""SQLite-backed cache of embedding vectors keyed by (model, role, sha256(text)).

Eliminates repeated calls to the embedding model for stable inputs (e.g. catalog
asset descriptions, which rarely change between queries). Vectors are stored as
float32 BLOBs.
"""
from __future__ import annotations

import hashlib
import logging
import os
import sqlite3
import struct
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DEFAULT_PATH = Path.home() / ".edc-agent" / "embedding_cache.sqlite"


def _default_cache_path() -> Path:
    override = os.getenv("EMBEDDING_CACHE_PATH")
    return Path(override).expanduser() if override else _DEFAULT_PATH


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _pack(vector: list[float]) -> bytes:
    return struct.pack(f"{len(vector)}f", *vector)


def _unpack(blob: bytes, dim: int) -> list[float]:
    return list(struct.unpack(f"{dim}f", blob))


class EmbeddingCache:
    """Process-wide cache of embedding vectors. Thread-safe via a single lock."""

    _SCHEMA = """
        CREATE TABLE IF NOT EXISTS embeddings (
            model      TEXT    NOT NULL,
            role       INTEGER NOT NULL,
            text_hash  TEXT    NOT NULL,
            dim        INTEGER NOT NULL,
            vector     BLOB    NOT NULL,
            created_at TEXT    NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (model, role, text_hash)
        );
    """

    def __init__(self, path: Path | None = None):
        self.path = path or _default_cache_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._connect() as conn:
            conn.execute(self._SCHEMA)
        logger.debug("EmbeddingCache initialised at %s", self.path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def lookup(self, model: str, is_query: bool, texts: list[str]) -> dict[int, list[float]]:
        """Return a {index: vector} dict for the texts already present in the cache."""
        if not texts:
            return {}
        role = 1 if is_query else 0
        hashes = [_hash_text(t) for t in texts]
        unique_hashes = list(set(hashes))
        placeholders = ",".join("?" for _ in unique_hashes)
        sql = (
            f"SELECT text_hash, dim, vector FROM embeddings "
            f"WHERE model = ? AND role = ? AND text_hash IN ({placeholders})"
        )
        with self._lock, self._connect() as conn:
            rows = conn.execute(sql, (model, role, *unique_hashes)).fetchall()
        by_hash = {h: _unpack(blob, dim) for h, dim, blob in rows}
        return {idx: by_hash[h] for idx, h in enumerate(hashes) if h in by_hash}

    def store(self, model: str, is_query: bool, items: list[tuple[str, list[float]]]) -> None:
        """Persist (text, vector) pairs. Uses INSERT OR REPLACE for idempotency."""
        if not items:
            return
        role = 1 if is_query else 0
        rows = [
            (model, role, _hash_text(text), len(vector), _pack(vector))
            for text, vector in items
        ]
        with self._lock, self._connect() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO embeddings(model, role, text_hash, dim, vector) "
                "VALUES (?, ?, ?, ?, ?)",
                rows,
            )

    def stats(self) -> dict[str, int]:
        with self._lock, self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
            by_role = dict(
                conn.execute(
                    "SELECT role, COUNT(*) FROM embeddings GROUP BY role"
                ).fetchall()
            )
        return {"total": total, "docs": by_role.get(0, 0), "queries": by_role.get(1, 0)}


_singleton: Optional[EmbeddingCache] = None
_singleton_lock = threading.Lock()


def get_cache() -> EmbeddingCache:
    """Lazy module-level singleton."""
    global _singleton
    if _singleton is None:
        with _singleton_lock:
            if _singleton is None:
                _singleton = EmbeddingCache()
    return _singleton
