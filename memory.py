"""
Structured long-term conversation memory.

MemoryStore is the only entry point to durable memories.  Like
SecureDataAccess, it binds (tenant_id, actor) at construction time and never
accepts them from the caller again — a memory written under one tenant/user can
never be read by another.  Memories persist across logout (keyed by username),
unlike the raw turn history held in Streamlit session state.

Each memory carries a type tag so retrieval can favour the kinds that matter:
  - preference : how this user likes answers shaped
  - entity     : a department/metric the user keeps returning to
  - pattern    : a recurring analytical interest
  - fact       : a stated business fact
"""
from __future__ import annotations

import datetime
import sqlite3
from pathlib import Path

from db import DB_PATH, TENANTS

MEMORY_TYPES = frozenset(["preference", "entity", "pattern", "fact"])


def init_memory(db_path: str | Path = DB_PATH) -> None:
    """Create the memories table if it does not exist."""
    con = sqlite3.connect(db_path)
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS memories (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id  TEXT NOT NULL,
            actor      TEXT NOT NULL,
            mem_type   TEXT NOT NULL,
            content    TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(tenant_id, actor, content)
        )
        """
    )
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_mem_scope ON memories(tenant_id, actor)"
    )
    con.commit()
    con.close()


class MemoryStore:
    """
    Tenant- and actor-scoped store for structured long-term memories.
    tenant_id and actor are bound at construction and never accepted again,
    so retrieval and writes can only ever touch this user's own memories.
    """

    def __init__(
        self,
        tenant_id: str,
        actor: str,
        db_path: str | Path = DB_PATH,
    ) -> None:
        if tenant_id not in TENANTS:
            raise ValueError(f"Unknown tenant: {tenant_id!r}")
        if not actor:
            raise ValueError("actor (username) is required for memory scope.")
        self._tenant_id = tenant_id
        self._actor = actor
        self._db_path = str(db_path)
        init_memory(db_path)

    def add(self, mem_type: str, content: str) -> bool:
        """
        Persist one memory under this scope.  Returns True if stored, False if
        it was a duplicate (same content already remembered) or invalid.
        """
        content = content.strip()
        if mem_type not in MEMORY_TYPES or not content:
            return False
        con = sqlite3.connect(self._db_path)
        try:
            con.execute(
                "INSERT INTO memories "
                "(tenant_id, actor, mem_type, content, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    self._tenant_id,
                    self._actor,
                    mem_type,
                    content,
                    datetime.datetime.now(datetime.timezone.utc).isoformat(),
                ),
            )
            con.commit()
            return True
        except sqlite3.IntegrityError:
            return False  # UNIQUE violation — already remembered
        finally:
            con.close()

    def all(self, limit: int = 50) -> list[dict]:
        """Return this scope's memories, most recent first."""
        con = sqlite3.connect(self._db_path)
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT id, mem_type, content, created_at FROM memories "
            "WHERE tenant_id = ? AND actor = ? "
            "ORDER BY id DESC LIMIT ?",
            (self._tenant_id, self._actor, limit),
        ).fetchall()
        con.close()
        return [dict(r) for r in rows]

    def delete(self, mem_id: int) -> None:
        """Delete one memory by id, scoped to this tenant/actor."""
        con = sqlite3.connect(self._db_path)
        con.execute(
            "DELETE FROM memories WHERE id = ? AND tenant_id = ? AND actor = ?",
            (mem_id, self._tenant_id, self._actor),
        )
        con.commit()
        con.close()

    def as_prompt_block(self, limit: int = 50) -> str:
        """
        Render this scope's memories as a compact block for the system prompt.
        Returns "" when there are none, so callers can skip the section.
        """
        memories = self.all(limit=limit)
        if not memories:
            return ""
        lines = [f"- ({m['mem_type']}) {m['content']}" for m in memories]
        return "\n".join(lines)
