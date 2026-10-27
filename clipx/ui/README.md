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


## Imagens no histórico

`clipx/images.py` centraliza decodificação do primeiro quadro, mensagens de falha,
identidade dos pixels e conversão para PNG. `clipx/storage.py` migra a propriedade
do arquivo (`external`/`managed`), referencia originais e grava PNGs sem origem em
`images/`, ao lado do banco. Um registro `managed_images` identifica exclusivamente os arquivos criados pelo
ClipX e reserva seus caminhos antes da gravação, permitindo recuperar interrupções.
Um lock de arquivo coordena processos; a limpeza após
commit ou rollback remove temporários interrompidos e PNGs próprios sem referências.
O banco guarda caminhos, propriedade e hashes, sem imagens ou thumbnails.

`ui/models/image_preview.py` faz stat e decodificação limitada em QRunnable.
`PreviewPaneWidget` revalida a seleção no timer existente, inclusive quando a linha
do banco não mudou, e descarta respostas de seleções antigas. Mudanças de arquivo,
permissões e restauração invalidam o cache. O pixmap existe apenas na memória e se
ajusta sem recorte; o caminho é abreviado visualmente, com tooltip completo.

`ClipboardService.copy_async` carrega e publica pixels em segundo plano. Texto
também usa worker no Linux, sinalizado por `ClipboardDriver.background_copy`;
texto no macOS mantém seu fluxo síncrono. Somente cópias bem-sucedidas atualizam a recência, sem
recriar entradas excluídas durante a operação. A janela e a bandeja usam o mesmo
serviço e o mesmo alerta temático. O alerta exibe um título no corpo para manter a
identificação também no macOS, onde títulos de QMessageBox podem ser omitidos.

macOS prioriza URLs locais e ignora o marcador privado do ClipX. X11 negocia TARGETS,
priorizando listas de arquivos sobre imagens e texto, e mantém INCR. Wayland usa
um único `wl-paste --watch` sem filtro exclusivo de texto; o helper compara o payload
do evento com uma nova leitura após buscar a representação preferida e descarta
mudanças concorrentes. Linux compara hashes de pixels publicados pelo próprio
ClipX entre processos para suprimir ecos; o marcador é substituído na próxima cópia
e esquecido ao capturar outro conteúdo. Pixels idênticos ao último conteúdo publicado
são considerados um eco até uma mudança de conteúdo ser observada.

Para reproduzir preview, indisponibilidade e alerta claro/escuro, inclusive na janela
mínima a 150%, sem tocar no clipboard do usuário:

```bash
.venv/bin/python tools/render_images.py
```

As fixtures ficam em `artifacts/images-*.png`. Testes de persistência, concorrência,
serviço, protocolo X11, eventos Wayland e interface estão em `tests/test_images.py`.
O teste nativo de pasteboard de imagens está em `tests/test_macos_native.py` e usa
um pasteboard privado com `CLIPX_TEST_MACOS=1`. Validação real X11/Wayland permanece
dependente de uma sessão Linux disponível.


Validação de imagens em 26/10/2026: suíte com 172 testes (159 aprovados e 13
ignorados por dependências/opt-in), mais dois testes nativos de pasteboard macOS
aprovados separadamente, incluindo escrita de imagem em worker. As seis fixtures
visuais foram renderizadas; preview, indisponibilidade, alertas claro/escuro e
mínimo ampliado foram inspecionados. Sessões nativas Linux não estavam disponíveis.


## Ativação e colagem no GNOME/Wayland

`LinuxDesktopDriver` mantém o ID de startup separado do token de ativação nativo.
A instância secundária encaminha ambos por IPC; a instância principal termina o
anúncio com `remove` após mostrar a pesquisa ou as preferências. Falhas de abertura,
falhas no encaminhamento e encerramento antecipado também concluem o anúncio.
Tokens XDG nativos nunca são interpretados como IDs de startup. Os helpers de cópia
e de colagem recebem um ambiente sem `DESKTOP_STARTUP_ID`/`XDG_ACTIVATION_TOKEN`.

