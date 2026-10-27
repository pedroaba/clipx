"""Structured maintenance confirmations with explicit effects and preservation."""
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QTextOption
from PyQt6.QtWidgets import (QDialog, QFrame, QHBoxLayout, QLabel, QPlainTextEdit,
                            QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from clipx.ui.foundations.appearance import apply_surface, palette_for
from clipx.ui.foundations.fonts import install_fonts
from clipx.ui.foundations.icons import icon, refresh_lucide_button
from clipx.ui.foundations.preferences import PREFERENCES_QSS


@dataclass(frozen=True)
class ConfirmationSpec:
    title: str
    subtitle: str
    action: str
    effects: tuple[str, ...]
    preserved: tuple[str, ...]
    details: str
    glyph: str = 'trash'
    effect_glyph: str = 'x'


def prune_confirmation(options, estimate):
    effects = []
    preserved = []
    if options.mode == 'content':
        effects.append({'all': 'Apagar as entradas de todo o histórico.',
                        'data': 'Apagar entradas de texto, código, JSON, links e cores.',
                        'images': 'Apagar as entradas de imagem do histórico.'}[options.target])
        if options.target == 'all' and not options.include_pinned:
            effects[0] = 'Apagar as entradas não fixadas do histórico.'
        if options.target in ('images', 'all'):
            effects.append('Liberar PNGs próprios que ficarem sem referências.')
        if options.include_pinned:
            effects.append('Incluir os fixados da categoria selecionada.')
        else:
            preserved.append('Fixados e suas imagens serão preservados.')
        if options.target == 'data':
            preserved.append('Entradas de imagem e seus arquivos serão mantidos.')
        elif options.target == 'images':
            preserved.append('O histórico de texto, código, JSON, links e cores será mantido.')
    else:
        if options.target in ('data', 'all'):
            effects.append('Compactar o banco para recuperar espaço já liberado.')
        if options.target in ('images', 'all'):
            effects.append('Remover PNGs próprios órfãos, registros sem arquivos e capturas temporárias interrompidas.')
        preserved.append('O histórico válido, incluindo fixados e suas imagens, será mantido.')
    preserved.extend(('Imagens originais externas serão preservadas.',
                      'O app, as preferências e o clipboard serão mantidos.'))
    return ConfirmationSpec('Limpar dados',
                            'Revise o que será apagado do histórico.' if options.mode == 'content' else 'Revise a limpeza de sobras e a recuperação de espaço.',
                            'Limpar dados', tuple(effects), tuple(preserved),
                            estimate.summary(estimate=True) + '\nOs alvos serão recalculados ao executar.',
                            effect_glyph='x' if options.mode == 'content' else 'eraser')


def uninstall_confirmation(estimate):
    home = str(Path.home())
    paths = [str(path) for path in estimate.paths]
    paths = ['~' + path[len(home):] if path == home or path.startswith(home + '/') else path for path in paths]
    details = estimate.summary(estimate=True)
    if paths:
        details += '\n\n' + '\n'.join(paths)
    return ConfirmationSpec('Desinstalar o ClipX?',
                            'Remove o app e todos os dados desta conta. Essa ação não pode ser desfeita.',
                            'Desinstalar e apagar dados',
                            ('Histórico completo, incluindo fixados.',
                             'PNGs próprios, bancos e backups.',
                             'Preferências, alterações pendentes e o conteúdo atual do clipboard.'),
                            ('Imagens originais externas serão preservadas.',),
                            details, glyph='alert')


class MaintenanceConfirmation(QDialog):
    """Modal alert. Cancel, Escape and close all reject without executing work."""
    def __init__(self, spec, values, parent=None):
        super().__init__(parent, Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        install_fonts()
        self.spec = spec
        self.values = values.copy()
        self.setWindowTitle(spec.title)
        self.setAccessibleName(spec.title)
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.shade = None
        self.glyphs = []
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        card = QFrame()
        card.setObjectName('ConfirmationCard')
        outer.addWidget(card)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        self.body = QWidget()
        body = QVBoxLayout(self.body)
        body.setAlignment(Qt.AlignmentFlag.AlignTop)
        body.setContentsMargins(24, 24, 24, 20)
        body.setSpacing(18)
        header = QHBoxLayout()
        header.setSpacing(14)
        badge = QFrame()
        badge.setObjectName('ConfirmationBadge')
        badge.setFixedSize(48, 48)
        badge_box = QVBoxLayout(badge)
        badge_box.setContentsMargins(12, 12, 12, 12)
        badge_box.addWidget(self.glyph(spec.glyph, 'danger', 24))
        header.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
        copy = QVBoxLayout()
        copy.setSpacing(4)
        self.heading = QLabel(spec.title)
        self.heading.setTextFormat(Qt.TextFormat.PlainText)
        self.heading.setObjectName('ConfirmationTitle')
        self.heading.setWordWrap(True)
        copy.addWidget(self.heading)
        subtitle = QLabel(spec.subtitle)
        subtitle.setObjectName('Description')
        subtitle.setTextFormat(Qt.TextFormat.PlainText)
        subtitle.setWordWrap(True)
        copy.addWidget(subtitle)
        header.addLayout(copy, 1)
        self.close_button = QPushButton()
        self.close_button.setObjectName('ConfirmationClose')
        self.close_button.setProperty('glyphName', 'x')
        self.close_button.setAccessibleName('Fechar confirmação')
        self.close_button.setToolTip('Fechar')
        self.close_button.setFixedSize(28, 28)
        self.close_button.setAutoDefault(False)
        self.close_button.clicked.connect(self.reject)
        header.addWidget(self.close_button, 0, Qt.AlignmentFlag.AlignTop)
        body.addLayout(header)

        summary = QFrame()
        summary.setObjectName('ConfirmationSummary')
        summary_box = QVBoxLayout(summary)
        summary_box.setContentsMargins(16, 16, 16, 16)
        summary_box.setSpacing(12)
        for text in spec.effects:
            self.add_row(summary_box, text, spec.effect_glyph, 'danger', False)
        separator = QFrame()
        separator.setObjectName('PreferencesSeparator')
        separator.setFixedHeight(1)
        summary_box.addWidget(separator)
        for text in spec.preserved:
            self.add_row(summary_box, text, 'check', 'secondary', True)
        body.addWidget(summary)
        self.details = QPlainTextEdit()
        self.details.setObjectName('ConfirmationDetails')
        self.details.setAccessibleName('Estimativa e detalhes da operação')
        self.details.setReadOnly(True)
        self.details.setPlainText(spec.details)
        self.details.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.details.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.details.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.details.setFixedHeight(min(164, max(96, 78 + spec.details.count('\n') * 18)))
        body.addWidget(self.details)
        self.scroll = QScrollArea()
        self.scroll.setObjectName('ConfirmationScroll')
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(self.body)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(self.scroll, 1)
        footer = QFrame()
        self.footer = footer
        footer.setObjectName('ConfirmationFooter')
        self.actions = QHBoxLayout(footer)
        self.actions.setContentsMargins(24, 16, 24, 16)
        self.actions.setSpacing(10)
        self.actions.addStretch()
        self.cancel = QPushButton('Cancelar')
        self.cancel.setObjectName('ConfirmationCancel')
        self.cancel.setDefault(True)
        self.cancel.clicked.connect(self.reject)
        self.confirm = QPushButton(spec.action)
        self.confirm.setObjectName('ConfirmationDestructive')
        self.confirm.setAutoDefault(False)
        self.confirm.setDefault(False)
        self.confirm.clicked.connect(self.accept)
        for button in (self.cancel, self.confirm):
            button.setMinimumHeight(38)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            self.actions.addWidget(button)
        layout.addWidget(footer)
        apply_surface(self, values, PREFERENCES_QSS)
        colors = palette_for(values)
        for label, name, role, base_size in self.glyphs:
            size = round(base_size * values['scale'] / 100)
            label.setPixmap(icon(name, size, colors[role]).pixmap(size, size))
        refresh_lucide_button(self.close_button, values)
        self.ensurePolished()
        for widget in self.findChildren(QWidget):
            widget.ensurePolished()
        scale = values['scale'] / 100
        screen = parent.screen() if parent is not None else self.screen()
        area = screen.availableGeometry()
        width = min(round(560 * scale), area.width() - 40)
        # Prime nested height-for-width layouts while hidden. QLabel wrapping
        # otherwise measures the scroll area's initial narrow viewport and
        # leaves a large empty header when the modal is first displayed.
        self.body.resize(width - 4, area.height())
        body.setGeometry(self.body.rect())
        body.invalidate()
        body_height = body.heightForWidth(width - 4)
        if body_height < 0:
            body_height = body.sizeHint().height()
        height = body_height + footer.sizeHint().height() + 2
        self.resize(width, min(height, area.height() - 40))
        self.cancel.setDefault(True)
        self.cancel.setFocus()
        self.finished.connect(self.clear_shade)

    def glyph(self, name, role, size=18):
        label = QLabel()
        self.glyphs.append((label, name, role, size))
        return label

    def add_row(self, layout, text, glyph, role, muted):
        row = QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(self.glyph(glyph, role), 0, Qt.AlignmentFlag.AlignTop)
        label = QLabel(text)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        label.setObjectName('ConfirmationPreserved' if muted else 'ConfirmationEffect')
        row.addWidget(label, 1)
        layout.addLayout(row)

    def showEvent(self, event):
        self.body.layout().invalidate()
        height = self.body.layout().heightForWidth(self.scroll.viewport().width())
        if height >= 0:
            self.resize(self.width(), min(height + self.footer.sizeHint().height() + 4,
                                          self.screen().availableGeometry().height() - 40))
        parent = self.parentWidget()
        if parent is not None and self.shade is None:
            self.shade = QWidget(parent)
            self.shade.setStyleSheet('background: rgba(0, 0, 0, 130);')
            self.shade.setGeometry(parent.rect())
            self.shade.show()
            self.shade.raise_()
            parent.installEventFilter(self)
        super().showEvent(event)
        self.confirm.setDefault(False)
        self.cancel.setDefault(True)
        self.cancel.setFocus()

    def eventFilter(self, watched, event):
        if watched is self.parentWidget() and event.type() == QEvent.Type.Resize and self.shade is not None:
            self.shade.setGeometry(watched.rect())
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event):
        # Cocoa must not promote the destructive button to the initial default.
        # Enter can confirm only after the user deliberately focuses that button.
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.focusWidget() is self.confirm:
            self.accept()
            event.accept()
            return
        super().keyPressEvent(event)

    def hideEvent(self, event):
        self.clear_shade()
        super().hideEvent(event)

    def clear_shade(self):
        if self.shade is not None:
            parent = self.parentWidget()
            if parent is not None:
                parent.removeEventFilter(self)
            self.shade.hide()
            self.shade.deleteLater()
            self.shade = None
