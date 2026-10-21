"""Shared Qt search surface. System behavior is injected through platform drivers."""
from PyQt6.QtCore import QEvent, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QCursor, QKeySequence
from PyQt6.QtWidgets import QApplication, QMainWindow, QMenu, QWidget
from clipx.platforms import get_platform
from clipx.platforms.base import Result, Status
from clipx.services import ClipboardService
from clipx.storage import Storage
from clipx.shortcuts import ShortcutSettings, normalize
from clipx.preferences import UISettings
from clipx.ui.foundations.appearance import apply_surface, is_light
from clipx.ui.templates.clipboard import ClipboardLayout
from clipx.ui.foundations.fonts import install_fonts
from clipx.ui.foundations.theme import QSS_STYLESHEET


class ClipXMainWindow(QMainWindow):
    operation_result = pyqtSignal(object)
    preferences_changed = pyqtSignal(object)

    def __init__(self, storage=None, shortcut_settings=None, platform=None):
        super().__init__()
        install_fonts()
        self.platform = platform or get_platform()
        self.storage = storage or Storage()
        self.clipboard_service = ClipboardService(self.storage, self.platform.clipboard)
        self.shortcut_settings = shortcut_settings or ShortcutSettings()
        self.shortcuts = self.shortcut_settings.load()
        self.ui_settings = UISettings(self.shortcut_settings.path)
        self.preferences = self.ui_settings.load()
        self._saved_window = self.ui_settings.read_document().get('window', {})
        if not isinstance(self._saved_window, dict):
            self._saved_window = {}
        self._panel_sizes = [380, 500]
        self.current_filter = 'all'
        self.current_query = ''
        self.capture_status = Result()
        self._signature = None
        self._operation_message = ''
        self._glass = False
        self.setWindowTitle('ClipX')
        self.resize(880, 540)
        self.setMinimumSize(720, 460)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet(QSS_STYLESHEET)
        self.center_on_cursor()
        self.init_ui()
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(500)
        self.refresh_timer.timeout.connect(self.load_clips)
        self.feedback_timer = QTimer(self)
        self.feedback_timer.setSingleShot(True)
        self.feedback_timer.timeout.connect(self.clear_feedback)
        self._drag = None
        self.dismiss_timer = QTimer(self)
        self.dismiss_timer.setSingleShot(True)
        self.dismiss_timer.setInterval(80)
        self.dismiss_timer.timeout.connect(self.dismiss_if_inactive)
        self.actions_menu.aboutToHide.connect(self.schedule_dismiss)
        QApplication.instance().applicationStateChanged.connect(self.schedule_dismiss)
        QApplication.instance().focusWindowChanged.connect(self.schedule_dismiss)
        self.apply_preferences(self.preferences)
        self.restore_window()
        QApplication.styleHints().colorSchemeChanged.connect(self.system_theme_changed)
        self.load_clips()

    def system_theme_changed(self, *args):
        if self.preferences['theme'] == 'system':
            self.apply_preferences(self.preferences)

    def center_on_cursor(self):
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        if screen:
            area = screen.availableGeometry()
            self.move(area.x() + (area.width() - self.width()) // 2,
                      area.y() + max(0, (area.height() - self.height()) // 2))

    def apply_preferences(self, values):
        was_preview = self.preferences.get('preview', True)
        if was_preview and not self.preview_pane.isHidden():
            self._panel_sizes = self.splitter.sizes()
        self.preferences = values.copy()
        self.clip_list.preferences = values.copy()
        self.preview_pane.preferences = {**values, 'light': is_light(values)}
        self.preview_pane.setVisible(values['preview'])
        if values['preview']:
            self.splitter.setSizes(self._panel_sizes)
        apply_surface(self, values, QSS_STYLESHEET)
        self._signature = None
        self.load_clips()
        self.preferences_changed.emit(values)
        if self.isVisible():
            self.refresh_material()

    def window_state(self):
        sizes = self.splitter.sizes() if self.preferences['preview'] else self._panel_sizes
        return {'size': [self.width(), self.height()], 'position': [self.x(), self.y()], 'splitter': sizes}

    def restore_window(self):
        state = self._saved_window
        if self.preferences['remember_size']:
            size = state.get('size')
            if self._valid_pair(size):
                self.resize(max(720, size[0]), max(460, size[1]))
            sizes = state.get('splitter')
            if self._valid_pair(sizes):
                self._panel_sizes = sizes
                self.splitter.setSizes(sizes)
        else:
            self.resize(880, 540)
            self._panel_sizes = [380, 500]
            self.splitter.setSizes(self._panel_sizes)
        cursor_screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        if cursor_screen and self.preferences['position'] == 'cursor':
            available = cursor_screen.availableGeometry()
            self.resize(min(self.width(), available.width()), min(self.height(), available.height()))
        position = state.get('position')
        if self.preferences['position'] == 'last' and self._valid_pair(position, positive=False):
            self.move(*position)
            screen = QApplication.screenAt(self.frameGeometry().center()) or QApplication.primaryScreen()
            if screen:
                area = screen.availableGeometry()
                self.resize(min(self.width(), area.width()), min(self.height(), area.height()))
                self.move(max(area.left(), min(self.x(), area.right() - self.width() + 1)),
                          max(area.top(), min(self.y(), area.bottom() - self.height() + 1)))
        else:
            self.center_on_cursor()

    @staticmethod
    def _valid_pair(value, positive=True):
        return isinstance(value, list) and len(value) == 2 and all(type(v) is int and abs(v) < 100000 and (not positive or v > 0) for v in value)

    def prepare_open(self):
        self.restore_window()
        if self.preferences['reopen'] == 'clear':
            self.search_bar.clear_search()
            self.search_bar.filter_select.setCurrentIndex(0)
            self.current_filter = 'all'
            self.current_query = ''
            self._signature = None
            self.load_clips()
            if self.clip_list.count():
                self.clip_list.setCurrentRow(0)

    def init_ui(self):
        self.surface = ClipboardLayout(self.shortcuts, self)
        self.setCentralWidget(self.surface)
        self.search_bar = self.surface.search_bar
        self.status_label = self.surface.status_label
        self.splitter = self.surface.splitter
        self.clip_list = self.surface.clip_list
        self.preview_pane = self.surface.preview_pane
        self.action_bar = self.surface.action_bar
        self.search_bar.query_changed.connect(self._on_search_query_changed)
        self.search_bar.filter_changed.connect(self._on_filter_changed)
        self.clip_list.currentItemChanged.connect(self._on_item_selection_changed)
        self.action_bar.primary_requested.connect(self._action_select_and_copy)
        self.action_bar.actions_requested.connect(self.open_actions)
        self.actions_menu = QMenu(self)
        self.actions_menu.addAction('Copiar e colar', self._action_select_and_copy)
        self.actions_menu.addAction('Copiar apenas', lambda: self._copy_selected(paste=False))
        self.actions_menu.addSeparator()
        self.pin_action = self.actions_menu.addAction('Fixar', self._action_toggle_pin)
        self.actions_menu.addAction('Excluir', self._action_delete)
        for widget in self.findChildren(QWidget):
            widget.installEventFilter(self)

    def load_clips(self):
        clips = self.storage.get_clips(query=self.current_query, filter_type=self.current_filter, limit=100)
        signature = (self.current_query, self.current_filter,
                     tuple((clip.id, clip.updated_at, clip.is_pinned) for clip in clips))
        if signature == self._signature:
            return
        self._signature = signature
        empty = ('Nenhum resultado.\nTente outro texto ou filtro.' if self.current_query or self.current_filter != 'all'
                 else 'Seu histórico está vazio.\nCopie um texto para começar.')
        self.clip_list.populate(clips, empty)
        self.search_bar.set_count(len(clips))
        self.action_bar.primary.setEnabled(bool(clips))
        if not clips:
            self.preview_pane.show_empty()

    def _on_search_query_changed(self, text):
        self.current_query = text.strip()
        self.load_clips()

    def _on_filter_changed(self, filter_key):
        self.current_filter = filter_key
        self.load_clips()

    def _on_item_selection_changed(self, current, previous):
        if current:
            self.preview_pane.display_item(current.data(Qt.ItemDataRole.UserRole))
        else:
            self.preview_pane.show_empty()

    def eventFilter(self, obj, event):
        if (event.type() == QEvent.Type.KeyPress and isinstance(obj, QWidget)
                and obj.window() is self and self._handle_shortcut(event)):
            return True
        if obj is self.search_bar:
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            elif event.type() == QEvent.Type.MouseMove and self._drag is not None:
                self.move(event.globalPosition().toPoint() - self._drag)
            elif event.type() == QEvent.Type.MouseButtonRelease:
                self._drag = None
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        if not self._handle_shortcut(event):
            super().keyPressEvent(event)

    def _handle_shortcut(self, event):
        try:
            sequence = normalize(QKeySequence(event.keyCombination()))
        except ValueError:
            return False
        actions = {'copy': self._action_select_and_copy, 'pin': self._action_toggle_pin,
                   'delete': self._action_delete, 'delete_alt': self._action_delete,
                   'filter': self.search_bar.cycle_filter, 'close': self.close,
                   'previous': lambda: self._move_selection(-1), 'next': lambda: self._move_selection(1)}
        for name, callback in actions.items():
            if sequence == self.shortcuts.get(name):
                callback()
                return True
        if sequence == 'Ctrl+K':
            self.open_actions()
            return True
        return False

    def _move_selection(self, delta):
        row = self.clip_list.currentRow() + delta
        if 0 <= row < self.clip_list.count():
            self.clip_list.setCurrentRow(row)

    def apply_shortcuts(self, values):
        self.shortcuts = values.copy()
        self.action_bar.update_shortcuts(values)

    def open_actions(self):
        clip = self.clip_list.get_selected_clip()
        for action in self.actions_menu.actions():
            if not action.isSeparator():
                action.setEnabled(clip is not None)
        self.pin_action.setText('Desafixar' if clip and clip.is_pinned else 'Fixar')
        self.actions_menu.popup(self.action_bar.actions.mapToGlobal(self.action_bar.actions.rect().topLeft()))

    def _action_select_and_copy(self):
        self._copy_selected(paste=True)

    def _copy_selected(self, paste):
        clip = self.clip_list.get_selected_clip()
        if clip is None:
            return
        result = self.clipboard_service.copy(clip)
        if not result.ok:
            self.show_result(result)
            return
        self.close()
        if paste:
            QTimer.singleShot(100, self._paste)

    def _paste(self):
        try:
            self.platform.desktop.paste_to_previous(callback=self.show_result)
        except Exception as exc:
            self.show_result(Result(Status.ERROR, f'Texto copiado. Não foi possível colar: {exc}'))

    def show_result(self, result):
        self._operation_message = result.message
        self._update_status()
        if result.message:
            self.feedback_timer.start(10000)
        self.operation_result.emit(result)

    def clear_feedback(self):
        self._operation_message = ''
        self._update_status()

    def set_capture_status(self, result):
        self.capture_status = result
        self._update_status()

    def _update_status(self):
        text = self._operation_message or (self.capture_status.message if not self.capture_status.ok else '')
        self.status_label.setText(text)
        self.status_label.setVisible(bool(text))

    def _action_toggle_pin(self):
        clip = self.clip_list.get_selected_clip()
        if clip:
            self.storage.toggle_pin(clip.id)
            self.load_clips()

    def _action_delete(self):
        clip = self.clip_list.get_selected_clip()
        if clip:
            self.storage.delete_clip(clip.id)
            self.load_clips()

    def refresh_material(self):
        if self.preferences['motion'] == 'reduce' or self.platform.effects.reduce_motion():
            self.setWindowOpacity(1)
        if self.preferences['material'] == 'opaque':
            self.platform.effects.remove(self)
            self._glass = False
        else:
            self._glass = self.platform.effects.apply(self)
        self.centralWidget().setProperty('nativeGlass', self._glass)
        self.centralWidget().style().unpolish(self.centralWidget())
        self.centralWidget().style().polish(self.centralWidget())
        self.centralWidget().update()

    def showEvent(self, event):
        super().showEvent(event)
        self.search_bar.focus_input(select_all=True)
        self.load_clips()
        self.refresh_timer.start()
        QTimer.singleShot(0, self.refresh_material)
        # Keep text and chrome fully opaque; only the native background is translucent.
        self.setWindowOpacity(1)

    def hideEvent(self, event):
        self.dismiss_timer.stop()
        self.refresh_timer.stop()
        self._saved_window = self.window_state()
        try:
            self.ui_settings.save(self.preferences, self._saved_window)
        except OSError as exc:
            self.show_result(Result(Status.ERROR, 'Não foi possível salvar a posição da janela: ' + str(exc)))
        self.setWindowOpacity(1)
        super().hideEvent(event)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.ActivationChange:
            if self.isActiveWindow():
                self.search_bar.focus_input()
            else:
                self.schedule_dismiss()

    def event(self, event):
        if event.type() == QEvent.Type.WindowDeactivate and hasattr(self, 'dismiss_timer'):
            self.schedule_dismiss()
        return super().event(event)

    def schedule_dismiss(self, *args):
        if self.isVisible() and not self.isMinimized() and not self.dismiss_timer.isActive():
            self.dismiss_timer.start()

    def dismiss_if_inactive(self):
        if not self.preferences['hide_on_blur'] or not self.isVisible() or self.isMinimized() or self.isActiveWindow():
            return
        popup = QApplication.activePopupWidget()
        owner = popup
        while owner is not None:
            if owner is self:
                return
            owner = owner.parentWidget()
        if QApplication.activeModalWidget() is not None:
            return
        self.close()
