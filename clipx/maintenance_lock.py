"""Per-user maintenance barrier and verified process registrations.

Writers take a shared lease; maintenance takes an exclusive lease. Capture
observers stay alive while their writes are paused, retaining native sequence
counters so resuming cannot recapture the unchanged clipboard.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import fcntl
import json
import os
import stat
import subprocess
import time
import signal

_exclusive = ContextVar('clipx_maintenance', default=False)
_registered_pid = ContextVar('clipx_registered_pid', default=None)


class MaintenanceBusy(OSError):
    """Another process is updating, writing, or maintaining ClipX."""


def runtime_directory():
    from clipx.platforms.paths import PlatformPaths
    # XDG_RUNTIME_DIR is shared with other applications. Use a private child.
    paths = PlatformPaths()
    directory = paths.runtime
    if paths.platform == 'linux' and os.environ.get('XDG_RUNTIME_DIR'):
        directory = directory / 'clipx-maintenance'
        directory.mkdir(mode=0o700, exist_ok=True)
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise OSError('Diretório de manutenção do ClipX não é privado.')
    return directory


def _open_lease(exclusive=False, timeout=0):
    deadline = time.monotonic() + timeout
    while True:
        path = runtime_directory() / 'maintenance.lock'
        try:
            fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        except FileNotFoundError:
            continue
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise OSError('Lock de manutenção inválido.')
            while True:
                try:
                    fcntl.flock(fd, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB)
                    break
                except BlockingIOError as exc:
                    if time.monotonic() >= deadline:
                        raise MaintenanceBusy('ClipX ocupado. Aguarde a operação atual e tente novamente.') from exc
                    time.sleep(0.025)
            # Uninstall can remove its final empty lock. Never use a lease on an
            # unlinked inode while a new application has created a replacement.
            try:
                current = path.lstat()
            except FileNotFoundError:
                os.close(fd)
                continue
            if (info.st_dev, info.st_ino) != (current.st_dev, current.st_ino):
                os.close(fd)
                continue
            return fd
        except BaseException:
            os.close(fd)
            raise


@contextmanager
def activity(exclusive=False, timeout=0):
    """Acquire a lease; only the exclusive owner may nest writes."""
    if _exclusive.get():
        yield
        return
    fd = _open_lease(exclusive, timeout)
    token = _exclusive.set(True) if exclusive else None
    try:
        yield
    finally:
        if token is not None:
            _exclusive.reset(token)
        os.close(fd)


def writer(function):
    @wraps(function)
    def guarded(*args, **kwargs):
        with activity():
            return function(*args, **kwargs)
    return guarded


@contextmanager
def inherited_activity():
    """Shared lease inherited by an OS-only update supervisor until it exits."""
    fd = _open_lease()
    try:
        yield fd
    finally:
        os.close(fd)


def capture_event(function):
    @wraps(function)
    def guarded(*args, **kwargs):
        try:
            with activity():
                return function(*args, **kwargs)
        except MaintenanceBusy:
            return None
    return guarded


def process_identity(pid):
    """Include OS start time and uid to reject stale/reused process IDs."""
    result = subprocess.run(['ps', '-p', str(pid), '-o', 'uid=,stat=,lstart='],
                            capture_output=True, text=True, timeout=5)
    fields = result.stdout.strip().split(None, 2)
    if result.returncode or len(fields) != 3 or fields[1].startswith('Z'):
        return ''
    return fields[0] + ' ' + fields[2]


@contextmanager
def registered_process():
    if _registered_pid.get() == os.getpid():
        yield
        return
    with activity():
        path = runtime_directory() / f'process-{os.getpid()}.json'
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump({'pid': os.getpid(), 'identity': process_identity(os.getpid())}, stream)
    token = _registered_pid.set(os.getpid())
    try:
        yield
    finally:
        _registered_pid.reset(token)
        path.unlink(missing_ok=True)


def stop_registered(exclude=(), timeout=10):
    """Stop only current-user registered processes with matching start times."""
    waiting = []
    for path in runtime_directory().glob('process-*.json'):
        try:
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
                continue
            record = json.loads(path.read_text())
            pid = int(record['pid'])
            identity = record['identity']
            if pid <= 1 or pid in (*exclude, os.getpid()):
                continue
            current = process_identity(pid)
            if not current or current != identity or current.split()[0] != str(os.getuid()):
                path.unlink(missing_ok=True)
                continue
            os.kill(pid, signal.SIGTERM)
            waiting.append((pid, identity))
        except (ProcessLookupError, FileNotFoundError):
            path.unlink(missing_ok=True)
        except (KeyError, ValueError, TypeError):
            raise OSError('Registro de processo inválido; encerramento cancelado.')
    deadline = time.monotonic() + timeout
    while waiting:
        waiting = [(pid, identity) for pid, identity in waiting if process_identity(pid) == identity]
        if waiting and time.monotonic() >= deadline:
            raise OSError('Não foi possível encerrar o ClipX. Nenhum dado foi apagado.')
        if waiting:
            time.sleep(0.1)


def wait_for_process_exit(pid, identity, timeout=15):
    """Require the original GUI to exit, even if its registration is missing.

    Never signal a PID supplied by the caller. The GUI requests its own orderly
    Qt shutdown once the independent progress window is ready.
    """
    if pid <= 1 or not identity or identity.split()[0] != str(os.getuid()):
        raise OSError('Identidade da instância original inválida; nenhum dado foi apagado.')
    deadline = time.monotonic() + timeout
    while process_identity(pid) == identity:
        if time.monotonic() >= deadline:
            raise OSError('O ClipX original continua aberto. A desinstalação foi cancelada antes de apagar dados.')
        time.sleep(0.05)


def cleanup_runtime():
    """Final uninstall step, while holding the exclusive lease."""
    from clipx.platforms.paths import PlatformPaths
    runtime = runtime_directory()
    for path in runtime.glob('process-*.json'):
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            continue
        record = json.loads(path.read_text())
        if not process_identity(int(record['pid'])):
            path.unlink(missing_ok=True)
    desktop_runtime = PlatformPaths().runtime
    for name in (f'clipx-{os.getuid()}', f'clipx-{os.getuid()}.lock'):
        path = desktop_runtime / name
        if path.exists() or path.is_symlink():
            if path.lstat().st_uid != os.getuid():
                raise OSError('Arquivo de runtime pertence a outra conta.')
            path.unlink()
    # No destructive work may follow removal of the barrier.
    (runtime / 'maintenance.lock').unlink(missing_ok=True)
    try:
        runtime.rmdir()
    except OSError:
        pass  # Never delete unknown files or the shared XDG runtime directory.
