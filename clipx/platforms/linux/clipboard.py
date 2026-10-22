"""Linux clipboard writing and event-worker selection.

Writes text with ``wl-copy`` or ``xclip`` and chooses how clipboard changes are
observed: in-process through XFixes when an X11 ``DISPLAY`` exists, otherwise
through a ``wl-paste --watch`` helper process.
"""
import os
import shutil
import subprocess
import sys
from clipx.processes import module_command
from clipx.platforms.base import Result, Status


def copy_to_clipboard(text: str) -> bool:
    """Copy text using the first available Linux clipboard tool.

    Tries ``wl-copy`` and then ``xclip -selection clipboard``. Each tool runs
    with a two second timeout; a failing or hanging process is killed before the
    next tool is tried.

    Args:
        text (str): Text to place on the clipboard, encoded as UTF-8.

    Returns:
        bool: ``True`` if a tool exited successfully, otherwise ``False``.
    """
    for tool, args in (("wl-copy", []), ("xclip", ["-selection", "clipboard"])):
        if not shutil.which(tool):
            continue
        process = None
        try:
            process = subprocess.Popen([tool, *args], stdin=subprocess.PIPE)
            process.communicate(input=text.encode("utf-8"), timeout=2)
            if process.returncode == 0:
                return True
        except (OSError, subprocess.SubprocessError):
            if process is not None and process.poll() is None:
                process.kill()
                process.communicate()
    return False


class LinuxClipboardDriver:
    """Clipboard driver that selects an X11 or Wayland observation strategy.

    Attributes:
        _stopped (threading.Event | None): Stop event stored while an
            observation is running, so :meth:`stop_observation` can signal it.
    """
    def __init__(self):
        """Initialize the driver with no active observation."""
        self._stopped = None

    def listener_command(self, database):
        """Build the helper command that watches the clipboard.

        Args:
            database (str | os.PathLike): Path to the ClipX database passed to
                the capture module.

        Returns:
            list[str]: Command that runs the capture module directly, using the
                X11 watch flag when ``DISPLAY`` is set, or a
                ``wl-paste --watch`` command otherwise.
        """
        capture = module_command("clipx.capture", database)
        if os.environ.get("DISPLAY"):
            return capture + ["--watch-x11"]
        return ["wl-paste", "--type", "text", "--watch", *capture]

    def write_text(self, text):
        """Copy text to the system clipboard.

        Args:
            text (str): Text to copy.

        Returns:
            Result: Success, or an error result when no clipboard tool worked.
        """
        if copy_to_clipboard(text):
            return Result()
        return Result(Status.ERROR, "Não foi possível copiar. Verifique wl-copy/xclip e a sessão gráfica.")

    def start_observation(self, capture, stopped, report):
        """Watch the clipboard until the stop event is set.

        With ``DISPLAY`` set, an in-process :class:`X11ClipboardListener` is
        used. Otherwise a ``wl-paste --watch`` child process is spawned; if that
        process exits early, an ``UNAVAILABLE`` result is reported. A success
        result is reported once observation is established. The child process is
        terminated (then killed after a two second grace period) on exit.

        Args:
            capture (object): Capture sink exposing ``save`` and ``storage``.
            stopped (threading.Event): Event that ends observation when set.
            report (callable): Callback receiving :class:`Result` updates.
        """
        self._stopped = stopped
        if os.environ.get("DISPLAY"):
            from .capture import X11ClipboardListener
            listener = X11ClipboardListener(capture)
            try:
                report(Result())
                listener.run(stopped)
            finally:
                listener.close()
            return
        process = None
        try:
            process = subprocess.Popen(self.listener_command(capture.storage.db_path))
            report(Result())
            while not stopped.wait(0.25):
                if process.poll() is not None:
                    report(Result(Status.UNAVAILABLE, "Captura Wayland pausada: verifique data-control."))
                    return
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()

    def stop_observation(self):
        """Signal the stored stop event, if an observation is active."""
        if self._stopped is not None:
            self._stopped.set()
