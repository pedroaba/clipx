"""Presentation metadata for existing shortcut actions, without widget dependencies."""
from dataclasses import dataclass
from clipx.shortcuts import SHORTCUTS


@dataclass(frozen=True)
class ShortcutSpec:
    name: str
    title: str
    description: str
    category: str


DESCRIPTIONS = {
    'copy': 'Cola o item no aplicativo anterior.',
    'pin': 'Mantém clips importantes no topo.',
    'delete': 'Remove o item selecionado do histórico.',
    'delete_alt': 'Segunda combinação para remover um item.',
    'filter': 'Alterna entre texto, código, links, cores e fixados.',
    'close': 'Fecha a pesquisa e mantém o ClipX na bandeja.',
    'previous': 'Seleciona o item anterior da lista.',
    'next': 'Seleciona o próximo item da lista.',
}
CATEGORIES = (('all', 'Todos', 'command'), ('system', 'Sistema', 'globe'),
              ('search', 'Pesquisa', 'command'), ('filters', 'Filtros', 'filter'))
CATALOG = (ShortcutSpec('global', 'Abrir pesquisa',
                       'Funciona em qualquer aplicativo, com a pesquisa fechada.', 'system'),) + tuple(
    ShortcutSpec(name, title, DESCRIPTIONS[name], 'filters' if name == 'filter' else 'search')
    for name, (title, _) in SHORTCUTS.items())

CONFLICT_NAMES = {
    'switch-input-source': 'Trocar idioma do teclado',
    'switch-input-source-backward': 'Trocar idioma do teclado (sentido inverso)',
    'switch-applications': 'Alternar aplicativos',
    'toggle-message-tray': 'Abrir central de notificações',
}
