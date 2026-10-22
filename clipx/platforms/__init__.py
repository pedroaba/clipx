"""Lazy selection of the native platform adapter.

Importing this module loads no OS SDK: the Linux or macOS implementation is
imported only when a platform is first requested. Instances are cached by
`functools.lru_cache`, so repeated calls return the same adapter object.
"""
from functools import lru_cache
import sys


@lru_cache(maxsize=2)
def get_platform(platform=None):
    """Return the cached platform adapter for the current or given platform.

    Args:
        platform (str | None): Platform identifier such as ``'darwin'`` or
            ``'linux'``. Defaults to `sys.platform`.

    Returns:
        The `LinuxPlatform` or `MacOSPlatform` instance for the platform. The
        result is cached per argument value.

    Raises:
        RuntimeError: If the platform is neither ``'linux'`` nor ``'darwin'``.
    """
    name = platform or sys.platform
    if name == 'linux':
        from .linux import LinuxPlatform
        return LinuxPlatform()
    if name == 'darwin':
        from .macos import MacOSPlatform
        return MacOSPlatform()
    raise RuntimeError(f'Sistema não suportado pelo ClipX: {name}. Use Linux ou macOS 14+.')
