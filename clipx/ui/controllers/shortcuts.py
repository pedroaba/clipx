"""Recording, draft validation and transactional apply, independent of page layout."""
from PyQt6.QtCore import QObject, QTimer
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import QApplication
from clipx.shortcuts import SHORTCUTS, normalize, validate_shortcuts
from clipx.ui.models.shortcut_catalog import CONFLICT_NAMES
from clipx.ui.foundations.theme import BORDER_ACCENT, TEXT_SECONDARY


class ShortcutsController(QObject):
    def __init__(self, view, window, backend):
        super().__init__(view)
        self.view = view
        self.window = window
        self.backend = backend
        self.recording_name = None
        self.paused_binding = None
        self.original_global = None
        self.current_category = 'all'
        self.pending_count = 0
        self.baseline = None
        self.recording_timer = QTimer(self)
        self.recording_timer.setSingleShot(True)
        self.recording_timer.setInterval(30000)
        self.recording_timer.timeout.connect(self.stop_recording)
        try:
            self.original_global = backend.read()
            view.global_edit.setKeySequence(QKeySequence(self.decode_binding(self.original_global)))
        except (OSError, RuntimeError, ValueError, KeyError):
            view.global_edit.setEnabled(False)
            view.clear_buttons['global'].setEnabled(False)
            view.choose_button.setEnabled(False)
            self.set_message('global', 'Atalho global indisponível nesta sessão.', error=True)
        self.baseline = self.draft()
        for name, recorder in view.recorders.items():
            recorder.recordingRequested.connect(lambda key=name: self.start_recording(key))
            recorder.recordingCancelled.connect(self.stop_recording)
            recorder.sequenceRecorded.connect(lambda sequence, key=name: self.record_sequence(key, sequence))
            recorder.sequence_changed.connect(self.update_draft)
            view.clear_buttons[name].clicked.connect(lambda checked=False, key=name: self.clear_shortcut(key))
        view.choose_button.clicked.connect(self.choose_global)
        view.sidebar.category_changed.connect(self.change_category)
        view.search_field.query_changed.connect(self.filter_rows)
        view.footer.reset.clicked.connect(self.restore_defaults)
        view.buttons.accepted.connect(self.save)
        view.buttons.rejected.connect(view.reject)
        QApplication.instance().aboutToQuit.connect(self.stop_recording)
        self.update_draft()

    def draft(self):
        return {name: recorder.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
                for name, recorder in self.view.recorders.items()}

    def update_draft(self):
        if self.baseline is None:
            return
        draft = self.draft()
        self.pending_count = sum(draft[name] != value for name, value in self.baseline.items())
        for name, row in self.view.rows.items():
            row.set_modified(draft[name] != self.baseline[name])
        self.view.footer.set_pending(self.pending_count, recording=self.recording_name is not None)
        if hasattr(self.view, 'update_pending'):
            self.view.update_pending()

    def change_category(self, category):
        self.stop_recording()
        if self.paused_binding is not None:
            self.view.sidebar.buttons[self.current_category].setChecked(True)
            return
        self.current_category = category
        self.filter_rows()

    def filter_rows(self, query=None):
        self.stop_recording()
        if self.paused_binding is not None:
            return
        self.view.sections.filter(self.current_category, self.view.search_field.input.text())

    def detach(self):
        try:
            QApplication.instance().aboutToQuit.disconnect(self.stop_recording)
        except (TypeError, RuntimeError):
            pass

    def decode_binding(self, binding):
        return self.backend.from_binding(binding)

    def encode_binding(self, sequence):
        return self.backend.to_binding(sequence)

    def choose_global(self):
        self.stop_recording()
        if self.paused_binding is not None:
            return
        sequence = self.view.pick_global_sequence()
        if sequence is None:
            return
        if sequence in (editor.keySequence().toString() for editor in self.view.editors.values()):
            self.set_message("global", "Esta combinação já está atribuída à pesquisa.", error=True)
            return
        self.view.global_edit.setKeySequence(QKeySequence(sequence))
        try:
            conflicts = self.backend.conflicts(sequence)
            if conflicts:
                names = [CONFLICT_NAMES.get(name, name) for name in conflicts]
                self.set_message("global", "Em uso: " + ", ".join(names)
                                 + ". Clique em Aplicar para revisar a transferência.", error=True)
            else:
                self.set_message("global", "Combinação escolhida · clique em Aplicar para ativar.")
        except RuntimeError as exc:
            self.set_message("global", str(exc), error=True)

    def set_message(self, name, message, error=False):
        self.view.messages[name].setText(message)
        from clipx.ui.foundations.appearance import stylesheet
        source = f"color: {BORDER_ACCENT if error else TEXT_SECONDARY};"
        self.view.messages[name]._ui_style = source
        self.view.messages[name].setStyleSheet(stylesheet(source, self.window.preferences))

    def start_recording(self, name):
        self.stop_recording()
        if self.paused_binding is not None:
            return
        try:
            self.paused_binding = self.backend.pause() if self.view.global_edit.isEnabled() else ""
        except (RuntimeError, OSError) as exc:
            self.set_message(name, str(exc), error=True)
            return
        self.recording_name = name
        self.view.recorders[name].start_recording()
        self.set_message(name, "Gravando · pressione a combinação; Esc cancela.")
        self.recording_timer.start()
        self.update_draft()

    def stop_recording(self):
        self.recording_timer.stop()
        name = self.recording_name
        self.recording_name = None
        if name:
            self.view.recorders[name].stop_recording()
            self.set_message(name, "")
        if self.paused_binding is not None:
            binding = self.paused_binding
            try:
                self.backend.resume(binding)
                self.paused_binding = None
            except (RuntimeError, OSError) as exc:
                self.view.error_label.setText("Não foi possível retomar o atalho global: " + str(exc))
                self.view.error_label.show()

        self.update_draft()

    def record_sequence(self, name, sequence):
        try:
            if name == "global":
                self.encode_binding(sequence)
                if sequence in (normalize(editor.keySequence()) for editor in self.view.editors.values()
                                if not editor.keySequence().isEmpty()):
                    raise ValueError("Esta combinação já está atribuída a uma ação da pesquisa.")
                conflicts = self.backend.conflicts(sequence)
                if conflicts:
                    raise ValueError("Combinação em uso no sistema: " + ", ".join(conflicts))
            else:
                values = {key: editor.keySequence().toString() for key, editor in self.view.editors.items()}
                validate_shortcuts({**values, name: sequence})
                global_sequence = self.view.global_edit.keySequence()
                if not global_sequence.isEmpty() and sequence == normalize(global_sequence):
                    raise ValueError("Esta combinação já está atribuída a abrir a pesquisa.")
        except (RuntimeError, ValueError, KeyError) as exc:
            self.set_message(name, str(exc), error=True)
            self.view.recorders[name].setText("Tente outra combinação…")
            return
        self.stop_recording()
        self.view.recorders[name].setKeySequence(QKeySequence(sequence))
        self.set_message(name, "Combinação válida · clique em Aplicar para ativar.")

    def clear_shortcut(self, name):
        self.stop_recording()
        self.view.recorders[name].clear()
        self.set_message(name, "Desativado no rascunho · clique em Aplicar para confirmar.")

    def restore_defaults(self):
        self.stop_recording()
        for name, (_, value) in SHORTCUTS.items():
            self.view.editors[name].setKeySequence(QKeySequence(value))
            self.set_message(name, "Padrão restaurado no rascunho.")
        if self.view.global_edit.isEnabled():
            self.view.global_edit.setKeySequence(QKeySequence(self.backend.default_sequence))
            self.set_message("global", "Padrão restaurado · verifique possíveis conflitos ao aplicar.")

    def save(self):
        return self.view.buttons.run_loading(self._save)

    def _save(self):
        self.stop_recording()
        if self.paused_binding is not None:
            return
        previous_global = self.original_global
        changed_global = False
        transferred = []
        try:
            values = validate_shortcuts({
                name: editor.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
                for name, editor in self.view.editors.items()
            })
            if self.view.global_edit.isEnabled():
                sequence = self.view.global_edit.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
                binding = self.encode_binding(sequence)
                if sequence and normalize(sequence) in values.values():
                    raise ValueError("O atalho global precisa ser diferente dos atalhos da pesquisa.")
                if self.decode_binding(binding) != self.decode_binding(self.original_global):
                    conflicts = self.backend.conflicts(sequence) if sequence else []
                    if conflicts:
                        approved = self.backend.conflict_bindings(sequence)
                        if not self.view.confirm_reassignment(sequence, approved):
                            raise ValueError("Alteração não aplicada. Combinação em uso: " + ", ".join(conflicts))
                        transferred = self.backend.reassign(binding, approved)
                    else:
                        self.backend.write(binding)
                    changed_global = True
            if hasattr(self.view, 'persist_settings'):
                self.view.persist_settings(values)
            else:
                self.window.shortcut_settings.save(values)
        except (OSError, RuntimeError, ValueError, KeyError) as exc:
            message = str(exc)
            if changed_global:
                try:
                    self.backend.write(previous_global)
                except RuntimeError:
                    message += " O atalho global foi alterado; verifique-o antes de tentar novamente."
            if transferred:
                try:
                    self.backend.restore_conflicts(transferred)
                except RuntimeError as restore_error:
                    message += " " + str(restore_error)
            self.view.error_label.setText(message)
            self.view.error_label.show()
            return
        self.window.apply_shortcuts(values)
        self.view.accept()

