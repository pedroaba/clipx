"""Shared Qt search surface. System behavior is injected through platform drivers."""
import logging
import time

from PyQt6.QtCore import QEvent, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QCursor, QKeySequence
from PyQt6.QtWidgets import QApplication, QMainWindow, QMenu, QWidget, QMessageBox
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
    """Frameless search window backed by a platform driver.

    Clips are reloaded by a short periodic timer and only repopulated when their
    signature changes, so typing stays responsive. The window hides itself when
    it loses focus unless a ClipX popup or modal dialog owns the focus.

    Attributes:
        operation_result (pyqtSignal): Emitted with a ``Result`` for clipboard
            and platform operations.
        preferences_changed (pyqtSignal): Emitted with the new preferences
            mapping after they are applied.
        platform (object): Platform driver bundle for clipboard, desktop and
            effects integration.
        storage (Storage): Persistence for clips.
        clipboard_service (ClipboardService): Copies clips to the clipboard.
        shortcut_settings (ShortcutSettings): Persistence for key bindings.
        shortcuts (dict[str, str]): Active shortcut bindings.
        ui_settings (UISettings): Persistence for preferences and window state.
        preferences (dict): Active UI preferences.
        current_filter (str): Active list filter key.
        current_query (str): Active search query.
        capture_status (Result): Latest clipboard capture status.
        search_bar (object): Search molecule with query and filter inputs.
        status_label (QLabel): Status line with the latest message.
        splitter (QSplitter): Splitter between list and preview.
        clip_list (ClipListWidget): Clipboard history list.
        preview_pane (PreviewPaneWidget): Preview of the selected clip.
        action_bar (ActionBarWidget): Bottom action bar.
        actions_menu (QMenu): Context menu with per-clip actions.
        pin_action (QAction): Pin or unpin action inside ``actions_menu``.
        refresh_timer (QTimer): Reloads clips every 500 ms while visible.
        feedback_timer (QTimer): Clears the operation message after 10 s.
        dismiss_timer (QTimer): Delayed check that closes an inactive window.
    """

    operation_result = pyqtSignal(object)
    preferences_changed = pyqtSignal(object)

    def __init__(self, storage=None, shortcut_settings=None, platform=None):
        """Assemble services, window flags, timers and the interface.

        Args:
            storage (Storage | None): Clip storage; a default instance is
                created when omitted.
            shortcut_settings (ShortcutSettings | None): Shortcut persistence; a
                default instance is created when omitted.
            platform (object | None): Platform driver bundle; the detected
                platform is used when omitted.
        """
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
        """Reapply preferences when the system color scheme changes.

        The change is ignored unless the theme preference follows the system.

        Args:
            *args: Color scheme arguments emitted by the Qt style hints.
        """
        if self.preferences['theme'] == 'system':
            self.apply_preferences(self.preferences)

    def center_on_cursor(self):
        """Move the window to the center of the screen under the cursor."""
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        if screen:
            area = screen.availableGeometry()
            self.move(area.x() + (area.width() - self.width()) // 2,
                      area.y() + max(0, (area.height() - self.height()) // 2))

    def apply_preferences(self, values):
        """Apply preferences to the window, list, preview and surface.

        Panel sizes are preserved while the preview stays visible; clips are
        reloaded, listeners are notified and native material is refreshed when
        the window is visible.

        Args:
            values (dict): Validated UI preferences to apply.
        """
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
        # Child minimum widths scale too; keep the supported window minimum
        # large enough for both panels instead of clipping at enlarged fonts.
        scale = max(1, values['scale'] / 100)
        self.setMinimumSize(round(720 * scale), round(460 * scale))
        self._signature = None
        self.load_clips()
        self.preferences_changed.emit(values)
        if self.isVisible():
            self.refresh_material()

    def window_state(self):
        """Describe the geometry to persist for the next session.

        Returns:
            dict: Window ``size``, ``position`` and current ``splitter`` sizes.
        """
        sizes = self.splitter.sizes() if self.preferences['preview'] else self._panel_sizes
        return {'size': [self.width(), self.height()], 'position': [self.x(), self.y()], 'splitter': sizes}

    def restore_window(self):
        """Restore size, splitter and position according to the preferences.

        Remembered geometry is validated before use; otherwise the window is
        reset to its defaults and centered on the cursor screen. The window is
        clamped to the available area of its screen.
        """
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
        """Check that a stored value is a pair of plausible integers.

        Args:
            value (object): Candidate value read from the saved state.
            positive (bool): Whether both entries must be greater than zero.

        Returns:
            bool: ``True`` when the value is a two-integer list within bounds.
        """
        return isinstance(value, list) and len(value) == 2 and all(type(v) is int and abs(v) < 100000 and (not positive or v > 0) for v in value)

    def prepare_open(self):
        """Prepare the window state right before it is shown.

        Geometry is restored and, when the reopen preference asks for it, the
        query and filter are cleared and the first row is selected.
        """
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
        """Build the layout, connect its signals and install the event filter.

        The actions menu holds the copy, pin and delete commands, and every
        child widget is registered with the event filter so key presses reach
        the window-level shortcut handler.
        """
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
        """Reload clips from storage and repopulate the list when they changed.

        The list signature combines the query, filter and each clip's identity,
        update time and pin state, so unchanged results are skipped entirely.
        """
        clips = self.storage.get_clips(query=self.current_query, filter_type=self.current_filter, limit=100)
        signature = (self.current_query, self.current_filter,
                     tuple((clip.id, clip.updated_at, clip.is_pinned) for clip in clips))
        if signature == self._signature:
            self.preview_pane.refresh_image()
            return
        self._signature = signature
        empty = ('Nenhum resultado.\nTente outro texto ou filtro.' if self.current_query or self.current_filter != 'all'
                 else 'Seu histórico está vazio.\nCopie um texto ou imagem para começar.')
        self.clip_list.populate(clips, empty)
        self.search_bar.set_count(len(clips))
        self.action_bar.primary.setEnabled(bool(clips) and not getattr(self, '_copy_busy', False))
        if not clips:
            self.preview_pane.show_empty()

    def _on_search_query_changed(self, text):
        """Store a trimmed query and reload the clips.

        Args:
            text (str): Raw text emitted by the search field.
        """
        self.current_query = text.strip()
        self.load_clips()

    def _on_filter_changed(self, filter_key):
        """Store the selected filter and reload the clips.

        Args:
            filter_key (str): Filter key emitted by the search bar.
        """
        self.current_filter = filter_key
        self.load_clips()

    def _on_item_selection_changed(self, current, previous):
        """Show the selected clip in the preview, or the empty page.

        Args:
            current (QListWidgetItem | None): Newly selected item.
            previous (QListWidgetItem | None): Previously selected item;
                unused.
        """
        if current:
            self.preview_pane.display_item(current.data(Qt.ItemDataRole.UserRole))
        else:
            self.preview_pane.show_empty()

    def eventFilter(self, obj, event):
        """Handle shortcuts and window dragging for filtered child widgets.

        Key presses inside this window are offered to the shortcut handler
        first. Mouse presses and moves on the search bar start and continue a
        manual drag of the frameless window.

        Args:
            obj (QObject): Watched object.
            event (QEvent): Filtered event.

        Returns:
            bool: ``True`` when the event was consumed.
        """
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
        """Route key presses through the shortcut handler before the base class.

        Args:
            event (QKeyEvent): Key press event.
        """
        if not self._handle_shortcut(event):
            super().keyPressEvent(event)

    def _handle_shortcut(self, event):
        """Run the action bound to a key event's combination.

        Matches the normalized combination against the configured search
        shortcuts, plus the fixed ``Ctrl+K`` binding that opens the actions
        menu.

        Args:
            event (QKeyEvent): Key event to interpret.

        Returns:
            bool: ``True`` when a bound action ran.
        """
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
        """Move the list selection, staying inside the available rows.

        Args:
            delta (int): Number of rows to move; negative moves upwards.
        """
        row = self.clip_list.currentRow() + delta
        if 0 <= row < self.clip_list.count():
            self.clip_list.setCurrentRow(row)

    def apply_shortcuts(self, values):
        """Store new bindings and refresh the action bar badges.

        Args:
            values (dict[str, str]): Shortcut bindings indexed by action name.
        """
        self.shortcuts = values.copy()
        self.action_bar.update_shortcuts(values)

    def open_actions(self):
        """Show the actions menu anchored to the actions button.

        Every non-separator action is enabled only when a clip is selected, and
        the pin action text reflects the current pin state.
        """
        clip = self.clip_list.get_selected_clip()
        for action in self.actions_menu.actions():
            if not action.isSeparator():
                action.setEnabled(clip is not None)
        self.pin_action.setText('Desafixar' if clip and clip.is_pinned else 'Fixar')
        self.actions_menu.popup(self.action_bar.actions.mapToGlobal(self.action_bar.actions.rect().topLeft()))

    def _action_select_and_copy(self):
        """Copy the selected clip and paste it into the previous application."""
        self._copy_selected(paste=True)

    def _copy_selected(self, paste):
        """Copy the selected clip, closing the window and optionally pasting.

        The window is only closed after a successful copy. Pasting is deferred
        briefly so the target application regains focus first.

        Args:
            paste (bool): Whether to paste into the previously focused
                application after copying.
        """
        clip = self.clip_list.get_selected_clip()
        if clip is None:
            return
        if getattr(self, '_copy_busy', False):
            return
        self._copy_busy = True
        self.action_bar.primary.setEnabled(False)
        self.clipboard_service.copy_async(clip, lambda result: self._copy_finished(clip, paste, result))

    def _copy_finished(self, clip, paste, result):
        """Close and optionally paste only after a completed successful copy."""
        self._copy_busy = False
        self.action_bar.primary.setEnabled(self.clip_list.get_selected_clip() is not None)
        if not result.ok:
            self.show_copy_failure(clip, result)
            return
        self.close()
        if paste:
            if self.platform.name == 'linux':
                generation = getattr(self, '_paste_generation', 0)
                QTimer.singleShot(100, lambda: self._wait_for_paste(generation, time.monotonic() + 1))
            else:
                QTimer.singleShot(100, self._paste)

    def show_copy_failure(self, clip, result):
        """Show themed image failures without losing the selection or search."""
        self.show_result(result)
        if clip.type != 'image':
            return
        from clipx.ui.templates.window import customize_message_box
        box = QMessageBox(self)
        box.setWindowTitle('Imagem indisponível')
        box.setText('Imagem indisponível')
        box.setInformativeText(result.message)
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setIcon(QMessageBox.Icon.Warning)
        button = box.addButton('Entendi', QMessageBox.ButtonRole.AcceptRole)
        box.setDefaultButton(button)
        box.setEscapeButton(button)
        customize_message_box(box)
        apply_surface(box, self.preferences, QSS_STYLESHEET)
        box.exec()
        self.preview_pane.refresh_image()
        self.search_bar.focus_input()

    def _wait_for_paste(self, generation, deadline):
        """Wait for Linux search dismissal and cancel when it is reopened."""
        if generation != getattr(self, '_paste_generation', 0):
            self.show_result(Result(Status.UNAVAILABLE,
                'Conteúdo copiado. Colagem cancelada porque a pesquisa foi reaberta; use Ctrl+V.',
                'paste_cancelled'))
            return
        if not self.isVisible() and not self.isActiveWindow():
            self._paste()
            return
        if time.monotonic() >= deadline:
            self.show_result(Result(Status.UNAVAILABLE,
                'Conteúdo copiado. Não foi possível colar automaticamente; use Ctrl+V.',
                'paste_unavailable'))
            return
        QTimer.singleShot(25, lambda: self._wait_for_paste(generation, deadline))

    def _paste(self):
        """Paste into the previously focused application through the platform.

        A failing paste is reported as an operation result; the text has
        already been copied at that point.
        """
        try:
            self.platform.desktop.paste_to_previous(callback=self.show_result)
        except Exception:
            logging.getLogger('clipx.desktop').exception('Could not request automatic paste')
            self.show_result(Result(Status.UNAVAILABLE, 'Conteúdo copiado. Não foi possível colar automaticamente; use Ctrl+V.', 'paste_unavailable'))

    def show_result(self, result):
        """Store and display an operation result and notify listeners.

        The feedback timer only runs when the result carries a message.

        Args:
            result (Result): Operation result with ``ok`` and ``message``.
        """
        self._operation_message = result.message
        self._update_status()
        if result.message:
            self.feedback_timer.start(10000)
        self.operation_result.emit(result)

    def clear_feedback(self):
        """Clear the operation message and refresh the status line."""
        self._operation_message = ''
        self._update_status()

    def set_capture_status(self, result):
        """Store the clipboard capture status and refresh the status line.

        Args:
            result (Result): Capture status with ``ok`` and ``message``.
        """
        self.capture_status = result
        self._update_status()

    def _update_status(self):
        """Show the operation message, or the capture error, in the status line."""
        text = self._operation_message or (self.capture_status.message if not self.capture_status.ok else '')
        self.status_label.setText(text)
        self.status_label.setVisible(bool(text))

    def _action_toggle_pin(self):
        """Toggle the pin state of the selected clip and reload the list."""
        clip = self.clip_list.get_selected_clip()
        if clip:
            self.storage.toggle_pin(clip.id)
            self.load_clips()

    def _action_delete(self):
        """Delete the selected clip and reload the list."""
        clip = self.clip_list.get_selected_clip()
        if clip:
            self.storage.delete_clip(clip.id)
            self.load_clips()

    def refresh_material(self):
        """Reapply the window material and motion preferences.

        Reduced motion forces full opacity. The opaque material removes native
        effects; otherwise they are applied and reported to the central widget
        so the stylesheet can react. The central widget is repolished to pick up
        the new property.
        """
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
        """Focus the search field, start timers and refresh the material.

        Args:
            event (QShowEvent): Show event forwarded to the base class.
        """
        if self.platform.name == 'linux':
            self._paste_generation = getattr(self, '_paste_generation', 0) + 1
            self.platform.desktop.cancel_paste()
        super().showEvent(event)
        self.search_bar.focus_input(select_all=True)
        self.load_clips()
        self.refresh_timer.start()
        QTimer.singleShot(0, self.refresh_material)
        # Keep text and chrome fully opaque; only the native background is translucent.
        self.setWindowOpacity(1)

    def hideEvent(self, event):
        """Persist the window state and stop the timers when hiding.

        Geometry is saved through the UI settings; a failure is surfaced as an
        operation result instead of raising.

        Args:
            event (QHideEvent): Hide event forwarded to the base class.
        """
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
        """Refocus the search field on activation and schedule dismissal on blur.

        Args:
            event (QEvent): Change event forwarded to the base class.
        """
        super().changeEvent(event)
        if event.type() == QEvent.Type.ActivationChange:
            if self.isActiveWindow():
                if self.platform.name == 'linux':
                    self._paste_generation = getattr(self, '_paste_generation', 0) + 1
                    self.platform.desktop.cancel_paste()
                self.search_bar.focus_input()
            else:
                self.schedule_dismiss()

    def event(self, event):
        """Schedule a dismissal check when the window is deactivated.

        Args:
            event (QEvent): Event being processed.

        Returns:
            bool: Result of the base class handler.
        """
        if event.type() == QEvent.Type.WindowDeactivate and hasattr(self, 'dismiss_timer'):
            self.schedule_dismiss()
        return super().event(event)

    def schedule_dismiss(self, *args):
        """Start the dismissal timer when the window is visible and idle.

        Args:
            *args: Extra signal arguments, ignored.
        """
        if self.isVisible() and not self.isMinimized() and not self.dismiss_timer.isActive():
            self.dismiss_timer.start()

    def dismiss_if_inactive(self):
        """Close the window when it lost focus and the preference allows it.

        The window stays open while a popup owned by this window, or any modal
        widget, is active.
        """
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
