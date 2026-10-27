"""Independent progress UI that survives shutdown/removal of the original app."""
import sys

from PyQt6.QtCore import QEvent, QThread, QTimer, pyqtSignal
from PyQt6.QtWidgets import QApplication, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget

from clipx.maintenance import MaintenanceResult, validate_path
from clipx.ui.foundations.appearance import apply_surface
from clipx.ui.foundations.preferences import PREFERENCES_QSS
from clipx.ui.templates.window import SystemDialog


class UninstallWorker(QThread):
    progress = pyqtSignal(str)
    result = pyqtSignal(object)

    def __init__(self, action, parent):
        super().__init__(parent)
        self.action = action

    def run(self):
        try:
            result = self.action(self.progress.emit)
        except Exception as exc:
            result = MaintenanceResult(errors=['Desinstalação interrompida: ' + str(exc)])
        self.result.emit(result)


class UninstallProgressDialog(SystemDialog):
    completed = pyqtSignal(int)

    def __init__(self, folder, action, values, success_delay_ms=1600):
        super().__init__()
        self.folder = validate_path(folder)
        self.outcome = None
        self.started = False
        self.success_delay_ms = success_delay_ms
        self.setWindowTitle('Desinstalando o ClipX')
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        self.heading = QLabel('Desinstalando o ClipX')
        self.heading.setObjectName('Heading')
        self.heading.setWordWrap(True)
        self.status = QLabel('Preparando o encerramento do aplicativo…')
        self.status.setObjectName('Description')
        self.status.setWordWrap(True)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setAccessibleName('Progresso da desinstalação')
        self.close_button = QPushButton('Fechar')
        self.close_button.setEnabled(False)
        self.close_button.clicked.connect(self.finish)
        for widget in (self.heading, self.status, self.progress, self.close_button):
            layout.addWidget(widget)
        self.mount_content(body, maximize=False)
        apply_surface(self, values, PREFERENCES_QSS)
        self.resize(min(round(500 * values['scale'] / 100), self.screen().availableGeometry().width() - 40),
                    self.sizeHint().height())
        self.worker = UninstallWorker(action, self)
        self.worker.progress.connect(self.set_progress)
        self.worker.result.connect(self.show_result)

    def showEvent(self, event):
        super().showEvent(event)
        if not self.started:
            self.started = True
            # Give the independent window its first frame before handing off.
            QTimer.singleShot(50, self.begin)

    def begin(self):
        try:
            (self.folder / 'helper-ready').write_text('ready\n')
        except OSError as exc:
            self.show_result(MaintenanceResult(errors=['Não foi possível preparar o encerramento: ' + str(exc)]))
            return
        self.worker.start()

    def set_progress(self, message):
        self.status.setText(message)
        print(message, flush=True)

    def show_result(self, result):
        self.outcome = 0 if result.ok else 1
        self.heading.setText('Desinstalação concluída' if result.ok else 'Não foi possível concluir')
        message = result.summary()
        if result.ok:
            message += '\nO ClipX foi encerrado. Esta janela será fechada automaticamente.'
        else:
            message += '\nDetalhes: ' + str(self.folder / 'result.log')
        self.status.setText(message)
        print(message, flush=True)
        self.progress.setRange(0, 1)
        self.progress.setValue(1 if result.ok else 0)
        self.close_button.setEnabled(True)
        self.close_button.setDefault(True)
        try:
            (self.folder / 'ui-result-shown').write_text(str(self.outcome))
        except OSError as exc:
            print('Não foi possível registrar o resultado visual: ' + str(exc), flush=True)
        if result.ok and self.success_delay_ms is not None:
            QTimer.singleShot(self.success_delay_ms, self.finish)

    def finish(self):
        if self.outcome is None:
            return
        self.worker.wait()
        code = self.outcome
        super().done(self.DialogCode.Accepted if code == 0 else self.DialogCode.Rejected)
        self.completed.emit(code)

    def reject(self):
        if self.outcome is not None:
            self.finish()

    def closeEvent(self, event):
        if self.outcome is None:
            event.ignore()
        else:
            self.finish()
            event.accept()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Quit and self.outcome is None:
            return True
        return super().eventFilter(watched, event)


def run_uninstall_progress(args):
    from clipx.uninstall import execute
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)
    def action(progress):
        return execute(args.original, args.kind, args.exclude_pid, progress=progress,
                       parent_pid=args.parent_pid, parent_identity=args.parent_identity)
    window = UninstallProgressDialog(args.helper_folder, action,
                                     {'theme': args.theme, 'scale': args.scale})
    window.completed.connect(app.exit)
    app.installEventFilter(window)
    window.show()
    code = app.exec()
    app.removeEventFilter(window)
    if window.outcome is None:
        window.worker.wait()
        print('O desinstalador encerrou sem confirmar o resultado.', flush=True)
        return 1
    return window.outcome if code == 0 else code
