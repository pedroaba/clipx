"""ClipX semantic dark tokens, shared across all Qt surfaces."""
BG_WINDOW = '#18181B'
BG_CARD = '#242428'
BG_CARD_HOVER = '#29292E'
BG_CARD_SELECTED = '#343439'
BORDER_DEFAULT = '#36363B'
BORDER_ACCENT = '#FF766D'
TEXT_PRIMARY = '#F4F4F5'
TEXT_SECONDARY = '#A1A1AA'
TEXT_MUTED = '#90909B'
ACCENT_BLUE = '#82B8F8'
ACCENT_PURPLE = '#C4B5FD'
ACCENT_GREEN = '#86D5B0'
ACCENT_AMBER = '#EBC58C'
ACCENT_CYAN = '#8AD5DE'
RADIUS = 16
MOTION_MS = 140

QSS_STYLESHEET = f'''
QWidget {{ color: {TEXT_PRIMARY}; font-family: 'Geist'; font-size: 14pt; }}
QMainWindow {{ background: transparent; }}
QWidget#CentralWidget {{ background: {BG_WINDOW}; border: 1px solid {BORDER_DEFAULT}; border-radius: 16px; }}
QWidget#CentralWidget[nativeGlass="true"] {{ background: rgba(24,24,27,238); }}
QLabel {{ background: transparent; border: none; }}
QLabel#Secondary, QLabel#Count, QLabel#Metadata {{ color: {TEXT_SECONDARY}; font-size: 11pt; }}
QWidget#SearchHeader {{ background: transparent; border-bottom: 1px solid {BORDER_DEFAULT}; }}
QLineEdit#SearchBar {{ background: transparent; border: none; padding: 10px 0; font-size: 17pt;
                     color: {TEXT_PRIMARY}; selection-background-color: #55555D; }}
QPushButton:hover {{ background: {BG_CARD_HOVER}; }}
QPushButton:focus {{ border-color: {TEXT_SECONDARY}; }}
QListWidget#ClipList {{ background: transparent; border: none; outline: none; padding: 6px; }}
QListWidget#ClipList::item {{ border: none; border-radius: 8px; margin: 2px 0; }}
QListWidget#ClipList::item:hover {{ background: rgba(255,255,255,10); }}
QListWidget#ClipList::item:selected {{ background: rgba(255,255,255,22); }}
QFrame#PreviewPane {{ background: rgba(0,0,0,18); border: none; border-left: 1px solid {BORDER_DEFAULT}; }}
QTextBrowser {{ background: transparent; border: none; padding: 0; color: {TEXT_PRIMARY}; font-size: 12pt; }}
QTextBrowser#CodePreview {{ font-family: "Geist Mono"; }}
QLabel#TypeBadge {{ color: {TEXT_SECONDARY}; background: {BG_CARD}; border-radius: 4px; padding: 3px 7px; font-size: 10pt; }}
QSplitter::handle {{ background: {BORDER_DEFAULT}; width: 1px; }}
QFrame#ActionBar {{ background: rgba(0,0,0,18); border: none; border-top: 1px solid {BORDER_DEFAULT}; border-bottom-left-radius: 16px; border-bottom-right-radius: 16px; }}
QLabel.KeyBadge {{ background: rgba(255,255,255,12); color: {TEXT_SECONDARY}; border-radius: 4px; padding: 2px 5px; font-size: 10pt; }}
QPushButton {{ background: transparent; border: 1px solid transparent; border-radius: 6px; padding: 6px 8px; font-size: 11pt; }}
QPushButton:disabled {{ color: {TEXT_MUTED}; }}
QLabel#Status {{ color: {ACCENT_AMBER}; background: {BG_CARD}; padding: 7px 12px; font-size: 11pt; }}
QMenu {{ background: {BG_CARD}; color: {TEXT_PRIMARY}; border: 1px solid {BORDER_DEFAULT}; border-radius: 8px; padding: 6px; font-size: 12pt; }}
QMenu::item {{ padding: 7px 16px; border-radius: 4px; }}
QMenu::item:selected {{ background: {BG_CARD_SELECTED}; }}
QMenu::item:disabled {{ color: {TEXT_MUTED}; }}
QMenu::separator {{ height: 1px; background: {BORDER_DEFAULT}; margin: 5px; }}
'''
