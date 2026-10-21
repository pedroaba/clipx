from functools import cached_property
from clipx.platforms.paths import PlatformPaths


class MacOSPlatform:
    name = 'macos'

    @cached_property
    def clipboard(self):
        from .clipboard import MacOSClipboardDriver
        return MacOSClipboardDriver()

    @cached_property
    def desktop(self):
        from .desktop import MacOSDesktopDriver
        return MacOSDesktopDriver()

    @cached_property
    def shortcuts(self):
        from .shortcuts import MacOSGlobalShortcut
        return MacOSGlobalShortcut(self.paths.config / 'settings.json')

    @cached_property
    def effects(self):
        from .effects import MacOSWindowEffects
        return MacOSWindowEffects()

    @property
    def paths(self):
        return PlatformPaths('darwin')
