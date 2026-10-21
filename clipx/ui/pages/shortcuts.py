"""Shortcut preferences page: composition and dialog lifecycle only."""
from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import QApplication, QDialog, QVBoxLayout, QMessageBox
from clipx.shortcuts import GlobalShortcut
from clipx.ui.templates.window import SystemDialog, customize_message_box
from clipx.ui.models.shortcut_catalog import CATALOG, CONFLICT_NAMES
from clipx.ui.molecules.shortcut_recorder import display_shortcut
from clipx.ui.molecules.shortcut_search import ShortcutSearch
from clipx.ui.organisms.shortcut_sidebar import ShortcutSidebar
from clipx.ui.organisms.shortcut_sections import ShortcutSections
from clipx.ui.organisms.preferences_footer import PreferencesFooter
from clipx.ui.templates.preferences import PreferencesLayout
from clipx.ui.controllers.shortcuts import ShortcutsController
from clipx.ui.pages.shortcut_picker import ShortcutPicker
from clipx.ui.foundations.preferences import PREFERENCES_QSS


class ShortcutsDialog(SystemDialog):
    def __init__(self, window, backend=None):
        super().__init__()
        self.window = window
        self.backend = backend or GlobalShortcut()
        self.setWindowTitle('ClipX — Atalhos')
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setMinimumSize(820, 580)
        screen = QApplication.screenAt(window.frameGeometry().center()) or QApplication.primaryScreen()
        area = screen.availableGeometry() if screen else None
        self.resize(min(1040, area.width() - 64) if area else 1040,
                    min(740, area.height() - 80) if area else 740)
        self.setStyleSheet(PREFERENCES_QSS)
        self.sidebar = ShortcutSidebar(CATALOG)
        self.search_field = ShortcutSearch()
        self.sections = ShortcutSections(CATALOG, {'global': '', **window.shortcuts})
        self.rows = self.sections.rows
        self.recorders = {name: row.recorder for name, row in self.rows.items()}
        self.editors = {name: recorder for name, recorder in self.recorders.items() if name != 'global'}
        self.messages = {name: row.message for name, row in self.rows.items()}
        self.clear_buttons = {name: row.clear_button for name, row in self.rows.items()}
        self.global_edit = self.recorders['global']
        self.choose_button = self.rows['global'].choose_button
        self.footer = PreferencesFooter()
        self.buttons = self.footer.buttons
        self.apply_button = self.footer.apply
        self.surface = PreferencesLayout(self.sidebar, self.search_field, self.sections,
                                         self.footer, self.backend.modifier_hint)
        self.error_label = self.surface.error_label
        self.mount_content(self.surface)
        self.controller = ShortcutsController(self, window, self.backend)
        self.find_shortcut = QShortcut(QKeySequence('Ctrl+F'), self)
        self.find_shortcut.activated.connect(self.focus_search)
        if area:
            self.move(area.x() + (area.width() - self.width()) // 2,
                      area.y() + max(0, (area.height() - self.height()) // 2))

    def focus_search(self):
        if self.controller.recording_name is None:
            self.search_field.input.setFocus()
            self.search_field.input.selectAll()

    def event(self, event):
        if event.type() == QEvent.Type.WindowDeactivate and hasattr(self, 'controller'):
            self.controller.stop_recording()
        return super().event(event)

    def done(self, result):
        self.controller.stop_recording()
        if self.controller.paused_binding is not None:
            return
        self.controller.detach()
        super().done(result)

    def pick_global_sequence(self):
        picker = ShortcutPicker(self.global_edit.keySequence(), self)
        from clipx.ui.foundations.appearance import apply_surface
        apply_surface(picker, self.window.preferences, picker.styleSheet())
        result = picker.exec()
        sequence = picker.selected_sequence if result == QDialog.DialogCode.Accepted else None
        picker.deleteLater()
        return sequence

    def confirm_reassignment(self, sequence, conflicts):
        names = [CONFLICT_NAMES.get(item["name"], item["name"]) for item in conflicts]
        question = QMessageBox(self)
        question.setWindowTitle("Usar " + display_shortcut(sequence) + " no ClipX?")
        question.setIcon(QMessageBox.Icon.Question)
        question.setText("Esta combinação está em uso em:\n" + "\n".join("• " + name for name in names))
        question.setInformativeText("Ao confirmar, somente esta combinação será removida dessas ações "
                                    "e usada para abrir a pesquisa do ClipX. "
                                    "Os outros atalhos dessas ações serão mantidos.")
        use_button = question.addButton("Usar no ClipX", QMessageBox.ButtonRole.AcceptRole)
        back_button = question.addButton("Voltar", QMessageBox.ButtonRole.RejectRole)
        question.setDefaultButton(back_button)
        customize_message_box(question)
        from clipx.ui.foundations.appearance import apply_surface
        apply_surface(question, self.window.preferences, PREFERENCES_QSS)
        question.exec()
        return question.clickedButton() is use_button
