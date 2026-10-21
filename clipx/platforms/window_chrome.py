"""Tint native window chrome without replacing OS controls or hit testing."""
import logging
import sys
from PyQt6.QtCore import QEvent, QObject
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

CHROME_COLOR = '#101012'


def apply_window_chrome(window):
    light = bool(window.property('lightTheme'))
    color = QColor('#FAFAFA' if light else CHROME_COLOR)
    palette = window.palette()
    palette.setColor(QPalette.ColorRole.Window, color)
    palette.setColor(QPalette.ColorRole.WindowText, QColor('#18181B' if light else '#F4F4F5'))
    window.setPalette(palette)
    if sys.platform != 'darwin' or QApplication.platformName() in ('offscreen', 'minimal'):
        return
    try:
        import objc
        import AppKit
        import Quartz
        native = objc.objc_object(c_void_p=int(window.winId())).window()
        native.setLevel_(AppKit.NSNormalWindowLevel)
        native.setAppearance_(AppKit.NSAppearance.appearanceNamed_(AppKit.NSAppearanceNameAqua if light else AppKit.NSAppearanceNameDarkAqua))
        native.setBackgroundColor_(AppKit.NSColor.colorWithSRGBRed_green_blue_alpha_(color.redF(), color.greenF(), color.blueF(), 1))
        native.setTitlebarAppearsTransparent_(True)
        native.setHasShadow_(True)
        if not getattr(window, '_native_chrome_toolbar', None):
            # Native toolbar lets AppKit place the traffic lights and
            # title within a single header, instead of adding an empty second row.
            toolbar = AppKit.NSToolbar.alloc().initWithIdentifier_('ClipX.WindowHeader')
            toolbar.setAllowsUserCustomization_(False)
            native.setToolbar_(toolbar)
            native.setToolbarStyle_(AppKit.NSWindowToolbarStyleUnifiedCompact)
            native.setTitlebarSeparatorStyle_(AppKit.NSTitlebarSeparatorStyleLine)
            window._native_chrome_toolbar = toolbar
            native.setTitleVisibility_(AppKit.NSWindowTitleHidden)
            titlebar = native.standardWindowButton_(AppKit.NSWindowCloseButton).superview()
            title = AppKit.NSTextField.labelWithString_(window.windowTitle())
            title.setAlignment_(AppKit.NSTextAlignmentCenter)
            title.setFont_(AppKit.NSFont.systemFontOfSize_weight_(12, AppKit.NSFontWeightMedium))
            title.setTextColor_(AppKit.NSColor.secondaryLabelColor())
            title.setFrame_(AppKit.NSMakeRect(90, 10, max(0, titlebar.bounds().size.width - 180), 18))
            title.setAutoresizingMask_(AppKit.NSViewWidthSizable)
            titlebar.addSubview_(title)
            separator = AppKit.NSView.alloc().initWithFrame_(AppKit.NSMakeRect(0, 0, titlebar.bounds().size.width, 1))
            separator.setWantsLayer_(True)
            separator.layer().setBackgroundColor_(Quartz.CGColorCreateGenericRGB(48 / 255, 48 / 255, 52 / 255, 1))
            separator.setAutoresizingMask_(AppKit.NSViewWidthSizable)
            titlebar.addSubview_(separator)
            window._native_chrome_title = title
            window._native_chrome_separator = separator
        # Leave styleMask and standardWindowButton untouched: AppKit owns all
        # traffic-light behavior, accessibility and native window dragging.
    except Exception as exc:
        logging.getLogger('clipx.chrome').warning('Native title bar tint unavailable: %s', exc)


class NativeChromeFilter(QObject):
    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Show:
            apply_window_chrome(watched)
        return False
