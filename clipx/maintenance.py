"""Explicit, scoped history maintenance without opening or migrating Storage."""
from contextlib import closing
from dataclasses import dataclass, field
import os
from pathlib import Path
import sqlite3
import stat

from clipx.maintenance_lock import activity
from clipx.platforms.paths import PlatformPaths


@dataclass(frozen=True)
class PruneOptions:
    target: str = 'all'
    mode: str = 'orphans'
    include_pinned: bool = False

    def __post_init__(self):
        if self.target not in ('data', 'images', 'all') or self.mode not in ('orphans', 'content'):
            raise ValueError('Categoria ou comportamento inválido.')
        if self.include_pinned and self.mode != 'content':
            raise ValueError('Incluir fixados só é permitido ao apagar conteúdo.')


@dataclass
class MaintenanceResult:
    items: int = 0
    files: int = 0
    bytes: int = 0
    errors: list[str] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)

    @property
    def ok(self):
        return not self.errors

    def summary(self, estimate=False):
        prefix = 'Estimativa: ' if estimate else 'Resultado: '
        items = 'item' if self.items == 1 else 'itens'
        files = 'arquivo' if self.files == 1 else 'arquivos'
        text = f'{prefix}{self.items} {items}, {self.files} {files}, {self.bytes:,} bytes'
        text += ' recuperáveis.' if estimate else ' recuperados.'
        if self.errors:
            text += '\nFalhas:\n' + '\n'.join(self.errors)
        return text


def validate_path(path, allow_root=False):
    """Reject symlink ancestors, foreign ownership and special-file targets."""
    path = Path(os.path.abspath(path))
    if path == Path(path.anchor) or path == Path.home():
        raise OSError('O alvo não pode ser uma pasta geral do usuário ou do sistema.')
    for ancestor in (*reversed(path.parents), path):
        if ancestor in (Path('/tmp'), Path('/var'), Path('/etc')) and ancestor.is_symlink() and ancestor.lstat().st_uid == 0 and ancestor.resolve() == Path('/private') / ancestor.name:
            continue
        if ancestor.is_symlink():
            raise OSError(f'Link simbólico não permitido: {ancestor}')
    if path.exists():
        info = path.lstat()
        if info.st_uid not in ((os.getuid(), 0) if allow_root else (os.getuid(),)) or not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
            raise OSError(f'Alvo sem propriedade segura: {path}')
    return path


class MaintenanceService:
    def __init__(self, database=None):
        self.database = Path(database) if database is not None else PlatformPaths().data / 'history.db'
        self.database = self.database.absolute()
        self.images = self.database.parent / 'images'

    def _connect(self, readonly=False):
        validate_path(self.database)
        connection = sqlite3.connect(self.database.as_uri() + ('?mode=ro' if readonly else '?mode=rw'), uri=True, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _tables(conn):
        return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    def _selection(self, conn, options):
        if options.mode != 'content':
            return []
        where = '1=1' if options.include_pinned else 'is_pinned = 0'
        if options.target == 'data':
            where += " AND type != 'image'"
        elif options.target == 'images':
            where += " AND type = 'image'"
        return conn.execute(f'SELECT id, type, content FROM clips WHERE {where}').fetchall()

    def _image_candidates(self, conn, selected):
        selected_ids = {row['id'] for row in selected}
        retained = {row['content'] for row in conn.execute("SELECT id, content FROM clips WHERE type='image'")
                    if row['id'] not in selected_ids}
        candidates = []
        if 'managed_images' in self._tables(conn):
            for row in conn.execute('SELECT path FROM managed_images'):
                path = Path(row[0])
                # Never adopt unknown files or paths stored outside our image directory.
                if path.parent == self.images and str(path) not in retained:
                    candidates.append((path, True))
        validate_path(self.images)
        if self.images.is_dir():
            candidates.extend((path, False) for path in self.images.glob('.capture-*') if str(path) not in retained)
        return candidates

    def inspect(self, options=PruneOptions()):
        result = MaintenanceResult()
        if not self.database.exists():
            return result
        result.paths.append(str(self.database))
        with closing(self._connect(readonly=True)) as conn:
            conn.execute('BEGIN')
            selected = self._selection(conn, options)
            result.items = len(selected)
            if options.target in ('images', 'all'):
                for path, _ in self._image_candidates(conn, selected):
                    try:
                        validate_path(path)
                        if path.is_file():
                            result.files += 1
                            result.bytes += path.stat().st_size
                            result.paths.append(str(path))
                    except OSError as exc:
                        result.errors.append(str(exc))
            if options.target in ('data', 'all'):
                result.bytes += conn.execute('PRAGMA freelist_count').fetchone()[0] * conn.execute('PRAGMA page_size').fetchone()[0]
        return result

    def prune(self, options=PruneOptions(), progress=lambda message: None):
        result = MaintenanceResult()
        with activity(exclusive=True, timeout=5):
            if not self.database.exists():
                return result
            progress('Captura pausada. Recalculando os itens…')
            with closing(self._connect()) as conn:
                selected = self._selection(conn, options)
                candidates = self._image_candidates(conn, selected) if options.target in ('images', 'all') else []
                # Commit rows first. Failure here leaves every image untouched.
                with conn:
                    conn.executemany('DELETE FROM clips WHERE id = ?', [(row['id'],) for row in selected])
                result.items = len(selected)
                progress('Liberando imagens próprias sem referências…')
                for path, registered in candidates:
                    try:
                        validate_path(path)
                        size = path.stat().st_size if path.exists() else 0
                        if path.exists():
                            if not path.is_file():
                                raise OSError(f'Imagem não é arquivo regular: {path}')
                            path.unlink()
                            result.files += 1
                            result.bytes += size
                        if registered:
                            with conn:
                                conn.execute('DELETE FROM managed_images WHERE path = ?', (str(path),))
                    except (OSError, sqlite3.Error) as exc:
                        result.errors.append(f'{path}: {exc}')
                if options.target in ('data', 'all'):
                    progress('Compactando o banco de dados…')
                    def database_size():
                        return sum(path.stat().st_size for path in (self.database, Path(str(self.database) + '-wal')) if path.exists())
                    before = database_size()
                    try:
                        if conn.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()[0]:
                            raise sqlite3.OperationalError('Banco em uso por outro leitor; tente novamente.')
                        conn.execute('VACUUM')
                        if conn.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()[0]:
                            raise sqlite3.OperationalError('Banco em uso por outro leitor; tente novamente.')
                        result.bytes += max(0, before - database_size())
                    except sqlite3.Error as exc:
                        result.errors.append(f'Compactação: {exc}')
        progress('Limpeza concluída.' if result.ok else 'Limpeza concluída com falhas.')
        return result
