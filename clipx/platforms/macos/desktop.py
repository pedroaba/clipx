"""App activation and authorized paste into the remembered application.

`MacOSDesktopDriver` records the frontmost application before ClipX shows its
window, then reactivates that application and posts a synthetic Command-V
through Quartz. Posting keyboard events requires macOS Accessibility trust, and
each activation attempt is guarded by a generation counter so a stale target
cannot receive the paste.
"""
import os
import time
from clipx.platforms.base import Result, Status


class MacOSDesktopDriver:
    """Drive AppKit activation and Quartz paste into a previous application.

    Attributes:
        target: Remembered `NSRunningApplication`, or None.
        _generation (int): Incremented whenever the target changes or the
            driver stops, invalidating in-flight paste attempts.
    """

    def __init__(self, appkit=None, quartz=None, permissions=None):
        """Initialize the driver with optional native dependencies.

        Args:
            appkit: AppKit module substitute for tests.
            quartz: Quartz module substitute for tests.
            permissions: Permission provider exposing ``can_paste()`` and
                ``request_paste()``.
        """
        self._appkit = appkit
        self._quartz = quartz
        self._permissions = permissions
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

    def remember_target(self):
        """Record the frontmost application unless it is ClipX itself.

        Also increments the generation, invalidating any paste attempt that is
        waiting for a different target.
        """
        app = self.appkit.NSWorkspace.sharedWorkspace().frontmostApplication()
        if app is not None and app.processIdentifier() != os.getpid():
            self.target = app
        self._generation += 1

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
        """Prompt for Accessibility trust and report the current state.

        Returns:
            Result: `Status.READY` when trust is already granted, otherwise
            `Status.PERMISSION_REQUIRED` with guidance.
        """
        granted = self.permissions.request_paste()
        return Result() if granted else Result(Status.PERMISSION_REQUIRED,
            'Autorize o interpretador/aplicativo lançador nos ajustes de privacidade do macOS e tente novamente.')

    def paste_to_previous(self, callback=None):
        """Paste into the remembered application with a synthetic Command-V.

        Fails immediately without Accessibility trust or when the target is
        missing or terminated. Otherwise activates the target and waits up to
        one second for it to become frontmost. The paste is aborted if the
        target changes, terminates, or loses trust before the key events are
        posted. With ``callback`` the waiting happens through 25 ms Qt timer
        ticks and the method returns a pending success; without it the wait is
        a blocking sleep loop. The synchronous loop is intended for non-Qt
        callers and deterministic native tests.

        Args:
            callback (Callable[[Result], None] | None): Receives the final
                result asynchronously when provided.

        Returns:
            Result: Immediate failure or pending `Status.READY`.
        """
        q = self.quartz
        if not self.permissions.can_paste():
            result = Result(Status.PERMISSION_REQUIRED,
                'Texto copiado. Autorize a colagem pelo menu da bandeja → Autorizar colagem no macOS.')
            if callback:
                callback(result)
            return result
        target = self.target
        if target is None or target.isTerminated():
            result = Result(Status.UNAVAILABLE, 'Texto copiado. O aplicativo de destino não está disponível.')
            if callback:
                callback(result)
            return result
        generation = self._generation
        if not target.activateWithOptions_(2):
            result = Result(Status.UNAVAILABLE, 'Texto copiado. Não foi possível ativar o aplicativo de destino.')
            if callback:
                callback(result)
            return result
        deadline = time.monotonic() + 1

        def attempt():
            """Try one paste step.

            Returns:
                Result | None: Final status, or None when the target is not yet
                frontmost and the deadline has not passed.
            """
            if generation != self._generation or target.isTerminated():
                return Result(Status.UNAVAILABLE, 'Colagem cancelada: o destino mudou.')
            current = self.appkit.NSWorkspace.sharedWorkspace().frontmostApplication()
            if current and current.processIdentifier() == target.processIdentifier():
                if not self.permissions.can_paste():
                    return Result(Status.PERMISSION_REQUIRED, 'Texto copiado. A permissão de colagem foi revogada.')
                down = q.CGEventCreateKeyboardEvent(None, 9, True)
                up = q.CGEventCreateKeyboardEvent(None, 9, False)
                if down is None or up is None:
                    return Result(Status.ERROR, 'Texto copiado. Não foi possível criar o evento de colagem.')
                for event in (down, up):
                    q.CGEventSetFlags(event, q.kCGEventFlagMaskCommand)
                    q.CGEventPost(q.kCGHIDEventTap, event)
                return Result()
            if time.monotonic() >= deadline:
                return Result(Status.UNAVAILABLE, 'Texto copiado. O aplicativo de destino não recebeu foco.')
            return None

        if callback:
            from PyQt6.QtCore import QTimer
            def tick():
                """Run one attempt tick, rescheduling itself while pending."""
                result = attempt()
                if result is None:
                    QTimer.singleShot(25, tick)
                else:
                    callback(result)
            QTimer.singleShot(25, tick)
            return Result()
        # Synchronous path for non-Qt callers and deterministic native tests.
        while True:
            result = attempt()
            if result is not None:
                return result
            time.sleep(0.025)

    def stop(self):
        """Forget the paste target and invalidate in-flight paste attempts."""
        self._generation += 1
        self.target = None
