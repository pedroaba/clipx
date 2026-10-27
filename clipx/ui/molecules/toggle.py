"""A switch-shaped checkbox retaining Qt's checked state and accessible action."""
from PyQt6.QtCore import QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QCheckBox
from clipx.ui.foundations.appearance import palette_for


class Toggle(QCheckBox):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.values = {'theme': 'dark', 'scale': 100}
        self._appearance_key = (tuple(palette_for(self.values).items()), 100)
        self.setAccessibleName(text)
        self.setMinimumHeight(32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def refresh_appearance(self, values):
        key = (tuple(palette_for(values).items()), values['scale'])
        scale_changed = self.values['scale'] != values['scale']
        self.values = values.copy()
        if self._appearance_key == key:
            return
        self._appearance_key = key
        if scale_changed:
            self.updateGeometry()
        self.update()

    def sizeHint(self):
        scale = self.values['scale'] / 100
        return QSize(round(52 * scale) + self.fontMetrics().horizontalAdvance(self.text()),
                     max(round(32 * scale), self.fontMetrics().height()))

    def hitButton(self, position):
        return self.rect().contains(position)

    def paintEvent(self, event):
        colors = palette_for(self.values)
        scale = self.values['scale'] / 100
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            painter.setOpacity(0.45)
        track = QRectF(1 * scale, (self.height() - 20 * scale) / 2, 36 * scale, 20 * scale)
        if self.layoutDirection() == Qt.LayoutDirection.RightToLeft:
            track.moveRight(self.width() - scale)
        painter.setPen(QPen(QColor(colors['border']), scale))
        painter.setBrush(QColor(colors['text'] if self.isChecked() else colors['card']))
        painter.drawRoundedRect(track, 10 * scale, 10 * scale)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(colors['canvas'] if self.isChecked() else colors['secondary']))
        on_right = self.isChecked() != (self.layoutDirection() == Qt.LayoutDirection.RightToLeft)
        thumb_x = track.left() + (18 if on_right else 2) * scale
        painter.drawEllipse(QRectF(thumb_x, track.top() + 2 * scale, 16 * scale, 16 * scale))
        text_rect = QRectF(self.rect()).adjusted(50 * scale, 0, 0, 0)
        if self.layoutDirection() == Qt.LayoutDirection.RightToLeft:
            text_rect = QRectF(self.rect()).adjusted(0, 0, -50 * scale, 0)
        painter.setPen(QColor(colors['text']))
        painter.setFont(self.font())
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeading, self.text())
        if self.hasFocus():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(colors['secondary']), scale))
            painter.drawRoundedRect(track.adjusted(-scale, -scale, scale, scale), 11 * scale, 11 * scale)
