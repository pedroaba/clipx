"""Shared themed select with a Qt list popup and standard combo-box semantics."""
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QColor, QPainter, QPen, QPolygonF, QPalette
from PyQt6.QtWidgets import QComboBox, QLabel, QListView, QProxyStyle, QStyle, QStyledItemDelegate
from clipx.ui.foundations.theme import BG_CARD, BG_CARD_HOVER, BORDER_DEFAULT, TEXT_PRIMARY, TEXT_SECONDARY


class _SelectStyle(QProxyStyle):
    def styleHint(self, hint, option=None, widget=None, returnData=None):
        if hint == QStyle.StyleHint.SH_ComboBox_Popup:
            return 0  # Use our list popup instead of the native macOS menu.
        return super().styleHint(hint, option, widget, returnData)


class _OptionDelegate(QStyledItemDelegate):
    def __init__(self, select):
        super().__init__(select)
        self.select = select

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        if index.row() == self.select.currentIndex():
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(QPen(self.select.palette().color(QPalette.ColorRole.Text), 1.7))
            x, y = option.rect.right() - 17, option.rect.center().y()
            painter.drawPolyline(QPolygonF([QPointF(x - 5, y), QPointF(x - 1, y + 4), QPointF(x + 6, y - 4)]))
            painter.restore()


class _OptionsList(QListView):
    def __init__(self, parent):
        super().__init__(parent)
        self.setViewportMargins(0, 32, 0, 0)
        self.heading = QLabel(self)
        self.heading.setObjectName('SelectHeading')
        self.heading.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.heading.setGeometry(14, 6, self.width() - 28, 28)


class Select(QComboBox):
    def __init__(self, parent=None, *, heading='Selecionar opção'):
        super().__init__(parent)
        self.setObjectName('Select')
        self._select_style = _SelectStyle()
        self._select_style.setParent(self)
        self.setStyle(self._select_style)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(34)
        self.setMaxVisibleItems(9)
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        view = _OptionsList(self)
        view.heading.setText(heading)
        view.setItemDelegate(_OptionDelegate(self))
        view.setObjectName('SelectOptions')
        view.setSpacing(2)
        view.setUniformItemSizes(True)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setView(view)
        self.setStyleSheet(f'''
            QComboBox#Select {{ background: #141414; color: {TEXT_PRIMARY};
                border: 1px solid {BORDER_DEFAULT}; border-radius: 8px;
                padding: 5px 32px 5px 12px; font-size: 11pt; }}
            QComboBox#Select:hover {{ background: {BG_CARD_HOVER}; border-color: #55555D; }}
            QComboBox#Select:focus, QComboBox#Select:on {{ border-color: {TEXT_SECONDARY}; }}
            QComboBox#Select:disabled {{ color: #71717A; background: #202024; }}
            QComboBox#Select::drop-down {{ border: none; width: 28px; }}
            QComboBox#Select::down-arrow {{ image: none; }}
            QListView#SelectOptions {{ background: #181818; color: {TEXT_PRIMARY};
                border: 1px solid #45454C; border-radius: 10px; padding: 6px;
                outline: none; font-size: 11pt; selection-color: {TEXT_PRIMARY}; }}
            QListView#SelectOptions::item {{ min-height: 32px; padding: 0 34px 0 8px;
                border: none; border-radius: 6px; }}
            QListView#SelectOptions::item:hover {{ background: #303036; }}
            QListView#SelectOptions::item:selected {{ background: #242424; color: {TEXT_PRIMARY}; }}
            QLabel#SelectHeading {{ background: transparent; color: {TEXT_SECONDARY}; font-size: 10pt; border: none; }}
            QListView#SelectOptions::item:disabled {{ color: #71717A; }}
        ''')

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(Qt.GlobalColor.gray if not self.isEnabled() else QColor(TEXT_SECONDARY), 1.5))
        x, y = self.width() - 18, self.height() / 2
        painter.drawPolyline(QPolygonF([QPointF(x - 4, y - 2), QPointF(x, y + 2), QPointF(x + 4, y - 2)]))

    def showPopup(self):
        self.view().setMinimumWidth(max(self.width(), 160))
        super().showPopup()
        popup = self.view().window()
        screen = self.screen().availableGeometry()
        rows = min(self.count(), self.maxVisibleItems())
        margins = self.view().contentsMargins()
        content_height = sum(self.view().sizeHintForRow(row) + 2 * self.view().spacing() for row in range(rows))
        height = min(content_height + 32 + margins.top() + margins.bottom() + 4, screen.height())
        width = max(self.width(), 180)
        below = self.mapToGlobal(QPoint(0, self.height() + 5))
        y = below.y() if below.y() + height <= screen.bottom() else self.mapToGlobal(QPoint(0, -height - 5)).y()
        x = max(screen.left(), min(below.x(), screen.right() - width + 1))
        popup.setGeometry(x, max(screen.top(), y), width, height)

