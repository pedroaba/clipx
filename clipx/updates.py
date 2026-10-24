"""Manual GitHub release checks and verified downloads, independent of widgets.

Only the worker touches the network or runs platform validation commands. One
application-owned service survives preferences dialogs and serializes operations.
"""
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import ssl
import sys
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request

from PyQt6.QtCore import QObject, QThread, pyqtSignal
from PyQt6.QtWidgets import QApplication

from clipx import __version__

REPOSITORY = 'pedroaba/clipx'
LATEST_URL = f'https://api.github.com/repos/{REPOSITORY}/releases/latest'
MAX_METADATA = 2 * 1024 * 1024
MAX_INSTALLER = 1024 * 1024 * 1024


class UpdateError(Exception):
    """An actionable, user-facing update failure."""


class Cancelled(Exception):
    """The user cancelled an operation before installation."""


def version_tuple(value):
    """Parse the exact stable version format accepted by the release builder."""
    if not isinstance(value, str) or not re.fullmatch(r'v?\d+\.\d+\.\d+', value):
        raise UpdateError('A versão informada não usa MAJOR.MINOR.PATCH.')
    return tuple(map(int, value.removeprefix('v').split('.')))


def architecture():
    """Use the running process architecture, including translated Intel apps."""
    machine = platform.machine().lower()
    if machine in ('arm64', 'aarch64'):
        return 'arm64'
    if machine in ('amd64', 'x86_64'):
        return 'amd64'
    raise UpdateError('Não há instalador para esta arquitetura.')


def release_url(value):
    """Accept only release asset URLs belonging to this repository."""
    if not isinstance(value, str):
        raise UpdateError('Endereço de download inválido.')
    url = urllib.parse.urlsplit(value)
    if (url.scheme != 'https' or url.netloc != 'github.com'
            or not url.path.startswith(f'/{REPOSITORY}/releases/download/')
            or url.query or url.fragment):
        raise UpdateError('Endereço de download inválido.')
    return value


@dataclass(frozen=True)
class Release:
    """The compatible installer and checksum manifest from a stable release."""
    version: str
    notes_url: str
    filename: str
    download_url: str
    checksum_url: str
    size: int


def parse_release(data, system=None, arch=None):
    """Validate release metadata and select one of the four shipped installers."""
    system = system or sys.platform
    arch = arch or architecture()
    if not isinstance(data, dict) or data.get('draft') or data.get('prerelease'):
        raise UpdateError('Resposta de release estável inválida.')
    tag = data.get('tag_name')
    version_tuple(tag)
    version = tag.removeprefix('v')
    if system not in ('darwin', 'linux') or arch not in ('amd64', 'arm64'):
        raise UpdateError('Não há instalador compatível com este sistema.')
    target = 'macos' if system == 'darwin' else 'linux'
    filename = f'ClipX-{version}-macos-{arch}.dmg' if system == 'darwin' else f'clipx_{version}_{arch}.deb'
    assets = data.get('assets')
    if not isinstance(assets, list) or not all(isinstance(a, dict) for a in assets):
        raise UpdateError('Lista de instaladores inválida.')
    matches = [a for a in assets if a.get('name') == filename]
    manifests = [a for a in assets if a.get('name') == f'SHA256SUMS-{target}-{arch}.txt']
    if len(matches) != 1:
        raise UpdateError('A versão publicada não contém um instalador compatível.')
    if len(manifests) != 1:
        raise UpdateError('A versão publicada não contém o checksum do instalador.')
    asset = matches[0]
    size = asset.get('size')
    if type(size) is not int or not 0 < size <= MAX_INSTALLER:
        raise UpdateError('Tamanho de instalador inválido.')
    return Release(version, f'https://github.com/{REPOSITORY}/releases/tag/{tag}',
                   filename, release_url(asset.get('browser_download_url')),
                   release_url(manifests[0].get('browser_download_url')), size)


class HTTPSRedirect(urllib.request.HTTPRedirectHandler):
    """Do not permit transport downgrade during GitHub/CDN redirects."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme != 'https':
            raise UpdateError('O servidor redirecionou para uma conexão insegura.')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def tls_context():
    """Use the distro CA bundle when uv's compiled-in paths are absent frozen."""
    context = ssl.create_default_context()
    system_bundle = Path('/etc/ssl/certs/ca-certificates.crt')
    if sys.platform == 'linux' and not context.get_ca_certs() and system_bundle.is_file():
        context.load_verify_locations(cafile=str(system_bundle))
    return context


def open_url(url):
    """Open a bounded HTTPS request using the system certificate store."""
    request = urllib.request.Request(url, headers={
        'User-Agent': f'ClipX/{__version__}', 'Accept': 'application/vnd.github+json' if url == LATEST_URL else '*/*',
        'X-GitHub-Api-Version': '2022-11-28',
    })
    opener = urllib.request.build_opener(HTTPSRedirect(), urllib.request.HTTPSHandler(context=tls_context()))
    return opener.open(request, timeout=15)


