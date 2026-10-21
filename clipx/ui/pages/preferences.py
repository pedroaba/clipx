"""Unified preferences, retaining the existing shortcut recorder and transaction."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
                            QStackedWidget, QScrollArea, QMessageBox, QFrame, QBoxLayout)
from clipx.preferences import DEFAULT_UI
from clipx.ui.pages.shortcuts import ShortcutsDialog
from clipx.ui.molecules.select import Select
from clipx.ui.foundations.appearance import apply_surface
from clipx.ui.foundations.preferences import PREFERENCES_QSS
from clipx.platforms.window_chrome import apply_window_chrome
from clipx.ui.foundations.icons import refresh_lucide_button

SECTIONS = {
    'appearance': ('Aparência', [
        ('theme', 'Tema', 'Escolha o visual de todas as janelas e menus.', [('Escuro', 'dark'), ('Claro', 'light'), ('Acompanhar sistema', 'system')]),
        ('scale', 'Escala da interface', 'Ajusta textos e controles juntos.', [(f'{n}%', n) for n in (100, 110, 125, 150)]),
        ('density', 'Densidade da lista', '', [('Confortável', 'comfortable'), ('Compacta', 'compact')]),
        ('material', 'Material da pesquisa', 'O material nativo depende da plataforma e da acessibilidade.', [('Padrão da plataforma', 'platform'), ('Opaco', 'opaque')]),
        ('motion', 'Movimento', 'A redução de movimento do sistema sempre prevalece.', [('Acompanhar sistema', 'system'), ('Reduzir', 'reduce')]),
    ]),
    'content': ('Lista e prévia', [
        ('preview', 'Painel de prévia', '', [('Mostrar', True), ('Ocultar', False)]),
        ('lines', 'Linhas de conteúdo por item', '', [(str(n), n) for n in (1, 2, 3)]),
        ('metadata', 'Metadados na lista', 'Tipo e tempo. A indicação de fixação permanece visível.', [('Mostrar', True), ('Ocultar', False)]),
        ('preview_size', 'Tamanho do texto da prévia', 'Tamanho base, antes da escala da interface.', [(f'{n} pt', n) for n in (12, 14, 16, 18)]),
        ('syntax', 'Destaque de sintaxe', '', [('Ativado', True), ('Desativado', False)]),
    ]),
    'window': ('Janela', [
        ('position', 'Posição ao abrir', '', [('Tela do cursor', 'cursor'), ('Última posição', 'last')]),
        ('remember_size', 'Lembrar tamanho e divisão dos painéis', '', [('Ativado', True), ('Desativado', False)]),
        ('hide_on_blur', 'Ocultar ao perder foco', 'Menus e diálogos do ClipX mantêm a pesquisa aberta.', [('Ativado', True), ('Desativado', False)]),
        ('reopen', 'Busca ao reabrir', 'Limpar também retorna ao filtro Todos.', [('Manter pesquisa', 'keep'), ('Limpar pesquisa', 'clear')]),
    ]),
}


class PreferenceRow(QWidget):
    """Keep descriptions readable instead of squeezing them beside long selects."""
    def resizeEvent(self, event):
        super().resizeEvent(event)
        scale = self.window().window.preferences['scale'] / 100
        narrow = self.width() < 620 * scale
        self.layout().setDirection(QBoxLayout.Direction.TopToBottom if narrow else QBoxLayout.Direction.LeftToRight)
        self.layout().setAlignment(self.control, Qt.AlignmentFlag.AlignLeft if narrow else Qt.AlignmentFlag.AlignVCenter)


class PreferencesDialog(ShortcutsDialog):
    def __init__(self, window, backend=None, section='appearance'):
        self._ready = False
        super().__init__(window, backend)
        self.setWindowTitle('ClipX — Preferências')
        self.baseline_ui = window.preferences.copy()
        self.controls = {}
        self.section = section
        self.navigation = {}
        # Move existing shortcut surface into the shared content stack.
        self.layout().removeWidget(self.surface)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.surface)
        self.surface.layout().itemAt(1).layout().removeWidget(self.footer)
        self.surface.findChild(QLabel, 'PreferencesHint').setWordWrap(True)
        self.sidebar.hide()
        self.category_select = Select(heading='Categoria de atalhos')
        self.category_select.setAccessibleName('Categoria dos atalhos')
        from clipx.ui.models.shortcut_catalog import CATEGORIES
        for key, label, glyph in CATEGORIES:
            self.category_select.addItem(label, key)
        self.category_select.currentIndexChanged.connect(lambda: self.controller.change_category(self.category_select.currentData()))
        header = self.surface.layout().itemAt(1).layout().itemAt(0).widget()
        header.layout().addWidget(self.category_select)
        self.root = QWidget()
        self.root.setObjectName('PreferencesLayout')
        row = QHBoxLayout(self.root)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        nav = QFrame()
        nav.setObjectName('PreferencesSidebar')
        nav.setFixedWidth(198)
        nav_layout = QVBoxLayout(nav)
        nav_layout.setContentsMargins(12, 20, 12, 12)
        for key, label in [(k, v[0]) for k, v in SECTIONS.items()] + [('shortcuts', 'Atalhos')]:
            button = QPushButton(label)
            button.setObjectName('NavigationItem')
            button.setProperty('lucideIcon', {'appearance': 'palette', 'content': 'panels-top-left',
                                              'window': 'app-window', 'shortcuts': 'keyboard'}[key])
            button.toggled.connect(lambda checked, item=button: refresh_lucide_button(item, self.window.preferences))
            button.setMinimumHeight(40)
            button.setCheckable(True)
            button.setAutoDefault(False)
            button.clicked.connect(lambda checked=False, name=key: self.select_section(name))
            nav_layout.addWidget(button)
            self.navigation[key] = button
        nav_layout.addStretch()
        row.addWidget(nav)
        main = QVBoxLayout()
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)
        main.addWidget(self.stack, 1)
        self.general_error = QLabel()
        self.general_error.setObjectName('PreferencesError')
        self.general_error.setWordWrap(True)
        self.general_error.hide()
        main.addWidget(self.general_error)
        main.addWidget(self.footer)
        row.addLayout(main, 1)
        self.layout().addWidget(self.root)
        self.pages = {}
        for key, (title, fields) in SECTIONS.items():
            page = QWidget()
            box = QVBoxLayout(page)
            box.setContentsMargins(28, 24, 28, 20)
            heading = QLabel(title)
            heading.setObjectName('Heading')
            box.addWidget(heading)
            box.addSpacing(16)
            for name, label, description, choices in fields:
                row_widget = PreferenceRow()
                line = QBoxLayout(QBoxLayout.Direction.LeftToRight, row_widget)
                line.setContentsMargins(0, 0, 0, 0)
                copy = QVBoxLayout()
                caption = QLabel(label)
                caption.setWordWrap(True)
                copy.addWidget(caption)
                if description:
                    hint = QLabel(description)
                    hint.setObjectName('Description')
                    hint.setWordWrap(True)
                    copy.addWidget(hint)
                line.addLayout(copy, 1)
                control = Select(heading=label)
                control.setAccessibleName(label)
                caption.setBuddy(control)
                for text, value in choices:
                    control.addItem(text, value)
                control.setCurrentIndex(control.findData(self.baseline_ui[name]))
                control.currentIndexChanged.connect(self.update_pending)
                self.controls[name] = control
                line.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
                row_widget.control = control
                box.addWidget(row_widget)
                separator = QFrame()
                separator.setObjectName('PreferencesSeparator')
                separator.setFixedHeight(1)
                box.addWidget(separator)
                box.addSpacing(8)
                if name == 'material' and window.platform.name != 'macos':
                    control.setEnabled(False)
                    hint.setText('Nesta plataforma, a pesquisa usa uma superfície opaca.')
                    control.setToolTip('Material nativo disponível no macOS.')
            if key == 'appearance':
                label = QLabel('Amostra · conteúdo fictício')
                label.setObjectName('Description')
                box.addWidget(label)
                self.sample = QFrame()
                self.sample.setObjectName('ShortcutGroup')
                sample_layout = QVBoxLayout(self.sample)
                sample_layout.addWidget(QLabel('Texto copiado de exemplo'))
                detail = QLabel('Código · agora\nprint("Olá, ClipX")')
                detail.setObjectName('Description')
                sample_layout.addWidget(detail)
                box.addWidget(self.sample)
            box.addStretch()
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(page)
            self.stack.addWidget(scroll)
            self.pages[key] = scroll
        self.footer.reset.clicked.disconnect()
        self.buttons.accepted.disconnect()
        self.buttons.rejected.disconnect()
        self.footer.change_label.setWordWrap(True)
        self.footer.reset.setText('Restaurar seção')
        self.footer.reset.clicked.connect(self.restore_section)
        self.buttons.accepted.connect(self.apply_changes)
        self.buttons.rejected.connect(self.cancel_changes)
        for recorder in self.recorders.values():
            recorder.sequence_changed.connect(self.update_pending)
        self._ready = True
        self.find_shortcut.activated.disconnect()
        self.find_shortcut.activated.connect(self.focus_shortcut_search)
        self._confirmed_close = False
        self.select_section(section)
        self.refresh_appearance()
        self.update_pending()
        from PyQt6.QtWidgets import QApplication
        QApplication.styleHints().colorSchemeChanged.connect(self.refresh_appearance)

    def focus_shortcut_search(self):
        self.select_section('shortcuts')
        self.focus_search()

    def ui_draft(self):
        return {key: control.currentData() for key, control in self.controls.items()}

    def dirty(self):
        return self.ui_draft() != self.baseline_ui or self.controller.draft() != self.controller.baseline

    def update_pending(self, *args):
        if not self._ready:
            return
        count = self.controller.pending_count + sum(value != self.baseline_ui[key] for key, value in self.ui_draft().items())
        self.footer.set_pending(count, recording=self.controller.recording_name is not None)
        apply_surface(self.sample, self.ui_draft(), PREFERENCES_QSS)

    def select_section(self, name):
        self.controller.stop_recording()
        if self.controller.paused_binding is not None:
            return
        self.section = name
        self.stack.setCurrentWidget(self.surface if name == 'shortcuts' else self.pages[name])
        for key, button in self.navigation.items():
            button.setChecked(key == name)
        self.update_pending()

    def restore_section(self):
        if self.section == 'shortcuts':
            self.controller.restore_defaults()
        else:
            for key, *_ in SECTIONS[self.section][1]:
                self.controls[key].setCurrentIndex(self.controls[key].findData(DEFAULT_UI[key]))
        self.update_pending()

    def persist_settings(self, shortcuts):
        self.window.ui_settings.save(self.ui_draft(), shortcuts=shortcuts)

    def apply_changes(self):
        self.general_error.hide()
        self.error_label.hide()
        if self.controller.draft() != self.controller.baseline:
            self.controller.save()
            if not self.error_label.isHidden():
                self.general_error.setText(self.error_label.text())
                self.general_error.show()
        else:
            try:
                self.persist_settings(self.window.shortcuts)
            except (OSError, ValueError) as exc:
                self.general_error.setText('Não foi possível salvar: ' + str(exc))
                self.general_error.show()
                return
            self.accept()

    def accept(self):
        if not self._ready:
            return super().accept()
        self.window.apply_preferences(self.ui_draft())
        self.baseline_ui = self.ui_draft()
        self.controller.baseline = self.controller.draft()
        try:
            self.controller.original_global = self.backend.read()
        except (OSError, RuntimeError):
            pass
        self.refresh_appearance()
        self.update_pending()

    def refresh_appearance(self, *args):
        apply_surface(self, self.window.preferences, PREFERENCES_QSS)
        apply_window_chrome(self)
        if self._ready:
            apply_surface(self.sample, self.ui_draft(), PREFERENCES_QSS)

    def cancel_changes(self):
        self._confirmed_close = True
        self.reject()

    def done(self, result):
        self.controller.stop_recording()
        if self.controller.paused_binding is not None:
            self._confirmed_close = False
            return
        if self._ready and not self._confirmed_close and self.dirty():
            box = QMessageBox(self)
            box.setWindowTitle('Alterações não salvas')
            box.setText('Aplicar as alterações antes de fechar?')
            apply_button = box.addButton('Aplicar', QMessageBox.ButtonRole.AcceptRole)
            discard = box.addButton('Descartar', QMessageBox.ButtonRole.DestructiveRole)
            keep_editing = box.addButton('Continuar editando', QMessageBox.ButtonRole.RejectRole)
            box.setDefaultButton(keep_editing)
            from clipx.ui.templates.window import customize_message_box
            customize_message_box(box)
            apply_surface(box, self.window.preferences, PREFERENCES_QSS)
            box.exec()
            if box.clickedButton() is apply_button:
                self.apply_changes()
                if self.dirty():
                    return
            elif box.clickedButton() is not discard:
                return
        super().done(result)
