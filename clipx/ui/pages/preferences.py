"""Unified preferences, retaining the existing shortcut recorder and transaction.

UI preferences and shortcuts share one dialog, one pending-changes counter and
one apply step; the shortcut transaction still rolls back on failure.
"""
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
    """Keep descriptions readable instead of squeezing them beside long selects.

    Attributes:
        control (Select): Control placed beside, or below, the label; assigned by
            the dialog after the row is built.
    """

    def resizeEvent(self, event):
        """Stack the label and control vertically on narrow rows.

        The threshold scales with the window's ``scale`` preference, and the
        control alignment follows the chosen direction.

        Args:
            event (QResizeEvent): Resize event forwarded to the base class.
        """
        super().resizeEvent(event)
        scale = self.window().window.preferences['scale'] / 100
        narrow = self.width() < 620 * scale
        self.layout().setDirection(QBoxLayout.Direction.TopToBottom if narrow else QBoxLayout.Direction.LeftToRight)
        self.layout().setAlignment(self.control, Qt.AlignmentFlag.AlignLeft if narrow else Qt.AlignmentFlag.AlignVCenter)


class PreferencesDialog(ShortcutsDialog):
    """Preferences dialog with shortcut, appearance, content and window pages.

    The shortcut surface built by the parent dialog becomes one page of a shared
    stack. UI controls and shortcuts share the footer counter, and closing with
    pending changes asks whether to apply, discard or keep editing. Successful
    applies advance the baseline without closing the dialog.

    Attributes:
        baseline_ui (dict): Saved UI preferences the draft is compared to.
        controls (dict[str, Select]): Preference selects indexed by key.
        section (str): Section currently displayed.
        navigation (dict[str, QPushButton]): Section buttons indexed by key.
        stack (QStackedWidget): Pages with the shortcut surface first.
        pages (dict[str, QScrollArea]): Scroll areas indexed by section key.
        sample (QFrame): Appearance sample rendered with the draft preferences.
        general_error (QLabel): Error line used outside the shortcut recorder.
    """

    def __init__(self, window, backend=None, section='appearance'):
        """Build the unified dialog and its preference pages.

        Args:
            window (ClipXMainWindow): Window that owns the settings.
            backend (object | None): Global-shortcut backend; a default is
                created by the parent when omitted.
            section (str): Section selected on open.
        """
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
        for key, label in [(k, v[0]) for k, v in SECTIONS.items()] + [('shortcuts', 'Atalhos'), ('updates', 'Atualizações')]:
            button = QPushButton(label)
            button.setObjectName('NavigationItem')
            button.setProperty('lucideIcon', {'appearance': 'palette', 'content': 'panels-top-left',
                                              'window': 'app-window', 'shortcuts': 'keyboard', 'updates': 'loader-circle'}[key])
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
        from clipx.updates import update_service
        from clipx.ui.organisms.update_page import UpdatePage
        self.updates_page = UpdatePage(update_service())
        updates_scroll = QScrollArea()
        updates_scroll.setWidgetResizable(True)
        updates_scroll.setWidget(self.updates_page)
        self.stack.addWidget(updates_scroll)
        self.pages['updates'] = updates_scroll
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
        """Switch to the Shortcuts section and focus its search field.

        This updates the sidebar selection and delegates focusing to the
        shortcut page's search field.
        """
        self.select_section('shortcuts')
        self.focus_search()

    def ui_draft(self):
        """Return the current UI preference values from the controls.

        Returns:
            dict: Preference values indexed by preference key.
        """
        return {key: control.currentData() for key, control in self.controls.items()}

    def dirty(self):
        """Report whether UI preferences or shortcuts differ from the baseline.

        Returns:
            bool: ``True`` when there are unsaved changes.
        """
        return self.ui_draft() != self.baseline_ui or self.controller.draft() != self.controller.baseline

    def update_pending(self, *args):
        """Recount pending changes and refresh the footer and appearance sample.

        Combined counts come from the shortcut controller and the preference
        controls. Does nothing until the dialog finished initializing.

        Args:
            *args: Extra signal arguments, ignored.
        """
        if not self._ready:
            return
        count = self.controller.pending_count + sum(value != self.baseline_ui[key] for key, value in self.ui_draft().items())
        self.footer.set_pending(count, recording=self.controller.recording_name is not None)
        apply_surface(self.sample, self.ui_draft(), PREFERENCES_QSS)

    def select_section(self, name):
        """Display a section, stopping any recording first.

        While the global binding is paused, the request is ignored so the active
        recorder keeps its state.

        Args:
            name (str): Section key to display.
        """
        self.controller.stop_recording()
        if self.controller.paused_binding is not None:
            return
        self.section = name
        self.footer.reset.setVisible(name != 'updates')
        self.stack.setCurrentWidget(self.surface if name == 'shortcuts' else self.pages[name])
        for key, button in self.navigation.items():
            button.setChecked(key == name)
        self.update_pending()

    def restore_section(self):
        """Restore defaults for the current section, without saving them."""
        if self.section == 'updates':
            return
        if self.section == 'shortcuts':
            self.controller.restore_defaults()
        else:
            for key, *_ in SECTIONS[self.section][1]:
                self.controls[key].setCurrentIndex(self.controls[key].findData(DEFAULT_UI[key]))
        self.update_pending()

    def prepare_update_restart(self):
        """Resolve drafts just before the detached installer takes ownership."""
        self.controller.stop_recording()
        if self.controller.paused_binding is not None:
            return False
        if not self.dirty():
            return True
        box = QMessageBox(self)
        box.setWindowTitle('Atualizar o ClipX')
        box.setText('Aplicar as alterações nas configurações antes de atualizar e reiniciar?')
        apply_button = box.addButton('Aplicar e atualizar', QMessageBox.ButtonRole.AcceptRole)
        discard = box.addButton('Descartar e atualizar', QMessageBox.ButtonRole.DestructiveRole)
        keep = box.addButton('Continuar editando', QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(keep)
        from clipx.ui.templates.window import customize_message_box
        customize_message_box(box)
        apply_surface(box, self.window.preferences, PREFERENCES_QSS)
        box.exec()
        if box.clickedButton() is apply_button:
            self.apply_changes()
            return not self.dirty()
        return box.clickedButton() is discard

    def persist_settings(self, shortcuts):
        """Persist the UI draft together with the validated shortcuts.

        Args:
            shortcuts (dict[str, str]): Shortcut values to store.
        """
        self.window.ui_settings.save(self.ui_draft(), shortcuts=shortcuts)

    def apply_changes(self):
        """Apply pending changes with loading feedback.

        Returns:
            object: Whatever ``run_loading`` returns for the apply callback.
        """
        return self.buttons.run_loading(self._apply_changes)

    def _apply_changes(self):
        """Persist shortcuts and preferences, reporting errors inline.

        Shortcuts are saved through the controller transaction when they
        changed; a controller error is mirrored into the footer message. When
        only UI preferences changed, the settings are written directly and write
        failures are shown instead of closing the dialog.
        """
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
        """Apply the UI draft, advance the baselines and refresh the appearance.

        Shortcut messages are cleared, the global binding is re-read when
        possible for future rollbacks, and the footer confirms the apply. The
        dialog stays open.
        """
        if not self._ready:
            return super().accept()
        self.window.apply_preferences(self.ui_draft())
        self.baseline_ui = self.ui_draft()
        self.controller.baseline = self.controller.draft()
        for name, recorder in self.recorders.items():
            if recorder.isEnabled():
                self.controller.set_message(name, '')
        try:
            self.controller.original_global = self.backend.read()
        except (OSError, RuntimeError):
            pass
        self.refresh_appearance()
        self.controller.update_draft()
        self.footer.show_applied()

    def refresh_appearance(self, *args):
        """Reapply the surface theme to the dialog and its appearance sample.

        Args:
            *args: Extra signal arguments, ignored.
        """
        apply_surface(self, self.window.preferences, PREFERENCES_QSS)
        apply_window_chrome(self)
        if self._ready:
            apply_surface(self.sample, self.ui_draft(), PREFERENCES_QSS)

    def cancel_changes(self):
        """Close the dialog without saving, marking the close as confirmed."""
        self._confirmed_close = True
        self.reject()

    def done(self, result):
        """Handle dialog close, offering to apply pending changes first.

        Recording is stopped first, and a paused global binding aborts the
        close. If the draft is dirty, a question offers to apply, discard or
        keep editing; applying still leaves the dialog open when saving fails.
        Args:
            result (int): Dialog result code.
        """
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