def read_small(url):
    """Reject oversized metadata rather than retaining an unbounded response."""
    with open_url(url) as response:
        result = response.read(MAX_METADATA + 1)
    if len(result) > MAX_METADATA:
        raise UpdateError('Resposta do servidor maior que o permitido.')
    return result


def checksum_for(manifest, filename):
    """Require one unambiguous SHA-256 entry for the selected asset."""
    values = []
    for line in manifest.decode('utf-8').splitlines():
        match = re.fullmatch(r'([0-9a-fA-F]{64}) [ *](.+)', line)
        if match and match[2] == filename:
            values.append(match[1].lower())
    if len(values) != 1:
        raise UpdateError('Checksum ausente ou inválido para este instalador.')
    return values[0]


def download_release(release, folder, cancelled, progress):
    """Stream a verified installer into a private directory; remove partials."""
    target = Path(folder) / release.filename
    partial = target.with_suffix(target.suffix + '.part')
    try:
        expected = checksum_for(read_small(release.checksum_url), release.filename)
        if cancelled.is_set():
            raise Cancelled()
        digest = hashlib.sha256()
        received = 0
        with open_url(release.download_url) as response, partial.open('xb') as output:
            while True:
                if cancelled.is_set():
                    raise Cancelled()
                block = response.read(128 * 1024)
                if not block:
                    break
                received += len(block)
                if received > release.size:
                    raise UpdateError('O tamanho do download diverge da release.')
                output.write(block)
                digest.update(block)
                progress(received, release.size)
        if cancelled.is_set():
            raise Cancelled()
        progress(-1, release.size)  # Validation is a distinct UI state.
        if received != release.size or digest.hexdigest() != expected:
            raise UpdateError('O checksum do instalador não confere. Tente baixar novamente.')
        partial.replace(target)
        return target
    finally:
        partial.unlink(missing_ok=True)


class UpdateWorker(QThread):
    """One interruptible network/validation job; signals never touch widgets."""
    result = pyqtSignal(object)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()
    progress = pyqtSignal(object, object)

    def __init__(self, action, parent=None):
        super().__init__(parent)
        self.action = action
        self.stop_event = threading.Event()

    def run(self):
        try:
            self.result.emit(self.action(self.stop_event, self.progress.emit))
        except Cancelled:
            self.cancelled.emit()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                message = ('Nenhuma release pública disponível.' if exc.url == LATEST_URL else
                           'O instalador ou checksum não está mais disponível. Verifique as atualizações novamente.')
            elif exc.code in (403, 429):
                message = 'Limite de consultas do GitHub atingido. Tente mais tarde.'
            else:
                message = f'O servidor não pôde concluir a solicitação (HTTP {exc.code}).'
            exc.close()
            self.failed.emit(message)
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            self.failed.emit('Não foi possível conectar ao GitHub. Verifique a conexão e tente novamente.')
        except (ValueError, KeyError, TypeError, UnicodeError):
            self.failed.emit('Resposta de atualização inválida.')
        except Exception as exc:
            self.failed.emit(str(exc) if isinstance(exc, (UpdateError, OSError)) else 'Não foi possível concluir a atualização.')


