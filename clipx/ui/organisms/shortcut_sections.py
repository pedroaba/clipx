"""Grouped shortcut list with search/category filtering that preserves every draft."""
import unicodedata
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QFrame, QLabel
from clipx.ui.models.shortcut_catalog import CATEGORIES
from clipx.ui.molecules.shortcut_row import ShortcutRow
from clipx.ui.molecules.shortcut_recorder import display_shortcut


def searchable(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', text.casefold()) if not unicodedata.combining(c))


class ShortcutSections(QWidget):
    def __init__(self, specs, values, parent=None):
        super().__init__(parent)
        self.setObjectName('ShortcutSections')
        self.specs = specs
        self.rows = {}
        self.sections = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 4, 4)
        layout.setSpacing(22)
        for category, title, _ in CATEGORIES[1:]:
            section = QWidget()
            box = QVBoxLayout(section)
            box.setContentsMargins(0, 0, 0, 0)
            box.setSpacing(10)
            label = QLabel(title.upper())
            label.setObjectName('Section')
            box.addWidget(label)
            group = QFrame()
            group.setObjectName('ShortcutGroup')
            group_box = QVBoxLayout(group)
            group_box.setContentsMargins(1, 1, 1, 1)
            group_box.setSpacing(0)
            for spec in specs:
                if spec.category == category:
                    row = ShortcutRow(spec, values.get(spec.name, ''))
                    self.rows[spec.name] = row
                    group_box.addWidget(row)
            box.addWidget(group)
            self.sections[category] = section
            layout.addWidget(section)
        self.empty_label = QLabel('Nenhum atalho encontrado.\nTente outro nome ou combinação de teclas.')
        self.empty_label.setObjectName('EmptyShortcuts')
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setWordWrap(True)
        self.empty_label.setMinimumHeight(180)
        self.empty_label.hide()
        layout.addWidget(self.empty_label)
        layout.addStretch()
        self.filter('all', '')

    def filter(self, category, query):
        wanted = searchable(query.strip())
        visible = []
        for spec in self.specs:
            row = self.rows[spec.name]
            keys = row.recorder.keySequence()
            haystack = searchable(' '.join((spec.title, spec.description,
                keys.toString(), display_shortcut(keys))))
            matches = (category == 'all' or spec.category == category) and wanted in haystack
            row.setVisible(matches)
            if matches:
                visible.append(spec.name)
        for name, section in self.sections.items():
            children = [self.rows[spec.name] for spec in self.specs
                        if spec.category == name and spec.name in visible]
            section.setVisible(bool(children))
            for row in children:
                row.setProperty('last', row is children[-1])
                row.style().unpolish(row)
                row.style().polish(row)
        self.empty_label.setVisible(not visible)
        return len(visible)

    def visible_names(self):
        return [spec.name for spec in self.specs if not self.rows[spec.name].isHidden()]
