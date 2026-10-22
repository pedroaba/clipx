"""Two-column preferences shell: navigation, header, scrollable content, fixed footer."""
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QScrollArea, QLabel
from clipx.ui.atoms.feedback import FeedbackLabel


class PreferencesLayout(QWidget):
    """Two-column preferences shell with a fixed sidebar and scrolling body.

    The right column contains a title and description, the supplied search
    control, a scrollable content area, an inline error label, a hint, and the
    supplied footer actions. The sidebar is placed directly in the root layout
    and is not scrolled.
    """

    def __init__(self, sidebar, search, content, footer, hint, parent=None):
        """Assemble the preferences shell from externally created widgets.

        Args:
            sidebar (QWidget): Navigation widget shown in the left column.
            search (QWidget): Search control embedded in the header.
            content (QWidget): Page content placed inside the scroll area.
            footer (QWidget): Action widget placed at the bottom of the right
                column.
            hint (str): Help text shown above the footer.
            parent (QWidget, optional): Parent widget that owns the layout.
        """
        super().__init__(parent)
        self.setObjectName('PreferencesLayout')
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(sidebar)
        main = QVBoxLayout()
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)
        header = QWidget()
        box = QVBoxLayout(header)
        box.setContentsMargins(28, 24, 28, 18)
        box.setSpacing(8)
        title = QLabel('Atalhos de teclado')
        title.setObjectName('Heading')
        box.addWidget(title)
        description = QLabel('Clique em um atalho e pressione a nova combinação.')
        description.setObjectName('Subtitle')
        description.setWordWrap(True)
        box.addWidget(description)
        box.addSpacing(10)
        box.addWidget(search)
        main.addWidget(header)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setObjectName('PreferencesScroll')
        body = QWidget()
        body.setObjectName('PreferencesBody')
        body_box = QVBoxLayout(body)
        body_box.setContentsMargins(28, 0, 24, 8)
        body_box.addWidget(content)
        self.scroll.setWidget(body)
        main.addWidget(self.scroll, 1)
        self.error_label = FeedbackLabel()
        self.error_label.setObjectName('PreferencesError')
        main.addWidget(self.error_label)
        help_text = QLabel(hint)
        help_text.setObjectName('PreferencesHint')
        help_text.setWordWrap(True)
        main.addWidget(help_text)
        main.addWidget(footer)
        root.addLayout(main, 1)
