"""Clipboard operations shared by the search window and tray.

The service wraps a storage backend and a platform clipboard driver so copying
an item both writes to the system clipboard and refreshes its history entry.
"""
import sqlite3
from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal
from clipx.platforms.base import Result, Status


class ClipboardService(QObject):
    """Copy stored clips to the system clipboard and refresh their history."""

    def __init__(self, storage, driver):
        """Initialize the service with its collaborators.

        Args:
            storage (Storage): History storage used to refresh copied items.
            driver: Platform clipboard driver exposing ``write_text``.
        """
        super().__init__()
        self._jobs = {}
        self._request_id = 0
        self.storage = storage
        self.driver = driver

    def copy(self, clip):
        """Write a clip to the system clipboard and refresh its history row.

        On a successful clipboard write, an existing row has its timestamp
        refreshed so it moves to the top of history. A failure to update history is
        reported as an error result even though the clipboard write succeeded.

        Args:
            clip: Clip to copy; when None a message result is returned.

        Returns:
            Result: Driver result, an unavailable result for a missing clip, or
            an error result when history persistence failed.
        """
        if clip is None:
            return Result(Status.UNAVAILABLE, 'Selecione um item para copiar.')
        if clip.type == 'image':
            from clipx.images import read_image, png_bytes, ImageError
            try:
                image, _, _ = read_image(clip.content)
                data = png_bytes(image)
                self.storage.mark_image_write(image)
            except ImageError as exc:
                return Result(Status.ERROR, str(exc), exc.code)
            except (OSError, sqlite3.Error) as exc:
                return Result(Status.ERROR, f'Não foi possível preparar a imagem: {exc}', 'image_unreadable')
            result = self.driver.write_image(data)
        else:
            result = self.driver.write_text(clip.content)
        if not result.ok and clip.type == 'image':
            self.storage.clear_image_write()
        if result.ok:
            try:
                self.storage.touch_clip(clip.id)
            except (sqlite3.Error, OSError) as exc:
                return Result(Status.ERROR, f"Conteúdo copiado, mas não foi possível atualizar o histórico: {exc}")
        return result

    def copy_async(self, clip, callback):
        """Copy images off the UI thread; keep existing synchronous text behavior."""
        if self._jobs:
            callback(Result(Status.UNAVAILABLE, 'Uma cópia já está em andamento.'))
            return
        if clip is None or clip.type != 'image':
            callback(self.copy(clip))
            return
        self._request_id += 1
        token = self._request_id
        task = _ImageCopyTask(self, clip, token)
        task.signals.ready.connect(self._copy_finished)
        self._jobs[token] = (task, callback)
        QThreadPool.globalInstance().start(task)

    def _copy_finished(self, token, result):
        """Deliver the result on the service's owning thread."""
        _, callback = self._jobs.pop(token)
        callback(result)


class _CopySignals(QObject):
    """Bridge worker completion back to the service's Qt thread."""

    ready = pyqtSignal(int, object)


class _ImageCopyTask(QRunnable):
    """Decode and copy an image without blocking keyboard and preview events."""

    def __init__(self, service, clip, token):
        """Retain the operation inputs until the worker completes."""
        super().__init__()
        self.service, self.clip, self.token = service, clip, token
        self.signals = _CopySignals()

    def run(self):
        """Report exceptions as a failed operation rather than killing a worker."""
        try:
            result = self.service.copy(self.clip)
        except Exception as exc:
            result = Result(Status.ERROR, f'Não foi possível copiar a imagem: {exc}')
        self.signals.ready.emit(self.token, result)
