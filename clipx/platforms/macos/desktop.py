"""Restore the original macOS window and field before sending Command-V."""
import os
import time
from dataclasses import dataclass

from clipx.platforms.base import Result, Status

from .focus import MacOSFocus

_MANUAL = 'Conteúdo copiado. '
_ANSI_V = 9


@dataclass(frozen=True)
class PasteTarget:
    app: object
    pid: int
    accessibility_app: object
    window: object
    element: object


class MacOSDesktopDriver:
    """Drive AppKit activation and Quartz paste into a previous application.

    Attributes:
        target: Original application, window and focused element, or None.
        _generation (int): Incremented whenever the target changes or the
            driver stops, invalidating in-flight paste attempts.
    """

    def __init__(self, appkit=None, quartz=None, permissions=None, focus=None):
        """Initialize the driver with optional native dependencies.

        Args:
            appkit: AppKit module substitute for tests.
            quartz: Quartz module substitute for tests.
            permissions: Permission provider exposing ``can_paste()`` and
                ``request_paste()``.
            focus: Accessibility adapter substitute for tests.
        """
        self._appkit = appkit
        self._quartz = quartz
        self._permissions = permissions
        self._focus = focus
        self.target = None
        self._generation = 0

    @property
    def appkit(self):
        """Return the AppKit module, importing it on first access.

        Returns:
            module: Imported or injected AppKit module.
        """
        if self._appkit is None:
            import AppKit
            self._appkit = AppKit
        return self._appkit

    @property
    def quartz(self):
        """Return the Quartz module, importing it on first access.

        Returns:
            module: Imported or injected Quartz module.
        """
        if self._quartz is None:
            import Quartz
            self._quartz = Quartz
        return self._quartz

    @property
    def permissions(self):
        """Return the permission provider, creating `MacOSPermissions` once.

        Returns:
            MacOSPermissions: Injected provider or a lazily created one.
        """
        if self._permissions is None:
            from .permissions import MacOSPermissions
            self._permissions = MacOSPermissions()
        return self._permissions

    def activation_token(self):
        """Return the platform activation token.

        Returns:
            str: Always an empty string; macOS does not use activation tokens.
        """
        return ''

    def _frontmost_application(self):
        return self.appkit.NSWorkspace.sharedWorkspace().frontmostApplication()

    def _frontmost_pid(self):
        app = self._frontmost_application()
        return app.processIdentifier() if app is not None else None

    def remember_target(self):
        """Capture the window and field while the original application owns focus."""
        self.cancel_paste()
        self.target = None
        app = self._frontmost_application()
        if app is None or app.processIdentifier() == os.getpid() or not self.permissions.can_paste():
            return
        pid = app.processIdentifier()
        if self._focus is None:
            self._focus = MacOSFocus()
        accessibility_app = self._focus.application(pid)
        if accessibility_app is None:
            return
        window = self._focus.read(accessibility_app, MacOSFocus.WINDOW)
        element = self._focus.read(accessibility_app, MacOSFocus.ELEMENT)
        if window is not None and element is not None and self._frontmost_pid() == pid:
            self.target = PasteTarget(app, pid, accessibility_app, window, element)

    def open_search(self, window, activation_token=''):
        """Show and activate the search window over other applications.

        Clears ``WA_ShowWithoutActivating``, restores the normal window state,
        activates the shared `NSApplication` (ignoring other apps), then raises
        and focuses the Qt window.

        Args:
            window: Qt window to show.
            activation_token (str): Unused on macOS.
        """
        from PyQt6.QtCore import Qt
        window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        window.showNormal()
        self.appkit.NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        window.raise_()
        window.activateWindow()

    def request_paste_permission(self):
        """Request the system authorization only from the explicit menu action."""
        if self.permissions.request_paste():
            if self.quartz.CGPreflightPostEventAccess() or self.quartz.CGRequestPostEventAccess():
                return Result()
        return Result(Status.PERMISSION_REQUIRED,
            'Adicione o ClipX ou seu lançador em Ajustes do Sistema → Privacidade e Segurança → Acessibilidade.')

    def _can_post(self):
        return self.permissions.can_paste() and self.quartz.CGPreflightPostEventAccess()

    def _post_paste(self, pid):
        q = self.quartz
        down = q.CGEventCreateKeyboardEvent(None, _ANSI_V, True)
        up = q.CGEventCreateKeyboardEvent(None, _ANSI_V, False)
        if down is None or up is None:
            return Result(Status.ERROR, _MANUAL + 'Falha ao criar o atalho de colagem. Use ⌘V.', 'paste_event_failed')
        for event in (down, up):
            q.CGEventSetFlags(event, q.kCGEventFlagMaskCommand)
            q.CGEventPostToPid(pid, event)
        return Result()

    def paste_to_previous(self, callback=None):
        """Restore the captured field, then send Command-V to its owning PID."""
        target = self.target
        generation = self._generation

        def finish(result):
            if callback is not None:
                callback(result)
            return result

        permission = Result(Status.PERMISSION_REQUIRED,
            _MANUAL + 'Use Autorizar colagem no macOS no menu do ClipX ou cole com ⌘V.',
            'paste_permission_required')
        unavailable = Result(Status.UNAVAILABLE,
            _MANUAL + 'O foco no campo original não pôde ser confirmado. Use ⌘V.',
            'paste_focus_unavailable')
        cancelled = Result(Status.UNAVAILABLE,
            _MANUAL + 'Colagem cancelada porque o foco mudou. Use ⌘V.', 'paste_cancelled')
        if not self._can_post():
            return finish(permission)
        if target is None or target.app.isTerminated():
            return finish(unavailable)

        own_pid = os.getpid()
        current = self._frontmost_pid()
        if current == own_pid:
            clipx_app = self.appkit.NSRunningApplication.currentApplication()
            self.appkit.NSApplication.sharedApplication().yieldActivationToApplication_(target.app)
            if not target.app.activateFromApplication_options_(clipx_app, 0):
                return finish(unavailable)
        elif current not in (None, target.pid):
            return finish(cancelled)

        deadline = time.monotonic() + 1
        focus = self._focus
        raised_window = False
        restored_element = False
        reached_target = current == target.pid

        def attempt():
            nonlocal reached_target, raised_window, restored_element
            if generation != self._generation or target.app.isTerminated():
                return cancelled
            current = self._frontmost_pid()
            if current != target.pid and (reached_target or current not in (None, own_pid)):
                return cancelled
            if time.monotonic() >= deadline:
                return unavailable
            if current != target.pid:
                return None
            reached_target = True
            if not self._can_post():
                return permission

            window = focus.read(target.accessibility_app, MacOSFocus.WINDOW)
            if not focus.same(window, target.window):
                if not raised_window and self._frontmost_pid() == target.pid:
                    raised_window = True
                    focus.raise_window(target.window)
                return None

            element = focus.read(target.accessibility_app, MacOSFocus.ELEMENT)
            if self._frontmost_pid() != target.pid:
                return cancelled
            if not focus.same(element, target.element):
                if not restored_element:
                    restored_element = True
                    focus.focus_element(target.element)
                return None

            if time.monotonic() >= deadline:
                return unavailable
            if not self._can_post():
                return permission
            return self._post_paste(target.pid)

        if callback is not None:
            from PyQt6.QtCore import QTimer

            def tick():
                result = attempt()
                if result is None:
                    QTimer.singleShot(25, tick)
                else:
                    finish(result)

            QTimer.singleShot(25, tick)
            return Result()

        while True:
            result = attempt()
            if result is not None:
                return result
            time.sleep(.025)

    def cancel_paste(self):
        """Invalidate pending work while retaining the current search's target."""
        self._generation += 1

    def stop(self):
        """Cancel any pending paste and release the captured Accessibility references."""
        self.cancel_paste()
        self.target = None
