"""ClipX - A modern, Raycast-styled clipboard history manager for Linux and macOS."""

import os
import sys

# Fix incompatibility with GNOME 50+ xsettings schema and Qt GTK platform theme
if sys.platform == "linux":
    os.environ["QT_QPA_PLATFORMTHEME"] = "generic"

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("clipx")
except PackageNotFoundError:
    __version__ = "0+uninstalled"
