"""Clipboard history row showing a type glyph, preview text, and metadata."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget, QSizePolicy
from clipx.utils import format_relative_time
from clipx.ui.foundations.icons import label_icon
from clipx.ui.foundations.theme import TEXT_PRIMARY


class ClipItemWidget(QWidget):
    """Present one clipboard item inside the history list.

    The row is transparent to mouse events so the owning list handles selection.
    It shows a type or color glyph, an elided title and subtitle, an optional
    pin marker, and a relative timestamp. Visibility of the glyph and metadata
    follows the supplied preferences.
    """

    def __init__(self, item, parent=None, preferences=None):
        """Build the row widgets for a clipboard item.

        Args:
            item (object): Clipboard item exposing ``type``, ``content``,
                ``is_pinned``, ``updated_at``, ``language``, and
                ``char_count``.
            parent (QWidget, optional): Parent widget that owns the row.
            preferences (dict, optional): Display preferences such as
                ``density``, ``metadata``, and ``lines``. Defaults to an empty
                dictionary.
        """
        super().__init__(parent)
        self.preferences = preferences or {}
        self.item = item
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 3 if self.preferences.get('density') == 'compact' else 6, 10, 3 if self.preferences.get('density') == 'compact' else 6)
        row.setSpacing(10)
        glyph = QLabel()
        glyph.setFixedSize(26, 26)
        if item.type == 'color':
            from PyQt6.QtGui import QColor
            color = QColor(item.content.strip())
            glyph.setStyleSheet(f'background: {color.name() if color.isValid() else "#55555D"}; border-radius: 5px;')
        else:
            label_icon(glyph, item.type, 20)
            glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        glyph.setVisible(self.preferences.get('metadata', True))
        row.addWidget(glyph)
        text = QVBoxLayout()
        text.setSpacing(3)
        self.title_label = QLabel()
        self.title_label.setTextFormat(Qt.TextFormat.PlainText)
        self.title_label.setStyleSheet(f'color: {TEXT_PRIMARY}; font-size: 12pt; font-weight: 500;')
        self.title_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.subtitle = QLabel()
        self.subtitle.setTextFormat(Qt.TextFormat.PlainText)
        self.subtitle.setObjectName('Secondary')
        self.subtitle.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        text.addWidget(self.title_label)
        text.addWidget(self.subtitle)
        row.addLayout(text, 1)
        if item.is_pinned:
            pin = QLabel()
            label_icon(pin, 'pin', 14)
            pin.setAccessibleName('Fixado')
            row.addWidget(pin)
        when = QLabel(format_relative_time(item.updated_at))
        when.setObjectName('Metadata')
        when.setVisible(self.preferences.get('metadata', True))
        row.addWidget(when)
        self.setAccessibleName(('Fixado. ' if item.is_pinned else '') + item.content[:120])

    def resizeEvent(self, event):
        """Recompose and elide the preview text to fit the current width.

        The first non-empty line becomes the title. Remaining lines form the
        subtitle up to the configured line count; when that would be empty and
        metadata is enabled, the subtitle falls back to language or type plus
        character count. Both texts are elided with a trailing ellipsis.

        Args:
            event (QResizeEvent): Resize event forwarded to the base class.
        """
        super().resizeEvent(event)
        lines = [line.strip() for line in self.item.content.splitlines() if line.strip()]
        title = lines[0] if lines else 'Vazio'
        count = self.preferences.get('lines', 2)
        detail = '\n'.join(lines[1:count])
        if not detail and count > 1 and self.preferences.get('metadata', True):
            detail = f'{self.item.language or self.item.type} · {self.item.char_count} caracteres'
        self.subtitle.setVisible(bool(detail) and count > 1)
        available = max(40, self.title_label.contentsRect().width())
        self.title_label.setText(self.title_label.fontMetrics().elidedText(title, Qt.TextElideMode.ElideRight, available))
        self.subtitle.setText('\n'.join(self.subtitle.fontMetrics().elidedText(line, Qt.TextElideMode.ElideRight, available) for line in detail.splitlines()))
