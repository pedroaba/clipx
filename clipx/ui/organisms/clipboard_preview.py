"""Preview text safely and decode referenced images in background workers.

The pane renders clips as escaped HTML or plain text, never as raw markup, and
switches between text, color, code and URL presentations through a stacked
widget. Image workers revalidate file identity independently of database rows.
Syntax highlighting is optional and degrades to plain text on failure.
"""
import html
from PyQt6.QtCore import Qt, QThreadPool
from PyQt6.QtGui import QColor, QFont, QPixmap
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QStackedWidget, QTextBrowser, QVBoxLayout, QWidget, QSizePolicy
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name, guess_lexer
from clipx.ui.foundations.appearance import palette_for
from clipx.utils import format_relative_time


class PreviewPaneWidget(QFrame):
    """Preview pane for the selected clip, with text, color, image and empty pages.

    Attributes:
        preferences (dict): UI preferences controlling font size, scale,
            syntax highlighting and light/dark palettes.
        current_item (object | None): Clip currently rendered, or ``None`` when
            the empty page is shown.
        type_badge (QLabel): Badge with the clip type or language.
        time_label (QLabel): Relative timestamp of the clip.
        stats_label (QLabel): Line, character and word counts.
        stack (QStackedWidget): Holds the text, color, image and empty pages.
        text_browser (QTextBrowser): Renderer for text, code and URL content.
        color_swatch (QFrame): Solid swatch for color clips.
        color_details (QTextBrowser): Hex and RGB details for color clips.
        empty_page (QLabel): Placeholder shown when nothing is selected.
    """

    def __init__(self, parent=None):
        """Build the header, the stacked pages and the initial empty state.

        Args:
            parent (QWidget | None): Optional parent widget.
        """
        super().__init__(parent)
        self.setObjectName('PreviewPane')
        self.preferences = {}
        self.current_item = None
        self._image_token = 0
        self._image_busy = None
        self._image_signature = None
        self._image_pixmap = None
        self._image_tasks = {}
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
        self.image_page = QWidget()
        image_layout = QVBoxLayout(self.image_page)
        image_layout.setContentsMargins(0, 0, 0, 0)
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setWordWrap(True)
        self.image_label.setObjectName('Secondary')
        self.image_label.setMinimumSize(1, 1)
        self.image_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.image_label.setAccessibleName('Prévia da imagem selecionada')
        image_layout.addWidget(self.image_label, 1)
        self.image_path = QLabel()
        self.image_path.setTextFormat(Qt.TextFormat.PlainText)
        self.image_path.setWordWrap(False)
        self.image_path.setMinimumWidth(0)
        self.image_path.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.image_path.setObjectName('Secondary')
        self.image_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        image_layout.addWidget(self.image_path)
        self.stack.addWidget(self.image_page)
        layout.addWidget(self.stack, 1)
        self.show_empty()

    def show_empty(self):
        """Clear the pane and display the empty page."""
        self.current_item = None
        self._invalidate_image()
        self._image_signature = None
        self._image_pixmap = None
        self.type_badge.hide()
        self.stats_label.clear()
        self.time_label.clear()
        self.stack.setCurrentIndex(2)

    def display_item(self, item):
        """Render a clip, skipping work when the item and preferences match.

        Color clips show the swatch and RGB details; code clips are highlighted
        with Pygments unless syntax highlighting is disabled; valid HTTP(S) URLs
        become escaped links. Any highlighting error falls back to plain text.

        Args:
            item (object): Clip record with ``type``, ``content``, ``language``,
                ``line_count``, ``char_count`` and ``updated_at`` attributes.
        """
        if item.type == 'image':
            if self.current_item != item:
                self._invalidate_image()
                self._image_signature = None
                self._image_pixmap = None
                self.image_label.clear()
                self.image_label.setText('Carregando…')
                self.stats_label.clear()
            self.current_item = item
            self.type_badge.show()
            self.type_badge.setText('IMAGEM')
            self.time_label.setText(format_relative_time(item.updated_at))
            self.image_path.setToolTip(item.content)
            self.image_path.setAccessibleName(item.content)
            self._elide_image_path()
            self.stack.setCurrentWidget(self.image_page)
            self.refresh_image()
            return
        if self.current_item is not None and self.current_item.type == 'image':
            self._invalidate_image()
            self._image_pixmap = None
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

    def refresh_image(self):
        """Schedule a filesystem check even when the database row is unchanged."""
        if self.current_item is None or self.current_item.type != 'image' or self.isHidden():
            return
        if self._image_busy == self._image_token:
            return
        from clipx.ui.models.image_preview import ImagePreviewTask
        token = self._image_token
        task = ImagePreviewTask(token, self.current_item.content, self._image_signature)
        task.signals.ready.connect(self._image_ready)
        self._image_tasks[token] = task
        self._image_busy = token
        QThreadPool.globalInstance().start(task)

    def _image_ready(self, token, result):
        """Accept only the current selection's worker result on the UI thread."""
        self._image_tasks.pop(token, None)
        if self._image_busy == token:
            self._image_busy = None
        if token != self._image_token or self.current_item is None or self.current_item.type != 'image':
            return
        if result.get('unchanged') or result.get('cancelled'):
            return
        if 'error' in result:
            self._image_signature = None
            self._image_pixmap = None
            self.image_label.clear()
            self.image_label.setText(result['error'])
            self.stats_label.setText('Imagem indisponível')
            return
        from clipx.images import image_title
        self._image_signature = result['signature']
        self._image_pixmap = QPixmap.fromImage(result['image'])
        dimensions = result['dimensions']
        self.stats_label.setText(f'{image_title(self.current_item)} · {dimensions.width()} × {dimensions.height()} px · {result["size"] / 1024:.1f} KB')
        self._scale_image()
        self._elide_image_path()

    def _scale_image(self):
        """Fit the cached preview into the available area without cropping."""
        if self._image_pixmap is not None:
            self.image_label.setPixmap(self._image_pixmap.scaled(
                self.image_label.size(), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, event):
        """Resize the displayed bitmap without decoding the file again."""
        super().resizeEvent(event)
        self._scale_image()
        self._elide_image_path()

    def _elide_image_path(self):
        """Keep long source paths from consuming the bitmap's preview area."""
        if self.current_item is not None and self.current_item.type == 'image':
            self.image_path.setText(self.image_path.fontMetrics().elidedText(
                self.current_item.content, Qt.TextElideMode.ElideMiddle,
                max(40, self.image_path.width())))

    def _invalidate_image(self):
        """Skip queued decodes belonging to a selection that is no longer active."""
        self._image_token += 1
        for task in self._image_tasks.values():
            task.cancelled.set()
