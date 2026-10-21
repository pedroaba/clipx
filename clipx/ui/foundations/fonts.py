"""Bundled Geist fonts; registration is local to the running Qt application."""
from pathlib import Path
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QFontDatabase
from PyQt6.QtWidgets import QApplication


def install_fonts():
    app = QApplication.instance()
    if app is None or app.property('clipxFontsLoaded'):
        return
    app.styleHints().setColorScheme(Qt.ColorScheme.Dark)
    root = Path(__file__).resolve().parents[2] / 'assets/fonts'
    for filename in ('Geist.ttf', 'GeistMono.ttf'):
        if QFontDatabase.addApplicationFont(str(root / filename)) < 0:
            raise RuntimeError(f'Não foi possível carregar a fonte incluída: {filename}')
    app.setFont(QFont('Geist', 13))
    app.setProperty('clipxFontsLoaded', True)
