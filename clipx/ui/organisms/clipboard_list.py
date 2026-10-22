"""Scrollable clipboard history list with identity-based reconciliation.

Rows are rebuilt only when their clip instance or position changes, so typing in
the search field does not reset selection or scroll position.
"""
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtWidgets import QLabel, QListWidget, QListWidgetItem
from clipx.ui.molecules.clipboard_item import ClipItemWidget


class ClipListWidget(QListWidget):
    """List of clipboard items rendered with one custom widget per row.

    Attributes:
        preferences (dict): UI preferences used to size rows and build item
            widgets; the owner replaces it before repopulating.
        empty_label (QLabel): Overlay label shown when the list has no items.
    """

    def __init__(self, parent=None):
        """Create the list, its empty-state overlay and scroll configuration.

        Args:
            parent (QWidget | None): Optional parent widget.
        """
        super().__init__(parent)
        self.preferences = {}
        self.setObjectName('ClipList')
        self.setAccessibleName('Itens do histórico')
        self.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.empty_label = QLabel(self.viewport())
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setWordWrap(True)
        self.empty_label.setObjectName('Secondary')
        self.empty_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.empty_label.hide()

    def resizeEvent(self, event):
        """Keep the empty-state overlay aligned with the resized viewport.

        Args:
            event (QResizeEvent): Resize event forwarded to the base class.
        """
        super().resizeEvent(event)
        self.empty_label.setGeometry(self.viewport().rect().adjusted(20, 0, -20, 0))

    def _insert_clip(self, index, item):
        """Insert a formatted row for one clip at the given position.

        The row height derives from the density, line count and scale
        preferences, and its surface is themed before being attached.

        Args:
            index (int): Row index where the item is inserted.
            item (object): Clip record stored in the item's user data.

        Returns:
            QListWidgetItem: The created list item.
        """
        from clipx.ui.foundations.appearance import apply_surface
        from clipx.preferences import validate_ui
        settings = self.preferences
        scale = settings.get('scale', 100) / 100
        height = (30 if settings.get('density') == 'compact' else 40) + (settings.get('lines', 2) - 1) * 20
        list_item = QListWidgetItem()
        list_item.setSizeHint(QSize(0, round(height * scale)))
        list_item.setData(Qt.ItemDataRole.UserRole, item)
        list_item.setData(Qt.ItemDataRole.AccessibleTextRole, item.content[:200])
        self.insertItem(index, list_item)
        widget = ClipItemWidget(item, preferences=settings)
        apply_surface(widget, validate_ui(settings))
        self.setItemWidget(list_item, widget)
        return list_item

    def populate(self, items, empty_message='Seu histórico está vazio.\nCopie um texto para começar.'):
        """Reconcile results by identity; typing must not rebuild unchanged rows.

        Existing rows are reused while matching clips keep their position and
        identity, obsolete rows are removed and missing rows are inserted around
        the reused ones. Selection and scroll position are restored afterwards,
        signals stay blocked during the whole update, and the current-item
        change is emitted at most once so the preview is not rendered for
        intermediate states. When the preferences change, the list is cleared
        and rebuilt from scratch.

        Args:
            items (list): Clip records in display order.
            empty_message (str): Text shown by the overlay when no items exist.
        """
        selected = self.get_selected_clip()
        selected_id = selected.id if selected else None
        scroll = self.verticalScrollBar().value()
        previous_signals = self.blockSignals(True)
        self.setUpdatesEnabled(False)
        try:
            if getattr(self, '_rendered_preferences', None) != self.preferences:
                self.clear()
                self._rendered_preferences = self.preferences.copy()
            wanted = {item.id for item in items}
            for index in range(self.count() - 1, -1, -1):
                if self.item(index).data(Qt.ItemDataRole.UserRole).id not in wanted:
                    self.takeItem(index)
            existing = {self.item(i).data(Qt.ItemDataRole.UserRole).id: self.item(i)
                        for i in range(self.count())}
            selected_item = None
            for index, item in enumerate(items):
                row = existing.get(item.id)
                if row is not None and (self.row(row) != index or row.data(Qt.ItemDataRole.UserRole) != item):
                    self.takeItem(self.row(row))
                    row = None
                if row is None:
                    row = self._insert_clip(index, item)
                if item.id == selected_id:
                    selected_item = row
            if self.count():
                self.setCurrentItem(selected_item or self.item(0))
                self.verticalScrollBar().setValue(scroll)
            self.empty_label.setText(empty_message)
            self.empty_label.setVisible(not items)
            self.empty_label.setGeometry(self.viewport().rect().adjusted(20, 0, -20, 0))
        finally:
            self.setUpdatesEnabled(True)
            self.blockSignals(previous_signals)
        # Notify once, after reconciliation, rather than clearing and rendering
        # the preview during every intermediate removal or insertion.
        current = self.get_selected_clip()
        if not previous_signals and (current != selected or getattr(self, '_preview_preferences', None) != self.preferences):
            self._preview_preferences = self.preferences.copy()
            self.currentItemChanged.emit(self.currentItem(), None)

    def get_selected_clip(self):
        """Return the clip stored by the current row.

        Returns:
            object | None: Clip record of the current item, or ``None`` when
            nothing is selected.
        """
        current = self.currentItem()
        return current.data(Qt.ItemDataRole.UserRole) if current else None