class UpdateService(QObject):
    """Application-lifetime state shared by the tray and preferences page."""
    changed = pyqtSignal()
    install_ready = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_version = __version__
        self.state = 'idle'
        self.message = 'Verifique se há uma nova versão do ClipX.'
        self.last_check = ''
        self.release = None
        self.received = self.total = 0
        self.worker = None
        self.folder = None
        self.installer = None
        self.prepared = None
        self.install_reason = self._install_reason()
        self.install_result = ''

    def restore_install_result(self):
        """Read the previous helper outcome only during a real GUI startup."""
        from clipx.update_install import read_install_result
        self.install_result = read_install_result()
        if self.install_result:
            self.set_state('installed' if self.install_result.startswith('Atualização instalada.') else 'error',
                           self.install_result)

    @staticmethod
    def _install_reason():
        if not getattr(sys, 'frozen', False):
            return 'Execução pelo código: baixe o instalador para instalar a nova versão.'
        if sys.platform == 'darwin':
            executable = Path(sys.executable).resolve()
            if executable.parent.name != 'MacOS' or executable.parents[2].suffix != '.app':
                return 'A instalação integrada requer um bundle ClipX.app.'
            if str(executable).startswith('/Volumes/'):
                return 'Arraste o ClipX para Applications antes de atualizar pelo aplicativo.'
            return ''
        if sys.platform == 'linux' and Path(sys.executable).resolve() == Path('/opt/clipx/clipx'):
            if all(shutil.which(tool) for tool in ('apt-get', 'dpkg-query', 'dpkg-deb', 'pkexec')):
                return ''
        return 'Instalação integrada indisponível neste ambiente. Baixe o instalador.'

    @property
    def busy(self):
        return self.worker is not None or self.state in ('checking', 'downloading', 'validating', 'installing')

    @property
    def update_available(self):
        """Keep the no-downgrade invariant independent of transient UI errors."""
        if self.release is None:
            return False
        try:
            return version_tuple(self.release.version) > version_tuple(self.current_version)
        except UpdateError:
            return False

    def set_state(self, state, message):
        self.state, self.message = state, message
        self.changed.emit()

    def _start(self, action, completed):
        self.worker = UpdateWorker(action, self)
        self.worker.result.connect(completed)
        self.worker.failed.connect(lambda message: self.set_state('error', message))
        self.worker.cancelled.connect(lambda: self.set_state('available', 'Download cancelado. Você pode tentar novamente.'))
        self.worker.progress.connect(self._progress)
        self.worker.finished.connect(self._finished)
        self.worker.start()
        self.changed.emit()

    def _finished(self):
        self.worker.deleteLater()
        self.worker = None
        self.changed.emit()
        if self.state == 'ready':
            self.install_ready.emit()

    def check(self):
        if self.busy:
            return
        self.release = None
        self._clean_download()
        self.last_check = datetime.now().astimezone().strftime('%d/%m/%Y às %H:%M')
        self.set_state('checking', 'Verificando atualizações…')
        def action(cancelled, progress):
            data = json.loads(read_small(LATEST_URL))
            return parse_release(data)
        self._start(action, self._checked)

    def _checked(self, release):
        self.last_check = datetime.now().astimezone().strftime('%d/%m/%Y às %H:%M')
        self.release = release
        try:
            newer = version_tuple(release.version) > version_tuple(self.current_version)
        except UpdateError:
            self.release = None
            self.set_state('error', 'Não foi possível determinar a versão instalada. Instale uma versão empacotada do ClipX.')
            return
        self.set_state('available' if newer else 'current',
                       f'ClipX {release.version} disponível.' if newer else 'Você está usando a versão mais recente disponível para esta instalação.')

    def download(self, destination=None, install=False):
        if self.busy or not self.update_available:
            return
        if install and self.install_reason:
            self.set_state('error', self.install_reason)
            return
        self._clean_download()
        self.folder = Path(tempfile.mkdtemp(prefix='clipx-update-'))
        self.received = 0
        self.total = self.release.size
        self.set_state('downloading', 'Baixando instalador…')
        def action(cancelled, progress):
            installer = download_release(self.release, self.folder, cancelled, progress)
            if install:
                from clipx.update_install import prepare_install
                prepared = prepare_install(installer, self.release.version, self.folder)
                if cancelled.is_set():
                    raise Cancelled()
                return installer, prepared
            if cancelled.is_set():
                raise Cancelled()
            if destination:
                # Replace only after a complete, verified copy on the destination filesystem.
                destination_path = Path(destination)
                fd, temporary = tempfile.mkstemp(prefix='.clipx-', dir=destination_path.parent)
                try:
                    with os.fdopen(fd, 'wb') as output, installer.open('rb') as source:
                        shutil.copyfileobj(source, output)
                    if cancelled.is_set():
                        raise Cancelled()
                    os.replace(temporary, destination_path)
                finally:
                    Path(temporary).unlink(missing_ok=True)
                return destination_path, None
            return installer, None
        def completed(result):
            self.installer, self.prepared = result
            self.set_state('ready' if install else 'downloaded',
                           'Instalador validado. Pronto para reiniciar.' if install else 'Instalador salvo. Abra o arquivo para concluir a instalação.')
        self._start(action, completed)

    def _progress(self, received, total):
        if received < 0:
            self.set_state('validating', 'Validando instalador…')
        else:
            self.received, self.total = received, total
            self.changed.emit()

    def cancel(self):
        if self.worker and self.state in ('downloading', 'validating'):
            self.worker.stop_event.set()
            self.message = 'Cancelando download…'
            self.changed.emit()

    def launch_install(self):
        if self.busy or not self.prepared:
            return
        from clipx.update_install import launch_install
        try:
            launch_install(self.prepared)
        except (OSError, UpdateError) as exc:
            self.set_state('error', str(exc))
            return
        self.set_state('installing', 'Encerrando o ClipX para instalar a atualização…')
        # The detached helper owns the staging directory from this point onward.
        self.folder = None
        QApplication.instance().quit()

    def defer_install(self):
        self.set_state('available', 'Atualização adiada. Suas configurações foram preservadas.')

    def _clean_download(self):
        if self.folder:
            shutil.rmtree(self.folder, ignore_errors=True)
        self.folder = self.installer = self.prepared = None

    def shutdown(self):
        if self.worker:
            self.worker.stop_event.set()
            self.worker.wait()  # Requests have a finite socket timeout.
        if self.state != 'installing':
            self._clean_download()


def update_service():
    """Return the singleton, creating it lazily without making network requests."""
    app = QApplication.instance()
    if not hasattr(app, '_clipx_updates'):
        app._clipx_updates = UpdateService(app)
        app.aboutToQuit.connect(app._clipx_updates.shutdown)
    return app._clipx_updates
