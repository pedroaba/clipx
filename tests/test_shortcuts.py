"""Shortcut recording, validation, persistence and GNOME binding transfer."""
import os
from pathlib import Path
import tempfile
import subprocess
import unittest
from unittest.mock import Mock, patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_QPA_PLATFORMTHEME"] = "generic"

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QDialog

from clipx.shortcuts import (
    DEFAULT_SHORTCUTS, ShortcutSettings, normalize, validate_shortcuts,
)
from clipx.platforms.linux.shortcuts import LinuxGlobalShortcut as GlobalShortcut, from_gnome, to_gnome
from clipx.platforms import get_platform
from clipx.storage import Storage
from clipx.ui.pages.shortcuts import ShortcutsDialog
from clipx.ui.pages.clipboard import ClipXMainWindow
from clipx.ui.molecules.shortcut_recorder import display_shortcut


class ShortcutTests(unittest.TestCase):
    """Exercise the shortcuts dialog, conversion helpers and Linux backend."""

    @classmethod
    def setUpClass(cls):
        """Create the shared offscreen QApplication."""
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        """Build isolated settings, storage, window, fake backend and dialog."""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = ShortcutSettings(Path(self.temp.name) / "settings.json")
        self.storage = Storage(Path(self.temp.name) / "history.db")
        self.window = ClipXMainWindow(self.storage, self.settings, platform=get_platform("linux"))
        self.addCleanup(self.window.deleteLater)
        self.backend = Mock()
        self.backend.to_binding.side_effect = to_gnome
        self.backend.from_binding.side_effect = from_gnome
        self.backend.default_sequence = "Meta+V"
        self.backend.modifier_hint = GlobalShortcut.modifier_hint
        self.backend.read.return_value = "<Super>v"
        self.backend.conflicts.return_value = []
        self.backend.pause.return_value = "<Super>v"
        self.dialog = ShortcutsDialog(self.window, self.backend)
        self.dialog.confirm_reassignment = Mock(return_value=False)
        self.addCleanup(self.dialog.deleteLater)
        self.addCleanup(self.dialog.close)

    def click_to_record(self, name):
        """Click the recorder for ``name`` and return it once recording has started.

        Args:
            name: Shortcut identifier whose recorder should capture the next chord.

        Returns:
            The recorder widget that is now waiting for input.
        """
        self.dialog.show()
        self.app.processEvents()
        recorder = self.dialog.recorders[name]
        QTest.mouseClick(recorder, Qt.MouseButton.LeftButton)
        self.assertIs(self.app.focusWidget(), recorder)
        self.assertTrue(recorder.recording)
        self.assertIn("Pressione", recorder.text())
        return recorder

    def test_mouse_click_and_real_key_events_record_a_global_shortcut(self):
        """A real key chord is recorded without saving until Apply is clicked."""
        recorder = self.click_to_record("global")
        self.backend.pause.assert_called_once()
        QTest.keyPress(recorder, Qt.Key.Key_Control)
        self.assertIn("⌘" if __import__("sys").platform == "darwin" else "Ctrl", recorder.text())
        QTest.keyRelease(recorder, Qt.Key.Key_Control)
        QTest.keyClick(self.app.focusWidget(), Qt.Key.Key_K,
                       Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)
        self.assertEqual(recorder.keySequence().toString(), "Ctrl+Alt+K")
        self.assertFalse(recorder.recording)
        self.backend.resume.assert_called_once_with("<Super>v")
        self.backend.write.assert_not_called()
        self.assertFalse(self.settings.path.exists())
        QTest.mouseClick(self.dialog.apply_button, Qt.MouseButton.LeftButton)
        self.backend.write.assert_called_once_with("<Control><Alt>k")
        self.assertEqual(self.dialog.result(), QDialog.DialogCode.Accepted)

    def test_mouse_click_records_internal_binding_without_triggering_search_actions(self):
        """Recording an internal shortcut does not fire the window action bound to that chord."""
        recorder = self.click_to_record("pin")
        with patch.object(self.window, "_action_toggle_pin") as pin:
            QTest.keyClick(self.app.focusWidget(), Qt.Key.Key_L, Qt.KeyboardModifier.ControlModifier)
            pin.assert_not_called()
        self.assertEqual(recorder.keySequence().toString(), "Ctrl+L")
        self.assertIn("Aplicar", self.dialog.messages["pin"].text())
        self.assertEqual(self.window.shortcuts["pin"], "Ctrl+P")

    def test_escape_cancels_only_recording_and_restores_previous_binding(self):
        """Escape ends recording, restores the binding and keeps the dialog open."""
        recorder = self.click_to_record("global")
        QTest.keyClick(self.app.focusWidget(), Qt.Key.Key_Escape)
        self.assertFalse(recorder.recording)
        self.assertTrue(self.dialog.isVisible())
        self.assertEqual(recorder.keySequence().toString(), "Meta+V")
        self.backend.resume.assert_called_once_with("<Super>v")
        self.assertFalse(self.settings.path.exists())

    def test_conflicting_recording_keeps_old_draft_and_shows_inline_error(self):
        """A chord that conflicts with a system action is rejected with an inline message."""
        self.backend.conflicts.return_value = ["switch-applications"]
        recorder = self.click_to_record("global")
        QTest.keyClick(recorder, Qt.Key.Key_Tab, Qt.KeyboardModifier.AltModifier)
        self.assertTrue(recorder.recording)
        self.assertEqual(recorder.keySequence().toString(), "Meta+V")
        self.assertIn("switch-applications", self.dialog.messages["global"].text())
        self.backend.write.assert_not_called()
        self.dialog.reject()
        self.backend.resume.assert_called_once_with("<Super>v")

    def test_deactivation_and_timeout_both_end_recording(self):
        """Both window deactivation and the recording timeout stop capture and resume globals."""
        from PyQt6.QtCore import QEvent

        recorder = self.click_to_record("global")
        self.app.sendEvent(self.dialog, QEvent(QEvent.Type.WindowDeactivate))
        self.assertFalse(recorder.recording)
        self.assertIsNone(self.dialog.controller.recording_name)
        self.dialog.controller.start_recording("global")
        self.dialog.controller.recording_timer.timeout.emit()
        self.assertFalse(recorder.recording)
        self.assertEqual(self.backend.resume.call_count, 2)

    def test_failed_resume_keeps_dialog_open_for_retry(self):
        """A resume failure keeps the dialog open for retry; a later success closes it."""
        self.click_to_record("global")
        self.backend.resume.side_effect = RuntimeError("GNOME unavailable")
        self.dialog.reject()
        self.assertTrue(self.dialog.isVisible())
        self.assertIn("GNOME unavailable", self.dialog.error_label.text())
        self.assertEqual(self.dialog.controller.paused_binding, "<Super>v")
        self.backend.resume.side_effect = None
        self.dialog.reject()
        self.assertFalse(self.dialog.isVisible())

    def test_conversion_and_duplicate_validation(self):
        """GNOME conversion round-trips while invalid or duplicate chords raise."""
        for value in ("Meta+V", "Ctrl+Shift+F8", "Alt+Space", "Ctrl++", ""):
            self.assertEqual(from_gnome(to_gnome(value)), normalize(value) if value else "")
        self.assertEqual(from_gnome("<Primary>v"), "Ctrl+V")
        self.assertEqual(from_gnome("<Control>ISO_Left_Tab"), "Ctrl+Shift+Tab")
        with self.assertRaises(ValueError):
            validate_shortcuts({**DEFAULT_SHORTCUTS, "pin": "Enter"})
        with self.assertRaises(ValueError):
            validate_shortcuts({**DEFAULT_SHORTCUTS, "pin": "P"})
        with self.assertRaises(ValueError):
            to_gnome("V")
        with self.assertRaises(ValueError):
            to_gnome("Shift+V")

    def test_save_applies_immediately_and_persists_for_next_window(self):
        """Saving applies internal shortcuts live and the next window loads them."""
        self.storage.add_clip("test clip")
        self.window.load_clips()
        self.dialog.editors["pin"].setKeySequence(QKeySequence("Ctrl+L"))
        self.dialog.controller.save()
        self.assertEqual(self.dialog.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(self.settings.load()["pin"], "Ctrl+L")
        self.assertEqual(self.window.action_bar.key_labels["pin"].text(), QKeySequence("Ctrl+L").toString(QKeySequence.SequenceFormat.NativeText))
        self.window.show()
        self.app.processEvents()
        QTest.keyClick(self.window.search_bar.input_field, Qt.Key.Key_L,
                       Qt.KeyboardModifier.ControlModifier)
        self.assertTrue(self.storage.get_clips()[0].is_pinned)
        QTest.keyClick(self.window.search_bar.input_field, Qt.Key.Key_P,
                       Qt.KeyboardModifier.ControlModifier)
        self.assertTrue(self.storage.get_clips()[0].is_pinned)
        self.window.close()
        reopened = ClipXMainWindow(self.storage, self.settings, platform=get_platform("linux"))
        self.addCleanup(reopened.deleteLater)
        self.assertEqual(reopened.shortcuts["pin"], "Ctrl+L")
        self.backend.write.assert_not_called()

    def test_global_conflict_is_reported_without_saving(self):
        """A conflicting global chord is reported and nothing is written or persisted."""
        self.dialog.global_edit.setKeySequence(QKeySequence("Alt+Tab"))
        self.backend.conflicts.return_value = ["switch-applications"]
        self.dialog.controller.save()
        self.backend.write.assert_not_called()
        self.assertFalse(self.settings.path.exists())
        self.assertIn("switch-applications", self.dialog.error_label.text())

    def choose_super_space(self):
        """Pick Super+Space in the modal shortcut picker via modifier buttons and key list."""
        from PyQt6.QtCore import QTimer
        from clipx.ui.pages.shortcut_picker import ShortcutPicker

        self.dialog.show()
        self.app.processEvents()

        def choose():
            """Drive the open picker: check Super, select Space and accept the sequence."""
            picker = self.app.activeModalWidget()
            self.assertIsInstance(picker, ShortcutPicker)
            picker.modifiers["Super"].setChecked(True)
            picker.key_combo.setCurrentIndex(picker.key_combo.findData("Space"))
            picker.accept_sequence()

        QTimer.singleShot(0, choose)
        QTest.mouseClick(self.dialog.choose_button, Qt.MouseButton.LeftButton)

    def test_super_space_can_be_chosen_without_pressing_the_intercepted_chord(self):
        """Super+Space is selectable without pressing it, and declining leaves the system alone."""
        self.backend.conflicts.return_value = ["switch-input-source"]
        self.choose_super_space()
        self.assertEqual(self.dialog.global_edit.keySequence().toString(), "Meta+Space")
        self.assertIn("Trocar idioma", self.dialog.messages["global"].text())
        self.backend.write.assert_not_called()
        self.backend.pause.assert_not_called()
        self.dialog.controller.save()  # Declining transfer leaves the system untouched.
        self.backend.reassign.assert_not_called()
        self.assertFalse(self.settings.path.exists())

    def test_picker_shows_live_preview_and_modifier_buttons(self):
        """The picker previews modifier combinations live and validates the final selection."""
        from clipx.ui.pages.shortcut_picker import ShortcutPicker
        from PyQt6.QtWidgets import QPushButton

        picker = ShortcutPicker(QKeySequence("Meta+Space"), self.dialog)
        self.addCleanup(picker.deleteLater)
        self.assertIsInstance(picker.modifiers["Super"], QPushButton)
        self.assertTrue(picker.preview_keys.caps)
        self.assertEqual(picker.preview_label.text(), display_shortcut("Meta+Space"))
        self.assertTrue(picker.use_button.isEnabled())
        picker.modifiers["Ctrl"].setChecked(True)
        self.assertEqual(picker.preview_label.text(), display_shortcut("Ctrl+Meta+Space"))
        picker.modifiers["Super"].setChecked(False)
        picker.modifiers["Ctrl"].setChecked(False)
        self.assertFalse(picker.use_button.isEnabled())
        self.assertTrue(picker.error_label.text())
        picker.modifiers["Alt"].setChecked(True)
        picker.accept_sequence()
        self.assertEqual(picker.selected_sequence, "Alt+Space")

    def test_super_space_is_recorded_when_the_desktop_delivers_the_key_event(self):
        """A delivered Meta+Space event is captured and converts to the GNOME Super binding."""
        recorder = self.click_to_record("global")
        QTest.keyClick(recorder, Qt.Key.Key_Space, Qt.KeyboardModifier.MetaModifier)
        self.assertEqual(recorder.keySequence().toString(), "Meta+Space")
        self.assertFalse(recorder.recording)
        self.assertEqual(to_gnome(recorder.keySequence().toString()), "<Super>space")

    def test_reassignment_confirmation_names_the_action_and_requires_the_use_button(self):
        """The confirmation names the conflicting action and only the use button accepts."""
        from PyQt6.QtCore import QTimer
        from PyQt6.QtWidgets import QMessageBox

        self.dialog.show()
        self.app.processEvents()
        for button_text, expected in (("Voltar", False), ("Usar no ClipX", True)):
            def respond(text=button_text):
                """Click the reassignment dialog button carrying ``text``.

                Args:
                    text (str): Label of the button to click.
                """
                box = self.app.activeModalWidget()
                self.assertIsInstance(box, QMessageBox)
                self.assertIn("Trocar idioma do teclado", box.text())
                button = next(button for button in box.buttons() if button.text() == text)
                QTest.mouseClick(button, Qt.MouseButton.LeftButton)

            QTimer.singleShot(0, respond)
            result = ShortcutsDialog.confirm_reassignment(
                self.dialog, "Meta+Space", [{"name": "switch-input-source"}],
            )
            self.assertEqual(result, expected)

    def test_super_space_transfer_requires_confirmation_and_can_be_applied(self):
        """A confirmed conflict transfer reassigns the system binding and accepts the dialog."""
        self.backend.conflicts.return_value = ["switch-input-source"]
        conflicts = [{"name": "switch-input-source"}]
        self.backend.conflict_bindings.return_value = conflicts
        self.backend.reassign.return_value = [{"name": "switch-input-source"}]
        self.choose_super_space()
        self.dialog.confirm_reassignment.return_value = True
        self.dialog.controller.save()
        self.dialog.confirm_reassignment.assert_called_once_with("Meta+Space", conflicts)
        self.backend.reassign.assert_called_once_with("<Super>space", conflicts)
        self.assertEqual(self.dialog.result(), QDialog.DialogCode.Accepted)

    def test_failed_local_save_rolls_back_transferred_system_bindings(self):
        """A local save failure restores the global binding and the transferred conflicts."""
        self.backend.conflicts.return_value = ["switch-input-source"]
        self.backend.conflict_bindings.return_value = [{"name": "switch-input-source"}]
        changes = [{"name": "switch-input-source", "value": ["<Super>space", "XF86Keyboard"]}]
        self.backend.reassign.return_value = changes
        self.dialog.global_edit.setKeySequence(QKeySequence("Meta+Space"))
        self.dialog.confirm_reassignment.return_value = True
        with patch.object(self.settings, "save", side_effect=OSError("save failed")):
            self.dialog.controller.save()
        self.backend.write.assert_called_once_with("<Super>v")
        self.backend.restore_conflicts.assert_called_once_with(changes)

    def test_backend_transfer_preserves_other_bindings_and_rolls_back_on_failure(self):
        """Transferring a conflict edits only the named key and restores state on failure."""
        import ast

        backend = GlobalShortcut(recovery_path=Path(self.temp.name) / "recording.json")
        schema = "org.gnome.desktop.wm.keybindings"
        original = ["<Super>space", "XF86Keyboard"]
        state = {(schema, "switch-input-source"): original.copy(),
                 (schema, "switch-input-source-backward"): ["<Shift><Super>space"],
                 ("clipx", "binding"): "<Super>v"}
        approved = [{"schema": schema, "key": "switch-input-source",
                     "name": "switch-input-source", "value": original.copy()}]
        backend.conflict_bindings = Mock(return_value=approved)
        backend.get = Mock(side_effect=lambda schema, key: state[(schema, key)])
        backend.read = Mock(side_effect=lambda: state[("clipx", "binding")])
        backend.write = Mock(side_effect=lambda binding: state.update({("clipx", "binding"): binding}))

        def write_system(operation, schema, key, value):
            """Record a ``gsettings set`` invocation in the simulated state.

            Args:
                operation (str): gsettings operation, asserted to be ``'set'``.
                schema (str): Schema receiving the value.
                key (str): Key receiving the value.
                value (str): Serialized value, parsed with ``ast.literal_eval``.
            """
            self.assertEqual(operation, "set")
            state[(schema, key)] = ast.literal_eval(value)

        backend.run = Mock(side_effect=write_system)
        changes = backend.reassign("<Super>space", approved)
        self.assertEqual(state[(schema, "switch-input-source")], ["XF86Keyboard"])
        self.assertEqual(state[(schema, "switch-input-source-backward")], ["<Shift><Super>space"])
        self.assertEqual(state[("clipx", "binding")], "<Super>space")
        backend.restore_conflicts(changes)
        state[("clipx", "binding")] = "<Super>v"
        backend.write.side_effect = RuntimeError("registration failed")
        with self.assertRaisesRegex(RuntimeError, "registration failed"):
            backend.reassign("<Super>space", approved)
        self.assertEqual(state[(schema, "switch-input-source")], original)
        self.assertEqual(state[("clipx", "binding")], "<Super>v")

    def test_transfer_refuses_conflicts_that_changed_after_confirmation(self):
        """A conflict set that changed after confirmation aborts before running gsettings."""
        backend = GlobalShortcut()
        backend.conflict_bindings = Mock(return_value=[])
        backend.run = Mock()
        with self.assertRaisesRegex(RuntimeError, "conflitos mudaram"):
            backend.reassign("<Super>space", [{"name": "old-conflict"}])
        backend.run.assert_not_called()

    def test_global_change_and_disable(self):
        """Changing the global chord writes the GNOME form and clearing writes an empty value."""
        self.dialog.global_edit.setKeySequence(QKeySequence("Meta+Alt+V"))
        self.dialog.controller.save()
        self.backend.write.assert_called_once_with("<Alt><Super>v")
        self.dialog = ShortcutsDialog(self.window, self.backend)
        self.addCleanup(self.dialog.deleteLater)
        self.dialog.global_edit.clear()
        self.dialog.controller.save()
        self.backend.write.assert_called_with("")

    def test_equivalent_global_modifier_order_does_not_rewrite_binding(self):
        """A different modifier order for the same chord does not rewrite the binding."""
        self.backend.read.return_value = "<Super><Alt>v"
        dialog = ShortcutsDialog(self.window, self.backend)
        self.addCleanup(dialog.deleteLater)
        dialog.controller.save()
        self.backend.write.assert_not_called()

    def test_failed_local_save_restores_global_binding(self):
        """When settings cannot be saved, the previous global binding is written back."""
        self.dialog.global_edit.setKeySequence(QKeySequence("Ctrl+Alt+F8"))
        with patch.object(self.settings, "save", side_effect=OSError("save failed")):
            self.dialog.controller.save()
        self.assertEqual([call.args[0] for call in self.backend.write.call_args_list],
                         ["<Control><Alt>F8", "<Super>v"])
        self.assertEqual(self.window.shortcuts, DEFAULT_SHORTCUTS)

    def test_unavailable_global_backend_still_allows_internal_shortcuts(self):
        """An unavailable global backend disables its editor but internal shortcuts still save."""
        self.backend.read.side_effect = RuntimeError("unavailable")
        dialog = ShortcutsDialog(self.window, self.backend)
        self.addCleanup(dialog.deleteLater)
        self.assertFalse(dialog.global_edit.isEnabled())
        dialog.editors["pin"].clear()
        dialog.controller.save()
        self.assertEqual(self.settings.load()["pin"], "")
        self.backend.write.assert_not_called()

    def test_typing_and_default_tab_navigation_still_work(self):
        """Typing searches normally and Tab keys cycle filters, while Escape hides the window."""
        self.window.show()
        self.app.processEvents()
        field = self.window.search_bar.input_field
        QTest.keyClicks(field, "sample search")
        self.assertEqual(self.window.current_query, "sample search")
        QTest.keyClick(field, Qt.Key.Key_Tab)
        self.assertEqual(self.window.current_filter, "text")
        self.window.apply_shortcuts({**DEFAULT_SHORTCUTS, "filter": "Shift+Tab"})
        QTest.keyClick(field, Qt.Key.Key_Backtab, Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual(self.window.current_filter, "code")
        QTest.keyClick(field, Qt.Key.Key_Escape)
        self.assertFalse(self.window.isVisible())

    def test_corrupted_settings_fall_back_and_disabled_keys_survive(self):
        """Corrupted settings load defaults, while an intentionally empty shortcut survives."""
        self.settings.path.write_text('{"shortcuts": []}')
        self.assertEqual(self.settings.load(), DEFAULT_SHORTCUTS)
        self.settings.save({**DEFAULT_SHORTCUTS, "pin": ""})
        self.assertEqual(self.settings.load()["pin"], "")

    def test_gnome_write_preserves_other_shortcuts_and_updates_only_own_binding(self):
        """The GNOME writer updates only ClipX's custom keybinding entry."""
        backend = GlobalShortcut()
        backend.get = Mock(side_effect=[["/another/", backend.PATH], "<Super><Alt>v"])
        backend.run = Mock()
        backend.write("<Super><Alt>v")
        backend.run.assert_called_once_with("set", backend.CUSTOM + backend.PATH,
                                            "binding", repr("<Super><Alt>v"))

    def test_gnome_checks_system_and_custom_conflicts(self):
        """Conflict detection reports both system bindings and other custom shortcuts."""
        backend = GlobalShortcut()
        backend.run = Mock(return_value="org.gnome.shell.keybindings toggle-message-tray ['<Super>v']")
        backend.get = Mock(side_effect=[[backend.PATH, "/another/"], "<Super>v", "Other app"])
        matches = backend.conflicts("Meta+V")
        self.assertIn("toggle-message-tray", matches)
        self.assertIn("Other app", matches)

    def test_installer_preserves_registered_binding_and_sets_default_only_once(self):
        """The installer keeps an existing ClipX binding and only writes a missing default."""
        installer = (Path(__file__).resolve().parents[1] / "install_shortcut.sh").read_text()
        shortcut_section = installer.split("# 3.", 1)[1].split("\n", 1)[1]
        # Run only the shortcut section, with gsettings replaced by a recording function.
        harness = '''
gsettings() {
    if [[ "$1" == "get" ]]; then
        printf '%s\\n' "$CLIPX_TEST_BINDINGS"
    else
        printf 'GSETTINGS %s\\n' "$*"
    fi
}
USER_BIN=/tmp/clipx-test-launcher
'''
        for bindings, should_set_default in (
            ("['/another/', '" + GlobalShortcut.PATH + "']", False),
            ("['/another/']", True),
        ):
            result = subprocess.run(["bash"], input=harness + shortcut_section,
                                    text=True, capture_output=True, check=True,
                                    env={**os.environ, "CLIPX_TEST_BINDINGS": bindings})
            binding_writes = [line for line in result.stdout.splitlines()
                              if line.startswith("GSETTINGS set ") and " binding " in line]
            self.assertEqual(len(binding_writes), int(should_set_default))
            if should_set_default:
                self.assertIn("<Super>v", binding_writes[0])

    def test_pause_resume_and_crash_recovery_preserve_the_global_binding(self):
        """Pause/resume and crash recovery restore the binding unless an external change wins."""
        path = Path(self.temp.name) / "recording.json"
        backend = GlobalShortcut(recovery_path=path)
        state = {"binding": "<Super>v"}
        backend.read = Mock(side_effect=lambda: state["binding"])
        backend.write = Mock(side_effect=lambda binding: state.update(binding=binding))
        original = backend.pause()
        self.assertEqual(state["binding"], "")
        self.assertTrue(path.exists())
        backend.resume(original)
        self.assertEqual(state["binding"], "<Super>v")
        self.assertFalse(path.exists())
        backend.pause()
        backend.recover()
        self.assertEqual(state["binding"], "<Super>v")
        self.assertFalse(path.exists())
        original = backend.pause()
        state["binding"] = "<Alt>F8"  # An external GNOME preference change wins.
        backend.resume(original)
        self.assertEqual(state["binding"], "<Alt>F8")


if __name__ == "__main__":
    unittest.main()
