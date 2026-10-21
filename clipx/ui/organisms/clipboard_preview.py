"""Text-only preview: content is escaped or supplied as plain text."""
import html
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QStackedWidget, QTextBrowser, QVBoxLayout, QWidget
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name, guess_lexer
from clipx.ui.foundations.appearance import palette_for
from clipx.utils import format_relative_time


class PreviewPaneWidget(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('PreviewPane')
        self.preferences = {}
        self.current_item = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)
        header = QHBoxLayout()
        self.type_badge = QLabel()
        self.type_badge.setObjectName('TypeBadge')
        header.addWidget(self.type_badge)
        header.addStretch()
        self.time_label = QLabel()
        self.time_label.setObjectName('Metadata')
        header.addWidget(self.time_label)
        layout.addLayout(header)
        self.stats_label = QLabel()
        self.stats_label.setObjectName('Metadata')
        self.stats_label.setWordWrap(True)
        layout.addWidget(self.stats_label)
        self.stack = QStackedWidget()
        self.text_browser = QTextBrowser()
        self.text_browser.setAccessibleName('Prévia do conteúdo selecionado')
        self.text_browser.setOpenExternalLinks(True)
        self.stack.addWidget(self.text_browser)
        color_page = QWidget()
        color_layout = QVBoxLayout(color_page)
        color_layout.setContentsMargins(0, 8, 0, 0)
        self.color_swatch = QFrame()
        self.color_swatch.setFixedHeight(160)
        color_layout.addWidget(self.color_swatch)
        self.color_details = QTextBrowser()
        color_layout.addWidget(self.color_details)
        self.stack.addWidget(color_page)
        self.empty_page = QLabel('Selecione um item para visualizar')
        self.empty_page.setObjectName('Secondary')
        self.empty_page.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_page.setWordWrap(True)
        self.stack.addWidget(self.empty_page)
        layout.addWidget(self.stack, 1)
        self.show_empty()

    def show_empty(self):
        self.current_item = None
        self.type_badge.hide()
        self.stats_label.clear()
        self.time_label.clear()
        self.stack.setCurrentIndex(2)

    def display_item(self, item):
        if self.current_item == item and getattr(self, '_rendered_preferences', None) == self.preferences:
            return
        self._rendered_preferences = self.preferences.copy()
        self.current_item = item
        self.type_badge.show()
        self.type_badge.setText({'text': 'TEXTO', 'code': item.language or 'CÓDIGO',
                                 'url': 'LINK', 'color': 'COR'}.get(item.type, 'TEXTO').upper())
        self.stats_label.setText(f'{item.line_count} linhas · {item.char_count} caracteres · {len(item.content.split())} palavras')
        self.time_label.setText(format_relative_time(item.updated_at))
        self.stack.setCurrentIndex(0)
        self.text_browser.setStyleSheet('')
        size = self.preferences.get('preview_size', 12) * self.preferences.get('scale', 100) / 100
        font = QFont('Geist', round(size))
        self.text_browser.setFont(font)
        self.text_browser.setStyleSheet(f'font-family: Geist; font-size: {size}pt;')
        self.color_details.setStyleSheet(f'font-family: Geist; font-size: {size}pt;')
        if item.type == 'color':
            color = QColor(item.content.strip())
            if color.isValid():
                self.color_swatch.setStyleSheet(f'background: {color.name()}; border-radius: 12px; border: 1px solid #777777;')
                self.color_details.setPlainText(f'{color.name().upper()}\n\nRGB {color.red()}, {color.green()}, {color.blue()}')
                self.stack.setCurrentIndex(1)
                return
        if item.type == 'code':
            self.text_browser.setFont(QFont('Geist Mono', round(size)))
            self.text_browser.setStyleSheet(f'font-family: "Geist Mono"; font-size: {size}pt;')
            try:
                if not self.preferences.get('syntax', True):
                    self.text_browser.setPlainText(item.content)
                    return
                lexer = get_lexer_by_name(item.language) if item.language else guess_lexer(item.content)
                formatter = HtmlFormatter(style='friendly' if self.preferences.get('light', False) else 'native', noclasses=True, nobackground=True,
                                          prestyles=f'font-family: Geist Mono; font-size: {size}pt;')
                rendered = highlight(item.content, lexer, formatter)
                self.text_browser.setHtml(rendered)
                return
            except Exception:
                pass
        colors = palette_for(self.preferences)
        if item.type == 'url' and item.content.strip().startswith(('https://', 'http://')):
            url = html.escape(item.content.strip(), quote=True)
            link_color = colors['link']
            secondary = colors['secondary']
            self.text_browser.setHtml(f'<p style="color:{secondary}">URL</p><a style="color:{link_color}" href="{url}">{url}</a>')
        else:
            self.text_browser.setPlainText(item.content)
