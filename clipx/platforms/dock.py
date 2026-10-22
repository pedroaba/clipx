"""Show the macOS application identity while settings dialogs are available.

The app runs as an accessory (menu-bar) process. When a settings dialog is
visible, this module switches the shared `NSApplication` to the regular
activation policy and installs the ClipX icon so the dialog also appears in the
Dock and the application switcher.
"""
import logging
import sys
from PyQt6.QtWidgets import QApplication


def sync_dialog_dock():
    """Show or hide the Dock icon and app identity according to dialog state.

    Does nothing when not running on macOS with the Cocoa Qt platform plugin.
    A settings dialog is any visible top-level widget carrying a truthy
    ``clipxSettingsDialog`` property. When such a dialog exists, the shared
    application gets the ClipX icon and the regular activation policy;
    otherwise the accessory policy is restored. Native failures are logged and
    never propagate, because the Dock identity is cosmetic.
    """
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
