"""Explicit maintenance actions, independent of the preference draft."""
from PyQt6.QtCore import Qt, QThread, QTimer, QSignalBlocker, pyqtSignal
from PyQt6.QtWidgets import (QApplication, QBoxLayout, QFrame, QHBoxLayout, QLabel,
                            QProgressBar, QPushButton, QSizePolicy, QVBoxLayout, QWidget)

from clipx.maintenance import MaintenanceService, PruneOptions
from clipx.ui.molecules.segmented_select import SegmentedSelect
from clipx.ui.molecules.toggle import Toggle
from clipx.ui.foundations.icons import icon, refresh_lucide_button
from clipx.ui.foundations.appearance import palette_for


def prune_description(options):
    if options.mode == 'orphans':
        text = {'data': 'Compacta o banco sem apagar o histórico.',
                'images': 'Remove apenas imagens próprias sem referências e capturas temporárias interrompidas.',
                'all': 'Compacta o banco e remove imagens próprias sem referências e capturas temporárias interrompidas.'}[options.target]
    else:
        text = {'data': 'Apaga o histórico de texto, código, JSON, links e cores. Preserva entradas de imagem.',
                'images': 'Apaga entradas de imagem e libera PNGs próprios sem referências. Preserva arquivos originais externos.',
                'all': 'Apaga o histórico e libera PNGs próprios sem referências. Preserva arquivos originais externos.'}[options.target]
        text += ' Inclui fixados.' if options.include_pinned else ' Preserva fixados e suas imagens.'
    return text + ' O app, as preferências e o clipboard serão mantidos.'


class StableWrapLabel(QLabel):
    """Reserve wrapped space for known copy variants at the current font/width.

    Changing text must not resize the entire scroll page or toggle its scrollbar.
    Long error messages can still grow beyond the reserved minimum.
    """
    def __init__(self, variants=(), minimum_lines=1):
        super().__init__()
        self.variants = tuple(variants)
        self.minimum_lines = minimum_lines
        self.setWordWrap(True)
        self.setTextFormat(Qt.TextFormat.PlainText)

    def heightForWidth(self, width):
        margins = self.contentsMargins()
        available = max(1, width - margins.left() - margins.right() - 2 * self.margin())
        metrics = self.fontMetrics()
        height = max((metrics.boundingRect(0, 0, available, 100000,
                                           int(Qt.TextFlag.TextWordWrap), text).height()
                      for text in (*self.variants, self.text())), default=0)
        return max(height, metrics.lineSpacing() * self.minimum_lines) + margins.top() + margins.bottom() + 2 * self.margin()

    def sizeHint(self):
        hint = super().sizeHint()
        hint.setHeight(self.heightForWidth(max(1, hint.width())))
        return hint


class MaintenanceWorker(QThread):
    result = pyqtSignal(object)
    failed = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, action, parent=None):
        super().__init__(parent)
        self.action = action

    def run(self):
        try:
            self.result.emit(self.action(self.progress.emit))
        except Exception as exc:
            self.failed.emit(str(exc))


