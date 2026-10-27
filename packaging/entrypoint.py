"""Single frozen entrypoint, including the background capture subprocess.

Dispatches on the first command-line argument: ``_capture`` starts the clipboard
capture subprocess, ``_self-test`` runs the bundle self-check, and any other
invocation starts the main application. The selected module's ``main`` result
becomes the process exit status.
"""
import multiprocessing
import sys

if __name__ == '__main__':
    multiprocessing.freeze_support()
    if len(sys.argv) > 1 and sys.argv[1] == '_capture':
        del sys.argv[1]
        from clipx.capture import main
    elif len(sys.argv) > 1 and sys.argv[1] == '_uninstall':
        del sys.argv[1]
        from clipx.uninstall import main
    elif len(sys.argv) > 1 and sys.argv[1] == '_self-test':
        del sys.argv[1]
        from clipx.bundle_check import main
    else:
        from clipx.main import main
    sys.exit(main())
