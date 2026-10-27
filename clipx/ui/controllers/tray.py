"""Tray lifecycle and navigation; menu composition lives in the organism layer.

The controller connects tray actions to the search window, the clipboard
service and platform desktop integration, refreshes the recent-clip entries and
surfaces operation results as native notifications.
"""
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon
from PyQt6.QtCore import QTimer
from clipx.ui.foundations.icons import icon
from clipx.platforms.base import Result
from clipx.ui.organisms.tray_menu import TrayMenu


def tray_icon():
    """Build the monochrome mask icon used by the system tray.

    Returns:
        QIcon: Clipboard icon rendered at 24 px and marked as a mask.
    """
    result = icon('clipboard', 24, '#E4E4E7')
    result.setIsMask(True)
    return result


class ClipXTray(QSystemTrayIcon):
    """System tray icon that owns the tray menu and its navigation.

    Attributes:
        storage (Storage): Provider of the recent clips shown in the menu.
        window (ClipXMainWindow): Search window opened by the tray actions.
        platform (object): Platform driver bundle for desktop integration.
        menu (TrayMenu): Context menu with search, clips and settings actions.
        shortcuts_dialog (PreferencesDialog | None): Open preferences dialog,
            reused while visible.
        refresh_timer (QTimer): Refreshes the recent clips every second.
    """

    def __init__(self, storage, window, parent=None):
        """Create the tray icon, wire its actions and start periodic refresh.

        Args:
            storage (Storage): Provider of the recent clips.
            window (ClipXMainWindow): Window receiving navigation requests.
            parent (QObject | None): Optional parent object.
        """
        super().__init__(tray_icon(), parent)
        self.storage = storage
        self.window = window
        self.platform = window.platform
        self.setToolTip('ClipX')
        self.menu = TrayMenu(macos=self.platform.name == "macos", parent=window)
        self.setContextMenu(self.menu)
        from clipx.ui.foundations.appearance import apply_surface
        from clipx.ui.foundations.theme import QSS_STYLESHEET
        apply_surface(self.menu, self.window.preferences, QSS_STYLESHEET)
        self.window.preferences_changed.connect(lambda values: apply_surface(self.menu, values, QSS_STYLESHEET))
        self._menu_open = False
        self.menu.aboutToShow.connect(self._about_to_show)
        self.menu.aboutToHide.connect(self._about_to_hide)
        self.shortcuts_dialog = None
        self.open_action = self.menu.open_action
        self.empty_action = self.menu.empty_action
        self.clip_actions = self.menu.clip_actions
        self.shortcuts_action = self.menu.shortcuts_action
        self.capture_action = self.menu.capture_action
        self.quit_action = self.menu.quit_action
        self.open_action.triggered.connect(lambda checked=False: self.open_search())
        for action in self.clip_actions:
            action.triggered.connect(lambda checked=False, item=action: self.copy_clip(item.data()))
        self.shortcuts_action.triggered.connect(self.open_shortcuts)
        self.menu.preferences_action.triggered.connect(lambda checked=False: self.open_preferences())
        from clipx.updates import update_service
        self.updates = update_service()
        self.menu.updates_action.triggered.connect(self.open_updates)
        self.updates.install_ready.connect(self._install_update)
        if self.menu.permission_action is not None:
            self.menu.permission_action.triggered.connect(self.request_paste_permission)
        self.quit_action.triggered.connect(QApplication.instance().quit)
        self._capture_status = Result()
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(1000)
        self.refresh_timer.timeout.connect(self.refresh_menu)
        self.refresh_timer.start()
        self._recent = None
        self.refresh_menu()
        self.activated.connect(self._on_activated)
        self.window.operation_result.connect(self.show_result)

    def show(self):
        """Install the macOS menu tracking guard, then show the tray icon."""
        if self.platform.name == 'macos' and QApplication.platformName() == 'cocoa':
            from clipx.platforms.macos.tray import install_menu_tracking_guard
            install_menu_tracking_guard()
        super().show()

    def _about_to_show(self):
        """Refresh the recent clips and capture status before the menu opens."""
        self.refresh_menu()
        self.capture_action.setText('Captura ativa' if self._capture_status.ok else 'Captura indisponível')
        self.capture_action.setToolTip(self._capture_status.message)
        self._menu_open = True

    def _about_to_hide(self):
        """Mark the menu as closed so refreshes resume."""
        self._menu_open = False

    def set_capture_status(self, result):
        """Store and display the clipboard capture status.

        The menu action is updated immediately unless the menu is open, in
        which case the change is deferred to the next show.

        Args:
            result (Result): Capture status with ``ok`` and ``message``.
        """
        self._capture_status = result
        self.window.set_capture_status(result)
        if not self._menu_open:
            self.capture_action.setText('Captura ativa' if result.ok else 'Captura indisponível')
            self.capture_action.setToolTip(result.message)

    def show_result(self, result):
        """Show an operation result as a tray notification when appropriate.

        Notifications are skipped when the window is visible or when the
        platform runs the offscreen/minimal Qt backends.

        Args:
            result (Result): Operation result carrying the message to display.
        """
        if result.message and not self.window.isVisible() and QApplication.platformName() not in ('offscreen', 'minimal'):
            self.showMessage('ClipX', result.message, QSystemTrayIcon.MessageIcon.Information, 8000)

    def request_paste_permission(self):
        """Ask the platform for paste permission and surface the result."""
        self.window.show_result(self.platform.desktop.request_paste_permission())

    def open_shortcuts(self):
        """Open the preferences dialog on the shortcuts section."""
        self.open_preferences('shortcuts')

    def open_updates(self):
        """Open the shared update page and check only on explicit user request."""
        self.open_preferences('updates')
        self.updates.check()

    def _install_update(self):
        """Bring back preferences to resolve edits made during the download."""
        self.open_preferences('updates')
        if self.shortcuts_dialog.prepare_update_restart():
            self.updates.launch_install()
        else:
            self.updates.defer_install()

    def open_preferences(self, section='appearance'):
        """Open the preferences dialog, hiding the menu and the search window.

        The dialog is created once and reused while it stays alive.

        Args:
            section (str): Section to select in the dialog.
        """
        from clipx.ui.pages.preferences import PreferencesDialog
        self.menu.hide()
        self.window.hide()
        if self.shortcuts_dialog is None:
            self.shortcuts_dialog = PreferencesDialog(self.window, section=section)
            self.shortcuts_dialog.finished.connect(self._shortcuts_closed)
        self.shortcuts_dialog.select_section(section)
        self._bring_to_front(self.shortcuts_dialog)

    def _shortcuts_closed(self, result):
        """Release the preferences dialog after it closes.

        Args:
            result (int): Dialog result code; unused by the controller.
        """
        self.shortcuts_dialog.deleteLater()
        self.shortcuts_dialog = None

    def open_search(self, activation_token='', startup_id=''):
        """Open the search window, or focus the preferences dialog if visible.

        Remembers the previously focused application, restores the window when
        hidden, reloads clips and focuses the search field.

        Args:
            activation_token (str): Platform token used when bringing the
                window to the front.
            startup_id (str): Startup announcement forwarded separately from focus.
        """
        try:
            if self.shortcuts_dialog is not None and self.shortcuts_dialog.isVisible():
                self._bring_to_front(self.shortcuts_dialog, activation_token, startup_id)
                return
            self.platform.desktop.remember_target()
            if not self.window.isVisible():
                self.window.prepare_open()
            self.window.load_clips()
            self._bring_to_front(self.window, activation_token, startup_id)
            self.window.search_bar.focus_input()
        except BaseException:
            if startup_id and self.platform.name == 'linux':
                self.platform.desktop.finish_startup(startup_id)
            raise

    def _bring_to_front(self, window, activation_token='', startup_id=''):
        """Delegate bringing a window to the front to the platform driver.

        Args:
            window (QWidget): Window to raise and activate.
            activation_token (str): Platform token identifying the activation.
            startup_id (str): Optional startup announcement to complete.
        """
        if startup_id and self.platform.name == 'linux':
            self.platform.desktop.open_search(window, activation_token, startup_id=startup_id)
        else:
            self.platform.desktop.open_search(window, activation_token)

    def _on_activated(self, reason):
        """Open the search window when the tray icon is triggered.

        On macOS, activations caused by opening the context menu are ignored so
        the search window does not appear as well.

        Args:
            reason (QSystemTrayIcon.ActivationReason): Activation that occurred.
        """
        if self.platform.name == 'macos' and self.contextMenu() is not None:
            return  # Opening the menu must not also activate the search window.
        if reason in (self.ActivationReason.Trigger, self.ActivationReason.DoubleClick):
            self.open_search()

    def refresh_menu(self):
        """Refresh the recent-clip actions, skipping work while the menu is open.

        The menu is only rewritten when the recent clips changed, and ampersands
        are escaped so clip text is not interpreted as mnemonics.
        """
        if self._menu_open:
            return
        clips = self.storage.get_clips(limit=5, pinned_first=False)
        recent = [(clip.id, clip.content, clip.updated_at) for clip in clips]
        if recent == self._recent:
            return
        self._recent = recent
        self.empty_action.setVisible(not clips)
        for index, action in enumerate(self.clip_actions):
            if index >= len(clips):
                action.setVisible(False)
                action.setData(None)
                continue
            clip = clips[index]
            if clip.type == 'image':
                from clipx.images import image_title
                preview = 'Imagem · ' + image_title(clip)
            else:
                preview = ' '.join(clip.content.split())
            if len(preview) > 60:
                preview = preview[:59] + '…'
            action.setText(preview.replace('&', '&&'))
            action.setData(clip)
            action.setVisible(True)

    def copy_clip(self, clip):
        """Copy a clip through the clipboard service and report the result.

        The menu is refreshed after a successful copy.

        Args:
            clip (object | None): Clip to copy; ``None`` is ignored.
        """
        if clip is None:
            return
        if getattr(self, '_copy_busy', False):
            return
        self._copy_busy = True
        self.window.clipboard_service.copy_async(clip, lambda result: self._copy_finished(clip, result))

    def _copy_finished(self, clip, result):
        """Report asynchronous image failures after the native menu has closed."""
        self._copy_busy = False
        if not result.ok and clip.type == 'image':
            self.open_search()
            QTimer.singleShot(0, lambda: self.window.show_copy_failure(clip, result))
        else:
            self.window.show_result(result)
        if result.ok:
            self.refresh_menu()
