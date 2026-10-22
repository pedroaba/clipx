"""Footer shared by the shortcut and preferences dialogs.

The footer owns the reset button, the pending-change counter and the apply /
cancel buttons. It reflows the buttons below the counter on narrow windows.
"""
from PyQt6.QtWidgets import QFrame, QGridLayout, QLabel, QPushButton


from clipx.ui.molecules.dialog_actions import DialogActions
from PyQt6.QtCore import Qt


class PreferencesFooter(QFrame):
    """Footer with reset, pending-changes label and dialog actions.

    Attributes:
        reset (QPushButton): Button that restores defaults for the active
            section.
        change_label (QLabel): Text describing the number of unsaved changes.
        buttons (DialogActions): Apply and cancel button pair.
        apply (QPushButton): Alias of the apply button inside ``buttons``.
    """

    def __init__(self, parent=None):
        """Build the footer in its idle state (no pending changes).

        Args:
            parent (QWidget | None): Optional parent widget.
        """
        super().__init__(parent)
        self.setObjectName('PreferencesFooter')
        layout = QGridLayout(self)
        layout.setContentsMargins(24, 14, 24, 14)
        layout.setSpacing(12)
        self.reset = QPushButton('Restaurar padrões')
        self.reset.setObjectName('ResetPreferences')
        self.reset.setAutoDefault(False)
        layout.addWidget(self.reset, 0, 0)
        self.change_label = QLabel('Nenhuma alteração')
        self.change_label.setObjectName('PendingChanges')
        layout.addWidget(self.change_label, 0, 1)
        layout.setColumnStretch(1, 1)
        self.buttons = DialogActions()
        self.apply = self.buttons.apply
        layout.addWidget(self.buttons, 0, 2)
        self.set_pending(0)

    def set_pending(self, count, recording=False):
        """Update the pending counter and enable or disable applying.

        Args:
            count (int): Number of unsaved changes.
            recording (bool): Whether a shortcut is being recorded; recording
                always disables the apply button.
        """
        self.change_label.setText('Nenhuma alteração' if not count else
            '1 alteração não salva' if count == 1 else f'{count} alterações não salvas')
        self.buttons.set_apply_enabled(count > 0 and not recording)

    def show_applied(self):
        """Replace the pending counter with a confirmation message."""
        self.change_label.setText('Configurações aplicadas')

    def resizeEvent(self, event):
        """Move the buttons to a second row when the footer becomes narrow.

        The threshold scales with the window's ``scale`` preference.

        Args:
            event (QResizeEvent): Resize event forwarded to the base class.
        """
        super().resizeEvent(event)
        scale = getattr(self.window(), 'window', None)
        scale = scale.preferences['scale'] / 100 if scale is not None else 1
        narrow = self.width() < 650 * scale
        self.layout().removeWidget(self.buttons)
        self.layout().addWidget(self.buttons, 1 if narrow else 0, 0 if narrow else 2,
                                1, 3 if narrow else 1, Qt.AlignmentFlag.AlignRight)
