"""Show the macOS application identity while settings dialogs are available."""
import logging
import sys
from PyQt6.QtWidgets import QApplication


def sync_dialog_dock():
    if sys.platform != 'darwin' or QApplication.platformName() != 'cocoa':
        return
    try:
        import AppKit
        from clipx.ui.foundations.branding import ICON_PATH
        visible = any(window.property('clipxSettingsDialog') and window.isVisible()
                      for window in QApplication.topLevelWidgets())
        app = AppKit.NSApplication.sharedApplication()
        if visible:
            image = AppKit.NSImage.alloc().initWithContentsOfFile_(str(ICON_PATH))
            if image is not None:
                app.setApplicationIconImage_(image)
        policy = (AppKit.NSApplicationActivationPolicyRegular if visible
                  else AppKit.NSApplicationActivationPolicyAccessory)
        if app.activationPolicy() != policy:
            app.setActivationPolicy_(policy)
    except Exception as exc:
        logging.getLogger('clipx.dock').warning('Application icon unavailable: %s', exc)
