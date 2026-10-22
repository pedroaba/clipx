"""Read/request Accessibility trust through the public ApplicationServices API.

The Accessibility permission allows ClipX to post the synthetic Command-V used
to paste into the previously active application. Trust is read with
`AXIsProcessTrusted` and requested with `AXIsProcessTrustedWithOptions` plus
the system prompt option.
"""
import ctypes as C


class MacOSPermissions:
    """Query and request macOS Accessibility trust for this process.

    Attributes:
        lib (ctypes.CDLL): Loaded ApplicationServices framework with configured
            function signatures.
    """

    def __init__(self):
        """Load ApplicationServices and configure the trust function prototypes."""
        self.lib = C.CDLL('/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices')
        self.lib.AXIsProcessTrusted.argtypes = []
        self.lib.AXIsProcessTrusted.restype = C.c_bool
        self.lib.AXIsProcessTrustedWithOptions.argtypes = [C.c_void_p]
        self.lib.AXIsProcessTrustedWithOptions.restype = C.c_bool

    def can_paste(self):
        """Return whether the process is trusted for Accessibility.

        Returns:
            bool: True when macOS reports the process as trusted; this does not
            display a prompt.
        """
        return bool(self.lib.AXIsProcessTrusted())

    def request_paste(self):
        """Ask macOS to show the Accessibility permission prompt.

        Builds the options dictionary with `kAXTrustedCheckOptionPrompt` set to
        True and queries trust again, so the return value reflects the state
        before the user responds to the prompt.

        Returns:
            bool: True when the process is already trusted.
        """
        import objc
        from Foundation import NSDictionary
        address = C.c_void_p.in_dll(self.lib, 'kAXTrustedCheckOptionPrompt').value
        key = objc.objc_object(c_void_p=address)
        options = NSDictionary.dictionaryWithObject_forKey_(True, key)
        return bool(self.lib.AXIsProcessTrustedWithOptions(C.c_void_p(objc.pyobjc_id(options))))
