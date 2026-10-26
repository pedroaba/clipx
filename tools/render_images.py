"""Render image history and themed alerts using isolated fixtures.

Run with .venv/bin/python tools/render_images.py. No native clipboard is used.
"""
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PyQt6.QtCore import QThreadPool, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QFont
from PyQt6.QtWidgets import QApplication, QMessageBox
from clipx.images import MISSING_IMAGE
from clipx.platforms.base import Result, Status
from clipx.platforms.effects import OpaqueWindowEffects
from clipx.shortcuts import ShortcutSettings
from clipx.storage import Storage
from clipx.ui.pages.clipboard import ClipXMainWindow


def wait_for(app, condition):
    """Wait for a preview worker while processing Qt events."""
    deadline = time.monotonic() + 5
    while not condition() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.005)
    if not condition():
        raise RuntimeError('Preview did not finish')


def main():
    """Render both themes, a scaled minimum window and unavailable states."""
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    output = Path(__file__).resolve().parents[1] / 'artifacts'
    output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        path = root / 'montanhas.png'
        image = QImage(1200, 800, QImage.Format.Format_RGB32)
        image.fill(QColor('#D8E5E2'))
        painter = QPainter(image)
        painter.fillRect(0, 530, 1200, 270, QColor('#415E56'))
        painter.fillRect(130, 230, 330, 400, QColor('#8CA99A'))
        painter.fillRect(490, 140, 340, 490, QColor('#739386'))
        painter.fillRect(860, 320, 210, 310, QColor('#A6BAA8'))
        painter.setPen(QColor('#F8FAF7'))
        painter.setFont(QFont('Arial', 44))
        painter.drawText(image.rect().adjusted(60, 50, -60, -50), Qt.AlignmentFlag.AlignBottom, 'Imagem de exemplo')
        painter.end()
        image.save(str(path))
        storage = Storage(root / 'history.db')
        storage.add_clip('Conteúdo de exemplo')
        storage.add_image(path)
        platform = SimpleNamespace(name='test', clipboard=Mock(), desktop=Mock(), effects=OpaqueWindowEffects())
        window = ClipXMainWindow(storage, ShortcutSettings(root / 'settings.json'), platform)
        window.show()
        window.refresh_timer.stop()
        for theme in ('dark', 'light'):
            values = {**window.preferences, 'theme': theme, 'material': 'opaque', 'scale': 100}
            window.apply_preferences(values)
            window.resize(1000, 650)
            window.load_clips()
            wait_for(app, lambda: window.preview_pane._image_pixmap is not None)
            app.processEvents()
            window.grab().save(str(output / f'images-{theme}.png'))
        values = {**window.preferences, 'scale': 150}
        window.apply_preferences(values)
        window.resize(window.minimumSize())
        app.processEvents()
        window.grab().save(str(output / 'images-light-scaled.png'))
        wait_for(app, lambda: window.preview_pane._image_busy is None)
        path.unlink()
        window.load_clips()
        wait_for(app, lambda: window.preview_pane.image_label.text() == MISSING_IMAGE)
        window.grab().save(str(output / 'images-missing.png'))
        clip = window.clip_list.get_selected_clip()
        for theme in ('dark', 'light'):
            window.apply_preferences({**window.preferences, 'theme': theme, 'scale': 100})
            def render_alert(box):
                box.show()
                app.processEvents()
                box.grab().save(str(output / f'images-alert-{theme}.png'))
                box.close()
                return 0
            with patch.object(QMessageBox, 'exec', render_alert):
                window.show_copy_failure(clip, Result(Status.ERROR, MISSING_IMAGE, 'image_missing'))
        QThreadPool.globalInstance().waitForDone(5000)
        app.processEvents()
        window.close()
    print('Rendered image fixtures in', output)


if __name__ == '__main__':
    main()
