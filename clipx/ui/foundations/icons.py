"""Small original SVG glyphs with a consistent stroke weight."""
from PyQt6.QtCore import QByteArray, Qt, QSize
from pathlib import Path
from functools import lru_cache
from PyQt6.QtGui import QIcon, QPixmap, QPainter
from PyQt6.QtSvg import QSvgRenderer
from clipx.ui.foundations.theme import TEXT_SECONDARY

PATHS = {
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
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">{PATHS.get(name, PATHS["text"])}</svg>'
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    QSvgRenderer(QByteArray(svg.encode())).render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)


def label_icon(label, name, size=20):
    """Keep source metadata so appearance changes can redraw crisp glyphs."""
    label.setProperty('iconName', name)
    label.setProperty('iconSize', size)
    label.setPixmap(icon(name, size).pixmap(size, size))


@lru_cache(maxsize=4)
def _lucide_svg(name):
    allowed = {'palette', 'panels-top-left', 'app-window', 'keyboard', 'loader-circle'}
    if name not in allowed:
        raise ValueError('Ícone Lucide desconhecido: ' + name)
    return (Path(__file__).resolve().parents[2] / 'assets' / 'icons' / 'lucide' / (name + '.svg')).read_text()


def loading_icon(size, color, angle):
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
    """Render original Lucide assets with semantic color and logical scaling."""
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