A janela mantém uma geração de foco para cancelar timers de colagem após reabrir
ou reativar a pesquisa. Depois de uma breve espera de 100 ms para o compositor,
aguarda ocultação e perda de foco por até um segundo. O desktop usa um Event para
cancelar a ferramenta em execução; um QObject persistente entrega resultados no
thread Qt, mesmo se o worker já terminou. Teclas já entregues ao sistema não podem
ser desfeitas por um cancelamento posterior.

GNOME/Wayland é detectado pela sessão, independentemente de `DISPLAY`, e usa
`ydotool`. Outros ambientes mantêm `wtype` com fallback em falha, timeout ou ausência.
Cada helper tem timeout de dois segundos e pode ser terminado quando a pesquisa
voltar a receber foco. A indisponibilidade preserva o clipboard e gera feedback
para colagem manual. `tests/test_linux_copy.py` cobre protocolo, IPC, ambiente,
responsividade, foco, cancelamento, fallback e entrega dos resultados via Qt.


Validação desta correção em 26/10/2026: 197 testes executados, com 184 aprovados
e 13 ignorados por dependências/opt-in. Inclui um processo auxiliar real sem
interação com o desktop, testes de cópia lenta com o event loop ativo e IPC em
socket local. `git diff --check` passou. Não havia sessão GNOME/Ubuntu Wayland
nativa disponível para confirmar o cursor ou a colagem em aplicativos Wayland e
XWayland; essa verificação permanece pendente. Não foram alterados serviços ou
permissões do sistema e não foi criado commit ou release.

## Dados e desinstalação

`ui/organisms/maintenance_page.py` apresenta as ações imediatas fora do rascunho de
Preferências: categoria Dados/Imagens/Tudo, comportamento sobras/conteúdo, proteção
de fixados, análise e confirmação. As tarefas executam em QThread, com progresso,
resultado persistente na tela e fechamento protegido enquanto o worker está ativo.
O prune atualiza a lista, prévia e bandeja sem alterar preferências ou clipboard.

`clipx/maintenance.py` implementa o serviço compartilhado com a CLI, sem instanciar
Storage na análise. A coleta explícita respeita a categoria, confirma as exclusões
de registros antes de remover PNGs e deixa falhas de arquivo recuperáveis por retry.
`clipx/maintenance_lock.py` coordena gravações, observadores, atualizações e processos
por conta do sistema. A observação permanece ativa durante prune, descartando eventos
que chegam enquanto as gravações estão pausadas, sem reiniciar os contadores nativos.

`clipx/uninstall.py` prepara o runtime independente, encerra processos registrados,
limpa os diretórios conhecidos e delega a remoção da instalação à plataforma. O
resultado final usa ferramentas do sistema, pois o app original já terá encerrado.
Os testes de segurança e persistência estão em `tests/test_maintenance.py`; os testes
da página e confirmação estão em `tests/test_ui_preferences.py`.

A página usa a referência visual fornecida em React: painel de limpeza com
seletores segmentados e ícones, toggle de fixados, ações lado a lado e zona de perigo
separada com cores semânticas nos dois temas. As categorias continuam sendo Tudo,
Dados e Imagens; os comportamentos continuam sobras ou conteúdo. A análise habilita
a limpeza somente para a seleção atual; trocar categoria, comportamento ou fixados
invalida a estimativa. A confirmação recalcula os alvos antes de executar.

`ui/molecules/segmented_select.py` mantém seleção exclusiva, um ponto de tabulação
por grupo e navegação por setas/Home/End. `ui/molecules/toggle.py` preserva o estado,
o teclado e a acessibilidade nativa de QCheckBox ao desenhar o switch. Em larguras
menores, os comportamentos e as ações se empilham e o botão de desinstalação quebra
seu texto, mantendo a rolagem vertical.

