"""ClipX package and version metadata.

ClipX is a clipboard history manager for Linux and macOS. Importing this package
normalizes the Qt platform theme on Linux and resolves ``__version__`` from the
installed distribution, falling back to ``"0+uninstalled"`` when distribution
metadata is unavailable.
"""

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
