"""Background filesystem checks and bounded image decoding for the preview."""
from pathlib import Path
from threading import Event

from PyQt6.QtCore import QObject, QRunnable, QSize, pyqtSignal
from clipx.images import read_image, ImageError


class ImagePreviewSignals(QObject):
    """Deliver an immutable request token and its result to the UI thread."""

    ready = pyqtSignal(int, object)


class ImagePreviewTask(QRunnable):
    """Revalidate a file and decode only when its filesystem identity changes."""

    def __init__(self, token, path, previous):
        """Keep request data without touching any widget from the worker."""
        super().__init__()
        self.token, self.path, self.previous = token, path, previous
        self.signals = ImagePreviewSignals()
        self.cancelled = Event()

    def run(self):
        """Report a scaled first frame, unchanged identity, or readable failure."""
        try:
            if self.cancelled.is_set():
                self.signals.ready.emit(self.token, {'cancelled': True})
                return
            stat = Path(self.path).stat()
            signature = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns,
                         stat.st_ctime_ns, stat.st_mode)
            if signature == self.previous:
                result = {'unchanged': True}
            elif self.cancelled.is_set():
                result = {'cancelled': True}
            else:
                image, dimensions, size = read_image(self.path, QSize(1600, 1200))
                result = dict(image=image, dimensions=dimensions, size=size, signature=signature)
        except (OSError, ImageError) as exc:
            if isinstance(exc, FileNotFoundError):
                from clipx.images import MISSING_IMAGE
                message = MISSING_IMAGE
            elif isinstance(exc, PermissionError):
                message = 'Sem permissão para ler a imagem.'
            else:
                message = str(exc) if isinstance(exc, ImageError) else 'Não foi possível acessar o arquivo da imagem.'
            result = {'error': message}
        self.signals.ready.emit(self.token, result)
