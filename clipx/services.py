"""Clipboard operations shared by the search window and tray.

The service wraps a storage backend and a platform clipboard driver so copying
an item both writes to the system clipboard and refreshes its history entry.
"""
import sqlite3
from clipx.platforms.base import Result, Status


class ClipboardService:
    """Copy stored clips to the system clipboard and refresh their history."""

    def __init__(self, storage, driver):
        """Initialize the service with its collaborators.

        Args:
            storage (Storage): History storage used to refresh copied items.
            driver: Platform clipboard driver exposing ``write_text``.
        """
        self.storage = storage
        self.driver = driver

    def copy(self, clip):
        """Write a clip to the system clipboard and refresh its history row.

        On a successful clipboard write, the clip is re-added to storage so its
        timestamp moves to the top of history. A failure to update history is
        reported as an error result even though the clipboard write succeeded.

        Args:
            clip: Clip to copy; when None a message result is returned.

        Returns:
            Result: Driver result, an unavailable result for a missing clip, or
            an error result when history persistence failed.
        """
        if clip is None:
            return Result(Status.UNAVAILABLE, 'Selecione um item para copiar.')
        result = self.driver.write_text(clip.content)
        if result.ok:
            try:
                self.storage.add_clip(clip.content, clip.type, clip.language)
            except (sqlite3.Error, OSError) as exc:
                return Result(Status.ERROR, f"Texto copiado, mas não foi possível atualizar o histórico: {exc}")
        return result
