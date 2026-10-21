"""Commands that work both from source and in a frozen application."""
import sys


def module_command(module, *arguments):
    if getattr(sys, 'frozen', False):
        command = {'clipx.capture': '_capture', 'clipx.main': None}[module]
        return [sys.executable, *([command] if command else []), *map(str, arguments)]
    return [sys.executable, '-m', module, *map(str, arguments)]
