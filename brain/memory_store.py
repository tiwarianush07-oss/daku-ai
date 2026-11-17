"""
DAKU Structured 10-Tier Memory Persistence Engine
Milestone 4: Zero-dependency SQLite + FTS5 unified memory system.

Configured with low-RAM speed and safety pragmas:
- PRAGMA journal_mode=WAL;
- PRAGMA synchronous=NORMAL;
- PRAGMA temp_store=MEMORY;
- PRAGMA cache_size=-4000; (caps cache at ~4 MB RAM)

Provides:
- MemoryTier enum (Tiers 1-10)
- MemoryStore: Thread-safe, multi-user, SQLite + FTS5 persistence engine with BM25 ranking
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
import time
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

logger = logging.getLogger("daku.memory")

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "daku_memory.db"


class MemoryTier(str, Enum):
    """The 10 structured architectural tiers of DAKU memory persistence."""

    WORKING_BUFFER = "WORKING_BUFFER"  # Tier 1: Ephemeral turn state
    SHORT_TERM_SESSION = "SHORT_TERM_SESSION"  # Tier 2: Active session context
    EPISODIC_EVENTS = "EPISODIC_EVENTS"  # Tier 3: Timestamped task & tool outcomes
    SEMANTIC_FACTS = "SEMANTIC_FACTS"  # Tier 4: Extracted user/world knowledge (FTS5 + BM25)
    PROCEDURAL_LESSONS = "PROCEDURAL_LESSONS"  # Tier 5: Bridge hook for LearningEngine strategies
    USER_PROFILE = "USER_PROFILE"  # Tier 6: Multi-user preferences, language, voice settings
    SECURITY_AUDIT_LOG = "SECURITY_AUDIT_LOG"  # Tier 7: Immutable log of CONFIRMATION & BLOCKED actions
    AGENT_SWARM_STATE = "AGENT_SWARM_STATE"  # Tier 8: Solar HUD agent telemetry snapshots
    MCP_TOOL_CACHE = "MCP_TOOL_CACHE"  # Tier 9: Discovered tool schemas & reliability scores
    ARCHIVAL_SUMMARY = "ARCHIVAL_SUMMARY"  # Tier 10: Compacted cross-session checkpoints


# Tiers that append new rows on store rather than overwriting existing keys
APPEND_ONLY_TIERS = {
    MemoryTier.EPISODIC_EVENTS,
    MemoryTier.SECURITY_AUDIT_LOG,
    MemoryTier.PROCEDURAL_LESSONS,
}


def _sanitize_fts5_query(query: str) -> str:
    """
    Sanitizes user input for SQLite FTS5 MATCH queries.
    Removes syntax operators and joins terms with prefix matching.
    """
    # Remove punctuation that causes FTS5 syntax errors
    clean = re.sub(r'[^\w\s]', ' ', query).strip()
    tokens = clean.split()
    if not tokens:
        return '""'
    # Format each token as a prefix search token
    terms = [f'"{t}"*' for t in tokens if len(t) > 0]
    return " AND ".join(terms) if terms else '""'


class MemoryStore:
    """
    SQLite + FTS5 10-Tier Memory Persistence Engine.
    Operates strictly within Python standard library, < 4 MB cache footprint.
    """

    def __init__(self, db_path: Optional[Union[str, Path]] = None):
        self.db_path = str(db_path or DEFAULT_DB_PATH)
        self._lock = threading.Lock()

        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
            timeout=10.0,
        )
        self._conn.row_factory = sqlite3.Row

        self._apply_pragmas()
        self._initialize_schema()

    def _apply_pragmas(self) -> None:
        """Applies high-speed low-RAM SQLite performance pragmas."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL;")
            cur.execute("PRAGMA synchronous=NORMAL;")
            cur.execute("PRAGMA temp_store=MEMORY;")
            cur.execute("PRAGMA cache_size=-4000;")  # 4000 KB = ~4 MB cache limit
            cur.close()

    def _initialize_schema(self) -> None:
        """Initializes relational tables, indexes, and the FTS5 virtual table."""
        with self._lock:
            cur = self._conn.cursor()

            # Main structured storage table
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL DEFAULT 'default_user',
                    tier TEXT NOT NULL,
                    key TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata_json TEXT DEFAULT '{}',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    expires_at REAL DEFAULT NULL
                );
                """
            )

            # Performance indexes
            cur.execute("CREATE INDEX IF NOT EXISTS idx_mem_user_tier ON memory_entries(user_id, tier);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_mem_user_key ON memory_entries(user_id, key);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_mem_expires ON memory_entries(expires_at);")

            # FTS5 full-text search table with BM25 support
            cur.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS semantic_facts_fts USING fts5(
                    entry_id UNINDEXED,
                    user_id UNINDEXED,
                    tier UNINDEXED,
                    key,
                    content,
                    tokenize='porter unicode61'
                );
                """
            )

            self._conn.commit()
            cur.close()

    def store_entry(
        self,
        user_id: str,
        tier: Union[str, MemoryTier],
        key: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        ttl_seconds: Optional[float] = None,
    ) -> int:
        """
        Stores or updates an entry in the specified memory tier.
        Automatically updates FTS5 index for searchable tiers (SEMANTIC_FACTS, PROCEDURAL_LESSONS, etc.).
        """
        tier_str = tier.value if isinstance(tier, MemoryTier) else str(tier)
        metadata_dict = metadata or {}
        metadata_str = json.dumps(metadata_dict)
        now = time.time()
        expires_at = (now + ttl_seconds) if ttl_seconds is not None else None

        with self._lock:
            cur = self._conn.cursor()

            is_append_only = tier in APPEND_ONLY_TIERS or tier_str in [t.value for t in APPEND_ONLY_TIERS]

            entry_id: Optional[int] = None
            if not is_append_only:
                # Check for existing key in this tier for upsert
                cur.execute(
                    "SELECT id FROM memory_entries WHERE user_id = ? AND tier = ? AND key = ?",
                    (user_id, tier_str, key),
                )
                row = cur.fetchone()
                if row:
                    entry_id = int(row["id"])

            if entry_id is not None:
                # Update existing entry
                cur.execute(
                    """
                    UPDATE memory_entries
                    SET content = ?, metadata_json = ?, updated_at = ?, expires_at = ?
                    WHERE id = ?
                    """,
                    (content, metadata_str, now, expires_at, entry_id),
                )
                # Update FTS
                cur.execute("DELETE FROM semantic_facts_fts WHERE entry_id = ?", (entry_id,))
                cur.execute(
                    """
                    INSERT INTO semantic_facts_fts (entry_id, user_id, tier, key, content)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (entry_id, user_id, tier_str, key, content),
                )
            else:
                # Insert new entry
                cur.execute(
                    """
                    INSERT INTO memory_entries (user_id, tier, key, content, metadata_json, created_at, updated_at, expires_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (user_id, tier_str, key, content, metadata_str, now, now, expires_at),
                )
                entry_id = cur.lastrowid
                assert entry_id is not None

                # Insert into FTS index
                cur.execute(
                    """
                    INSERT INTO semantic_facts_fts (entry_id, user_id, tier, key, content)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (entry_id, user_id, tier_str, key, content),
                )

            self._conn.commit()
            cur.close()
            return entry_id

    def get_entry(
        self,
        user_id: str,
        tier: Union[str, MemoryTier],
        key: str,
    ) -> Optional[Dict[str, Any]]:
        """Retrieves a single entry by user, tier, and key if not expired."""
        tier_str = tier.value if isinstance(tier, MemoryTier) else str(tier)
        now = time.time()

        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                SELECT id, user_id, tier, key, content, metadata_json, created_at, updated_at, expires_at
                FROM memory_entries
                WHERE user_id = ? AND tier = ? AND key = ?
                  AND (expires_at IS NULL OR expires_at > ?)
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (user_id, tier_str, key, now),
            )
            row = cur.fetchone()
            cur.close()

            if not row:
                return None

            return self._row_to_dict(row)

    def recall_fts(
        self,
        user_id: str,
        query: str,
        tiers: Optional[Sequence[Union[str, MemoryTier]]] = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Executes BM25 full-text search query across FTS5 virtual table.
        Returns top ranked results ordered by relevance (BM25 ascending score).
        """
        clean_match = _sanitize_fts5_query(query)
        if clean_match == '""':
            return []

        now = time.time()
        with self._lock:
            cur = self._conn.cursor()

            tier_filter = ""
            params: List[Any] = [clean_match, user_id, now]

            if tiers:
                tier_strs = [t.value if isinstance(t, MemoryTier) else str(t) for t in tiers]
                placeholders = ",".join("?" for _ in tier_strs)
                tier_filter = f"AND f.tier IN ({placeholders})"
                params.extend(tier_strs)

            params.append(limit)

            sql = f"""
                SELECT f.entry_id, f.user_id, f.tier, f.key, f.content,
                       m.metadata_json, m.created_at, m.updated_at,
                       bm25(semantic_facts_fts) AS rank
                FROM semantic_facts_fts f
                JOIN memory_entries m ON f.entry_id = m.id
                WHERE semantic_facts_fts MATCH ?
                  AND f.user_id = ?
                  AND (m.expires_at IS NULL OR m.expires_at > ?)
                  {tier_filter}
                ORDER BY rank ASC
                LIMIT ?
            """

            try:
                cur.execute(sql, params)
                rows = cur.fetchall()
            except sqlite3.OperationalError as e:
                logger.warning(f"FTS5 query error: {e}")
                rows = []

            cur.close()

            results = []
            for r in rows:
                meta = {}
                try:
                    meta = json.loads(r["metadata_json"])
                except Exception:
                    pass

                results.append({
                    "id": r["entry_id"],
                    "user_id": r["user_id"],
                    "tier": r["tier"],
                    "key": r["key"],
                    "content": r["content"],
                    "metadata": meta,
                    "created_at": r["created_at"],
                    "updated_at": r["updated_at"],
                    "rank": round(float(r["rank"]), 4),
                })
            return results

    def get_session_context(
        self,
        user_id: str,
        session_id: str,
        include_working_buffer: bool = True,
    ) -> Dict[str, Any]:
        """
        Retrieves active session state and ephemeral working buffer context
        for the given user and session ID.
        """
        tiers = [MemoryTier.SHORT_TERM_SESSION.value]
        if include_working_buffer:
            tiers.append(MemoryTier.WORKING_BUFFER.value)

        placeholders = ",".join("?" for _ in tiers)
        now = time.time()

        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                f"""
                SELECT id, user_id, tier, key, content, metadata_json, created_at, updated_at
                FROM memory_entries
                WHERE user_id = ?
                  AND tier IN ({placeholders})
                  AND (expires_at IS NULL OR expires_at > ?)
                ORDER BY updated_at ASC
                """,
                [user_id] + tiers + [now],
            )
            rows = cur.fetchall()
            cur.close()

            session_entries = []
            working_buffer = []

            for r in rows:
                item = self._row_to_dict(r)
                meta = item.get("metadata", {})
                item_session = meta.get("session_id") or ""
                # Filter to matching session if key or metadata references it
                if item_session == session_id or session_id in item["key"]:
                    if item["tier"] == MemoryTier.WORKING_BUFFER.value:
                        working_buffer.append(item)
                    else:
                        session_entries.append(item)

            return {
                "user_id": user_id,
                "session_id": session_id,
                "session_entries": session_entries,
                "working_buffer": working_buffer,
                "total_entries": len(session_entries) + len(working_buffer),
            }

    def prune_expired(self) -> int:
        """
        Prunes all expired entries past their TTL timestamp.
        Cleans corresponding rows in the FTS5 virtual table.
        """
        now = time.time()
        with self._lock:
            cur = self._conn.cursor()

            cur.execute("SELECT id FROM memory_entries WHERE expires_at IS NOT NULL AND expires_at <= ?", (now,))
            expired_ids = [row["id"] for row in cur.fetchall()]

            if not expired_ids:
                cur.close()
                return 0

            placeholders = ",".join("?" for _ in expired_ids)
            cur.execute(f"DELETE FROM semantic_facts_fts WHERE entry_id IN ({placeholders})", expired_ids)
            cur.execute(f"DELETE FROM memory_entries WHERE id IN ({placeholders})", expired_ids)

            pruned_count = cur.rowcount
            self._conn.commit()
            cur.close()
            return pruned_count

    def list_entries(
        self,
        user_id: str,
        tier: Optional[Union[str, MemoryTier]] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Lists entries for a user, optionally filtered by tier."""
        now = time.time()
        tier_str = tier.value if isinstance(tier, MemoryTier) else (str(tier) if tier else None)

        with self._lock:
            cur = self._conn.cursor()
            if tier_str:
                cur.execute(
                    """
                    SELECT id, user_id, tier, key, content, metadata_json, created_at, updated_at, expires_at
                    FROM memory_entries
                    WHERE user_id = ? AND tier = ?
                      AND (expires_at IS NULL OR expires_at > ?)
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (user_id, tier_str, now, limit),
                )
            else:
                cur.execute(
                    """
                    SELECT id, user_id, tier, key, content, metadata_json, created_at, updated_at, expires_at
                    FROM memory_entries
                    WHERE user_id = ?
                      AND (expires_at IS NULL OR expires_at > ?)
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (user_id, now, limit),
                )

            rows = cur.fetchall()
            cur.close()
            return [self._row_to_dict(r) for r in rows]

    def delete_entry(
        self,
        user_id: str,
        tier: Union[str, MemoryTier],
        key: str,
    ) -> bool:
        """Deletes a specific entry by key and removes it from FTS index."""
        tier_str = tier.value if isinstance(tier, MemoryTier) else str(tier)
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT id FROM memory_entries WHERE user_id = ? AND tier = ? AND key = ?",
                (user_id, tier_str, key),
            )
            rows = cur.fetchall()
            if not rows:
                cur.close()
                return False

            ids = [r["id"] for r in rows]
            placeholders = ",".join("?" for _ in ids)
            cur.execute(f"DELETE FROM semantic_facts_fts WHERE entry_id IN ({placeholders})", ids)
            cur.execute(f"DELETE FROM memory_entries WHERE id IN ({placeholders})", ids)
            self._conn.commit()
            cur.close()
            return True

    def clear_tier(self, user_id: str, tier: Union[str, MemoryTier]) -> int:
        """Deletes all entries in a specific tier for a given user."""
        tier_str = tier.value if isinstance(tier, MemoryTier) else str(tier)
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("SELECT id FROM memory_entries WHERE user_id = ? AND tier = ?", (user_id, tier_str))
            rows = cur.fetchall()
            if not rows:
                cur.close()
                return 0

            ids = [r["id"] for r in rows]
            placeholders = ",".join("?" for _ in ids)
            cur.execute(f"DELETE FROM semantic_facts_fts WHERE entry_id IN ({placeholders})", ids)
            cur.execute(f"DELETE FROM memory_entries WHERE id IN ({placeholders})", ids)
            count = cur.rowcount
            self._conn.commit()
            cur.close()
            return count

    def get_stats(self) -> Dict[str, Any]:
        """Returns storage metrics and count per tier for memory monitoring."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("SELECT tier, COUNT(*) as count FROM memory_entries GROUP BY tier")
            tier_counts = {r["tier"]: r["count"] for r in cur.fetchall()}

            cur.execute("SELECT COUNT(*) as total FROM memory_entries")
            total = cur.fetchone()["total"]

            cur.close()

            return {
                "total_entries": total,
                "tier_breakdown": tier_counts,
                "db_path": self.db_path,
            }

    def close(self) -> None:
        """Cleanly closes database connection."""
        with self._lock:
            try:
                self._conn.close()
            except Exception:
                pass

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        """Helper to convert sqlite3.Row to Python dictionary."""
        meta = {}
        try:
            meta = json.loads(row["metadata_json"])
        except Exception:
            pass

        return {
            "id": row["id"],
            "user_id": row["user_id"],
            "tier": row["tier"],
            "key": row["key"],
            "content": row["content"],
            "metadata": meta,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "expires_at": row["expires_at"] if "expires_at" in row.keys() else None,
        }
