"""Maintenance safety with isolated homes, databases and fake native operations."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import json
import io
from contextlib import redirect_stdout
from types import SimpleNamespace
from pathlib import Path
import plistlib
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from clipx.capture import ClipboardCapture
from clipx.maintenance import MaintenanceService, PruneOptions
from clipx.maintenance_lock import activity, inherited_activity, MaintenanceBusy, registered_process, stop_registered
from clipx.maintenance_lock import wait_for_process_exit, process_identity
from clipx.platforms.paths import PlatformPaths
from clipx.storage import Storage
from clipx.uninstall import data_roots, execute, inventory, installation


class MaintenanceFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.runtime = self.root / 'runtime'
        self.runtime.mkdir(mode=0o700)
        self.addCleanup(patch.stopall)
        patch('clipx.maintenance_lock.runtime_directory', return_value=self.runtime).start()
        (self.root / 'data').mkdir()
        self.storage = Storage(self.root / 'data/history.db')
        self.service = MaintenanceService(self.storage.db_path)


class MaintenanceTests(MaintenanceFixture):
    def seed(self):
        text = self.storage.add_clip('text')
        pinned = self.storage.add_clip('keep me')
        self.storage.toggle_pin(pinned)
        self.storage.images_dir.mkdir(exist_ok=True)
        image = self.storage.images_dir / 'owned.png'
        image.write_bytes(b'owned bytes')
        keep = self.storage.images_dir / 'pinned.png'
        keep.write_bytes(b'pinned bytes')
        external = self.root / 'original.png'
        external.write_bytes(b'original')
        unknown = self.storage.images_dir / 'unknown.png'
        unknown.write_bytes(b'unknown')
        with self.storage._get_connection(write=True, cleanup=False) as conn:
            conn.executemany('INSERT INTO managed_images VALUES (?, ?)', [('owned', str(image)), ('pinned', str(keep))])
            self.storage.add_clip(str(image), 'image', file_owner='managed', _connection=conn)
            pinned_image = self.storage.add_clip(str(keep), 'image', file_owner='managed', _connection=conn)
            conn.execute('UPDATE clips SET is_pinned=1 WHERE id=?', (pinned_image,))
        external_id = self.storage.add_clip(str(external), 'image', file_owner='external')
        return image, keep, external, unknown

    def orphan(self, name='orphan.png'):
        self.storage.images_dir.mkdir(exist_ok=True)
        path = self.storage.images_dir / name
        path.write_bytes(b'unreferenced')
        with self.storage._get_connection(write=True, cleanup=False) as conn:
            conn.execute('INSERT INTO managed_images VALUES (?, ?)', (name, str(path)))
        return path

    def test_all_six_combinations_preserve_scope_and_originals(self):
        for mode in ('orphans', 'content'):
            for target in ('data', 'images', 'all'):
                with self.subTest(mode=mode, target=target):
                    # Each combination uses a fresh fixture.
                    folder = self.root / f'{mode}-{target}'
                    folder.mkdir()
                    self.storage = Storage(folder / 'history.db')
                    self.service = MaintenanceService(self.storage.db_path)
                    image, keep, external, unknown = self.seed()
                    orphan = self.orphan()
                    before = self.service.inspect(PruneOptions(target, mode))
                    self.assertTrue(image.exists())
                    result = self.service.prune(PruneOptions(target, mode))
                    self.assertTrue(result.ok, result.errors)
                    clips = self.storage.get_clips()
                    self.assertEqual(len(clips), 5 - (1 if target in ('data', 'all') and mode == 'content' else 0)
                                     - (2 if target in ('images', 'all') and mode == 'content' else 0))
                    self.assertEqual(image.exists(), not (mode == 'content' and target in ('images', 'all')))
                    self.assertEqual(orphan.exists(), target == 'data')
                    self.assertTrue(keep.exists())
                    self.assertTrue(external.exists())
                    self.assertTrue(unknown.exists())

    def test_include_pinned_clears_all_selected_rows_only(self):
        image, keep, external, unknown = self.seed()
        result = self.service.prune(PruneOptions('images', 'content', True))
        self.assertTrue(result.ok)
        self.assertEqual(len(self.storage.get_clips()), 2)
        self.assertFalse(image.exists())
        self.assertFalse(keep.exists())
        self.assertTrue(external.exists())
        self.assertTrue(unknown.exists())

    def test_shared_image_survives_a_pinned_reference(self):
        image, keep, external, unknown = self.seed()
        # Legacy databases may contain multiple entries referring to one file.
        with self.storage._get_connection(write=True, cleanup=False) as conn:
            conn.execute("UPDATE clips SET content = ? WHERE type='image' AND is_pinned=1", (str(image),))
        self.assertTrue(self.service.prune(PruneOptions('images', 'content')).ok)
        self.assertTrue(image.exists())

    def test_orphan_records_missing_files_and_capture_temporary(self):
        orphan = self.orphan()
        missing = self.orphan('missing.png')
        missing.unlink()
        capture = self.storage.images_dir / '.capture-interrupted'
        capture.write_bytes(b'partial')
        self.assertEqual(self.service.inspect().files, 2)
        result = self.service.prune()
        self.assertTrue(result.ok)
        self.assertEqual(result.files, 2)
        self.assertFalse(capture.exists())
        with self.storage._get_connection() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM managed_images').fetchone()[0], 0)

    def test_missing_external_reference_is_preserved(self):
        self.storage.add_clip(str(self.root / 'missing-external.png'), 'image', file_owner='external')
        self.assertTrue(self.service.prune().ok)
        self.assertEqual(len(self.storage.get_clips()), 1)

    def test_file_failure_reports_partial_result_and_retry_reclaims_orphan(self):
        image, keep, external, unknown = self.seed()
        unlink = Path.unlink
        def fail(path, *args, **kwargs):
            if path == image:
                raise PermissionError('denied')
            return unlink(path, *args, **kwargs)
        with patch('pathlib.Path.unlink', fail):
            result = self.service.prune(PruneOptions('images', 'content'))
        self.assertFalse(result.ok)
        self.assertEqual(result.items, 2)
        self.assertTrue(image.exists())
        self.assertTrue(self.service.prune().ok)
        self.assertFalse(image.exists())

    def test_symlink_and_outside_registered_paths_cannot_delete_original(self):
        orphan = self.orphan()
        external = self.root / 'outside.png'
        external.write_bytes(b'precious')
        orphan.unlink()
        orphan.symlink_to(external)
        with self.storage._get_connection(write=True, cleanup=False) as conn:
            conn.execute('INSERT INTO managed_images VALUES (?, ?)', ('outside', str(external)))
        result = self.service.prune()
        self.assertFalse(result.ok)
        self.assertEqual(external.read_bytes(), b'precious')
        self.assertTrue(orphan.is_symlink())

    def test_readonly_inspection_and_no_database_do_not_create_data(self):
        missing = MaintenanceService(self.root / 'missing/history.db')
        self.assertTrue(missing.inspect().ok)
        self.assertTrue(missing.prune().ok)
        self.assertFalse(missing.database.parent.exists())
        self.seed()
        before = self.storage.db_path.read_bytes()
        self.service.inspect(PruneOptions('all', 'content', True))
        self.assertEqual(self.storage.db_path.read_bytes(), before)

    def test_settings_and_capture_observer_are_paused_by_external_barrier(self):
        from clipx.preferences import UISettings, DEFAULT_UI
        capture = ClipboardCapture(self.storage)
        # A subprocess holds the lock; no thread-context bypass is possible.
        program = 'import fcntl,sys; f=open(sys.argv[1],"a"); fcntl.flock(f,fcntl.LOCK_EX); print("ready",flush=True); sys.stdin.read()'
        process = subprocess.Popen([sys.executable, '-c', program, str(self.runtime / 'maintenance.lock')],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(process.stdout.readline().strip(), 'ready')
            with self.assertRaises(MaintenanceBusy):
                self.storage.add_clip('blocked')
            with self.assertRaises(MaintenanceBusy):
                UISettings(self.root / 'settings.json').save(DEFAULT_UI)
            capture.save('ignored during maintenance')
            self.assertEqual(self.storage.get_clips(), [])
        finally:
            process.communicate('done', timeout=5)
        capture.save('new event')
        self.assertEqual(self.storage.get_clips()[0].content, 'new event')

    def test_update_shared_lease_prevents_prune_and_exclusive_prevents_update(self):
        with inherited_activity():
            with self.assertRaises(MaintenanceBusy):
                with activity(exclusive=True):
                    pass
        # An exclusive lease in a different context must reject update launch.
        import contextvars
        with activity(exclusive=True):
            with self.assertRaises(MaintenanceBusy):
                contextvars.Context().run(lambda: inherited_activity().__enter__())

    def test_update_lease_survives_launcher_exit_until_child_finishes(self):
        with inherited_activity() as descriptor:
            process = subprocess.Popen([sys.executable, '-c', 'import sys; print("ready",flush=True); sys.stdin.read()'],
                                       pass_fds=(descriptor,), stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
            self.assertEqual(process.stdout.readline().strip(), 'ready')
        try:
            with self.assertRaises(MaintenanceBusy):
                with activity(exclusive=True):
                    pass
        finally:
            process.communicate('done', timeout=5)
        with activity(exclusive=True):
            pass

    def test_invalid_options_are_rejected(self):
        for arguments in [('unknown', 'orphans', False), ('all', 'unknown', False), ('all', 'orphans', True)]:
            with self.assertRaises(ValueError):
                PruneOptions(*arguments)

    def test_observer_consumes_paused_event_without_recapturing_on_resume(self):
        import contextvars
        from clipx.platforms.macos.clipboard import MacOSClipboardDriver, TEXT_TYPE
        class Board:
            count = 1
            def changeCount(self):
                return self.count
            def types(self):
                return [TEXT_TYPE]
            def stringForType_(self, kind):
                return 'clipboard content'
        board = Board()
        driver = MacOSClipboardDriver(board)
        capture = ClipboardCapture(self.storage)
        with activity(exclusive=True):
            contextvars.Context().run(lambda: driver.poll(capture))
        self.assertIsNone(driver.poll(capture))
        self.assertEqual(self.storage.get_clips(), [])
        board.count += 1
        driver.poll(capture)
        self.assertEqual(self.storage.get_clips()[0].content, 'clipboard content')

    def test_stale_process_registration_never_signals_reused_pid(self):
        record = self.runtime / 'process-456.json'
        record.write_text(json.dumps({'pid': 456, 'identity': 'old identity'}))
        with patch('clipx.maintenance_lock.process_identity', return_value='new identity'), patch('os.kill') as kill:
            stop_registered()
            kill.assert_not_called()
        self.assertFalse(record.exists())

    def test_cli_dry_run_and_noninteractive_confirmation(self):
        from clipx.main import run_maintenance
        from unittest.mock import Mock
        self.storage.add_clip('keep until confirmed')
        args = SimpleNamespace(command='prune', target='all', mode='content', include_pinned=False, dry_run=True, yes=False)
        parser = Mock()
        parser.error.side_effect = SystemExit(2)
        with patch('clipx.maintenance.MaintenanceService', return_value=self.service), redirect_stdout(io.StringIO()):
            self.assertEqual(run_maintenance(args, parser), 0)
            self.assertEqual(len(self.storage.get_clips()), 1)
            args.dry_run = False
            with patch('sys.stdin.isatty', return_value=False), self.assertRaises(SystemExit):
                run_maintenance(args, parser)
            self.assertEqual(len(self.storage.get_clips()), 1)
            args.yes = True
            self.assertEqual(run_maintenance(args, parser), 0)
            self.assertEqual(self.storage.get_clips(), [])

    def test_nested_process_registration_has_one_record(self):
        with registered_process():
            with registered_process():
                self.assertEqual(len(list(self.runtime.glob('process-*.json'))), 1)
        self.assertEqual(list(self.runtime.glob('process-*.json')), [])


class UninstallTests(MaintenanceFixture):
    # Keep destructive backend tests in a disposable macOS-style home on any OS.
    def paths(self):
        return PlatformPaths('darwin', home=self.root / 'home')

    def test_corrupt_current_legacy_backups_removed_and_reinstall_empty(self):
        paths = self.paths()
        for root in data_roots(paths):
            root.mkdir(parents=True, exist_ok=True)
            (root / 'history.db').write_bytes(b'corrupt')
            (root / 'history.db.pre-migration.bak').write_bytes(b'old secret')
        outside = paths.home / 'original.png'
        outside.write_bytes(b'precious')
        (paths.data / 'images').mkdir()
        (paths.data / 'images/link.png').symlink_to(outside)
        with patch('clipx.uninstall.clear_clipboard') as clear:
            result = execute(sys.executable, 'source', paths=paths, progress=lambda _: None)
        self.assertTrue(result.ok, result.errors)
        clear.assert_called_once()
        self.assertTrue(outside.exists())
        for root in data_roots(paths):
            self.assertFalse(root.exists())
        paths.migrate_legacy()
        paths.data.mkdir(parents=True)
        self.assertEqual(Storage(paths.data / 'history.db').get_clips(), [])

    def make_app(self):
        app = self.root / 'Applications/ClipX.app'
        (app / 'Contents/MacOS').mkdir(parents=True)
        executable = app / 'Contents/MacOS/clipx'
        executable.write_text('placeholder')
        with (app / 'Contents/Info.plist').open('wb') as stream:
            plistlib.dump({'CFBundleIdentifier': 'org.clipx.ClipX'}, stream)
        return app, executable

    def test_disposable_macos_bundle_is_removed_after_user_data(self):
        app, executable = self.make_app()
        paths = self.paths()
        paths.data.mkdir(parents=True)
        (paths.data / 'history.db').write_bytes(b'corrupt')
        with patch('clipx.uninstall.clear_clipboard'):
            result = execute(executable, 'macos', paths=paths, progress=lambda _: None)
        self.assertTrue(result.ok, result.errors)
        self.assertFalse(app.exists())
        self.assertFalse(paths.data.exists())

    def test_application_failure_explicitly_reports_data_already_deleted(self):
        app, executable = self.make_app()
        paths = self.paths()
        paths.data.mkdir(parents=True)
        with patch('clipx.uninstall.clear_clipboard'), patch('clipx.uninstall.remove_app', side_effect=PermissionError('authorization cancelled')):
            result = execute(executable, 'macos', paths=paths, progress=lambda _: None)
        self.assertFalse(result.ok)
        self.assertIn('dados foram apagados', result.errors[0])
        self.assertFalse(paths.data.exists())
        self.assertTrue(app.exists())

    def test_shutdown_timeout_prevents_data_deletion(self):
        paths = self.paths()
        paths.data.mkdir(parents=True)
        with patch('clipx.uninstall.stop_registered', side_effect=OSError('timeout')), patch('clipx.uninstall.clear_clipboard') as clear:
            with self.assertRaises(OSError):
                execute(sys.executable, 'source', paths=paths, progress=lambda _: None)
        self.assertTrue(paths.data.exists())
        clear.assert_not_called()

    def test_missing_registration_cannot_bypass_original_gui_shutdown(self):
        paths = self.paths()
        paths.data.mkdir(parents=True)
        with patch('clipx.uninstall.wait_for_process_exit', side_effect=OSError('original GUI still running')) as wait, patch('clipx.uninstall.clear_clipboard') as clear:
            with self.assertRaises(OSError):
                execute(sys.executable, 'source', paths=paths, parent_pid=123,
                        parent_identity=f'{os.getuid()} original', progress=lambda _: None)
        wait.assert_called_once_with(123, f'{os.getuid()} original')
        clear.assert_not_called()
        self.assertTrue(paths.data.exists())

    def test_original_pid_is_waited_without_signalling_or_relying_on_registry(self):
        process = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
        try:
            identity = process_identity(process.pid)
            with patch('os.kill') as kill:
                with self.assertRaises(OSError):
                    wait_for_process_exit(process.pid, identity, timeout=0)
                kill.assert_not_called()
            process.terminate()
            process.wait(timeout=5)
            wait_for_process_exit(process.pid, identity, timeout=0)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()

    def test_uninstall_rejects_symlink_root_and_foreign_bundle(self):
        paths = self.paths()
        paths.data.parent.mkdir(parents=True)
        paths.data.symlink_to(self.root / 'data')
        with self.assertRaises(OSError):
            inventory(paths=paths, kind='source')
        app, executable = self.make_app()
        (app / 'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier': 'other.app'}))
        with self.assertRaises(OSError):
            installation(executable, 'macos')

    def test_supervisor_cleans_success_and_preserves_failure_log(self):
        template = Path(__file__).resolve().parents[1] / 'clipx/scripts/maintenance/supervisor.sh'
        for code in (0, 1):
            folder = self.root / f'helper-{code}'
            folder.mkdir()
            result = subprocess.run(['/bin/sh', str(template), str(folder), 'cli', '/bin/sh', '-c', f'echo outcome; exit {code}'],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, code)
            self.assertIn('outcome', result.stdout)
            self.assertEqual(folder.exists(), code != 0)


if __name__ == '__main__':
    unittest.main()
