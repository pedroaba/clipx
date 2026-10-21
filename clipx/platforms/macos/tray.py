"""Work around Qt's unsafe menu-tracking activation on macOS 27.

Qt 6.11's QStatusItemDelegate calls NSEvent.clickCount for the current event
when NSMenuDidBeginTrackingNotification fires. macOS 27 can deliver a
KitDefined event here, whose clickCount raises an Objective-C exception.

An attached context menu already supplies all user actions. Suppress only
this redundant activation callback; preserve the native menu and its actions.
See qtbase/src/plugins/platforms/cocoa/qcocoasystemtrayicon.mm, emitActivated.
"""
_installed = False
_replacement = None


def _menu_began_tracking(delegate, notification):
    # A tracking notification is not a mouse event. Never inspect its clickCount.
    return None


def install_menu_tracking_guard():
    global _installed, _replacement
    if _installed:
        return
    import objc
    delegate_class = objc.lookUpClass('QStatusItemDelegate')
    if not hasattr(delegate_class, 'statusItemMenuBeganTracking_'):
        raise RuntimeError('A versão do Qt não oferece o callback esperado para proteger o menu da bandeja.')
    _replacement = objc.selector(_menu_began_tracking,
        selector=b'statusItemMenuBeganTracking:', signature=b'v@:@')
    objc.classAddMethods(delegate_class, [_replacement])
    _installed = True
