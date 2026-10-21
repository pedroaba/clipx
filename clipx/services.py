"""Clipboard operations shared by the search window and tray."""
import sqlite3
from clipx.platforms.base import Result, Status


class ClipboardService:
    def __init__(self, storage, driver):
        self.storage = storage
        self.driver = driver

    def copy(self, clip):
        if clip is None:
            return Result(Status.UNAVAILABLE, 'Selecione um item para copiar.')
        result = self.driver.write_text(clip.content)
        if result.ok:
            try:
                self.storage.add_clip(clip.content, clip.type, clip.language)
            except (sqlite3.Error, OSError) as exc:
                return Result(Status.ERROR, f"Texto copiado, mas não foi possível atualizar o histórico: {exc}")
        return result