class MaintenancePage(QWidget):
    def __init__(self, dialog):
        super().__init__(dialog)
        self.dialog = dialog
        self.service = MaintenanceService(dialog.window.storage.db_path)
        self.worker = None
        self.uninstaller = None
        self.uninstall_folder = None
        self.uninstall_timer = QTimer(self)
        self.uninstall_timer.setInterval(500)
        self.uninstall_timer.timeout.connect(self.check_uninstaller)
        self.pending_result = None
        self._analyzed_options = None
        self._appearance_values = dialog.window.preferences.copy()
        self._target_icon_states = {}
        self.glyph_labels = []
        self.setObjectName('MaintenancePage')
        box = QVBoxLayout(self)
        box.setContentsMargins(28, 24, 28, 24)
        box.setSpacing(18)
        header = QVBoxLayout()
        header.setSpacing(6)
        title = QLabel('Dados e desinstalação')
        title.setObjectName('Heading')
        title.setWordWrap(True)
        header.addWidget(title)
        subtitle = QLabel('Escolha o que limpar do histórico ou remova o app por completo.')
        subtitle.setObjectName('Description')
        subtitle.setWordWrap(True)
        header.addWidget(subtitle)
        box.addLayout(header)

        self.clean_card = QFrame()
        self.clean_card.setObjectName('MaintenanceCard')
        clean = QVBoxLayout(self.clean_card)
        clean.setContentsMargins(18, 18, 18, 18)
        clean.setSpacing(12)
        self.add_heading(clean, 'Limpar dados', 'eraser')
        self.target = SegmentedSelect([('Tudo', 'all', 'layers'), ('Dados', 'data', 'type'),
                                       ('Imagens', 'images', 'image')], vertical_icons=True)
        self.target.setAccessibleName('O que limpar')
        self.target.buttons[1].setToolTip('Texto, código, JSON, links e cores')
        self.mode = SegmentedSelect([('Remover apenas sobras', 'orphans', None),
                                     ('Apagar conteúdo', 'content', None)])
        self.mode.setAccessibleName('Comportamento da limpeza')
        for text, control in [('O que limpar', self.target), ('Comportamento', self.mode)]:
            label = QLabel(text)
            label.setObjectName('MaintenanceLabel')
            label.setBuddy(control.buttons[0])
            clean.addWidget(label)
            clean.addWidget(control)
        self.include_pinned = Toggle('Incluir fixados')
        clean.addWidget(self.include_pinned)
        variants = [prune_description(PruneOptions(target, mode, pins))
                    for target in ('all', 'data', 'images') for mode in ('orphans', 'content')
                    for pins in ((False, True) if mode == 'content' else (False,))]
        self.description = StableWrapLabel(variants)
        self.description.setObjectName('Description')
        self.description.setTextFormat(Qt.TextFormat.PlainText)
        clean.addWidget(self.description)
        self.analyze = QPushButton('Analisar dados')
        self.analyze.setObjectName('MaintenanceAnalyze')
        self.analyze.setProperty('glyphName', 'scan')
        self.prune = QPushButton('Limpar dados…')
        self.prune.setObjectName('MaintenancePrimary')
        self.prune.setProperty('glyphName', 'trash')
        self.prune.setProperty('iconRole', 'canvas')
        actions = QHBoxLayout()
        self.actions = actions
        actions.setSpacing(10)
        actions.addWidget(self.analyze, 1)
        actions.addWidget(self.prune, 1)
        clean.addLayout(actions)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setAccessibleName('Manutenção em andamento')
        self.progress.hide()
        clean.addWidget(self.progress)
        self.status = StableWrapLabel(minimum_lines=2)
        self.status.setObjectName('Description')
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setAccessibleName('Resultado da manutenção')
        clean.addWidget(self.status)
        box.addWidget(self.clean_card)

        self.danger_card = QFrame()
        self.danger_card.setObjectName('MaintenanceDanger')
        danger = QVBoxLayout(self.danger_card)
        danger.setContentsMargins(18, 18, 18, 18)
        danger.setSpacing(12)
        self.add_heading(danger, 'Zona de perigo', 'alert', danger=True)
        hint = QLabel('Desinstalar o ClipX remove o aplicativo e todos os dados desta conta, incluindo '
                      'fixados, backups, preferências e o conteúdo atual da área de transferência. '
                      'Imagens originais externas são preservadas. Essa ação não pode ser desfeita.')
        hint.setWordWrap(True)
        hint.setObjectName('Description')
        danger.addWidget(hint)
        self.uninstall = QPushButton('Desinstalar ClipX e apagar meus dados…')
        self.uninstall.setAccessibleName('Desinstalar ClipX e apagar meus dados')
        self.uninstall.setObjectName('MaintenanceDelete')
        self.uninstall.setProperty('glyphName', 'trash')
        self.uninstall.setProperty('iconRole', 'danger')
        danger.addWidget(self.uninstall)
        box.addWidget(self.danger_card)
        box.addStretch()
        for button in (self.analyze, self.prune, self.uninstall):
            button.setAutoDefault(False)
            button.setMinimumHeight(36)
            button.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.target.currentIndexChanged.connect(self.describe)
        self.mode.currentIndexChanged.connect(self.describe)
        self.include_pinned.toggled.connect(self.describe)
        self.analyze.clicked.connect(self.analyze_data)
        self.prune.clicked.connect(self.confirm_prune)
        self.uninstall.clicked.connect(self.confirm_uninstall)
        self.describe()
        self.refresh_appearance(dialog.window.preferences)
        QApplication.instance().aboutToQuit.connect(self.shutdown)

    def add_heading(self, layout, text, glyph, danger=False):
        row = QHBoxLayout()
        row.setSpacing(10)
        image = QLabel()
        self.glyph_labels.append((image, glyph, 'danger' if danger else 'secondary'))
        row.addWidget(image)
        label = QLabel(text)
        label.setObjectName('MaintenanceDangerTitle' if danger else 'MaintenanceTitle')
        row.addWidget(label, 1)
        layout.addLayout(row)

    def refresh_appearance(self, values):
        self._appearance_values = values.copy()
        self._target_icon_states.clear()
        colors = palette_for(values)
        size = round(18 * values['scale'] / 100)
        for label, glyph, role in self.glyph_labels:
            label.setPixmap(icon(glyph, size, colors[role]).pixmap(size, size))
        for button in self.findChildren(QPushButton):
            if button.property('glyphName'):
                refresh_lucide_button(button, values)
        self.include_pinned.refresh_appearance(values)
        self.refresh_target_icons()
        self.layout_actions()

    def refresh_target_icons(self):
        for button in self.target.buttons:
            checked = button.isChecked()
            if self._target_icon_states.get(button) != checked:
                refresh_lucide_button(button, self._appearance_values)
                self._target_icon_states[button] = checked

    def layout_actions(self):
        margins = self.clean_card.layout().contentsMargins()
        available = self.clean_card.width() - margins.left() - margins.right()
        required = self.analyze.sizeHint().width() + self.prune.sizeHint().width() + self.actions.spacing()
        direction = QBoxLayout.Direction.TopToBottom if available < required else QBoxLayout.Direction.LeftToRight
        if self.actions.direction() != direction:
            self.actions.setDirection(direction)
        label = 'Desinstalar ClipX e apagar meus dados…'
        required = self.uninstall.fontMetrics().horizontalAdvance(label) + self.uninstall.iconSize().width() + 40
        text = 'Desinstalar ClipX e\napagar meus dados…' if available < required else label
        if self.uninstall.text() != text:
            self.uninstall.setText(text)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.layout_actions()

    def sync_controls(self):
        for widget in (self.target, self.mode, self.analyze, self.uninstall):
            widget.setEnabled(not self.busy)
        self.include_pinned.setEnabled(not self.busy and self.mode.currentData() == 'content')
        self.prune.setEnabled(not self.busy and self._analyzed_options == self.options())

    @property
    def busy(self):
        return self.worker is not None or self.uninstaller is not None

    def options(self):
        return PruneOptions(self.target.currentData(), self.mode.currentData(), self.include_pinned.isChecked())

    def describe(self, *args):
        content = self.mode.currentData() == 'content'
        self.include_pinned.setEnabled(content and not self.busy)
        if not content:
            with QSignalBlocker(self.include_pinned):
                self.include_pinned.setChecked(False)
        self.description.setText(prune_description(self.options()))
        self._analyzed_options = None
        self.status.setText('Analise os dados para ver a estimativa com a configuração atual.')
        self.sync_controls()
        self.refresh_target_icons()

    def start(self, action, completed):
        if self.busy:
            return
        from clipx.updates import update_service
        if update_service().busy:
            self.status.setText('Aguarde a atualização ou cancele o download antes de limpar dados.')
            return
        self.pending_result = None
        self.worker = MaintenanceWorker(action, self)
        self.worker.result.connect(lambda result: setattr(self, 'pending_result', (completed, result)))
        self.worker.failed.connect(lambda message: self.status.setText('Não foi possível concluir: ' + message))
        self.worker.progress.connect(self.status.setText)
        self.worker.finished.connect(self.finished)
        self.progress.show()
        self.sync_controls()
        QTimer.singleShot(0, self.reveal_progress)
        self.worker.start()

    def reveal_progress(self):
        if self.busy and not self.progress.isHidden():
            self.dialog.pages['maintenance'].ensureWidgetVisible(self.progress, 0, 24)

    def finished(self):
        self.worker.deleteLater()
        self.worker = None
        self.progress.hide()
        self.sync_controls()
        if self.pending_result is not None:
            callback, result = self.pending_result
            self.pending_result = None
            callback(result)

    def confirmation(self, spec):
        from clipx.ui.organisms.maintenance_confirmation import MaintenanceConfirmation
        box = MaintenanceConfirmation(spec, self.dialog.window.preferences, self.dialog)
        try:
            return box.exec() == box.DialogCode.Accepted
        finally:
            box.deleteLater()

    def analyze_data(self):
        options = self.options()
        self._analyzed_options = None
        self.sync_controls()
        def analyzed(result):
            self._analyzed_options = options if result.ok else None
            self.status.setText(result.summary(estimate=True))
            self.sync_controls()
        self.start(lambda progress: self.service.inspect(options), analyzed)

    def confirm_prune(self):
        options = self.options()
        from clipx.ui.organisms.maintenance_confirmation import prune_confirmation
        def inspected(result):
            self.status.setText(result.summary(estimate=True))
            if self.confirmation(prune_confirmation(options, result)):
                self.start(lambda progress: self.service.prune(options, progress), self.pruned)
        self.start(lambda progress: self.service.inspect(options), inspected)

    def pruned(self, result):
        self._analyzed_options = None
        self.sync_controls()
        self.status.setText(result.summary())
        self.dialog.window.load_clips()
        self.dialog.window.preview_pane.refresh_image()
        self.dialog.window.maintenance_finished.emit()

    def confirm_uninstall(self):
        from clipx.uninstall import inventory, prepare_helper, launch_helper
        def inspected(result):
            from clipx.ui.organisms.maintenance_confirmation import uninstall_confirmation
            if not self.confirmation(uninstall_confirmation(result)):
                return
            appearance = self.dialog.window.preferences.copy()
            def prepared(value):
                try:
                    self.uninstaller = launch_helper(value, detached=True)
                except OSError as exc:
                    import shutil
                    shutil.rmtree(value[0])
                    self.status.setText('Não foi possível iniciar a desinstalação: ' + str(exc))
                    return
                self.dialog._confirmed_close = True
                self.dialog.controller.stop_recording()
                self.uninstall_folder = value[0]
                self.progress.show()
                for widget in (self.target, self.mode, self.include_pinned, self.analyze, self.prune, self.uninstall):
                    widget.setEnabled(False)
                self.uninstall_timer.start()
                self.status.setText('Abrindo a janela independente de progresso…')
            def prepare(progress):
                progress('Preparando uma cópia independente do desinstalador…')
                return prepare_helper(gui=True, values=appearance)
            self.start(prepare, prepared)
        self.start(lambda progress: inventory(), inspected)

    def check_uninstaller(self):
        """Quit only after the independent progress UI is ready to take over."""
        if self.uninstaller is None:
            return
        code = self.uninstaller.poll()
        ready = (self.uninstall_folder / 'helper-ready').is_file()
        shown_result = (self.uninstall_folder / 'ui-result-shown').is_file()
        if code is None:
            if ready and not shown_result and not getattr(self.dialog, '_maintenance_shutdown', False):
                self.dialog._confirmed_close = True
                self.dialog._maintenance_shutdown = True
                self.status.setText('Encerrando o ClipX. A desinstalação continua na janela de progresso…')
                QApplication.instance().quit()
            return
        self.uninstall_timer.stop()
        self.uninstaller = None
        self.progress.hide()
        try:
            message = (self.uninstall_folder / 'result.log').read_text()[:8192]
        except OSError:
            message = 'O desinstalador encerrou antes de confirmar o encerramento do ClipX. Tente novamente.'
        if code == 0:
            message = 'A interface original continua aberta; a desinstalação não foi confirmada.\n' + message
        self.status.setText(message)
        self.dialog._confirmed_close = False
        self.dialog._maintenance_shutdown = False
        self.sync_controls()

    def shutdown(self):
        if self.worker is not None:
            self.worker.wait()
