"""Shared search shell; the page supplies behavior and platform integration."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QSplitter, QLabel
from clipx.ui.molecules.clipboard_search import SearchBarWidget
from clipx.ui.organisms.clipboard_list import ClipListWidget
from clipx.ui.organisms.clipboard_preview import PreviewPaneWidget
from clipx.ui.organisms.clipboard_actions import ActionBarWidget


class ClipboardLayout(QWidget):
    def __init__(self, shortcuts, parent=None):
        super().__init__(parent)
        self.setObjectName('CentralWidget')
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setProperty('nativeGlass', False)
        box = QVBoxLayout(self)
        box.setContentsMargins(1, 1, 1, 1)
        box.setSpacing(0)
        self.search_bar = SearchBarWidget()
        box.addWidget(self.search_bar)
        self.status_label = QLabel()
        self.status_label.setObjectName('Status')
        self.status_label.setWordWrap(True)
        self.status_label.setAccessibleName('Estado da captura e das operações')
        self.status_label.hide()
        box.addWidget(self.status_label)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.clip_list = ClipListWidget()
        self.clip_list.setMinimumWidth(270)
        self.preview_pane = PreviewPaneWidget()
        self.preview_pane.setMinimumWidth(270)
        self.splitter.addWidget(self.clip_list)
        self.splitter.addWidget(self.preview_pane)
        self.splitter.setSizes([380, 500])
        box.addWidget(self.splitter, 1)
        self.action_bar = ActionBarWidget(shortcuts=shortcuts)
        box.addWidget(self.action_bar)
