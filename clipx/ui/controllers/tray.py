"""Tray lifecycle and navigation; menu composition lives in the organism layer."""
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon
from PyQt6.QtCore import QTimer
from clipx.ui.foundations.icons import icon
from clipx.platforms.base import Result
from clipx.ui.organisms.tray_menu import TrayMenu


def tray_icon():
    result = icon('clipboard', 24, '#E4E4E7')
    result.setIsMask(True)
    return result


class ClipXTray(QSystemTrayIcon):
    def __init__(self, storage, window, parent=None):
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
        if self.platform.name == 'macos' and QApplication.platformName() == 'cocoa':
            from clipx.platforms.macos.tray import install_menu_tracking_guard
            install_menu_tracking_guard()
        super().show()

    def _about_to_show(self):
        self.refresh_menu()
        self.capture_action.setText('Captura ativa' if self._capture_status.ok else 'Captura indisponível')
        self.capture_action.setToolTip(self._capture_status.message)
        self._menu_open = True

    def _about_to_hide(self):
        self._menu_open = False

    def set_capture_status(self, result):
        self._capture_status = result
        self.window.set_capture_status(result)
        if not self._menu_open:
            self.capture_action.setText('Captura ativa' if result.ok else 'Captura indisponível')
            self.capture_action.setToolTip(result.message)

    def show_result(self, result):
        if result.message and not self.window.isVisible() and QApplication.platformName() not in ('offscreen', 'minimal'):
            self.showMessage('ClipX', result.message, QSystemTrayIcon.MessageIcon.Information, 8000)

    def request_paste_permission(self):
        self.window.show_result(self.platform.desktop.request_paste_permission())

    def open_shortcuts(self):
        self.open_preferences('shortcuts')

    def open_preferences(self, section='appearance'):
        from clipx.ui.pages.preferences import PreferencesDialog
        self.menu.hide()
        self.window.hide()
        if self.shortcuts_dialog is None:
            self.shortcuts_dialog = PreferencesDialog(self.window, section=section)
            self.shortcuts_dialog.finished.connect(self._shortcuts_closed)
        self.shortcuts_dialog.select_section(section)
        self._bring_to_front(self.shortcuts_dialog)

    def _shortcuts_closed(self, result):
        self.shortcuts_dialog.deleteLater()
        self.shortcuts_dialog = None

    def open_search(self, activation_token=''):
        if self.shortcuts_dialog is not None and self.shortcuts_dialog.isVisible():
            self._bring_to_front(self.shortcuts_dialog, activation_token)
            return
        self.platform.desktop.remember_target()
        if not self.window.isVisible():
            self.window.prepare_open()
        self.window.load_clips()
        self._bring_to_front(self.window, activation_token)
        self.window.search_bar.focus_input()

    def _bring_to_front(self, window, activation_token=''):
        self.platform.desktop.open_search(window, activation_token)

    def _on_activated(self, reason):
        if self.platform.name == 'macos' and self.contextMenu() is not None:
            return  # Opening the menu must not also activate the search window.
        if reason in (self.ActivationReason.Trigger, self.ActivationReason.DoubleClick):
            self.open_search()

    def refresh_menu(self):
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
            preview = ' '.join(clip.content.split())
            if len(preview) > 60:
                preview = preview[:59] + '…'
            action.setText(preview.replace('&', '&&'))
            action.setData(clip)
            action.setVisible(True)

    def copy_clip(self, clip):
        if clip is None:
            return
        result = self.window.clipboard_service.copy(clip)
        self.window.show_result(result)
        if result.ok:
            self.refresh_menu()
