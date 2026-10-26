"""Image decoding and identity shared by capture, copy and preview."""
import hashlib
import os
from pathlib import Path

from PyQt6.QtCore import QByteArray, QBuffer, QIODevice, QSize
from PyQt6.QtGui import QImage, QImageReader

MISSING_IMAGE = 'A imagem foi movida ou excluída.'


class ImageError(Exception):
    """An image cannot currently be read, with a stable UI error code."""

    def __init__(self, message, code='image_unreadable'):
        super().__init__(message)
        self.code = code


def read_image(source, preview_size=None):
    """Decode the first frame, optionally downsampling for a preview.

    Args:
        source: Local path or encoded image bytes.
        preview_size: Optional bounding QSize for the decoded image.

    Returns:
        tuple: Decoded QImage, original dimensions and source byte size.

    Raises:
        ImageError: Missing, inaccessible, unsupported or invalid source.
    """
    buffer = None
    if isinstance(source, (str, Path)):
        try:
            with open(source, 'rb') as stream:
                # Opening first distinguishes access failures from decoder errors.
                size = os.fstat(stream.fileno()).st_size
        except FileNotFoundError:
            raise ImageError(MISSING_IMAGE, 'image_missing') from None
        except PermissionError:
            raise ImageError('Sem permissão para ler a imagem.', 'image_permission') from None
        except OSError:
            raise ImageError('Não foi possível acessar o arquivo da imagem.') from None
        reader = QImageReader(str(source))
    else:
        size = len(source)
        buffer = QBuffer()
        buffer.setData(QByteArray(source))
        buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        reader = QImageReader(buffer)
    reader.setAutoTransform(True)
    if bytes(reader.format()).lower() == b'pdf':
        raise ImageError('O arquivo não é uma imagem.', 'image_unsupported')
    dimensions = reader.size()
    if preview_size and dimensions.isValid():
        from PyQt6.QtCore import Qt
        reader.setScaledSize(dimensions.scaled(preview_size, Qt.AspectRatioMode.KeepAspectRatio))
    image = reader.read()
    if image.isNull():
        if isinstance(source, (str, Path)) and not Path(source).exists():
            raise ImageError(MISSING_IMAGE, 'image_missing')
        if reader.error() == QImageReader.ImageReaderError.UnsupportedFormatError:
            raise ImageError('Formato de imagem não suportado.', 'image_unsupported')
        raise ImageError('A imagem está corrompida ou não pôde ser decodificada.')
    return image, dimensions if dimensions.isValid() else image.size(), size


def image_digest(image):
    """Hash canonical pixels and dimensions independently of input encoding."""
    normalized = image.convertToFormat(QImage.Format.Format_RGBA8888)
    raw = normalized.constBits().asstring(normalized.sizeInBytes())
    return hashlib.sha256(f'{normalized.width()}x{normalized.height()}:'.encode() + raw).hexdigest()


def png_bytes(image):
    """Encode a QImage as a PNG without creating an intermediate file."""
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, 'PNG'):
        raise ImageError('Não foi possível preparar a imagem para copiar.')
    return bytes(buffer.data())


def image_title(clip):
    """Return a readable label for external and managed image clips."""
    return 'Imagem capturada' if clip.file_owner == 'managed' else Path(clip.content).name
