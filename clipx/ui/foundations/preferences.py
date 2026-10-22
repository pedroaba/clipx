"""Preference components derive from the same semantic palette as search.

Extends the shared style sheet with dialog, sidebar, shortcut-row and footer
styles so preferences inherit the same colors, radii and focus treatment as the
clipboard overlay.
"""
from clipx.ui.foundations.theme import QSS_STYLESHEET, BG_WINDOW, BG_CARD, BORDER_DEFAULT, TEXT_SECONDARY

PREFERENCES_QSS = QSS_STYLESHEET + f'''
QDialog {{ background: {BG_WINDOW}; }}
QLabel#Heading {{ font-size: 22pt; font-weight: 600; }}
QLabel#Subtitle, QLabel#Description {{ color: {TEXT_SECONDARY}; font-size: 11pt; }}
QLabel#Section {{ color: {TEXT_SECONDARY}; font-size: 10pt; font-weight: 600; padding-top: 4px; }}
QFrame#ShortcutPreview {{ background: {BG_CARD}; border: 1px solid {BORDER_DEFAULT}; border-radius: 8px; }}
QLabel#ActionTitle {{ font-size: 12pt; font-weight: 600; }}
QPushButton {{ background: {BG_CARD}; border: 1px solid {BORDER_DEFAULT}; padding: 7px 10px; }}
QPushButton#ShortcutRecorder {{ font-weight: 500; }}
QPushButton#ShortcutRecorder[recording="true"] {{ border: 2px solid #A1A1AA; background: #343439; }}
QPushButton#ApplyButton {{ background: #3E3E45; border-color: #666671; }}
QScrollArea {{ border: none; background: transparent; }}
QWidget#ShortcutRows {{ background: {BG_WINDOW}; }}
'''

# Preferences deliberately use a quieter canvas than the clipboard overlay.
PREFERENCES_QSS += '''
QDialog, QWidget#PreferencesLayout { background: #101012; }
QFrame#PreferencesSidebar { background: #0D0D0F; border: none; border-right: 1px solid #29292D; }
QPushButton#NavigationItem { background: transparent; border: 1px solid transparent; border-radius: 7px; padding: 0; text-align: left; }
QLabel#NavigationTitle { color: #A1A1AA; font-size: 13pt; }
QPushButton#NavigationItem:hover { background: #18181B; }
QPushButton#NavigationItem:checked { background: #202023; }
QLabel#NavigationTitle[active="true"], QLabel#NavigationCount[active="true"] { color: #F4F4F5; }
QPushButton#NavigationItem:focus { border-color: #72727D; }
QLabel#NavigationCount { color: #A1A1AA; font-size: 11pt; }
QLabel#Heading { font-size: 21pt; font-weight: 600; }
QLabel#Subtitle { font-size: 12pt; color: #A1A1AA; }
QFrame#ShortcutSearch { background: #141416; border: 1px solid #303034; border-radius: 8px; }
QFrame#ShortcutSearch[focused="true"] { border-color: #72727D; }
QLineEdit#ShortcutSearchInput { background: transparent; border: none; font-size: 13pt; padding: 6px 0; color: #F4F4F5; selection-background-color: #44444C; }
QScrollArea#PreferencesScroll, QWidget#PreferencesBody, QWidget#ShortcutSections { background: #101012; border: none; }
QLabel#Section { color: #90909B; font-size: 10pt; font-weight: 500; padding: 0 4px; }
QFrame#ShortcutGroup { background: #141416; border: 1px solid #2B2B30; border-radius: 10px; }
QFrame#ShortcutRow { background: transparent; border: none; border-bottom: 1px solid #2B2B30; }
QFrame#ShortcutRow[last="true"] { border-bottom: none; }
QLabel#ActionTitle { color: #F4F4F5; font-size: 13pt; font-weight: 500; }
QLabel#Description { color: #A1A1AA; font-size: 11pt; }
QLabel#ModifiedDot { color: #60A5FA; font-size: 9pt; }
QPushButton#ShortcutRecorder { background: transparent; border: 1px solid transparent; border-radius: 6px; padding: 0; }
QPushButton#ShortcutRecorder:hover { background: #202024; }
QPushButton#ShortcutRecorder:focus { border-color: #72727D; }
QPushButton#ShortcutRecorder[recording="true"] { background: #23232A; border-color: #A1A1AA; }
QLabel#Keycap { background: #232326; color: #F4F4F5; border: 1px solid #3C3C42; border-bottom: 2px solid #46464D; border-radius: 6px; padding: 0 6px; font-size: 11pt; }
QLabel#RecorderMessage { color: #A1A1AA; font-size: 11pt; }
QPushButton#ClearShortcut { background: transparent; color: #A1A1AA; border: 1px solid transparent; padding: 0; font-size: 16pt; }
QPushButton#ClearShortcut:hover { background: #26262B; color: #F4F4F5; }
QPushButton#ChooseShortcut { background: transparent; color: #A1A1AA; border: 1px solid #303034; font-size: 10pt; padding: 5px 7px; }
QPushButton#ChooseShortcut:hover { color: #F4F4F5; background: #232326; }
QLabel#InlineFeedback { font-size: 10pt; }
QLabel#PreferencesError { color: #FF766D; padding: 8px 28px; font-size: 11pt; }
QLabel#PreferencesHint { color: #A1A1AA; padding: 6px 28px 12px; font-size: 10pt; }
QLabel#EmptyShortcuts { color: #A1A1AA; font-size: 12pt; }
QFrame#PreferencesFooter { background: #0D0D0F; border: none; border-top: 1px solid #29292D; }
QLabel#PendingChanges { color: #A1A1AA; font-size: 10pt; }
QPushButton#ResetPreferences, QPushButton#CancelPreferences { color: #D4D4D8; border: 1px solid transparent; background: transparent; padding: 7px 8px; }
QPushButton#ResetPreferences { font-size: 10pt; }
QPushButton#ResetPreferences:hover, QPushButton#CancelPreferences:hover { background: #202023; }
QPushButton#ApplyButton { background: #F4F4F5; color: #101012; border: 1px solid #F4F4F5; border-radius: 7px; padding: 8px 18px; font-size: 12pt; font-weight: 500; }
QPushButton#ApplyButton:hover { background: #D4D4D8; }
QPushButton#ApplyButton:disabled { background: #303034; border-color: #303034; color: #A1A1AA; }
QPushButton:focus { border-color: #A1A1AA; }
'''



PREFERENCES_QSS += """
QFrame#PreferencesSeparator { background: #2B2B30; border: none; }
QPushButton#NavigationItem { color: #A1A1AA; padding: 8px; }
QPushButton#NavigationItem:checked { color: #F4F4F5; }
"""
