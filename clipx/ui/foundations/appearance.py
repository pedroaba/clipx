"""Semantic appearance resolution for all shared Qt surfaces.

Maps the light and dark palettes, rewrites dark theme literals into light
equivalents, scales style-sheet metrics, and re-renders icons and palettes for a
widget tree. Appearance values are dictionaries containing at least ``theme``
(``dark``, ``light`` or ``system``) and ``scale`` (a percentage).
"""
import re
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication, QWidget

DARK_PALETTE = {
    'canvas': '#18181B', 'preferences': '#101012', 'sidebar': '#0D0D0F',
    'card': '#242428', 'hover': '#29292E', 'selection': '#343439',
    'border': '#36363B', 'text': '#F4F4F5', 'secondary': '#A1A1AA',
    'muted': '#90909B', 'danger': '#FF766D', 'link': '#82B8F8',
    'danger_surface': '#1D1112', 'danger_border': '#793C39',
    'danger_action': '#D92D20', 'danger_action_hover': '#B42318',
}
LIGHT_PALETTE = {
    'canvas': '#FFFFFF', 'preferences': '#FAFAFA', 'sidebar': '#F0F0F2',
    'card': '#F1F1F4', 'hover': '#E9E9ED', 'selection': '#DFDFE6',
    'border': '#D1D1D8', 'text': '#18181B', 'secondary': '#52525B',
    'muted': '#60606B', 'danger': '#B42318', 'link': '#175CD3',
    'danger_surface': '#FFF5F4', 'danger_border': '#E5AAA5',
    'danger_action': '#D92D20', 'danger_action_hover': '#B42318',
}
# Resolve existing QSS literals through the semantic palette, with aliases for
# component-specific surfaces. This keeps one authoritative light/dark mapping.
LIGHT_COLORS = {
    '#161616': '#FAFAFA', '#111111': '#FFFFFF', '#333337': '#D1D1D8', '#3B3B3F': '#C5C5D0',
    '#302819': '#FFFAEB', '#766025': '#DCB564', '#F5B82E': '#93370D', '#101010': '#F0F0F2',
    '#181818': '#FFFFFF', '#45454C': '#C5C5D0', '#303036': '#E9E9ED', '#242424': '#E4E4EB',
    '#101012': '#FAFAFA', '#0D0D0F': '#F0F0F2', '#18181B': '#FFFFFF',
    '#141416': '#FFFFFF', '#141414': '#FFFFFF', '#242428': '#F1F1F4',
    '#29292E': '#E9E9ED', '#343439': '#DFDFE6', '#36363B': '#D1D1D8',
    '#FF766D': '#B42318', '#F4F4F5': '#18181B', '#A1A1AA': '#52525B',
    '#90909B': '#60606B', '#82B8F8': '#175CD3', '#C4B5FD': '#6941C6',
    '#86D5B0': '#067647', '#EBC58C': '#93370D', '#8AD5DE': '#0E7090',
    '#29292D': '#D8D8DF', '#202023': '#E4E4EB', '#202024': '#EBEBEF',
    '#303034': '#CDCDD5', '#2B2B30': '#D8D8DF', '#232326': '#E7E7ED',
    '#3C3C42': '#C5C5D0', '#46464D': '#ADADBA', '#72727D': '#71717A',
    '#23232A': '#E4E4EC', '#26262B': '#E4E4EC', '#D4D4D8': '#3F3F46',
    '#60A5FA': '#175CD3', '#55555D': '#CCCCD5', '#44444C': '#D4E3FA',
    '#3E3E45': '#E3E3EA', '#666671': '#71717A',
}


def is_light(values):
    """Decide whether the light palette should be used.

    ``theme`` set to ``light`` always selects light; ``system`` follows the
    current Qt color scheme and selects light only when Qt reports
    ``Qt.ColorScheme.Light``.

    Args:
        values (dict): Appearance values containing an optional ``theme`` key.

    Returns:
        bool: ``True`` when the light palette applies.
    """
    return values.get('theme', 'dark') == 'light' or (values.get('theme') == 'system' and
        QApplication.styleHints().colorScheme() == Qt.ColorScheme.Light)


LIGHT_COLORS.update({value: LIGHT_PALETTE[role] for role, value in DARK_PALETTE.items()})

def palette_for(values):
    """Select the semantic color mapping for the requested appearance.

    Args:
        values (dict): Appearance values passed to :func:`is_light`.

    Returns:
        dict[str, str]: ``LIGHT_PALETTE`` or ``DARK_PALETTE``.
    """
    return LIGHT_PALETTE if is_light(values) else DARK_PALETTE


