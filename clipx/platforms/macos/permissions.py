"""Read/request Accessibility trust through the public ApplicationServices API."""
import ctypes as C


class MacOSPermissions:
    def __init__(self):
        self.lib = C.CDLL('/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices')
        self.lib.AXIsProcessTrusted.argtypes = []
        self.lib.AXIsProcessTrusted.restype = C.c_bool
        self.lib.AXIsProcessTrustedWithOptions.argtypes = [C.c_void_p]
        self.lib.AXIsProcessTrustedWithOptions.restype = C.c_bool

    def can_paste(self):
        return bool(self.lib.AXIsProcessTrusted())

    def request_paste(self):
        import objc
        from Foundation import NSDictionary
        address = C.c_void_p.in_dll(self.lib, 'kAXTrustedCheckOptionPrompt').value
        key = objc.objc_object(c_void_p=address)
        options = NSDictionary.dictionaryWithObject_forKey_(True, key)
        return bool(self.lib.AXIsProcessTrustedWithOptions(C.c_void_p(objc.pyobjc_id(options))))
