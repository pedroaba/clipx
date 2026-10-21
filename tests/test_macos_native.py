"""Opt-in integration checks using a private pasteboard; never alter the global clipboard."""
import os
import sys
import unittest
from uuid import uuid4


@unittest.skipUnless(sys.platform == 'darwin' and os.environ.get('CLIPX_TEST_MACOS'), 'requires opt-in native macOS session')
class MacOSNativeTests(unittest.TestCase):
    def test_dialog_chrome_uses_native_traffic_lights_and_dark_tint(self):
        import AppKit
        import objc
        from PyQt6.QtWidgets import QApplication, QWidget
        from clipx.ui.templates.window import SystemDialog
        app = QApplication.instance() or QApplication([])
        dialog = SystemDialog()
        dialog.setWindowTitle('ClipX — Native chrome test')
        dialog.mount_content(QWidget())
        try:
            dialog.show()
            app.processEvents()
            native = objc.objc_object(c_void_p=int(dialog.winId())).window()
            self.assertEqual(native.level(), AppKit.NSNormalWindowLevel)
            self.assertTrue(native.titlebarAppearsTransparent())
            self.assertIsNotNone(native.toolbar())
            self.assertEqual(native.toolbarStyle(), AppKit.NSWindowToolbarStyleUnifiedCompact)
            self.assertEqual(native.titlebarSeparatorStyle(), AppKit.NSTitlebarSeparatorStyleLine)
            title = dialog._native_chrome_title
            close = native.standardWindowButton_(AppKit.NSWindowCloseButton)
            self.assertAlmostEqual(title.frame().origin.y + title.frame().size.height / 2,
                                   close.frame().origin.y + close.frame().size.height / 2, delta=1)
            self.assertEqual(dialog._native_chrome_separator.frame().size.height, 1)
            self.assertEqual(native.effectiveAppearance().name(), AppKit.NSAppearanceNameDarkAqua)
            for kind in (AppKit.NSWindowCloseButton, AppKit.NSWindowMiniaturizeButton, AppKit.NSWindowZoomButton):
                self.assertIsNotNone(native.standardWindowButton_(kind))
            color = native.backgroundColor().colorUsingColorSpace_(AppKit.NSColorSpace.sRGBColorSpace())
            self.assertAlmostEqual(color.redComponent(), 16 / 255, places=3)
        finally:
            dialog.close()
            dialog.deleteLater()

    def test_private_pasteboard_write_marker_and_observation(self):
        import AppKit
        from unittest.mock import Mock
        from clipx.platforms.macos.clipboard import MacOSClipboardDriver, TEXT_TYPE, SELF_TYPE
        board = AppKit.NSPasteboard.pasteboardWithName_('ClipX.Tests.' + uuid4().hex)
        self.addCleanup(board.releaseGlobally)
        driver = MacOSClipboardDriver(pasteboard=board)
        self.assertTrue(driver.write_text('Olá\n世界').ok)
        self.assertEqual(board.stringForType_(TEXT_TYPE), 'Olá\n世界')
        self.assertIn(SELF_TYPE, board.types())
        sink = Mock()
        driver.poll(sink)
        sink.save.assert_not_called()
        board.clearContents()
        board.setString_forType_('External private test', TEXT_TYPE)
        driver.poll(sink)
        sink.save.assert_called_once_with('External private test')

    def test_carbon_register_unregister(self):
        from PyQt6.QtWidgets import QApplication
        from clipx.platforms.macos.shortcuts import CarbonHotKeys
        app = QApplication.instance() or QApplication([])
        native = CarbonHotKeys()
        self.addCleanup(native.close)
        handle = native.register('Ctrl+Alt+Shift+F12', lambda: None)
        self.assertTrue(handle[0].value)
        native.unregister(handle)
        self.assertFalse(native.callbacks)

    def test_background_observer_stops_and_records_private_test_board(self):
        import AppKit
        from pathlib import Path
        import tempfile
        import threading
        from clipx.capture import ClipboardCapture
        from clipx.storage import Storage
        from clipx.platforms.macos.clipboard import MacOSClipboardDriver, TEXT_TYPE
        board = AppKit.NSPasteboard.pasteboardWithName_('ClipX.Tests.' + uuid4().hex)
        self.addCleanup(board.releaseGlobally)
        board.clearContents()
        board.setString_forType_('Worker in background\nUnicode: 你好', TEXT_TYPE)
        with tempfile.TemporaryDirectory() as folder:
            storage = Storage(Path(folder) / 'history.db')
            driver = MacOSClipboardDriver(pasteboard=board)
            stopped, reported = threading.Event(), threading.Event()
            results = []
            def report(result):
                results.append(result)
                reported.set()
            thread = threading.Thread(target=driver.start_observation,
                args=(ClipboardCapture(storage), stopped, report))
            thread.start()
            try:
                self.assertTrue(reported.wait(2))
                self.assertTrue(results[0].ok)
                self.assertEqual(storage.get_clips()[0].content, 'Worker in background\nUnicode: 你好')
            finally:
                driver.stop_observation()
                thread.join(2)
            self.assertFalse(thread.is_alive())

    def test_native_material_is_a_noninteractive_sibling_of_qt(self):
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        if app.platformName() != 'cocoa':
            self.skipTest('requires QT_QPA_PLATFORM=cocoa')
        import AppKit
        import objc
        from pathlib import Path
        import tempfile
        from clipx.platforms import get_platform
        from clipx.storage import Storage
        from clipx.shortcuts import ShortcutSettings
        from clipx.ui.pages.clipboard import ClipXMainWindow
        if AppKit.NSWorkspace.sharedWorkspace().accessibilityDisplayShouldReduceTransparency():
            self.skipTest('system transparency reduction is enabled')
        with tempfile.TemporaryDirectory() as folder:
            window = ClipXMainWindow(Storage(Path(folder) / 'history.db'),
                                     ShortcutSettings(Path(folder) / 'settings.json'))
            try:
                window.show()
                app.processEvents()
                window.refresh_material()
                self.assertTrue(window.property('nativeGlass'))
                effect = window.platform.effects.views[id(window)]
                qt_view = objc.objc_object(c_void_p=int(window.winId()))
                self.assertEqual(effect.superview(), qt_view.superview())
                self.assertIsNone(effect.hitTest_((10, 10)))
                window.resize(720, 460)
                app.processEvents()
                self.assertEqual(effect.frame().size.width, qt_view.frame().size.width)
            finally:
                window.platform.effects.remove(window)
                window.close()
                window.deleteLater()
                app.processEvents()

    def test_accessibility_api_reads_status_without_prompt(self):
        from clipx.platforms.macos.permissions import MacOSPermissions
        permissions = MacOSPermissions()
        self.assertIsInstance(permissions.can_paste(), bool)
        # Exercise CFDictionary bridging, while replacing the call that would prompt.
        from unittest.mock import patch
        with patch.object(permissions.lib, 'AXIsProcessTrustedWithOptions', return_value=False) as request:
            self.assertFalse(permissions.request_paste())
            request.assert_called_once()

    def test_tray_menu_tracking_callback_never_queries_mouse_event(self):
        from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon
        app = QApplication.instance() or QApplication([])
        if app.platformName() != 'cocoa':
            self.skipTest('requires QT_QPA_PLATFORM=cocoa')
        import objc
        from clipx.platforms.macos.tray import install_menu_tracking_guard
        install_menu_tracking_guard()
        install_menu_tracking_guard()  # Reopening/showing is idempotent.
        delegate = objc.lookUpClass('QStatusItemDelegate').alloc().init()
        # No platformSystemTray is attached: calling Qt's old implementation would crash.
        delegate.statusItemMenuBeganTracking_(None)
        from clipx.ui.controllers.tray import tray_icon
        tray = QSystemTrayIcon(tray_icon())
        menu = QMenu()
        menu.addAction('ClipX regression test')
        tray.setContextMenu(menu)
        try:
            tray.show()
            app.processEvents()
            from AppKit import NSNotificationCenter, NSMenu
            # Replay Qt's observer registration with a native menu and the same delegate class.
            native_menu = NSMenu.alloc().initWithTitle_('ClipX regression')
            center = NSNotificationCenter.defaultCenter()
            center.addObserver_selector_name_object_(delegate, 'statusItemMenuBeganTracking:',
                'NSMenuDidBeginTrackingNotification', native_menu)
            try:
                center.postNotificationName_object_('NSMenuDidBeginTrackingNotification', native_menu)
                app.processEvents()
                self.assertTrue(tray.isVisible())
            finally:
                center.removeObserver_(delegate)
        finally:
            tray.hide()

    def test_light_native_chrome_and_material_respect_preference(self):
        import objc
        import AppKit
        from clipx.ui.templates.window import SystemDialog
        from clipx.platforms.window_chrome import apply_window_chrome
        from clipx.platforms.macos.effects import MacOSWindowEffects
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        dialog = SystemDialog()
        effects = MacOSWindowEffects()
        try:
            dialog.setProperty('lightTheme', True)
            dialog.show()
            app.processEvents()
            apply_window_chrome(dialog)
            native = objc.objc_object(c_void_p=int(dialog.winId())).window()
            match = native.appearance().bestMatchFromAppearancesWithNames_([AppKit.NSAppearanceNameAqua, AppKit.NSAppearanceNameDarkAqua])
            self.assertEqual(match, AppKit.NSAppearanceNameAqua)
            color = native.backgroundColor().colorUsingColorSpace_(AppKit.NSColorSpace.sRGBColorSpace())
            self.assertAlmostEqual(color.redComponent(), 250 / 255, places=3)
            effects.apply(dialog)
            if id(dialog) in effects.views:
                match = effects.views[id(dialog)].appearance().bestMatchFromAppearancesWithNames_([AppKit.NSAppearanceNameAqua, AppKit.NSAppearanceNameDarkAqua])
                self.assertEqual(match, AppKit.NSAppearanceNameAqua)
        finally:
            effects.remove(dialog)
            dialog.close()
            dialog.deleteLater()