def stylesheet(source, values):
    """Adapt a dark style sheet to the current appearance and scale.

    For light mode, six-digit hex colors are looked up in ``LIGHT_COLORS`` (or
    kept unchanged when unknown) and a few translucent white/dark overlays are
    swapped for their light equivalents. Every ``pt`` or ``px`` length is then
    multiplied by ``values['scale'] / 100``.

    Args:
        source (str): Qt style sheet written against the dark palette.
        values (dict): Appearance values containing ``theme`` and ``scale``.

    Returns:
        str: Transformed style sheet.
    """
    if is_light(values):
        source = re.sub(r'#[0-9a-fA-F]{6}', lambda m: LIGHT_COLORS.get(m[0].upper(), m[0]), source)
        source = source.replace('rgba(24,24,27,238)', 'rgba(255,255,255,238)')
        source = source.replace('rgba(255,255,255,10)', 'rgba(0,0,0,8)')
        source = source.replace('rgba(255,255,255,22)', 'rgba(0,0,0,18)')
        source = source.replace('rgba(255,255,255,12)', 'rgba(0,0,0,12)')
    scale = values['scale'] / 100
    return re.sub(r'(\d+(?:\.\d+)?)(pt|px)', lambda m: f'{float(m[1]) * scale:g}{m[2]}', source)


def apply_surface(widget, values, source=None):
    """Scale layout metrics once from their original values, never cumulatively.

    Applies the optional style sheet, marks the widget with a ``lightTheme``
    property, and walks the widget tree. Original layout margins, spacing,
    minimum and maximum sizes, and child-specific style sheets are cached on the
    objects on first application, so repeated calls rescale from the originals.
    Lucide buttons and labelled glyphs are re-rendered at the scaled size, and
    every child receives a palette with the semantic text and canvas colors.

    Args:
        widget (QWidget): Root widget of the surface to update.
        values (dict): Appearance values containing ``theme`` and ``scale``.
        source (str | None): Optional style sheet to apply to ``widget``.
    """
    light = is_light(values)
    colors = palette_for(values)
    widget.setProperty('lightTheme', light)
    if source is not None:
        widget.setStyleSheet(stylesheet(source, values))
    scale = values['scale'] / 100
    for child in [widget, *widget.findChildren(QWidget)]:
        layout = child.layout()
        if layout:
            if not hasattr(layout, '_ui_metrics'):
                m = layout.contentsMargins()
                layout._ui_metrics = ((m.left(), m.top(), m.right(), m.bottom()), layout.spacing())
            margins, spacing = layout._ui_metrics
            layout.setContentsMargins(*(round(x * scale) for x in margins))
            if spacing >= 0:
                layout.setSpacing(round(spacing * scale))
        if not child.isWindow() and (child.minimumHeight() > 0 or child.minimumWidth() > 0):
            if not hasattr(child, '_ui_minimum'):
                child._ui_minimum = (child.minimumWidth(), child.minimumHeight())
            if not hasattr(child, '_ui_maximum'):
                child._ui_maximum = (child.maximumWidth(), child.maximumHeight())
            child.setMaximumSize(*(round(x * scale) if x < 16777215 else x for x in child._ui_maximum))
            child.setMinimumSize(*(round(x * scale) for x in child._ui_minimum))
        # Some existing components own their styles; resolve those as well.
        if child is not widget and child.styleSheet():
            if not hasattr(child, '_ui_style'):
                child._ui_style = child.styleSheet()
            child.setStyleSheet(stylesheet(child._ui_style, values))
        if child.property('lucideIcon') or child.property('glyphName'):
            from clipx.ui.foundations.icons import refresh_lucide_button
            refresh_lucide_button(child, values)
        if child.property('iconName'):
            from clipx.ui.foundations.icons import icon
            size = round(child.property('iconSize') * scale)
            child.setPixmap(icon(child.property('iconName'), size, colors['secondary']).pixmap(size, size))
        palette = child.palette()
        foreground = QColor(colors['text'])
        background = QColor(colors['canvas'])
        for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText, QPalette.ColorRole.ButtonText):
            palette.setColor(role, foreground)
        for role in (QPalette.ColorRole.Window, QPalette.ColorRole.Base, QPalette.ColorRole.Button):
            palette.setColor(role, background)
        child.setPalette(palette)
