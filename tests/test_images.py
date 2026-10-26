"""Image persistence, native payload routing and asynchronous preview regressions."""
import io
from contextlib import closing
import os
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PyQt6.QtCore import QThreadPool, Qt, QUrl
from PyQt6.QtGui import QImage, QColor
from PyQt6.QtWidgets import QApplication, QMessageBox
from clipx.capture import ClipboardCapture
from clipx.images import ImageError, MISSING_IMAGE, png_bytes, read_image
from clipx.platforms.base import Result, Status
from clipx.services import ClipboardService
from clipx.storage import Storage


def pixels(color='red', width=40):
    """Build encoded image content without fixtures or global clipboard access."""
    image = QImage(width, 20, QImage.Format.Format_RGBA8888)
    image.fill(QColor(color))
    return png_bytes(image)


class ImageTests(unittest.TestCase):
    """Test path identity, lifecycle, capture routing and copy failures."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.storage = Storage(self.root / 'history.db')
        self.capture = ClipboardCapture(self.storage)

    def external(self, name='photo.png', color='red'):
        path = self.root / name
        path.write_bytes(pixels(color))
        return path

    def test_migration_preserves_existing_history(self):
        self.storage.add_clip('old text')
        with closing(sqlite3.connect(self.storage.db_path)) as conn, conn:
            conn.execute('ALTER TABLE clips DROP COLUMN file_owner')
        migrated = Storage(self.storage.db_path)
        clip = migrated.get_clips()[0]
        self.assertEqual((clip.content, clip.file_owner), ('old text', None))
        migrated.add_image(self.external())
        self.assertEqual(len(migrated.get_clips()), 2)

    def test_external_path_is_not_duplicated_or_confused_with_text(self):
        path = self.external('photo with á space.dat')
        image_id = self.storage.add_image(path)
        self.storage.add_clip(str(path))
        self.storage.add_clip('image:' + str(path))
        self.storage.add_image(self.root / '.' / path.name)
        clips = self.storage.get_clips()
        self.assertEqual(len(clips), 3)
        image = next(c for c in clips if c.id == image_id)
        self.assertEqual((image.type, image.file_owner, image.content), ('image', 'external', str(path)))
        self.assertFalse(self.storage.images_dir.exists())
        self.assertTrue(all(isinstance(c.content, str) for c in clips))

    def test_raw_pixels_have_one_png_and_no_binary_database_payload(self):
        self.capture.save_image(pixels())
        self.capture.save_image(pixels())
        clips = self.storage.get_clips()
        self.assertEqual(len(clips), 1)
        clip = clips[0]
        self.assertEqual(clip.file_owner, 'managed')
        self.assertTrue(Path(clip.content).is_file())
        self.assertEqual(len(list(self.storage.images_dir.glob('*.png'))), 1)
        with closing(sqlite3.connect(self.storage.db_path)) as conn, conn:
            row = conn.execute('SELECT typeof(content), content FROM clips').fetchone()
        self.assertEqual(row, ('text', clip.content))

    def test_equal_pixels_with_different_encoding_deduplicate(self):
        image, _, _ = read_image(pixels())
        from PyQt6.QtCore import QBuffer, QIODevice
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, 'BMP')
        self.storage.add_image(pixels())
        self.storage.add_image(bytes(buffer.data()))
        self.assertEqual(len(self.storage.get_clips()), 1)

    def test_cleanup_never_adopts_or_deletes_unowned_files_in_image_folder(self):
        from clipx.images import image_digest
        self.storage.images_dir.mkdir()
        image, _, _ = read_image(pixels())
        original = self.storage.images_dir / (image_digest(image) + '.png')
        original.write_bytes(pixels())
        self.storage.add_image(pixels())
        managed = Path(self.storage.get_clips()[0].content)
        self.assertNotEqual(original, managed)
        self.storage.clear_history(keep_pinned=False)
        self.assertTrue(original.exists())
        self.assertFalse(managed.exists())

    def test_interrupted_reserved_image_is_reclaimed_at_next_start(self):
        orphan = self.storage.images_dir / ('0' * 64 + '.png')
        self.storage.images_dir.mkdir()
        orphan.write_bytes(pixels())
        with self.storage._get_connection() as conn:
            conn.execute('INSERT INTO managed_images VALUES (?, ?)', ('0' * 64, str(orphan)))
        Storage(self.storage.db_path)
        self.assertFalse(orphan.exists())

    def test_recapturing_pixels_repairs_a_modified_managed_png(self):
        image_id = self.storage.add_image(pixels())
        path = Path(self.storage.get_clips()[0].content)
        path.write_bytes(pixels('blue'))
        self.assertEqual(self.storage.add_image(pixels()), image_id)
        self.assertEqual(read_image(path)[0].pixelColor(0, 0), QColor('red'))

    def test_selection_creates_one_entry_per_valid_image(self):
        one = self.external()
        two = self.external('second.png', 'blue')
        other = self.root / 'document.txt'
        other.write_text('not an image')
        self.capture.save_files([str(one), str(two), str(other), str(one)])
        self.assertEqual({c.content for c in self.storage.get_clips()}, {str(one), str(two)})

    def test_uri_lists_decode_spaces_unicode_and_ignore_remote_uris(self):
        path = self.external('olá space.png')
        payload = '# comment\r\n' + QUrl.fromLocalFile(str(path)).toString() + '\r\nhttps://example.com/x.png\r\n'
        self.capture.save_mime('text/uri-list', payload.encode())
        self.assertEqual(self.storage.get_clips()[0].content, str(path))
        self.assertFalse(self.storage.images_dir.exists())

    def test_delete_and_clear_only_remove_owned_unreferenced_images(self):
        external = self.external()
        self.storage.add_image(external)
        image_id = self.storage.add_image(pixels('blue'))
        managed = Path(next(c.content for c in self.storage.get_clips() if c.id == image_id))
        self.storage.toggle_pin(image_id)
        self.storage.clear_history()
        self.assertTrue(managed.exists())
        self.assertTrue(external.exists())
        self.storage.delete_clip(image_id)
        self.assertFalse(managed.exists())
        self.assertTrue(external.exists())

    def test_pruning_releases_managed_png_but_keeps_pinned(self):
        pinned = self.storage.add_image(pixels('red'), max_history=1)
        self.storage.toggle_pin(pinned)
        discarded = self.storage.add_image(pixels('blue'), max_history=1)
        old_path = Path(next(c.content for c in self.storage.get_clips() if c.id == discarded))
        self.storage.add_image(pixels('green'), max_history=1)
        self.assertFalse(old_path.exists())
        self.assertEqual(len(self.storage.get_clips()), 2)
        self.assertTrue(Path(next(c.content for c in self.storage.get_clips() if c.id == pinned)).exists())

    def test_write_failure_never_inserts_a_dangling_row(self):
        with patch('clipx.storage.os.replace', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.storage.add_image(pixels())
        self.assertEqual(self.storage.get_clips(), [])
        self.assertEqual(list(self.storage.images_dir.iterdir()), [])

    def test_concurrent_capture_and_cleanup_keep_referenced_pngs(self):
        errors = []
        def write():
            try:
                for _ in range(5):
                    Storage(self.storage.db_path).add_image(pixels())
            except Exception as exc:
                errors.append(exc)
        threads = [threading.Thread(target=write) for _ in range(3)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(10)
        self.assertFalse(errors)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(len(self.storage.get_clips()), 1)
        self.assertTrue(Path(self.storage.get_clips()[0].content).is_file())

    def test_copy_reads_current_pixels_and_suppresses_capture_echo(self):
        path = self.external()
        self.storage.add_image(path)
        clip = self.storage.get_clips()[0]
        path.write_bytes(pixels('blue'))
        driver = Mock()
        driver.write_image.return_value = Result()
        service = ClipboardService(self.storage, driver)
        self.assertTrue(service.copy(clip).ok)
        data = driver.write_image.call_args.args[0]
        image, _, _ = read_image(data)
        self.assertEqual(image.pixelColor(0, 0), QColor('blue'))
        driver.write_text.assert_not_called()
        self.capture.save_image(data)
        self.assertEqual(len(self.storage.get_clips()), 1)
        self.assertFalse(self.storage.images_dir.exists())

    def test_missing_corrupt_and_permission_errors_do_not_write_or_reorder(self):
        path = self.external()
        self.storage.add_image(path)
        clip = self.storage.get_clips()[0]
        driver = Mock()
        service = ClipboardService(self.storage, driver)
        path.unlink()
        result = service.copy(clip)
        self.assertEqual((result.code, result.message), ('image_missing', MISSING_IMAGE))
        path.write_bytes(b'corrupt')
        self.assertFalse(service.copy(clip).ok)
        with patch('builtins.open', side_effect=PermissionError):
            result = service.copy(clip)
        self.assertEqual(result.code, 'image_permission')
        driver.write_image.assert_not_called()
        self.assertEqual(self.storage.get_clips()[0].updated_at, clip.updated_at)

    def test_failed_native_write_clears_echo_marker(self):
        self.storage.add_image(self.external())
        driver = Mock()
        driver.write_image.return_value = Result(Status.ERROR, 'failed')
        self.assertFalse(ClipboardService(self.storage, driver).copy(self.storage.get_clips()[0]).ok)
        image, _, _ = read_image(pixels())
        self.assertFalse(self.storage.is_image_echo(image))

    def test_sql_failure_rolls_back_row_and_reclaims_saved_png(self):
        with patch.object(self.storage, 'add_clip', side_effect=sqlite3.OperationalError('failed')):
            with self.assertRaises(sqlite3.OperationalError):
                self.storage.add_image(pixels())
        self.assertEqual(self.storage.get_clips(), [])
        self.assertEqual(list(self.storage.images_dir.iterdir()), [])

    def test_capture_and_cleanup_are_safe_across_processes(self):
        import subprocess
        import sys
        script = """
