"""Small original SVG glyphs with a consistent stroke weight.

Glyphs are rendered to a transparent pixmap at twice the requested size and
tagged with a device pixel ratio of two, so they stay crisp on HiDPI screens.
Lucide assets are loaded from the bundled icon set for a few richer controls.
"""
from PyQt6.QtCore import QByteArray, Qt, QSize
from pathlib import Path
from functools import lru_cache
from PyQt6.QtGui import QIcon, QPixmap, QPainter
from PyQt6.QtSvg import QSvgRenderer
from clipx.ui.foundations.theme import TEXT_SECONDARY

PATHS = {
    'image': '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8" cy="8" r="2"/><path d="m21 15-6-6L3 21"/>',
    'command': '<path d="M8 8h8v8H8zM8 8H5a3 3 0 1 1 3-3v3Zm8 0V5a3 3 0 1 1 3 3h-3Zm0 8h3a3 3 0 1 1-3 3v-3Zm-8 0v3a3 3 0 1 1-3-3h3Z"/>',
    'globe': '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a18 18 0 0 1 0 18 18 18 0 0 1 0-18Z"/>',
    'filter': '<path d="M3 4h18l-7 8v7l-4 2v-9Z"/>',
    'search': '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4 4"/>',
    'text': '<path d="M6 3h9l4 4v14H6zM14 3v5h5M9 12h7M9 16h7"/>',
    'code': '<path d="m8 6-6 6 6 6m8-12 6 6-6 6M14 3l-4 18"/>',
    'url': '<path d="m10 14 4-4m-5 7-2 2a4 4 0 0 1-6-6l4-4a4 4 0 0 1 6 0m2-2 2-2a4 4 0 0 1 6 6l-4 4a4 4 0 0 1-6 0"/>',
    'pin': '<path d="m9 3 8 0-1 6 4 4H6l4-4zM13 13v8"/>',
    'clipboard': '<rect x="5" y="5" width="14" height="16" rx="2"/><rect x="9" y="2" width="6" height="5" rx="1"/>',
}


def icon(name, size=20, color=TEXT_SECONDARY):
    """Render a named built-in glyph as a QIcon.

    Unknown names fall back to the ``text`` glyph. The SVG is rendered into a
    transparent pixmap of ``size * 2`` pixels with a device pixel ratio of two.

    Args:
        name (str): Key from ``PATHS`` identifying the glyph.
        size (int): Logical icon size in pixels.
        color (str): Stroke color applied to the SVG.

    Returns:
        QIcon: Rendered icon.
    """
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">{PATHS.get(name, PATHS["text"])}</svg>'
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    QSvgRenderer(QByteArray(svg.encode())).render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)


def label_icon(label, name, size=20):
    """Keep source metadata so appearance changes can redraw crisp glyphs.

    Stores the glyph name and size as dynamic properties and immediately sets
    the corresponding pixmap on the label.

    Args:
        label (QLabel): Label that displays the glyph.
        name (str): Key from ``PATHS`` identifying the glyph.
        size (int): Logical icon size in pixels.
    """
    label.setProperty('iconName', name)
    label.setProperty('iconSize', size)
    label.setPixmap(icon(name, size).pixmap(size, size))


@lru_cache(maxsize=4)
def _lucide_svg(name):
    """Read a bundled Lucide SVG from disk, caching the result.

    Args:
        name (str): Lucide icon name; only ``palette``, ``panels-top-left``,
            ``app-window``, ``keyboard`` and ``loader-circle`` are allowed.

    Returns:
        str: Raw SVG markup.

    Raises:
        ValueError: If ``name`` is not one of the allowed icons.
    """
    allowed = {'palette', 'panels-top-left', 'app-window', 'keyboard', 'loader-circle'}
    if name not in allowed:
        raise ValueError('Ícone Lucide desconhecido: ' + name)
    return (Path(__file__).resolve().parents[2] / 'assets' / 'icons' / 'lucide' / (name + '.svg')).read_text()


def loading_icon(size, color, angle):
    """Render the Lucide spinner glyph rotated by a given angle.

    The pixmap is drawn at twice the requested size and scaled down through a
    device pixel ratio of two. The same pixmap is registered for normal and
    disabled icon modes.

    Args:
        size (int): Logical icon size in pixels.
        color (str): Stroke color substituted for ``currentColor``.
        angle (int | float): Rotation in degrees.

    Returns:
        QIcon: Rotated spinner icon.
    """
    svg = _lucide_svg('loader-circle').replace('currentColor', color)
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.translate(size, size)
    painter.rotate(angle)
    painter.translate(-size, -size)
    QSvgRenderer(QByteArray(svg.encode())).render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    result = QIcon()
    for mode in (QIcon.Mode.Normal, QIcon.Mode.Disabled):
        result.addPixmap(pixmap, mode)
    return result


def refresh_lucide_button(button, values):
    """Render original Lucide assets with semantic color and logical scaling.

    The icon name is read from the button's ``lucideIcon`` property. The color
    follows the semantic palette (primary text when checked, secondary
    otherwise) and the size is the 18 px base scaled by ``values['scale']``.
    The rendered pixmap is assigned together with a matching icon size.

    Args:
        button (QAbstractButton): Button carrying the ``lucideIcon`` property.
        values (dict): Appearance values, including ``scale`` (percent).
    """
    from clipx.ui.foundations.appearance import palette_for
    colors = palette_for(values)
    color = colors['text' if button.isChecked() else 'secondary']
    size = round(18 * values['scale'] / 100)
    svg = _lucide_svg(button.property('lucideIcon')).replace('currentColor', color)
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    QSvgRenderer(QByteArray(svg.encode())).render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    button.setIcon(QIcon(pixmap))
    button.setIconSize(QSize(size, size))
