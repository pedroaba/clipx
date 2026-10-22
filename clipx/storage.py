"""SQLite-backed clipboard history storage.

The module defines the row model and a small storage layer that opens a short
lived connection per operation, initializes the schema on demand, deduplicates
clips by content hash, and prunes old unpinned entries.
"""

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
    """A clipboard history row loaded from the database.

    Attributes:
        id (int): Primary key of the clip.
        content (str): Original clipboard content.
        content_hash (str): SHA-256 hex digest used for deduplication.
        type (str): Clip type: ``"text"``, ``"code"``, ``"url"``, or
            ``"color"``.
        language (Optional[str]): Detected language for code clips.
        is_pinned (bool): Whether the clip is protected from pruning.
        char_count (int): Number of characters in ``content``.
        line_count (int): Number of lines in ``content``, at least one.
        created_at (str): SQLite timestamp of the first insertion.
        updated_at (str): SQLite timestamp of the last update.
    """

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
    """Persist clipboard history in a SQLite database.

    Each operation opens its own connection and transaction, which keeps the
    class usable from multiple threads and processes. Default construction uses
    the platform data directory and migrates legacy locations first.
    """

    def __init__(self, db_path: Optional[Path] = None):
        """Open or create the history database.

        When ``db_path`` is omitted, the platform data directory is resolved,
        legacy data is migrated, and the directory is created before using
        ``history.db``. The schema is initialized immediately.

        Args:
            db_path (Optional[Path]): Explicit database path.

        Raises:
            OSError: If the default data directory cannot be created.
            sqlite3.Error: If the database schema cannot be initialized.
        """
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
        """Open a SQLite connection wrapped in a transaction.

        The connection uses ``sqlite3.Row`` rows and is committed or rolled back
        by the context manager before being closed.

        Yields:
            sqlite3.Connection: Connection usable only within the context.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_db(self):
        """Create the clips table and its indexes when they do not exist.

        Raises:
            sqlite3.Error: If schema creation fails.
        """
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
        """Compute the SHA-256 digest used to identify duplicate content.

        Args:
            content (str): Text to hash, encoded as UTF-8.

        Returns:
            str: Lowercase hexadecimal digest.
        """
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def add_clip(
        self,
        content: str,
        clip_type: str = "text",
        language: Optional[str] = None,
        max_history: int = 500,
    ) -> Optional[int]:
        """Insert a clip or refresh an existing clip with identical content.

        Deduplication is based on the hash of the unstripped content. Existing
        rows have their ``updated_at``, type, and language refreshed but keep
        their original content. New rows are unpinned and trigger pruning of
        the oldest unpinned clips beyond ``max_history``.

        Args:
            content (str): Clipboard content; blank content is ignored.
            clip_type (str): Detected clip type.
            language (Optional[str]): Detected language for code clips.
            max_history (int): Maximum number of unpinned rows to retain.

        Returns:
            Optional[int]: Row identifier, or None when content is blank.

        Raises:
            sqlite3.Error: If the database operation fails.
        """
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
        """Load history clips with optional text, type, and ordering filters.

        Args:
            query (str): SQL ``LIKE`` substring; empty matches all content. SQLite
                applies its default ASCII case-insensitive comparison.
            filter_type (str): ``"all"``, ``"pinned"``, or a clip type stored in
                the ``type`` column.
            limit (int): Maximum number of rows to return.
            pinned_first (bool): Whether pinned clips should sort before
                unpinned clips.

        Returns:
            List[ClipItem]: Matching clips, newest first by ``updated_at`` and
            then by descending identifier.
        """
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
        """Toggle the pinned state of a clip.

        Args:
            clip_id (int): Identifier of the clip to update.

        Returns:
            bool: The new pinned state, or False when the clip does not exist.
        """
        with self._get_connection() as conn:
            row = conn.execute("SELECT is_pinned FROM clips WHERE id = ?", (clip_id,)).fetchone()
            if not row:
                return False
            new_val = 0 if row["is_pinned"] else 1
            conn.execute("UPDATE clips SET is_pinned = ? WHERE id = ?", (new_val, clip_id))
            return bool(new_val)

    def delete_clip(self, clip_id: int) -> bool:
        """Delete one clip from history.

        Args:
            clip_id (int): Identifier of the clip to delete.

        Returns:
            bool: True when a row was deleted, False when no row matched.
        """
        with self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM clips WHERE id = ?", (clip_id,))
            return cursor.rowcount > 0

    def clear_history(self, keep_pinned: bool = True):
        """Delete history rows, optionally preserving pinned clips.

        Args:
            keep_pinned (bool): When True, only unpinned clips are deleted.
        """
        with self._get_connection() as conn:
            if keep_pinned:
                conn.execute("DELETE FROM clips WHERE is_pinned = 0")
            else:
                conn.execute("DELETE FROM clips")
