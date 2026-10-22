"""macOS platform adapter exposing lazily imported native drivers.

Each driver is created on first access and cached for the adapter's lifetime.
Native SDKs are imported inside the driver modules, so importing this package
does not load AppKit, Quartz, or Carbon.
"""
from functools import cached_property
from clipx.platforms.paths import PlatformPaths


class MacOSPlatform:
    """Aggregate the macOS clipboard, desktop, shortcut, and effect drivers.

    Attributes:
        name (str): Stable platform identifier, ``'macos'``.
    """

    name = 'macos'

    @cached_property
    def clipboard(self):
        """Return the cached macOS clipboard driver.

        Returns:
            MacOSClipboardDriver: Driver backed by `NSPasteboard`.
        """
        from .clipboard import MacOSClipboardDriver
        return MacOSClipboardDriver()

    @cached_property
    def desktop(self):
        """Return the cached macOS desktop driver.

        Returns:
            MacOSDesktopDriver: Driver using AppKit activation and Quartz
            keyboard events.
        """
        from .desktop import MacOSDesktopDriver
        return MacOSDesktopDriver()

    @cached_property
    def shortcuts(self):
        """Return the cached macOS global shortcut driver.

        Returns:
            MacOSGlobalShortcut: Driver persisting to ``settings.json`` under
            the macOS configuration directory.
        """
        from .shortcuts import MacOSGlobalShortcut
        return MacOSGlobalShortcut(self.paths.config / 'settings.json')

    @cached_property
    def effects(self):
        """Return the cached macOS window effects implementation.

        Returns:
            MacOSWindowEffects: Driver applying native vibrancy or glass.
        """
        from .effects import MacOSWindowEffects
        return MacOSWindowEffects()

    @property
    def paths(self):
        """Return a new macOS path resolver.

        Returns:
            PlatformPaths: Resolver configured for ``'darwin'``.
        """
        return PlatformPaths('darwin')