import sys
from clipx.storage import Storage
from PyQt6.QtGui import QImage, QColor
from clipx.images import png_bytes
image = QImage(10, 10, QImage.Format.Format_RGBA8888)
image.fill(QColor('red'))
s = Storage(sys.argv[1])
for i in range(3):
    s.add_image(png_bytes(image))
    s.add_clip(str(i))
"""
        processes = [subprocess.Popen([sys.executable, '-c', script, str(self.storage.db_path)],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(3)]
        for process in processes:
            _, error = process.communicate(timeout=15)
            self.assertEqual(process.returncode, 0, error.decode())
        images = self.storage.get_clips(filter_type='image')
        self.assertEqual(len(images), 1)
        self.assertTrue(Path(images[0].content).is_file())

    def test_linux_explicit_image_mime_and_failure(self):
        from clipx.platforms.linux.clipboard import LinuxClipboardDriver
        with patch.dict(os.environ, {'DISPLAY': ''}), patch('shutil.which', return_value='/bin/tool'), patch('subprocess.run') as run:
            run.return_value.returncode = 0
            self.assertTrue(LinuxClipboardDriver().write_image(b'png').ok)
            self.assertEqual(run.call_args.args[0], ['wl-copy', '--type', 'image/png'])
            self.assertEqual(run.call_args.kwargs['input'], b'png')
            run.side_effect = OSError('missing')
            self.assertFalse(LinuxClipboardDriver().write_image(b'png').ok)

    def test_macos_prefers_paths_over_pixels_and_never_reads_private_payload(self):
        from clipx.platforms.macos.clipboard import MacOSClipboardDriver
        board = Mock()
        board.changeCount.return_value = 1
        board.types.return_value = ['NSFilenamesPboardType', 'public.png']
        board.propertyListForType_.return_value = ['/tmp/photo.png', '/tmp/two.png']
        sink = Mock()
        driver = MacOSClipboardDriver(board)
        driver.poll(sink)
        sink.save_files.assert_called_once_with(['/tmp/photo.png', '/tmp/two.png'])
        sink.save_image.assert_not_called()
        board.dataForType_.assert_not_called()
        board.changeCount.return_value = 2
        board.types.return_value = ['org.nspasteboard.ConcealedType', 'public.png']
        driver.poll(sink)
        board.dataForType_.assert_not_called()

    def test_wayland_prefers_reference_and_discards_changed_clipboard(self):
        from clipx.platforms.linux.clipboard import capture_wayland_event
        stdin = SimpleNamespace(buffer=io.BytesIO(b'watch payload'))
        sink = Mock()
        responses = [b'image/png\ntext/uri-list\n', b'file:///tmp/photo.png', b'watch payload']
        with patch('sys.stdin', stdin), patch('subprocess.check_output', side_effect=responses):
            capture_wayland_event(sink)
        sink.save_mime.assert_called_once_with('text/uri-list', b'file:///tmp/photo.png')
        sink.reset_mock()
        stdin.buffer = io.BytesIO(b'old')
        with patch('sys.stdin', stdin), patch('subprocess.check_output', side_effect=[b'image/png\n', b'png', b'new']):
            capture_wayland_event(sink)
        sink.save_mime.assert_not_called()


class ImageWindowTests(unittest.TestCase):
    """Exercise the worker/UI boundary and themed failure dialog."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        from clipx.platforms.effects import OpaqueWindowEffects
        from clipx.shortcuts import ShortcutSettings
        from clipx.ui.pages.clipboard import ClipXMainWindow
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'photo.png'
        self.path.write_bytes(pixels())
        self.storage = Storage(self.root / 'history.db')
        self.storage.add_image(self.path)
        self.platform = SimpleNamespace(name='test', clipboard=Mock(), desktop=Mock(), effects=OpaqueWindowEffects())
        self.platform.clipboard.write_image.return_value = Result()
        self.window = ClipXMainWindow(self.storage, ShortcutSettings(self.root / 'settings.json'), self.platform)
        self.window.show()
        self.window.refresh_timer.stop()
        self.addCleanup(self.finish)

    def finish(self):
        QThreadPool.globalInstance().waitForDone(5000)
        self.app.processEvents()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def wait_for(self, condition):
        deadline = time.monotonic() + 5
        while not condition() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.005)
        self.assertTrue(condition())

    def test_preview_revalidates_missing_replaced_and_restored_files(self):
        pane = self.window.preview_pane
        self.window.load_clips()
        self.wait_for(lambda: pane._image_pixmap is not None)
        self.path.unlink()
        self.window.load_clips()
        self.wait_for(lambda: pane.image_label.text() == MISSING_IMAGE)
        self.assertIsNone(pane._image_pixmap)
        self.path.write_bytes(pixels('blue', 90))
        self.window.load_clips()
        self.wait_for(lambda: pane._image_pixmap is not None)
        self.assertIn('90 × 20', pane.stats_label.text())
        self.assertEqual(pane._image_pixmap.toImage().pixelColor(0, 0), QColor('blue'))

    def test_stale_preview_cannot_replace_new_selection(self):
        pane = self.window.preview_pane
        token = pane._image_token
        self.storage.add_clip('new selection')
        self.window.load_clips()
        self.window.clip_list.setCurrentRow(0)
        pane._image_ready(token, {'error': 'stale result'})
        self.assertEqual(pane.current_item.type, 'text')
        self.assertNotEqual(pane.stack.currentWidget(), pane.image_page)

    def test_missing_copy_keeps_window_and_shows_themed_alert(self):
        self.path.unlink()
        seen = []
        def close_alert(box):
            seen.append((box.text(), box.informativeText(), box.buttons()[0].text(), box.property('lightTheme')))
            return 0
        before = self.storage.get_clips()[0].updated_at
        with patch.object(QMessageBox, 'exec', close_alert):
            self.window._copy_selected(paste=True)
            self.wait_for(lambda: bool(seen))
        self.assertEqual(seen[0][:3], ('Imagem indisponível', MISSING_IMAGE, 'Entendi'))
        self.assertTrue(self.window.isVisible())
        self.platform.desktop.paste_to_previous.assert_not_called()
        self.platform.clipboard.write_image.assert_not_called()
        self.assertEqual(self.storage.get_clips()[0].updated_at, before)

    def test_tray_uses_same_image_validation_and_themed_failure(self):
        from clipx.ui.controllers.tray import ClipXTray
        tray = ClipXTray(self.storage, self.window)
        self.addCleanup(tray.deleteLater)
        self.addCleanup(tray.refresh_timer.stop)
        clip = self.storage.get_clips()[0]
        self.path.unlink()
        with patch.object(self.window, 'show_copy_failure') as show:
            tray.copy_clip(clip)
            self.wait_for(lambda: show.called)
        self.assertEqual(show.call_args.args[1].code, 'image_missing')
        self.platform.clipboard.write_image.assert_not_called()
        self.platform.desktop.paste_to_previous.assert_not_called()

    def test_scaled_minimum_contains_both_preview_panels(self):
        self.window.apply_preferences({**self.window.preferences, 'scale': 150})
        self.window.resize(self.window.minimumSize())
        self.app.processEvents()
        self.assertGreaterEqual(self.window.width(), sum(self.window.splitter.sizes()))
        self.assertGreater(self.window.preview_pane.image_label.height(), 50)

    def test_copy_only_completes_in_background_and_does_not_paste(self):
        self.window._copy_selected(paste=False)
        self.wait_for(lambda: not getattr(self.window, '_copy_busy', False))
        self.assertFalse(self.window.isVisible())
        self.platform.clipboard.write_image.assert_called_once()
        self.platform.clipboard.write_text.assert_not_called()
        self.platform.desktop.paste_to_previous.assert_not_called()


