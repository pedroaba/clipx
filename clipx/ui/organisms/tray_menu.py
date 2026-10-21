"""Tray menu composition, without storage, drivers, or page navigation."""
from PyQt6.QtWidgets import QMenu


class TrayMenu(QMenu):
    def __init__(self, macos=False, parent=None):
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
        action = self.addAction(title)
        action.setEnabled(False)
        font = action.font()
        font.setBold(True)
        action.setFont(font)
