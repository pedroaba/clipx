import hashlib
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional


@dataclass
class ClipItem:
    id: int
    content: str
    content_hash: str
    type: str  # 'text', 'code', 'url', 'color'
    language: Optional[str]
    is_pinned: bool
    char_count: int
    line_count: int
    created_at: str
    updated_at: str


class Storage:
    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            from clipx.platforms.paths import PlatformPaths
            paths = PlatformPaths()
            paths.migrate_legacy()
            paths.data.mkdir(parents=True, exist_ok=True)
            db_path = paths.data / "history.db"

        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS clips (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    content_hash TEXT UNIQUE NOT NULL,
                    type TEXT NOT NULL,
                    language TEXT,
                    is_pinned INTEGER DEFAULT 0,
                    char_count INTEGER NOT NULL,
                    line_count INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_clips_hash ON clips(content_hash);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_clips_updated ON clips(updated_at DESC);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_clips_pinned ON clips(is_pinned DESC, updated_at DESC);"
            )

    @staticmethod
    def compute_hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def add_clip(
        self,
        content: str,
        clip_type: str = "text",
        language: Optional[str] = None,
        max_history: int = 500,
    ) -> Optional[int]:
        cleaned = content.strip()
        if not cleaned:
            return None

        content_hash = self.compute_hash(content)
        char_count = len(content)
        line_count = len(content.splitlines()) or 1

        with self._get_connection() as conn:
            # Check if clip already exists
            existing = conn.execute(
                "SELECT id, is_pinned FROM clips WHERE content_hash = ?",
                (content_hash,),
            ).fetchone()

            if existing:
                clip_id = existing["id"]
                conn.execute(
                    """
                    UPDATE clips
                    SET updated_at = STRFTIME('%Y-%m-%d %H:%M:%f', 'now'),
                        type = ?,
                        language = ?
                    WHERE id = ?
                    """,
                    (clip_type, language, clip_id),
                )
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO clips (
                        content, content_hash, type, language, is_pinned,
                        char_count, line_count, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, 0, ?, ?, CURRENT_TIMESTAMP,
                            STRFTIME('%Y-%m-%d %H:%M:%f', 'now'))
                    """,
                    (content, content_hash, clip_type, language, char_count, line_count),
                )
                clip_id = cursor.lastrowid

                # Prune old unpinned items if exceeding max_history
                conn.execute(
                    """
                    DELETE FROM clips
                    WHERE is_pinned = 0 AND id NOT IN (
                        SELECT id FROM clips
                        WHERE is_pinned = 0
                        ORDER BY updated_at DESC
                        LIMIT ?
                    )
                    """,
                    (max_history,),
                )

            return clip_id

    def get_clips(
        self,
        query: str = "",
        filter_type: str = "all",
        limit: int = 100,
        pinned_first: bool = True,
    ) -> List[ClipItem]:
        sql = """
            SELECT id, content, content_hash, type, language, is_pinned,
                   char_count, line_count, created_at, updated_at
            FROM clips
            WHERE 1=1
        """
        params = []

        if filter_type == "pinned":
            sql += " AND is_pinned = 1"
        elif filter_type and filter_type != "all":
            sql += " AND type = ?"
            params.append(filter_type)

        if query:
            sql += " AND content LIKE ?"
            params.append(f"%{query}%")

        order = "is_pinned DESC, " if pinned_first else ""
        sql += f" ORDER BY {order}updated_at DESC, id DESC LIMIT ?"
        params.append(limit)

        with self._get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [
                ClipItem(
                    id=row["id"],
                    content=row["content"],
                    content_hash=row["content_hash"],
                    type=row["type"],
                    language=row["language"],
                    is_pinned=bool(row["is_pinned"]),
                    char_count=row["char_count"],
                    line_count=row["line_count"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
                for row in rows
            ]

    def toggle_pin(self, clip_id: int) -> bool:
        with self._get_connection() as conn:
            row = conn.execute("SELECT is_pinned FROM clips WHERE id = ?", (clip_id,)).fetchone()
            if not row:
                return False
            new_val = 0 if row["is_pinned"] else 1
            conn.execute("UPDATE clips SET is_pinned = ? WHERE id = ?", (new_val, clip_id))
            return bool(new_val)

    def delete_clip(self, clip_id: int) -> bool:
        with self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM clips WHERE id = ?", (clip_id,))
            return cursor.rowcount > 0

    def clear_history(self, keep_pinned: bool = True):
        with self._get_connection() as conn:
            if keep_pinned:
                conn.execute("DELETE FROM clips WHERE is_pinned = 0")
            else:
                conn.execute("DELETE FROM clips")
