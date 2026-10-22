"""Linux platform composition root.

Wires the Linux-specific clipboard, desktop and shortcut drivers into the
platform-agnostic interface. Driver modules are imported lazily so that
importing this package does not require a graphical session or optional
X11/Wayland dependencies.
"""
from functools import cached_property
from clipx.platforms.paths import PlatformPaths


class LinuxPlatform:
    """Platform implementation for Linux desktops.

    Attributes:
        name (str): Stable platform identifier consumed by the rest of ClipX.
        clipboard (LinuxClipboardDriver): Clipboard driver, created on first access.
        desktop (LinuxDesktopDriver): Window activation and paste driver.
        shortcuts (LinuxGlobalShortcut): GNOME global shortcut backend.
        effects (OpaqueWindowEffects): Window effects, which are opaque on Linux.
        paths (PlatformPaths): Filesystem locations for the Linux platform.
    """
    name = 'linux'

    @cached_property
    def clipboard(self):
        """Return the lazily created Linux clipboard driver.

        Returns:
            LinuxClipboardDriver: Cached driver bound to this platform instance.
        """
        from .clipboard import LinuxClipboardDriver
        return LinuxClipboardDriver()

    @cached_property
    def desktop(self):
        """Return the lazily created Linux desktop driver.

        Returns:
            LinuxDesktopDriver: Cached driver for activation and paste handling.
        """
        from .desktop import LinuxDesktopDriver
        return LinuxDesktopDriver()

    @cached_property
    def shortcuts(self):
        """Return the lazily created GNOME global shortcut backend.

        Returns:
            LinuxGlobalShortcut: Cached backend that stores bindings via gsettings.
        """
        from .shortcuts import LinuxGlobalShortcut
        return LinuxGlobalShortcut()

    @cached_property
    def effects(self):
        """Return the window effects implementation used on Linux.

        Returns:
            OpaqueWindowEffects: Effects object that reports opaque windows.
        """
        from clipx.platforms.effects import OpaqueWindowEffects
        return OpaqueWindowEffects()

    @property
    def paths(self):
        """Return the filesystem locations for the Linux platform.

        Returns:
            PlatformPaths: Paths resolved for the ``linux`` platform name.
        """
        return PlatformPaths('linux')
