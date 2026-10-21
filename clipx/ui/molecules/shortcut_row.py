"""One shortcut preference, composed from recorder, feedback and action controls."""
from PyQt6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from clipx.ui.atoms.feedback import FeedbackLabel
from clipx.ui.molecules.shortcut_recorder import ShortcutRecorder


class ShortcutRow(QFrame):
    def __init__(self, spec, sequence, parent=None):
        super().__init__(parent)
        self.spec = spec
        self.setObjectName('ShortcutRow')
        self.setProperty('modified', False)
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(18, 12, 18, 12)
        self.box.setSpacing(5)
        line = QHBoxLayout()
        line.setSpacing(10)
        copy = QVBoxLayout()
        copy.setSpacing(4)
        heading = QHBoxLayout()
        heading.setSpacing(8)
        self.title = QLabel(spec.title)
        self.title.setObjectName('ActionTitle')
        self.title.setWordWrap(True)
        heading.addWidget(self.title)
        self.changed_dot = QLabel('●')
        self.changed_dot.setObjectName('ModifiedDot')
        self.changed_dot.setAccessibleName('Atalho alterado, ainda não salvo')
        self.changed_dot.hide()
        heading.addWidget(self.changed_dot)
        heading.addStretch()
        copy.addLayout(heading)
        details = QLabel(spec.description)
        details.setObjectName('Description')
        details.setWordWrap(True)
        copy.addWidget(details)
        line.addLayout(copy, 1)
        self.clear_button = QPushButton('×')
        self.clear_button.setObjectName('ClearShortcut')
        self.clear_button.setFixedSize(26, 28)
        self.clear_button.setAutoDefault(False)
        self.clear_button.setAccessibleName('Desativar atalho: ' + spec.title)
        self.clear_button.setToolTip('Desativar este atalho no rascunho')
        line.addWidget(self.clear_button)
        self.recorder = ShortcutRecorder(sequence)
        self.recorder.setAccessibleName('Alterar atalho: ' + spec.title)
        line.addWidget(self.recorder)
        self.choose_button = None
        if spec.name == 'global':
            self.choose_button = QPushButton('⋯')
            self.choose_button.setObjectName('ChooseShortcut')
            self.choose_button.setAutoDefault(False)
            self.choose_button.setFixedSize(28, 28)
            self.choose_button.setAccessibleName('Escolher atalho sem pressionar uma combinação')
            self.choose_button.setToolTip('Escolher sem pressionar uma combinação interceptada pelo sistema')
            line.addWidget(self.choose_button)
        self.box.addLayout(line)
        self.message = FeedbackLabel()
        self.box.addWidget(self.message)

    def set_modified(self, modified):
        self.setProperty('modified', modified)
        self.changed_dot.setVisible(modified)