class X11ImageProtocolTests(unittest.TestCase):
    """Exercise TARGETS negotiation and incremental image transfers without X11."""

    def setUp(self):
        import types
        from clipx.platforms.linux.capture import X11ClipboardListener
        self.X = SimpleNamespace(NONE=0, AnyPropertyType=0, SelectionNotify=31,
                                 PropertyNotify=28, PropertyNewValue=0)
        self.changed_type = type('OwnerChanged', (), {})
        xlib = types.ModuleType('Xlib')
        xlib.X = self.X
        ext = types.ModuleType('Xlib.ext')
        ext.xfixes = SimpleNamespace(SelectionNotify=self.changed_type)
        self.patch = patch.dict('sys.modules', {'Xlib': xlib, 'Xlib.ext': ext})
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.listener = X11ClipboardListener.__new__(X11ClipboardListener)
        self.listener.capture = Mock()
        self.listener.window = Mock()
        self.listener.display = Mock()
        self.listener.clipboard = 1
        self.listener.targets = 2
        self.listener.utf8 = 3
        self.listener.string = 4
        self.listener.property = 5
        self.listener.incr = 6
        self.listener.mime_targets = {7: 'text/uri-list', 8: 'image/png'}
        self.listener.target = self.listener.targets
        self.listener.timestamp = 123
        self.listener.chunks = None

    def event(self, target):
        return SimpleNamespace(type=31, selection=1, target=target, time=123, property=5)

    def test_targets_prefer_file_urls_over_pixels_and_text(self):
        listener = self.listener
        listener.window.get_full_property.return_value = SimpleNamespace(format=32, property_type=2, value=[3, 8, 7])
        listener.handle_event(self.event(2))
        self.assertEqual(listener.target, 7)
        listener.window.get_full_property.return_value = SimpleNamespace(format=8, property_type=7, value=b'file:///tmp/photo.png')
        listener.handle_event(self.event(7))
        listener.capture.save_mime.assert_called_once_with('text/uri-list', b'file:///tmp/photo.png')
        listener.capture.save.assert_not_called()

    def test_incremental_png_is_reassembled_and_stale_reply_is_ignored(self):
        listener = self.listener
        listener.target = 8
        listener.window.get_full_property.return_value = SimpleNamespace(property_type=6, format=32, value=[100])
        listener.handle_event(self.event(8))
        payload = pixels()
        for chunk in (payload[:20], payload[20:], b''):
            listener.window.get_full_property.return_value = SimpleNamespace(property_type=8, format=8, value=chunk)
            listener.handle_event(SimpleNamespace(type=28, atom=5, state=0))
        listener.capture.save_mime.assert_called_once_with('image/png', payload)
        listener.capture.reset_mock()
        stale = self.event(8)
        stale.time = 100
        listener.handle_event(stale)
        listener.capture.save_mime.assert_not_called()
