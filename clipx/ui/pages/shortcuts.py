"""Shortcut preferences page: composition and dialog lifecycle only.

The dialog composes the sidebar, search field, sections and footer into the
preferences layout, wires the controller for recording and transactions, and
provides the global-shortcut picker and conflict confirmation flows.
"""
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
    """Dialog that composes the shortcut preferences UI and its controller.

    Attributes:
        window (ClipXMainWindow): Window that owns the shortcut settings.
        backend (object): Global-shortcut backend used to read, write and pause
            bindings.
        sidebar (ShortcutSidebar): Category navigation.
        search_field (ShortcutSearch): Shortcut search input.
        sections (ShortcutSections): Grouped shortcut rows.
        rows (dict[str, ShortcutRow]): Rows indexed by shortcut name.
        recorders (dict[str, ShortcutRecorder]): Recorders indexed by name.
        editors (dict[str, ShortcutRecorder]): Search shortcut recorders only.
        messages (dict[str, QLabel]): Status labels indexed by shortcut name.
        clear_buttons (dict[str, QPushButton]): Clear buttons indexed by name.
        global_edit (ShortcutRecorder): Recorder for the global shortcut.
        choose_button (QPushButton): Button that opens the global picker.
        footer (PreferencesFooter): Footer with reset and apply/cancel.
        buttons (DialogActions): Apply and cancel button pair.
        apply_button (QPushButton): Alias of the footer apply button.
        surface (PreferencesLayout): Composed layout inside the dialog.
        error_label (QLabel): Error label used by the controller.
        controller (ShortcutsController): Coordinator for recording and saving.
        find_shortcut (QShortcut): Shortcut that focuses the search field.
    """

    def __init__(self, window, backend=None):
        """Compose the UI and start the controller.

        Args:
            window (ClipXMainWindow): Window that owns the shortcut settings.
            backend (object | None): Global-shortcut backend; a default
                ``GlobalShortcut`` is created when omitted.
        """
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
        """Focus and select the search field, unless a shortcut is recording."""
        if self.controller.recording_name is None:
            self.search_field.input.setFocus()
            self.search_field.input.selectAll()

    def event(self, event):
        """Stop recording when the dialog loses focus.

        Args:
            event (QEvent): Event being processed.

        Returns:
            bool: Result of the base class handler.
        """
        if event.type() == QEvent.Type.WindowDeactivate and hasattr(self, 'controller'):
            self.controller.stop_recording()
        return super().event(event)

    def done(self, result):
        """Close the dialog, stopping recording and detaching the controller.

        A paused global binding aborts the close so the active recording can
        finish cleanly.

        Args:
            result (int): Dialog result code.
        """
        self.controller.stop_recording()
        if self.controller.paused_binding is not None:
            return
        self.controller.detach()
        super().done(result)

    def pick_global_sequence(self):
        """Open the global shortcut picker and return the selected sequence.

        The picker is themed with the window preferences and deleted after use.

        Returns:
            str | None: Normalized portable sequence, or ``None`` if canceled.
        """
        picker = ShortcutPicker(self.global_edit.keySequence(), self)
        from clipx.ui.foundations.appearance import apply_surface
        apply_surface(picker, self.window.preferences, picker.styleSheet())
        result = picker.exec()
        sequence = picker.selected_sequence if result == QDialog.DialogCode.Accepted else None
        picker.deleteLater()
        return sequence

    def confirm_reassignment(self, sequence, conflicts):
        """Ask the user whether to transfer a system shortcut to ClipX.

        Only the chosen combination is removed from the listed apps; other
        bindings in those apps remain unchanged.

        Args:
            sequence (str): Portable key sequence to assign to ClipX.
            conflicts (list[dict]): Conflicting bindings reported by the backend,
                each with a ``name``.

        Returns:
            bool: ``True`` when the user chose to use the combination in ClipX.
        """
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
