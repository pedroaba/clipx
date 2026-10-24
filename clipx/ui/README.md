# Interface e Atomic Design

A interface usa PyQt6 nas duas plataformas. Atomic Design organiza a composição visual; controladores e modelos de apresentação ficam em camadas complementares.

| Camada | Responsabilidade | Exemplos |
| --- | --- | --- |
| `foundations/` | Tokens, estilos e ícones compartilhados | `theme.py`, `preferences.py`, `icons.py` |
| `atoms/` | Elementos visuais básicos, sem fluxo de aplicação | Tecla individual, mensagem inline |
| `molecules/` | Pequenas composições com uma função | Sequência de teclas, gravador, linha de atalho, busca, navegação |
| `organisms/` | Blocos completos da interface | Sidebar, seções, rodapé, lista, prévia e menu da bandeja |
| `templates/` | Estrutura e distribuição das áreas da janela | Preferências em duas colunas, pesquisa com lista e detalhe |
| `pages/` | Composição concreta, diálogos e ciclo de vida da janela | Atalhos, seletor de combinação e pesquisa |
| `controllers/` | Coordenação de interações e integração com a aplicação | Gravação/aplicação de atalhos e controle da bandeja |
| `models/` | Metadados de apresentação sem dependência de widgets | Catálogo, descrições e categorias dos atalhos |

## Docstrings

Todos os módulos, classes, funções e métodos da interface seguem o
[Google Python Style Guide](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings),
com docstrings em inglês. Documente o comportamento real do componente,
incluindo sinais Qt, foco, ciclo de vida e efeitos colaterais.

## Dependências e limites

- Componentes básicos não importam páginas, controladores ou drivers nativos. Use sinais Qt para comunicar intenção.
- Moléculas compõem átomos e controles Qt; organismos compõem moléculas; templates distribuem blocos; páginas conectam a composição ao comportamento.
- Estilos e ícones têm uma fonte compartilhada em `foundations`. Os controles Qt básicos também são primitivas: não precisam de wrappers sem comportamento próprio.
- `foundations/fonts.py` registra Geist e Geist Mono incluídas em `clipx/assets/fonts`. `templates/window.py` oferece a estrutura reutilizável dos diálogos com controles nativos do sistema. A pesquisa usa um painel sem barra de título ou controles. `platforms/window_chrome.py` integra a cor da barra nativa dos diálogos ao tema; no macOS preserva os botões AppKit e aplica aparência escura. O painel da pesquisa habilita `WA_StyledBackground` para desenhar sua superfície sobre o vidro nativo.
- Persistência e integrações nativas continuam nos serviços, preferências e drivers existentes. O controlador da bandeja coordena navegação, mas a construção do menu fica em `organisms/tray_menu.py`.
- Ao mover um componente, atualize os consumidores e testes. Não mantenha arquivos de reexportação nos caminhos antigos.

## Selects

`molecules/select.py` fornece `Select`, com a API de `QComboBox` para itens, dados, sinais e navegação por teclado. O filtro de histórico e a escolha de tecla usam o mesmo componente. O menu Qt tem altura limitada com rolagem, destaque de seleção, hover e foco; não usa o menu compacto nativo do macOS. As barras de rolagem permanecem sem estilos personalizados.

## Tela de atalhos

`pages/shortcuts.py` compõe o template de preferências. `controllers/shortcuts.py` cuida da pausa/restauração do atalho global, validação, rascunho e aplicação com rollback em caso de falha. A página apresenta o seletor e a confirmação de conflitos.

O seletor manual de combinação apresenta prévia com `ShortcutKeycaps`, modificadores agrupados, o componente `Select` e rodapé de confirmação. O aviso para ⌘Space é preventivo: a integração macOS não altera os atalhos do Spotlight; a disponibilidade depende do registro nativo ao aplicar.

O catálogo deriva das ações existentes em `clipx/shortcuts.py`: nove entradas atualmente, incluindo o atalho global. As contagens são calculadas, sem números fixos copiados da referência visual. O filtro de pesquisa considera nome, descrição e combinação de teclas nos formatos Qt portátil e nativo.

Trocar de categoria ou pesquisar apenas oculta as linhas; não recria editores nem perde combinações do rascunho. As alterações são sinalizadas por linha e contadas no rodapé. Cancelar descarta o rascunho; aplicar mantém as verificações e a recuperação da integração global. O botão de reticências abre a escolha manual de combinações interceptadas pelo sistema.

## Prévia reproduzível

Na raiz do projeto:

```bash
uv run --frozen python tools/render_ui.py
uv run --frozen python tools/render_ui.py --native
```

O primeiro comando usa Qt offscreen; o segundo usa a sessão gráfica local. Ambos usam conteúdo fictício, banco temporário e backend de atalhos de prévia, sem registrar atalhos ou modificar o clipboard global. As imagens de janela normal, mínima, busca, vazio e gravação ficam em `artifacts/`.