As prévias da página são reproduzíveis com
`.venv/bin/python tools/render_preferences.py --maintenance` e ficam em
`artifacts/preferences-{dark,light}-maintenance.png`. A revisão visual incluiu os
dois temas e a janela mínima de 820 × 580 a 150%, sem rolagem horizontal.

As descrições das opções reservam a altura da maior variante na largura e fonte
atuais; o status reserva ao menos duas linhas. Isso evita deslocar os painéis e
alternar a rolagem quando o texto muda. Trocar opções atualiza somente os ícones
das categorias cuja seleção mudou, sem reaplicar a aparência ao restante da página.
O reset de fixados ao voltar para sobras bloqueia o sinal interno para não executar
a mesma atualização duas vezes. Mudanças reais de tema/escala continuam recalculando
a apresentação e a quebra de linhas.

Validação desta correção em 27/10/2026: teste de regressão de geometria falhou antes
da correção e passou depois; suíte com 226 testes, 214 aprovados e 12 ignorados.
Em Cocoa nativo, 72 combinações de seleção, tema, escala (100%/150%) e tamanho
(820 × 580, 900 × 760, 1040 × 820) mantiveram posições dos botões/painéis e faixa de
rolagem estáveis entre opções. A mensagem de timeout do serviço TSM relatada não
foi reproduzida nessa execução; sua relação com o sintoma não foi confirmada.

### Confirmações de manutenção

`ui/organisms/maintenance_confirmation.py` separa o resumo da operação da sua
apresentação. Os factories de prune e desinstalação descrevem efeitos e itens
preservados conforme categoria, modo e fixados, sem alterar o serviço de limpeza.
O modal usa título com ícone, lista de efeitos, lista de preservação, detalhes
monoespaçados selecionáveis e botão destrutivo preenchido. A janela de Preferências
fica escurecida enquanto a confirmação está aberta; o sombreado é removido ao sair.

Cancelar é o foco e a ação padrão inicial. Esc, X e Cancelar rejeitam a confirmação;
Enter só confirma depois de focar explicitamente o botão destrutivo. Os detalhes
longos têm quebra de linha e rolagem, mantendo as ações visíveis em escala ampliada.
Os resumos de sobras descrevem compactação/coleta de órfãos, preservando a distinção
em relação a apagar conteúdo. Valores, fixados e caminhos vêm da análise real.

Prévias com dados fictícios são reproduzíveis com
`.venv/bin/python tools/render_preferences.py --confirmations`, gerando
`artifacts/confirmation-{dark,light}-{prune,uninstall}.png`. Os cinco testes em
`tests/test_maintenance_confirmation.py` passaram também em Cocoa nativo, cobrindo
fechamento, aceitação explícita, teclado, escopo dos resumos e caminhos longos em 150%.

### Progresso e encerramento na desinstalação

`ui/organisms/uninstall_progress.py` executa no runtime independente do helper e
mantém visíveis as etapas após encerrar a aplicação original. O indicador da página
permanece ativo durante preparação/passagem ao helper, com rolagem até o progresso.
O sinal `helper-ready` permite à interface pedir seu próprio `QApplication.quit()`;
a proteção de fechamento das Preferências libera apenas esse encerramento planejado.
O worker aguarda o PID/identidade original terminar antes de adquirir a barreira e
apagar dados. Um registro de processo ausente não permite pular essa verificação.

O progresso é indeterminado durante o trabalho, apresenta o resultado verificado e
fecha sozinho no sucesso. Falhas mantêm a janela e o relatório disponíveis. Sair
durante a operação é bloqueado; código de saída zero sem confirmação de passagem
não produz uma mensagem de conclusão. O supervisor evita repetir o resultado já
apresentado pela interface independente.

Validação em 27/10/2026: suíte de 238 testes (226 aprovados/12 ignorados), mais três
testes da janela de progresso em Cocoa. Uma integração nativa com dois processos
confirmou a ordem janela pronta → GUI original encerrada → dados isolados removidos
→ helper fechado, inclusive sem registro da GUI original. A área de transferência
foi substituída por um mock; nenhum dado pessoal foi usado nessa validação.
