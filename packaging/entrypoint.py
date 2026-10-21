"""Single frozen entrypoint, including the background capture subprocess."""
import multiprocessing
import sys

if __name__ == '__main__':
    multiprocessing.freeze_support()
    if len(sys.argv) > 1 and sys.argv[1] == '_capture':
        del sys.argv[1]
        from clipx.capture import main
    elif len(sys.argv) > 1 and sys.argv[1] == '_self-test':
        del sys.argv[1]
        from clipx.bundle_check import main
    else:
        from clipx.main import main
    sys.exit(main())
