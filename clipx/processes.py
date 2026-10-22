"""Commands that work both from source and in a frozen application.

Builds subprocess argument lists that run a ClipX module either through the
Python interpreter or through the frozen executable itself.
"""
import sys


def module_command(module, *arguments):
    """Build a subprocess command for a ClipX module.

    When running from source, the interpreter is invoked with ``-m module``. In
    a frozen application, known modules map to their bundled subcommand (or to
    no subcommand when ``None``) and are executed directly by the frozen binary.

    Args:
        module (str): Module name, such as ``"clipx.capture"``.
        *arguments: Additional positional arguments appended as strings.

    Returns:
        list: Argument list suitable for ``subprocess``.
    """
    if getattr(sys, 'frozen', False):
        command = {'clipx.capture': '_capture', 'clipx.main': None}[module]
        return [sys.executable, *([command] if command else []), *map(str, arguments)]
    return [sys.executable, '-m', module, *map(str, arguments)]
