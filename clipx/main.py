"""Command-line entry points for the ClipX GUI and clipboard daemon.

The CLI exposes the desktop overlay (``gui``/``show``), tray mode, the standalone
clipboard daemon, and lightweight history commands (``add`` and ``clear``).
"""

import argparse
import os
import signal
import sys

# Prevent Qt from querying deprecated GNOME 50+ xsettings keys
if sys.platform == "linux":
    os.environ["QT_QPA_PLATFORMTHEME"] = "generic"

from clipx.daemon import ClipboardDaemon, run_standalone_daemon
from clipx.detector import ContentDetector
from clipx.storage import Storage


def run_gui(start_hidden=False):
    """Run the Qt desktop application, tray, and background capture daemon.

    The function resolves the platform backend, acquires the single-instance
    lock, builds the main window and tray, and then hands control to the Qt
    event loop. Shutdown hooks stop the daemon, shortcuts, desktop backend, and
    window effects when the application quits.

    Args:
        start_hidden (bool): If True, start in the tray without opening search.

    Raises:
        RuntimeError: If running on macOS older than version 14.
        SystemExit: With the exit code returned by the Qt event loop.
    """
    # Save it before QApplication initializes the platform plugin in this process.
    from clipx.platforms import get_platform
    platform = get_platform()
    if platform.name == "macos":
        import platform as system_platform
        if tuple(int(part) for part in system_platform.mac_ver()[0].split(".")[:1]) < (14,):
            raise RuntimeError("O ClipX requer macOS 14 ou superior.")
    platform.paths.migrate_legacy()
    activation_token = platform.desktop.activation_token() if not start_hidden else ""
    from PyQt6.QtCore import QTimer, Qt
    from PyQt6.QtWidgets import QApplication
    from clipx.instance import DesktopInstance
    from clipx.ui.controllers.tray import ClipXTray
    from clipx.ui.pages.clipboard import ClipXMainWindow

    # Optimize for Wayland / X11
    if not os.environ.get("QT_QPA_PLATFORM"):
        if platform.name == "linux" and os.environ.get("WAYLAND_DISPLAY"):
            os.environ["QT_QPA_PLATFORM"] = "wayland;xcb"

    app = QApplication(sys.argv)
    from clipx.ui.foundations.branding import app_icon
    app.setWindowIcon(app_icon())
    app.setApplicationName("ClipX")
    app.setDesktopFileName("clipx")
    app.setQuitOnLastWindowClosed(False)
    if platform.name == "macos" and app.platformName() not in ("offscreen", "minimal"):
        import AppKit
        AppKit.NSApplication.sharedApplication().setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)

    instance = DesktopInstance()
    if not instance.acquire(show=not start_hidden, activation_token=activation_token):
        return

    storage = Storage()

    window = ClipXMainWindow(storage=storage, platform=platform)
    tray = ClipXTray(storage, window, app)
    instance.listen(tray.open_search)
    tray.show()
    if not start_hidden:
        tray.open_search(activation_token=activation_token)

    try:
        platform.shortcuts.start(tray.open_search)
    except (OSError, RuntimeError, ValueError) as exc:
        from clipx.platforms.base import Result, Status
        window.show_result(Result(Status.UNAVAILABLE, f"Atalho global indisponível: {exc}"))
    daemon = ClipboardDaemon(storage=storage, driver=platform.clipboard)
    daemon.status_changed.connect(tray.set_capture_status, Qt.ConnectionType.QueuedConnection)
    tray.set_capture_status(daemon.status)
    daemon.start_background()
    app.aboutToQuit.connect(daemon.stop)
    app.aboutToQuit.connect(tray.hide)
    app.aboutToQuit.connect(instance.close)
    app.aboutToQuit.connect(platform.shortcuts.stop)
    app.aboutToQuit.connect(lambda: platform.effects.remove(window))
    if hasattr(platform.desktop, "stop"):
        app.aboutToQuit.connect(platform.desktop.stop)

    # Let Python handle termination signals while Qt owns the event loop.
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    signal.signal(signal.SIGTERM, lambda *_: app.quit())
    signal_timer = QTimer(app)
    signal_timer.timeout.connect(lambda: None)
    signal_timer.start(250)

    exit_code = app.exec()
    sys.exit(exit_code)


def main():
    """Parse command-line arguments and dispatch to the requested command.

    With no subcommand, the GUI overlay is opened. ``tray`` starts hidden,
    ``daemon`` runs the standalone clipboard listener, ``add`` stores text in
    history, and ``clear`` deletes history items.

    Raises:
        SystemExit: If argument parsing fails, the platform is unsupported, or
            the invoked command exits the process.
    """
    parser = argparse.ArgumentParser(
        description="ClipX - A modern Raycast-styled clipboard history manager for Linux and macOS"
    )
    from clipx import __version__
    parser.add_argument("--version", action="version", version="ClipX " + __version__)
    subparsers = parser.add_subparsers(dest="command")

    # Command: gui (default)
    subparsers.add_parser("gui", help="Open the ClipX GUI overlay (default)")
    subparsers.add_parser("show", help="Alias for gui")
    subparsers.add_parser("tray", help="Start in the system tray without opening search")

    # Command: daemon
    subparsers.add_parser("daemon", help="Run the background clipboard monitoring daemon")

    # Command: add
    add_parser = subparsers.add_parser("add", help="Add text directly to history")
    add_parser.add_argument("text", help="Text to add to clipboard history")

    # Command: clear
    clear_parser = subparsers.add_parser("clear", help="Clear clipboard history")
    clear_parser.add_argument(
        "--all", action="store_true", help="Clear all items including pinned items"
    )

    args = parser.parse_args()
    if sys.platform not in ("linux", "darwin"):
        parser.error("Sistema não suportado. Use Linux ou macOS 14+.")

    if args.command == "daemon":
        run_standalone_daemon()
    elif args.command == "tray":
        run_gui(start_hidden=True)
    elif args.command == "add":
        storage = Storage()
        detection = ContentDetector.detect(args.text)
        clip_id = storage.add_clip(args.text, clip_type=detection.clip_type, language=detection.language)
        print(f"Clip #{clip_id} added successfully.")
    elif args.command == "clear":
        storage = Storage()
        storage.clear_history(keep_pinned=not args.all)
        print("History cleared.")
    else:
        # Default action is to show GUI
        run_gui()


if __name__ == "__main__":
    main()
