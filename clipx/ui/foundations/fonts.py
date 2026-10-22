"""Bundled Geist fonts; registration is local to the running Qt application."""
from pathlib import Path
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QFontDatabase
from PyQt6.QtWidgets import QApplication


def install_fonts():
    """Register the bundled Geist fonts on the running Qt application.

    Forces the dark color scheme and registers ``Geist.ttf`` and
    ``GeistMono.ttf`` from the bundled assets. The operation is idempotent: it
    returns immediately when there is no application instance or when the
    ``clipxFontsLoaded`` property is already set. Once loaded, ``Geist`` at
    13 points becomes the application font and the property is stored.

    Raises:
        RuntimeError: If either bundled font file cannot be registered.
    """
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