## Preferências de interface

A bandeja abre `pages/preferences.py`, uma janela única com Aparência, Lista e prévia,
Janela e Atalhos. O acesso Atalhos abre diretamente essa seção; suas categorias usam
um filtro interno. Os gravadores, validações, pausa do global e rollback continuam
sob responsabilidade de `controllers/shortcuts.py`.

`clipx/preferences.py` valida cada opção do bloco `ui` em `settings.json`. Ausências
ou valores inválidos usam o padrão individual. UI e atalhos são gravados juntos por
substituição atômica, preservando campos desconhecidos. O bloco `window` guarda tamanho,
posição e divisão dos painéis. Preferências não alteram dados do histórico.

O rascunho sobrevive à troca de seção. Restaurar seção afeta somente a seção atual;
Cancelar descarta mudanças pendentes. Aplicar salva sem fechar e atualiza pesquisa,
menus e moldura sem reinício. Fechar com rascunho oferece aplicar, descartar ou continuar.
Erros de gravação mantêm o rascunho e a interface aplicada anteriormente.

`foundations/appearance.py` centraliza as paletas semânticas clara/escura, resolve os
estilos dos componentes e escala medidas a partir dos valores originais, sem acumular
multiplicações. A prévia usa tema de sintaxe adequado e tamanho de texto independente.
Em espaços estreitos, as linhas de preferências empilham rótulo e controle; o rodapé
mantém os botões em uma segunda linha. O conteúdo tem rolagem.

O macOS mantém a prioridade das opções de acessibilidade para material e movimento.
No Linux, material nativo fica indisponível no controle, com explicação. Acompanhar
sistema observa mudanças de tema do Qt. A pesquisa preserva as proteções para menus
e diálogos ao perder foco e limita posições restauradas à área visível de uma tela.

Prévia com dados fictícios e atalhos simulados:

```bash
uv run --frozen python tools/render_preferences.py
uv run --frozen python tools/render_preferences.py --native
```

As imagens `artifacts/preferences-*.png` cobrem as quatro seções nos dois temas e
janela mínima a 150%; `clipboard-*-scaled.png` mostra a pesquisa ampliada. O modo
nativo usa a sessão gráfica do host; não registra atalhos nem copia conteúdo.

A sidebar de Preferências usa SVGs oficiais Lucide locais: palette, panels-top-left, app-window e keyboard. Assets, origem e licença ficam em `clipx/assets/icons/lucide/`. Cor acompanha tema/seleção; tamanho acompanha a escala.

O foco da busca preserva o cursor e a seleção existentes ao reativar a janela. Selecionar toda a consulta é uma opção explícita, usada apenas na abertura da pesquisa. Os testes de janela cobrem digitação com ativações repetidas e edição no meio da consulta.

## Desempenho da busca

A lista reconcilia resultados por ID: preserva widgets inalterados, remove os que
saíram e cria somente entradas novas ou alteradas. Mudanças de preferências invalidam
a apresentação das linhas. A seleção e a rolagem são restauradas e a prévia recebe
um único sinal após a atualização, apenas quando seleção, dados ou preferências mudam.
Uma prévia idêntica não executa novamente o destaque de sintaxe.

Validação em 21/10/2026: 111 testes (101 aprovados, 10 ignorados). No cenário local
com 120 textos fictícios e 100 resultados visíveis, oito consultas progressivas
caíram de 45–77 ms por atualização para 1,6–1,9 ms, incluindo processEvents offscreen
sob cProfile. Essa medição descreve a fixture; não é garantia para qualquer histórico.

## Atualizações

`organisms/update_page.py` apresenta o estado do serviço compartilhado em
`clipx/updates.py`. `pages/preferences.py` adiciona a navegação Atualizações,
oculta Restaurar seção e resolve rascunhos antes de reiniciar. A página não
participa do rascunho de configurações e não consulta a rede ao abrir.

`controllers/tray.py` conecta Verificar atualizações à página e à consulta
explícita, além de coordenar a instalação após validar configurações pendentes.
O serviço pertence à QApplication: fechar o diálogo não interrompe operações.
Rede e validações executam em QThread com sinais de progresso/estado para a UI;
`clipx/update_install.py` prepara instaladores e inicia o helper separado.

## Identidade do aplicativo

`foundations/branding.py` fornece o PNG do projeto para janelas e QApplication,
separadamente do glifo monocromático da barra de menus. A imagem e o prompt de geração
ficam em `clipx/assets/branding/`. O README usa o mesmo arquivo.

`SystemDialog` identifica diálogos de configurações e sincroniza sua presença no Dock
pelo adaptador `platforms/dock.py`. No macOS, o processo assume a política Regular
quando há um diálogo visível e volta a Accessory após fechar o último, mantendo a
pesquisa como utilitário da barra de menus. O teste nativo cobre múltiplos diálogos.
O instalador Linux aponta o arquivo desktop para o ícone local do projeto.
