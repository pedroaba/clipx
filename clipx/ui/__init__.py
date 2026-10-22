"""Public entry point for the ClipX Qt interface.

Re-exports the main window so callers can import it from :mod:`clipx.ui`
without depending on the internal page structure.
"""
from clipx.ui.pages.clipboard import ClipXMainWindow

__all__ = ["ClipXMainWindow"]
