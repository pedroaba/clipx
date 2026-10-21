"""Linux clipboard tools and event worker selection."""
import os
import shutil
import subprocess
import sys
from clipx.processes import module_command
from clipx.platforms.base import Result, Status

def copy_to_clipboard(text: str) -> bool:
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
    def __init__(self):
        self._stopped = None

    def listener_command(self, database):
        capture = module_command("clipx.capture", database)
        if os.environ.get("DISPLAY"):
            return capture + ["--watch-x11"]
        return ["wl-paste", "--type", "text", "--watch", *capture]

    def write_text(self, text):
        if copy_to_clipboard(text):
            return Result()
        return Result(Status.ERROR, "Não foi possível copiar. Verifique wl-copy/xclip e a sessão gráfica.")

    def start_observation(self, capture, stopped, report):
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
        if self._stopped is not None:
            self._stopped.set()
