"""Predictable dark material where native glass is unavailable.

`OpaqueWindowEffects` is the base implementation shared by every platform: it
adds no native blur or vibrancy, reports that material is not active, and
signals the Qt side through the ``nativeGlass`` window property. Platforms with
native materials subclass it and fall back to this behavior.
"""


class OpaqueWindowEffects:
    """Window effects that never add a native material."""

    def apply(self, window):
        """Mark the window as having no native material.

        Args:
            window: Qt window exposing ``setProperty``.

        Returns:
            bool: Always False, meaning no native material is active.
        """
        window.setProperty('nativeGlass', False)
        return False

    def remove(self, window):
        """Clear the native-material flag on the window.

        Args:
            window: Qt window exposing ``setProperty``.
        """
        window.setProperty('nativeGlass', False)

    def reduce_motion(self):
        """Return whether the user asked for reduced motion.

        Returns:
            bool: Always False; this base implementation has no access to the
            OS accessibility preferences.
        """
        return False
