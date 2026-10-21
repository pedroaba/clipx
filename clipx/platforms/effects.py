"""Predictable dark material where native glass is unavailable."""


class OpaqueWindowEffects:
    def apply(self, window):
        window.setProperty('nativeGlass', False)
        return False

    def remove(self, window):
        window.setProperty('nativeGlass', False)

    def reduce_motion(self):
        return False
