from functools import cached_property
from clipx.platforms.paths import PlatformPaths


class LinuxPlatform:
    name = 'linux'

    @cached_property
    def clipboard(self):
        from .clipboard import LinuxClipboardDriver
        return LinuxClipboardDriver()

    @cached_property
    def desktop(self):
        from .desktop import LinuxDesktopDriver
        return LinuxDesktopDriver()

    @cached_property
    def shortcuts(self):
        from .shortcuts import LinuxGlobalShortcut
        return LinuxGlobalShortcut()

    @cached_property
    def effects(self):
        from clipx.platforms.effects import OpaqueWindowEffects
        return OpaqueWindowEffects()

    @property
    def paths(self):
        return PlatformPaths('linux')
