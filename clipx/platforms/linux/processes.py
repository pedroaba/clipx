"""Environment isolation for Linux clipboard and input helper processes."""
import os


def helper_environment():
    """Copy the session environment without one-shot desktop launch tokens."""
    environment = os.environ.copy()
    environment.pop('DESKTOP_STARTUP_ID', None)
    environment.pop('XDG_ACTIVATION_TOKEN', None)
    return environment
