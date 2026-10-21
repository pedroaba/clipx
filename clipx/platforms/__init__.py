"""Lazy native integration selection. Importing this module loads no OS SDK."""
from functools import lru_cache
import sys


@lru_cache(maxsize=2)
def get_platform(platform=None):
    name = platform or sys.platform
    if name == 'linux':
        from .linux import LinuxPlatform
        return LinuxPlatform()
    if name == 'darwin':
        from .macos import MacOSPlatform
        return MacOSPlatform()
    raise RuntimeError(f'Sistema não suportado pelo ClipX: {name}. Use Linux ou macOS 14+.')
