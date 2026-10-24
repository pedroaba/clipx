"""Release contracts, streamed downloads and application-lifetime update state."""
import hashlib
import io
import json
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
import urllib.error

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QCoreApplication, QEvent
from clipx.updates import (Cancelled, LATEST_URL, UpdateError, UpdateService,
                           HTTPSRedirect, checksum_for, download_release, parse_release, version_tuple, tls_context)
from clipx.update_install import (macos_transaction, prepare_install, PreparedInstall,
                                  launch_install, native_environment)
from clipx.ui.organisms.update_page import UpdatePage


def release_data(version='0.10.0'):
    """Construct the same four artifact names and manifests as the release job."""
    names = []
    for arch in ('amd64', 'arm64'):
        names += [f'ClipX-{version}-macos-{arch}.dmg', f'clipx_{version}_{arch}.deb',
                  f'SHA256SUMS-macos-{arch}.txt', f'SHA256SUMS-linux-{arch}.txt']
    return {'tag_name': 'v' + version, 'draft': False, 'prerelease': False,
            'assets': [{'name': name, 'size': 7,
                        'browser_download_url': f'https://github.com/pedroaba/clipx/releases/download/v{version}/{name}'}
                       for name in names]}


class ReleaseContractTests(unittest.TestCase):
    def test_numeric_versions_and_four_artifacts(self):
        self.assertGreater(version_tuple('0.10.0'), version_tuple('v0.9.0'))
        for system in ('linux', 'darwin'):
            for arch in ('amd64', 'arm64'):
                release = parse_release(release_data(), system, arch)
                self.assertIn(arch, release.filename)
                self.assertTrue(release.filename.endswith('.dmg' if system == 'darwin' else '.deb'))
                self.assertIn(arch, release.checksum_url)
        for invalid in ('1.0.0rc1', '1.0', None, 'v1.0.0/../x'):
            with self.assertRaises(UpdateError):
                version_tuple(invalid)

    def test_missing_incompatible_and_untrusted_release_assets(self):
        for mutate in (
            lambda data: data.update(prerelease=True),
            lambda data: data.update(draft=True),
            lambda data: data.update(assets=[]),
            lambda data: data.update(assets=data['assets'][:2]),
            lambda data: data['assets'][1].update(browser_download_url='http://github.com/asset'),
            lambda data: data['assets'][1].update(browser_download_url='https://example.com/asset'),
        ):
            data = release_data()
            mutate(data)
            with self.assertRaises(UpdateError):
                parse_release(data, 'linux', 'amd64')

    def test_unique_manifest_entry_required(self):
        line = ('a' * 64 + '  installer.deb\n').encode()
        self.assertEqual(checksum_for(line, 'installer.deb'), 'a' * 64)
        for manifest in (b'', line + line, b'invalid  installer.deb'):
            with self.assertRaises(UpdateError):
                checksum_for(manifest, 'installer.deb')

    def test_https_redirect_never_downgrades_transport(self):
        import urllib.request
        request = urllib.request.Request('https://github.com/asset')
        with self.assertRaises(UpdateError):
            HTTPSRedirect().redirect_request(request, None, 302, 'redirect', {}, 'http://example.com/asset')

    def test_frozen_linux_falls_back_to_system_ca_without_disabling_tls(self):
        context = Mock()
        context.get_ca_certs.return_value = []
        with patch('clipx.updates.ssl.create_default_context', return_value=context), patch('clipx.updates.sys.platform', 'linux'), patch('pathlib.Path.is_file', return_value=True):
            self.assertIs(tls_context(), context)
        context.load_verify_locations.assert_called_once_with(cafile='/etc/ssl/certs/ca-certificates.crt')

    def test_download_verification_size_cancellation_and_partial_cleanup(self):
        release = parse_release(release_data(), 'linux', 'amd64')
        content = b'fixture'
        manifest = (hashlib.sha256(content).hexdigest() + '  ' + release.filename).encode()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            for payload in (b'wrong!!', b'short', b'oversized'):
                with patch('clipx.updates.read_small', return_value=manifest), patch('clipx.updates.open_url', return_value=io.BytesIO(payload)):
                    with self.assertRaises(UpdateError):
                        download_release(release, path, threading.Event(), Mock())
                self.assertEqual(list(path.iterdir()), [])
            cancel = threading.Event()
            cancel.set()
            with patch('clipx.updates.read_small', return_value=manifest):
                with self.assertRaises(Cancelled):
                    download_release(release, path, cancel, Mock())
            with patch('clipx.updates.read_small', return_value=manifest), patch('clipx.updates.open_url', return_value=io.BytesIO(content)):
                progress = Mock()
                saved = download_release(release, path, threading.Event(), progress)
                self.assertEqual(saved.read_bytes(), content)
                self.assertIn(((7, 7), {}), progress.call_args_list)
                self.assertEqual(progress.call_args_list[-1].args, (-1, 7))


class UpdateServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.service = UpdateService()
        self.service.current_version = '0.9.0'
        self.addCleanup(self.service.shutdown)
        self.addCleanup(self.service.deleteLater)

    def wait(self):
        end = time.monotonic() + 5
        while self.service.worker is not None and time.monotonic() < end:
            self.app.processEvents()
            time.sleep(.005)
        self.app.processEvents()
        self.assertIsNone(self.service.worker)

    def test_check_serialized_and_state_survives_page_destruction(self):
        gate = threading.Event()
        def read(url):
            gate.wait(2)
            return json.dumps(release_data()).encode()
        with patch('clipx.updates.read_small', side_effect=read) as fetch:
            page = UpdatePage(self.service)
            self.assertEqual(fetch.call_count, 0)
            self.service.check()
            self.assertFalse(page.check.isEnabled())
            worker = self.service.worker
            self.service.check()
            self.assertIs(self.service.worker, worker)
            page.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            gate.set()
            self.wait()
            page = UpdatePage(self.service)
            self.assertEqual(self.service.state, 'available')
            self.assertIn('0.10.0', page.status.text())
            self.assertTrue(self.service.last_check)
            self.assertEqual(fetch.call_count, 1)
            page.deleteLater()

    def test_helper_result_is_only_consumed_by_explicit_startup(self):
        with patch('clipx.update_install.read_install_result', return_value='Atualização instalada. O ClipX foi reiniciado.') as read:
            service = UpdateService()
            read.assert_not_called()
            service.restore_install_result()
            self.assertEqual(service.state, 'installed')
            read.assert_called_once_with()
            service.deleteLater()

    def test_current_and_newer_local_versions_never_offer_downgrade(self):
        for version in ('0.10.0', '1.0.0'):
            self.service.current_version = version
            with patch('clipx.updates.read_small', return_value=json.dumps(release_data()).encode()):
                self.service.check()
                self.wait()
            self.assertEqual(self.service.state, 'current')
            self.service.download(install=True)
            self.assertIsNone(self.service.worker)
            self.service.set_state('error', 'Não foi possível abrir as notas da versão.')
            self.service.download(install=True)
            self.assertIsNone(self.service.worker)
            self.assertFalse(self.service.update_available)

    def test_http_and_connection_failures_are_distinct(self):
        for error, expected in (
            (urllib.error.HTTPError(LATEST_URL, 404, 'missing', {}, None), 'Nenhuma release'),
            (urllib.error.HTTPError('https://github.com/asset', 404, 'missing', {}, None), 'instalador ou checksum'),
            (urllib.error.HTTPError('url', 429, 'rate', {}, None), 'Limite'),
            (urllib.error.URLError('offline'), 'conectar'),
            (ValueError('bad json'), 'inválida'),
        ):
            with patch('clipx.updates.read_small', side_effect=error):
                self.service.check()
                self.wait()
            self.assertEqual(self.service.state, 'error')
            self.assertIn(expected, self.service.message)

    def test_save_is_verified_and_source_install_is_rejected(self):
        self.service.release = parse_release(release_data(), 'linux', 'amd64')
        self.service.state = 'available'
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / 'installer.deb'
            def download(release, work, cancelled, progress):
                path = work / release.filename
                path.write_bytes(b'fixture')
                return path
            with patch('clipx.updates.download_release', side_effect=download):
                self.service.download(destination)
                self.wait()
            self.assertEqual(destination.read_bytes(), b'fixture')
            self.assertEqual(self.service.state, 'downloaded')
            self.service.download(install=True)
            self.assertEqual(self.service.state, 'error')
            self.assertIsNone(self.service.worker)

    def test_cancel_during_validation_does_not_launch_installer(self):
        self.service.release = parse_release(release_data(), 'linux', 'amd64')
        self.service.state = 'available'
        self.service.install_reason = ''
        gate = threading.Event()
        started = threading.Event()
        def prepare(*args):
            started.set()
            gate.wait(2)
            return Mock()
        ready = Mock()
        self.service.install_ready.connect(ready)
        with patch('clipx.updates.download_release', return_value=Path('/fake/installer')), patch('clipx.update_install.prepare_install', side_effect=prepare):
            self.service.download(install=True)
            self.assertTrue(started.wait(2))
            self.service.cancel()
            gate.set()
            self.wait()
        self.assertEqual(self.service.state, 'available')
        ready.assert_not_called()


