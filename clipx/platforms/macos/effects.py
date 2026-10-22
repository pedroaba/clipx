"""Native background siblings behind the Qt view; foreground remains PyQt6.

`MacOSWindowEffects` inserts an `NSVisualEffectView` (or `NSGlassEffectView`
when the OS provides it) as a sibling behind Qt's view, so AppKit draws the
material while PyQt6 keeps painting and handling input. The material is
refreshed when accessibility display options change, and removed when the user
enables Reduce Transparency.
"""
import logging
from clipx.platforms.effects import OpaqueWindowEffects

_EFFECT_CLASSES = {}


def _effect_class(glass):
    """Create or return the Objective-C subclass used for the material view.

    The generated class overrides ``hitTest_`` to return ``None`` so the native
    view never consumes clicks intended for Qt. Subclasses are cached by the
    ``glass`` flag.

    Args:
        glass (bool): Use `NSGlassEffectView` when available; otherwise use
            `NSVisualEffectView`.

    Returns:
        type: The cached Objective-C class for the requested material.
    """
    if glass not in _EFFECT_CLASSES:
        import objc
        import AppKit
        base = objc.lookUpClass('NSGlassEffectView') if glass else AppKit.NSVisualEffectView
        name = 'ClipXGlassBackground' if glass else 'ClipXVibrancyBackground'
        _EFFECT_CLASSES[glass] = type(name, (base,), {'hitTest_': lambda self, point: None})
    return _EFFECT_CLASSES[glass]


class MacOSWindowEffects(OpaqueWindowEffects):
    """Apply native macOS materials behind Qt windows.

    Attributes:
        views (dict[int, object]): Material view per ``id(window)``.
        observers (dict[int, tuple]): Notification center, token, and callback
            registered per ``id(window)``.
    """

    def __init__(self):
        """Initialize empty view and observer registries."""
        self.views = {}
        self.observers = {}

    def reduce_motion(self):
        """Return the system Reduce Motion preference.

        Returns:
            bool: True when AppKit reports reduced motion, and also True if the
            preference cannot be read.
        """
        try:
            import AppKit
            return bool(AppKit.NSWorkspace.sharedWorkspace().accessibilityDisplayShouldReduceMotion())
        except Exception:
            return True

    def _watch_preferences(self, window):
        """Subscribe the window to accessibility display-option changes.

        Registers at most one observer per window on the workspace notification
        center. The callback calls ``window.refresh_material()`` on the main
        operation queue.

        Args:
            window: Qt window to refresh; identified by ``id(window)``.
        """
        if id(window) in self.observers:
            return
        import AppKit
        from Foundation import NSOperationQueue
        center = AppKit.NSWorkspace.sharedWorkspace().notificationCenter()
        callback = lambda notification: window.refresh_material()
        token = center.addObserverForName_object_queue_usingBlock_(
            AppKit.NSWorkspaceAccessibilityDisplayOptionsDidChangeNotification, None,
            NSOperationQueue.mainQueue(), callback)
        self.observers[id(window)] = (center, token, callback)

    def _remove_view(self, window):
        """Detach the material view from the window, if present.

        Args:
            window: Qt window whose view is removed; the ``nativeGlass``
            property is reset to False.
        """
        effect = self.views.pop(id(window), None)
        if effect is not None:
            effect.removeFromSuperview()
        window.setProperty('nativeGlass', False)

    def apply(self, window):
        """Insert or update the native material behind a window.

        Returns the opaque fallback under the ``offscreen`` and ``minimal`` Qt
        platforms. Native work is skipped when Reduce Transparency is enabled,
        reusing an existing view for appearance-only updates. Glass is used when
        available and vibrancy otherwise, both with a 16-point corner radius,
        the window's light or dark appearance, and a non-opaque native window
        background. Native errors are logged, the view is removed, and False is
        returned.

        Args:
            window: Qt window to decorate.

        Returns:
            bool: True when a native material is active, otherwise False.
        """
        from PyQt6.QtWidgets import QApplication
        if QApplication.platformName() in ('offscreen', 'minimal'):
            return super().apply(window)
        try:
            import objc
            import AppKit
            self._watch_preferences(window)
            if AppKit.NSWorkspace.sharedWorkspace().accessibilityDisplayShouldReduceTransparency():
                self._remove_view(window)
                return False
            key = id(window)
            appearance = AppKit.NSAppearance.appearanceNamed_(AppKit.NSAppearanceNameAqua if window.property('lightTheme') else AppKit.NSAppearanceNameDarkAqua)
            if key in self.views:
                self.views[key].setAppearance_(appearance)
                return True
            qt_view = objc.objc_object(c_void_p=int(window.winId()))
            native_window = qt_view.window()
            container = qt_view.superview()
            if native_window is None or container is None:
                return False
            try:
                effect_class = _effect_class(glass=True)
            except objc.nosuchclass_error:
                effect_class = _effect_class(glass=False)
            effect = effect_class.alloc().initWithFrame_(qt_view.frame())
            effect.setAutoresizingMask_(18)
            if hasattr(effect, 'setCornerRadius_'):
                effect.setCornerRadius_(16)
            else:
                effect.setWantsLayer_(True)
                effect.layer().setCornerRadius_(16)
                effect.layer().setMasksToBounds_(True)
            if hasattr(effect, 'setMaterial_'):
                effect.setMaterial_(AppKit.NSVisualEffectMaterialPopover)
                effect.setBlendingMode_(AppKit.NSVisualEffectBlendingModeBehindWindow)
                effect.setState_(AppKit.NSVisualEffectStateActive)
            effect.setAppearance_(appearance)
            # A child of QNSView would cover Qt's backing-store painting. Use a sibling.
            container.addSubview_positioned_relativeTo_(effect, -1, qt_view)
            native_window.setOpaque_(False)
            native_window.setBackgroundColor_(AppKit.NSColor.clearColor())
            native_window.setHasShadow_(True)
            self.views[key] = effect
            window.setProperty('nativeGlass', True)
            return True
        except Exception as exc:
            logging.getLogger('clipx.effects').warning('Native material unavailable: %s', exc)
            self._remove_view(window)
            return False

    def remove(self, window):
        """Remove the material view, preference observer, and glass flag.

        Args:
            window: Qt window to restore.
        """
        self._remove_view(window)
        observed = self.observers.pop(id(window), None)
        if observed is not None:
            center, token, callback = observed
            center.removeObserver_(token)
        super().remove(window)
