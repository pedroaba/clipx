"""Tray menu composition, without storage, drivers, or page navigation.

The menu only creates actions and exposes them; ``ClipXTray`` connects them to
storage, platform and window behavior.
"""
from PyQt6.QtWidgets import QMenu


class TrayMenu(QMenu):
    """Context menu with search, recent clips, settings and quit actions.

    Attributes:
        open_action (QAction): Opens the search window.
        empty_action (QAction): Disabled placeholder shown for an empty history.
        clip_actions (list[QAction]): Five reusable slots for recent clips.
        preferences_action (QAction): Opens the preferences dialog.
        shortcuts_action (QAction): Opens the shortcuts section.
        permission_action (QAction | None): macOS-only paste permission request.
        capture_action (QAction): Disabled status line for clipboard capture.
        quit_action (QAction): Quits the application.
    """

    def __init__(self, macos=False, parent=None):
        """Build the menu sections and their actions.

        Args:
            macos (bool): Whether to include the paste-permission action.
            parent (QWidget | None): Optional parent widget.
        """
        super().__init__(parent)
        self.add_section('Pesquisa')
        self.open_action = self.addAction('Open')
        self.addSeparator()
        self.add_section('Últimos 5 clips')
        self.empty_action = self.addAction('Histórico vazio')
        self.empty_action.setEnabled(False)
        self.clip_actions = []
        for _ in range(5):
            action = self.addAction('')
            action.setVisible(False)
            self.clip_actions.append(action)
        self.addSeparator()
        self.add_section('Configurações')
        self.preferences_action = self.addAction('Preferências…')
        self.shortcuts_action = self.addAction('Atalhos')
        self.permission_action = self.addAction('Autorizar colagem no macOS') if macos else None
        self.capture_action = self.addAction('Captura ativa')
        self.capture_action.setEnabled(False)
        self.addSeparator()
        self.add_section('Aplicativo')
        self.quit_action = self.addAction('Quit')

    def add_section(self, title):
        """Add a disabled, bold section heading action.

        Args:
            title (str): Heading text.
        """
        action = self.addAction(title)
        action.setEnabled(False)
        font = action.font()
        font.setBold(True)
        action.setFont(font)