class NativeInstallTests(unittest.TestCase):
    def test_system_tools_do_not_inherit_frozen_library_paths(self):
        with patch.dict(os.environ, {'LD_LIBRARY_PATH': '/bundle', 'LD_LIBRARY_PATH_ORIG': '/original', 'DYLD_LIBRARY_PATH': '/bundle'}, clear=True):
            environment = native_environment()
            self.assertEqual(environment['LD_LIBRARY_PATH'], '/original')
            self.assertNotIn('DYLD_LIBRARY_PATH', environment)
            self.assertEqual(os.environ['LD_LIBRARY_PATH'], '/bundle')

    def test_deb_validation_checks_installed_package_and_metadata(self):
        with tempfile.TemporaryDirectory() as folder, patch('clipx.update_install.sys.platform', 'linux'), patch('clipx.update_install.sys.executable', '/opt/clipx/clipx'), patch('clipx.update_install.architecture', return_value='amd64'):
            artifact = Path(folder) / 'a package.deb'
            for installed, fields in (('installed arm64', 'clipx\n0.10.0\namd64'), ('installed amd64', 'other\n0.10.0\namd64'), ('installed amd64', 'clipx\n0.9.0\namd64')):
                with patch('clipx.update_install.run_checked', side_effect=[installed, fields]):
                    with self.assertRaises(UpdateError):
                        prepare_install(artifact, '0.10.0', folder)
            with patch('clipx.update_install.run_checked', side_effect=['installed amd64', 'clipx\n0.10.0\namd64']):
                prepared = prepare_install(artifact, '0.10.0', folder)
            command = prepared.transaction.read_text()
            self.assertIn('/usr/bin/pkexec /usr/bin/apt-get', command)
            self.assertIn("'" + str(artifact.resolve()) + "'", command)
            self.assertEqual(prepared.restart, ('/usr/bin/clipx', 'tray'))

    def test_failed_helper_launch_does_not_quit_application(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            prepared = PreparedInstall(root, root / 'result', ('/fake/clipx', 'tray'), root / 'transaction')
            with patch('PyQt6.QtCore.QProcess.startDetached', return_value=(False, 0)):
                with self.assertRaises(UpdateError):
                    launch_install(prepared)

    def test_detached_helper_is_copied_from_bundled_scripts(self):
        """The installed script is copied intact before launching independently."""
        source = Path(__file__).resolve().parents[1] / 'clipx/scripts/updates/supervisor.sh'
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            prepared = PreparedInstall(root, root / 'result', ('/fake/clipx', 'tray'), root / 'transaction')
            with patch('PyQt6.QtCore.QProcess.startDetached', return_value=(True, 123)):
                launch_install(prepared)
            self.assertEqual((root / 'supervisor.sh').read_bytes(), source.read_bytes())
            self.assertEqual((root / 'supervisor.sh').stat().st_mode & 0o777, 0o700)

    def test_supervisor_records_result_and_restarts_as_original_user(self):
        template = Path(__file__).resolve().parents[1] / 'clipx/scripts/updates/supervisor.sh'
        for success in (True, False):
            with tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                work = root / 'work with spaces'
                work.mkdir()
                transaction = work / 'transaction.sh'
                transaction.write_text('exit ' + ('0' if success else '1'))
                restart = root / 'restart.sh'
                marker = root / 'restarted'
                restart.write_text('printf done > "$1"\n')
                result = root / 'result.txt'
                subprocess.run(['/bin/sh', template, '99999999', work, result, transaction, '', '/bin/sh', restart, marker], check=True)
                end = time.monotonic() + 2
                while not marker.exists() and time.monotonic() < end:
                    time.sleep(.01)
                self.assertTrue(marker.exists())
                self.assertFalse(work.exists())
                self.assertIn('Atualização instalada' if success else 'Não foi possível', result.read_text())

    @unittest.skipUnless(sys.platform == 'darwin', 'requires native codesign and PlistBuddy')
    def test_macos_replacement_and_rollback_use_real_signed_temporary_bundles(self):
        for succeeds in (True, False):
            with tempfile.TemporaryDirectory(prefix='clipx-replace-') as folder:
                root = Path(folder)
                current = root / 'Installed ClipX.app'
                staged = root / 'New ClipX.app'
                for app, version, exit_code in ((current, '0.9.0', 0), (staged, '0.10.0', 0 if succeeds else 1)):
                    (app / 'Contents/MacOS').mkdir(parents=True)
                    # Re-signing copied Apple platform binaries can be rejected by
                    # AMFI on older macOS runners. Build an ordinary app executable.
                    subprocess.run(['cc', '-x', 'c', '-', '-o', str(app / 'Contents/MacOS/clipx')],
                                   input=f'int main(void) {{ return {exit_code}; }}\n',
                                   text=True, check=True, capture_output=True)
                    with (app / 'Contents/Info.plist').open('wb') as stream:
                        plistlib.dump({'CFBundleIdentifier': 'org.clipx.ClipX', 'CFBundleVersion': version,
                                       'CFBundleShortVersionString': version, 'CFBundleExecutable': 'clipx', 'CFBundlePackageType': 'APPL'}, stream)
                    subprocess.run(['codesign', '--force', '--deep', '--sign', '-', str(app)], check=True, capture_output=True)
                script = macos_transaction(staged, current, '0.10.0', root)
                result = subprocess.run(['/bin/sh', script], capture_output=True, text=True)
                self.assertEqual(result.returncode == 0, succeeds, result.stderr)
                with (current / 'Contents/Info.plist').open('rb') as stream:
                    self.assertEqual(plistlib.load(stream)['CFBundleShortVersionString'], '0.10.0' if succeeds else '0.9.0')
                self.assertEqual(list(root.glob('.clipx-update.*')), [])


if __name__ == '__main__':
    unittest.main()
