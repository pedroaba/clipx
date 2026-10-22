"""Small contracts shared by native integrations and the Qt application.

The protocols here describe the surface each operating-system adapter must
provide to the application: clipboard access, desktop activation and paste,
global shortcuts, and window effects. Implementations live under the
per-platform packages and report outcomes through `Result`/`Status`.
"""
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Callable, Protocol


class Status(StrEnum):
    """Outcome categories shared by native operations.

    Attributes:
        READY: The operation completed successfully.
        UNAVAILABLE: The underlying native capability is not available.
        ERROR: The operation failed for an unexpected reason.
        PERMISSION_REQUIRED: The user must grant an OS permission first.
    """

    READY = 'ready'
    UNAVAILABLE = 'unavailable'
    ERROR = 'error'
    PERMISSION_REQUIRED = 'permission_required'


@dataclass(frozen=True)
class Result:
    """Immutable outcome returned by native adapter operations.

    Attributes:
        status (Status): Category of the outcome; defaults to `Status.READY`.
        message (str): Human-readable detail, often empty on success.
    """

    status: Status = Status.READY
    message: str = ''

    @property
    def ok(self):
        """Return whether the result is `Status.READY`."""
        return self.status == Status.READY


class ClipboardDriver(Protocol):
    """Contract for background clipboard observation and text copying."""

    def listener_command(self, database: Path) -> list[str]:
        """Return the command line that starts the clipboard watcher process.

        Args:
            database (Path): Path to the history database the watcher writes to.

        Returns:
            list[str]: Executable and arguments for the watcher subprocess.
        """
        ...

    def write_text(self, text: str) -> Result:
        """Copy text to the system clipboard.

        Args:
            text (str): Text to place on the clipboard.

        Returns:
            Result: `Status.READY` on success, otherwise the failure reason.
        """
        ...

    def start_observation(self, capture, stopped, report: Callable[[Result], None]):
        """Run the clipboard observation loop until `stopped` is set.

        Args:
            capture: Capture sink providing ``reset()`` and ``save(text)``.
            stopped: Threading event whose ``is_set()``/``wait()`` stop the loop.
            report (Callable[[Result], None]): Callback for status changes.
        """
        ...

    def stop_observation(self):
        """Ask a running observation loop to stop."""
        ...


class DesktopDriver(Protocol):
    """Contract for remembering an app and pasting into it."""

    def remember_target(self):
        """Remember the frontmost application as the future paste target."""
        ...

    def open_search(self, window, activation_token: str = ''):
        """Bring the search window to the front and focus it.

        Args:
            window: Qt window to show and activate.
            activation_token (str): Platform-specific activation hint.
        """
        ...

    def paste_to_previous(self, callback: Callable[[Result], None] | None = None) -> Result:
        """Paste the clipboard contents into the remembered application.

        Args:
            callback (Callable[[Result], None] | None): Optional receiver for
                asynchronous completion; when provided the call may return
                before the paste finishes.

        Returns:
            Result: Immediate outcome, or a pending success when a callback
            will report the final status.
        """
        ...


class GlobalShortcutDriver(Protocol):
    """Contract for registering and persisting one global hotkey."""

    def to_binding(self, sequence: str) -> str:
        """Validate and normalize a user-facing shortcut sequence.

        Args:
            sequence (str): Shortcut in Qt portable notation.

        Returns:
            str: Normalized binding, or an empty string when unset.
        """
        ...

    def from_binding(self, binding: str) -> str:
        """Convert a stored binding back into a shortcut sequence.

        Args:
            binding (str): Stored platform binding.

        Returns:
            str: Normalized sequence, or an empty string when unset.
        """
        ...

    def start(self, callback: Callable[[], None]):
        """Start listening and register the stored shortcut.

        Args:
            callback (Callable[[], None]): Invoked when the shortcut fires.
        """
        ...

    def stop(self):
        """Unregister the shortcut, disconnect callbacks, and release natives."""
        ...

    def read(self) -> str:
        """Return the currently configured shortcut sequence."""
        ...

    def write(self, sequence: str):
        """Persist and activate a new shortcut sequence.

        Args:
            sequence (str): Shortcut in Qt portable notation; empty disables it.
        """
        ...

    def pause(self) -> str:
        """Temporarily release the shortcut while recording a new one.

        Returns:
            str: The sequence that was active before pausing.
        """
        ...

    def resume(self, sequence: str):
        """Re-register the shortcut after recording.

        Args:
            sequence (str): Sequence to restore; currently the stored value wins.
        """
        ...

    def recover(self):
        """Restore registrations lost after an OS-level interruption."""
        ...


class WindowEffects(Protocol):
    """Contract for adding and removing native window materials."""

    def apply(self, window) -> bool:
        """Apply the native effect to a window.

        Args:
            window: Qt window whose native handle is decorated.

        Returns:
            bool: True when a native material is active.
        """
        ...

    def remove(self, window):
        """Remove any native material previously applied to the window.

        Args:
            window: Qt window to restore.
        """
        ...
