"""Update status and actions; all work and lifetime belong to UpdateService."""
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QPushButton, QProgressBar,
                            QFileDialog)


class UpdatePage(QWidget):
    """A read-only preferences section with independent immediate actions."""

    def __init__(self, service, parent=None):
        super().__init__(parent)
        self.service = service
        box = QVBoxLayout(self)
        box.setContentsMargins(28, 24, 28, 20)
        box.setSpacing(12)
        heading = QLabel('Atualizações')
        heading.setObjectName('Heading')
        box.addWidget(heading)
        self.installed = QLabel(f'Versão instalada · {service.current_version}')
        box.addWidget(self.installed)
        self.available = QLabel()
        box.addWidget(self.available)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setAccessibleName('Status da atualização')
        box.addWidget(self.status)
        self.last_check = QLabel()
        self.last_check.setObjectName('Description')
        self.last_check.setWordWrap(True)
        box.addWidget(self.last_check)
        self.progress = QProgressBar()
        self.progress.setAccessibleName('Progresso do download')
        self.progress.setRange(0, 100)
        box.addWidget(self.progress)
        self.check = QPushButton('Verificar atualizações')
        self.check.clicked.connect(service.check)
        self.install = QPushButton('Atualizar e reiniciar')
        self.install.setObjectName('ApplyButton')
        self.install.clicked.connect(lambda: service.download(install=True))
        self.download = QPushButton('Baixar instalador')
        self.download.clicked.connect(self.save_installer)
        self.cancel = QPushButton('Cancelar download')
        self.cancel.clicked.connect(service.cancel)
        self.open_file = QPushButton('Abrir instalador')
        self.open_file.clicked.connect(self.open_installer)
        self.notes = QPushButton('Notas da versão ↗')
        self.notes.clicked.connect(self.open_notes)
        for button in (self.check, self.install, self.download, self.cancel, self.open_file, self.notes):
            button.setAutoDefault(False)
            box.addWidget(button, 0, Qt.AlignmentFlag.AlignLeft)
        self.hint = QLabel(service.install_reason)
        self.hint.setObjectName('Description')
        self.hint.setWordWrap(True)
        box.addWidget(self.hint)
        box.addStretch()
        service.changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        """Reflect shared state without initiating checks on page navigation."""
        service = self.service
        self.status.setText(service.message)
        self.last_check.setText('Última verificação · ' + service.last_check if service.last_check else 'A verificação acontece somente quando você solicita.')
        self.available.setText('Versão publicada · ' + service.release.version if service.release else '')
        self.available.setVisible(service.release is not None)
        self.check.setEnabled(not service.busy)
        self.check.setText('Verificando…' if service.state == 'checking' else 'Verificar atualizações')
        has_update = service.update_available
        self.install.setVisible(has_update and not service.install_reason)
        self.install.setEnabled(not service.busy)
        self.download.setVisible(has_update)
        self.download.setEnabled(not service.busy)
        cancellable = service.state in ('downloading', 'validating') and service.worker is not None
        self.cancel.setVisible(cancellable)
        self.progress.setVisible(service.state in ('downloading', 'validating'))
        self.progress.setValue(round(100 * service.received / service.total) if service.total else 0)
        self.progress.setFormat('%p%' if service.state == 'downloading' else 'Validando…')
        self.open_file.setVisible(service.state == 'downloaded' and service.installer is not None)
        self.notes.setVisible(service.release is not None)
        self.hint.setVisible(bool(service.install_reason))

    def save_installer(self):
        """Ask for a destination before starting a verified download."""
        if self.service.busy or not self.service.release:
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Salvar instalador do ClipX', self.service.release.filename,
                                             'Instalador (*.dmg)' if self.service.release.filename.endswith('.dmg') else 'Pacote Debian (*.deb)')
        if path:
            self.service.download(path)

    def open_installer(self):
        if self.service.installer and not QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.service.installer))):
            self.service.set_state('error', 'Não foi possível abrir o instalador. Abra o arquivo salvo pelo gerenciador de arquivos.')

    def open_notes(self):
        if self.service.release and not QDesktopServices.openUrl(QUrl(self.service.release.notes_url)):
            self.service.set_state('error', 'Não foi possível abrir as notas da versão no navegador.')
