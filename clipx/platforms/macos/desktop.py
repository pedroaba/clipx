"""App activation and authorized paste into the remembered application."""
import os
import time
from clipx.platforms.base import Result, Status


class MacOSDesktopDriver:
    def __init__(self, appkit=None, quartz=None, permissions=None):
        self._appkit = appkit
        self._quartz = quartz
        self._permissions = permissions
        self.target = None
        self._generation = 0

    @property
    def appkit(self):
        if self._appkit is None:
            import AppKit
            self._appkit = AppKit
        return self._appkit

    @property
    def quartz(self):
        if self._quartz is None:
            import Quartz
            self._quartz = Quartz
        return self._quartz

    @property
    def permissions(self):
        if self._permissions is None:
            from .permissions import MacOSPermissions
            self._permissions = MacOSPermissions()
        return self._permissions

    def activation_token(self):
        return ''

    def remember_target(self):
        app = self.appkit.NSWorkspace.sharedWorkspace().frontmostApplication()
        if app is not None and app.processIdentifier() != os.getpid():
            self.target = app
        self._generation += 1

    def open_search(self, window, activation_token=''):
        from PyQt6.QtCore import Qt
        window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        window.showNormal()
        self.appkit.NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        window.raise_()
        window.activateWindow()

    def request_paste_permission(self):
        granted = self.permissions.request_paste()
        return Result() if granted else Result(Status.PERMISSION_REQUIRED,
            'Autorize o interpretador/aplicativo lançador nos ajustes de privacidade do macOS e tente novamente.')

    def paste_to_previous(self, callback=None):
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
        self._generation += 1
        self.target = None
