"""Platform paths and non-destructive import of pre-portability macOS data.

`PlatformPaths` resolves the data, configuration, and runtime directories for
the current platform. On macOS it can also import history and settings written
by older releases under XDG-style directories, copying them atomically into the
native locations without overwriting existing files.
"""
from contextlib import closing
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
from clipx.maintenance_lock import writer


class PlatformPaths:
    """Resolve ClipX directories for a platform and home directory.

    Attributes:
        platform (str): Platform identifier used for all path decisions.
        home (Path): Home directory that anchors the macOS paths.
    """

    def __init__(self, platform=None, home=None):
        """Initialize the resolver.

        Args:
            platform (str | None): Platform identifier such as ``'darwin'`` or
                ``'linux'``. Defaults to `sys.platform`.
            home (str | Path | None): Home directory override. Defaults to
                `Path.home()`.
        """
        self.platform = platform or sys.platform
        self.home = Path(home) if home else Path.home()
        self._explicit_home = home is not None

    @property
    def data(self):
        """Return the directory holding persistent data.

        Returns:
            Path: ``~/Library/Application Support/ClipX`` on macOS, otherwise
            ``$XDG_DATA_HOME/clipx`` or ``~/.local/share/clipx``.
        """
        if self.platform == 'darwin':
            return self.home / 'Library/Application Support/ClipX'
        return Path(os.environ.get('XDG_DATA_HOME', self.home / '.local/share')) / 'clipx'

    @property
    def config(self):
        """Return the directory holding configuration files.

        Returns:
            Path: ``~/Library/Preferences/ClipX`` on macOS, otherwise
            ``$XDG_CONFIG_HOME/clipx`` or ``~/.config/clipx``.
        """
        if self.platform == 'darwin':
            return self.home / 'Library/Preferences/ClipX'
        return Path(os.environ.get('XDG_CONFIG_HOME', self.home / '.config')) / 'clipx'

    @property
    def runtime(self):
        """Return a private directory for runtime files such as sockets.

        Returns:
            Path: `$XDG_RUNTIME_DIR` on Linux when set; otherwise a ``0700``
            directory under ``/tmp`` named after the current user ID.

        Raises:
            RuntimeError: If the fallback directory is a symlink, is owned by
                another user, or is readable or writable by group or others.
        """
        if self.platform == 'linux' and os.environ.get('XDG_RUNTIME_DIR'):
            return Path(os.environ['XDG_RUNTIME_DIR'])
        # Unix-domain socket paths are limited to ~104 bytes on macOS.
        folder = Path("/tmp") / f'clipx-runtime-{os.getuid()}'
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = folder.lstat()
        if folder.is_symlink() or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise RuntimeError('Diretório de runtime do ClipX não é privado.')
        return folder

    @writer
    def migrate_legacy(self):
        """Import macOS history and settings written by older releases.

        Only runs on macOS. For each legacy file, an existing destination is
        left untouched. The database is copied with the SQLite backup API so
        committed WAL contents survive, other files are copied directly. A
        ``.pre-migration.bak`` copy with ``0600`` permissions is created before
        the destination is linked into place atomically, so a concurrent launch
        cannot be overwritten.
        """
        if self.platform != 'darwin':
            return
        legacy_data = self.home / '.local/share'
        legacy_config = self.home / '.config'
        if not self._explicit_home:
            legacy_data = Path(os.environ.get('XDG_DATA_HOME', legacy_data))
            legacy_config = Path(os.environ.get('XDG_CONFIG_HOME', legacy_config))
        for old, new, database in (
            (legacy_data / 'clipx/history.db', self.data / 'history.db', True),
            (legacy_config / 'clipx/settings.json', self.config / 'settings.json', False),
        ):
            if not old.is_file() or new.exists():
                continue
            new.parent.mkdir(parents=True, exist_ok=True)
            handle, filename = tempfile.mkstemp(prefix='.migration-', dir=new.parent)
            os.close(handle)
            temporary = Path(filename)
            try:
                if database:
                    # SQLite backup includes committed data in a WAL, unlike copying the file.
                    with closing(sqlite3.connect(old)) as source, closing(sqlite3.connect(temporary)) as target:
                        source.backup(target)
                else:
                    shutil.copyfile(old, temporary)
                backup = new.with_name(new.name + '.pre-migration.bak')
                if not backup.exists():
                    shutil.copyfile(temporary, backup)
                    backup.chmod(0o600)
                try:
                    # Link atomically, without overwriting another launch's migration.
                    os.link(temporary, new)
                except FileExistsError:
                    pass
            finally:
                temporary.unlink(missing_ok=True)
