from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget
from clipx.ui.foundations.icons import label_icon
from clipx.ui.molecules.select import Select


class SearchBarWidget(QWidget):
    query_changed = pyqtSignal(str)
    filter_changed = pyqtSignal(str)
    FILTERS = [('Todos', 'all'), ('Texto', 'text'), ('Código', 'code'),
               ('Links', 'url'), ('Cores', 'color'), ('Fixados', 'pinned')]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('SearchHeader')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 12, 20, 12)
        layout.setSpacing(8)
        row = QHBoxLayout()
        row.setSpacing(12)
        glyph = QLabel()
        label_icon(glyph, 'search', 20)
        row.addWidget(glyph)
        self.input_field = QLineEdit()
        self.input_field.setObjectName('SearchBar')
        self.input_field.setPlaceholderText('Pesquisar histórico…')
        self.input_field.setAccessibleName('Pesquisar histórico da área de transferência')
        self.input_field.textChanged.connect(self.query_changed.emit)
        row.addWidget(self.input_field, 1)
        layout.addLayout(row)
        metadata = QHBoxLayout()
        caption = QLabel('Histórico da área de transferência')
        caption.setObjectName('Secondary')
        metadata.addWidget(caption, 1)
        self.count_badge = QLabel('0 itens')
        self.count_badge.setObjectName('Count')
        metadata.addWidget(self.count_badge)
        self.filter_select = Select(heading='Filtrar por tipo')
        self.filter_select.setAccessibleName('Filtrar histórico por tipo')
        for label, value in self.FILTERS:
            self.filter_select.addItem(label, value)
        self.filter_select.currentIndexChanged.connect(
            lambda _: self.filter_changed.emit(self.filter_select.currentData()))
        metadata.addWidget(self.filter_select)
        layout.addLayout(metadata)

    def set_count(self, count):
        self.count_badge.setText(f'{count} ' + ('item' if count == 1 else 'itens'))

    def clear_search(self):
        self.input_field.clear()

    def focus_input(self, *, select_all=False):
        """Returning focus must not replace a query or move its editing cursor."""
        self.input_field.setFocus()
        if select_all:
            self.input_field.selectAll()

    def cycle_filter(self):
        self.filter_select.setCurrentIndex((self.filter_select.currentIndex() + 1) % len(self.FILTERS))
