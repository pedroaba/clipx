# Builds e instaladores do ClipX

O mesmo empacotador é usado localmente e no GitHub Actions. PyInstaller inclui Python,
Qt, fontes, ícones e os módulos de captura; o computador de destino não precisa de uv
nem de um interpretador Python instalado.

| Artefato | Ambiente de build | Destino |
| --- | --- | --- |
| `clipx_VERSION_amd64.deb` | Docker Ubuntu 24.04, amd64 | Ubuntu 24.04+ / Debian 13+, x86-64 |
| `clipx_VERSION_arm64.deb` | Docker Ubuntu 24.04, arm64 | Ubuntu 24.04+ / Debian 13+, ARM64 |
| `ClipX-VERSION-macos-arm64.dmg` | macOS nativo, Apple Silicon | macOS 14+, Apple Silicon |
| `ClipX-VERSION-macos-amd64.dmg` | macOS nativo, Intel | macOS 14+, Intel |

Docker Desktop no Mac executa containers Linux. Ele testa e gera os DEBs, mas não gera
um `.app` macOS válido. O DMG exige macOS e as ferramentas Apple. Não há serviço
Compose simulando um build macOS. A compatibilidade final em versões antigas de macOS
e em desktops Linux reais ainda exige teste nesses sistemas.

## Validar Linux pelo Compose

Com o Docker Desktop/Engine iniciado, na raiz do projeto:

```bash
mkdir -p dist
export BUILD_UID="$(id -u)" BUILD_GID="$(id -g)"
docker compose build linux-build
docker compose --profile test run --rm linux-test
docker compose run --rm linux-build
docker compose --profile test run --rm linux-install-test
```

O padrão é `linux/amd64`, inclusive em Apple Silicon, onde a emulação pode ser lenta.
Para testar ARM64, defina `export BUILD_PLATFORM=linux/arm64` antes dos comandos.
Reconstrua a imagem após alterar código: ela contém uma cópia do projeto, sem montar
ou reutilizar a `.venv` do host. O único diretório compartilhado é `dist/`.

O serviço `linux-install-test` inicia um Ubuntu limpo, instala o DEB com suas
bibliotecas de sistema, executa a verificação do binário e remove o pacote. Não usa o
Python do builder. Os testes de captura usam texto fictício e banco temporário,
sem conectar ao clipboard ou à sessão gráfica do host.

O DEB inclui o executável em `/opt/clipx`, launcher em `/usr/bin/clipx`, ícone e entrada
do menu. Não modifica atalhos, serviços ou preferências de usuários durante a instalação.
Para instalar em um desktop Ubuntu/Debian compatível:

```bash
sudo apt install ./dist/clipx_0.1.0_amd64.deb
clipx
```

Ajuste a versão/arquitetura no nome. Abra Preferências → Atalhos para escolher a
combinação global no GNOME. A instalação não configura inicialização automática;
`clipx tray` inicia somente na bandeja. GNOME precisa de suporte a AppIndicator;
Wayland depende de data-control. Colagem automática usa wtype/ydotool quando disponíveis.

## Gerar o DMG no Mac

```bash
uv sync --frozen --group build --python 3.14.6
uv run --frozen --group build python tools/release.py test
uv run --frozen --group build python tools/release.py macos
```

A saída em `dist/` contém o DMG da arquitetura nativa e um manifesto SHA-256. Monte o
DMG e arraste `ClipX.app` para Applications. O ícone, identificador estável, nome e
versão são incluídos no bundle. O executável também suporta `--version`, `show`,
`tray` e os comandos de histórico; o modo interno `_capture` permite iniciar o worker
sem depender de `python -m` no computador do usuário.

Cada build executa `--version` e `_self-test` no binário congelado. O smoke test verifica
SQLite, subprocesso de captura, carregamento de fontes/ícones e os temas/Preferências
em Qt offscreen. O DMG é verificado, montado somente para leitura e o teste é repetido
no executável dentro dele. Isso não substitui os testes de permissões e colagem em uma
sessão gráfica real. O DEB também é extraído e tem seu executável testado.

## GitHub Actions

`.github/workflows/release.yml` executa em PRs, pushes para `main`, tags `v*` e manualmente.
A matriz contém Linux amd64/arm64 via Compose e macOS Apple Silicon/Intel via runners
nativos. Em PRs e branches, apenas gera e armazena os instaladores como artifacts.

Em uma tag, todos os builds e testes devem passar. Um job final confere os checksums e
cria a release com os quatro instaladores. Não é necessário um PAT: usa `GITHUB_TOKEN`
com escrita de conteúdo somente no job de publicação. Nenhuma release foi publicada
pela configuração local.

Para uma versão nova:

1. Altere `project.version` em `pyproject.toml` e execute `uv lock`.
2. Faça commit e push; a versão do aplicativo é lida dos metadados do pacote.
3. Crie e envie uma tag idêntica, por exemplo `v0.1.0` para a versão `0.1.0`.
4. Acompanhe **Actions → Build installers and release**.

Tags divergentes da versão interrompem o build. Reexecutar a publicação de uma release
já existente falha em vez de substituir os arquivos publicados silenciosamente.
Opcionalmente configure a variável de repositório `DEB_MAINTAINER` com o contato real do
mantenedor; sem ela, o pacote de teste usa um endereço explicitamente inválido.

## Assinatura e notarização Apple

### Distribuição gratuita (padrão)

Os DMGs usam assinatura ad-hoc do PyInstaller, **sem Developer ID e sem conta paga
da Apple**. Esse modo também pode ser usado nas releases públicas. Assinatura ad-hoc
valida a integridade do bundle, mas não identifica o desenvolvedor perante a Apple.
Os aplicativos não são notarizados e o macOS pode bloquear sua abertura inicial ou
solicitar autorização novamente após uma atualização.

Para instalar, monte o DMG, arraste ClipX.app para Applications e tente abri-lo.
Se houver bloqueio e você confiar no instalador obtido nas releases oficiais, abra
**Ajustes do Sistema → Privacidade e Segurança → Abrir Mesmo Assim** e confirme.
O arquivo `Instalar.txt` no DMG inclui essas instruções; as releases também informam
o modo de distribuição. Consulte o [procedimento oficial da Apple](https://support.apple.com/102445).

O atualizador aceita bundles ad-hoc e mantém a validação de checksum, identidade,
versão e assinatura. Não remove quarentena nem desativa o Gatekeeper. Developer ID
e notarização são opcionais, fora dos requisitos da distribuição gratuita.

### Developer ID e notarização (opcionais)

Para usar a identidade de desenvolvedor reconhecida pela Apple e notarizar o app,
é necessário um certificado Developer ID Application e acesso ao Apple Developer
Program. Esse caminho não é necessário para gerar ou publicar as releases ad-hoc.

Cadastre os seguintes **secrets** no repositório, sem colocar valores no código:

| Secret | Conteúdo |
| --- | --- |
| `MACOS_CERTIFICATE_P12` | Certificado Developer ID Application com chave privada, em P12 codificado em base64 |
| `MACOS_CERTIFICATE_PASSWORD` | Senha do P12 |
| `MACOS_SIGNING_IDENTITY` | Nome completo da identidade Developer ID Application |
| `APPLE_ID` | Apple ID habilitado para notarização |
| `APPLE_TEAM_ID` | Team ID da conta Apple Developer |
| `APPLE_APP_PASSWORD` | Senha específica de aplicativo para notarytool |

Em tags, se o certificado estiver configurado, o workflow importa-o para um chaveiro
CI temporário. PyInstaller assina o bundle com hardened runtime; o empacotador envia
app e DMG para notarização e anexa os tickets. O chaveiro é removido no passo de
limpeza, inclusive após falhas. Certificado/credenciais parciais causam erro em vez de
publicar um instalador supostamente notarizado. PRs nunca importam os certificados.

Para testar localmente a assinatura, instale seu certificado no chaveiro, configure as
variáveis de ambiente correspondentes e execute:

```bash
uv run --frozen --group build python tools/release.py macos --notarize
```

Assinatura Developer ID e notarização só podem ser verificadas com as credenciais reais;
o build local ad-hoc não comprova essas etapas. Não há credenciais Apple neste projeto.

## Instalação de atualizações pelo aplicativo

Releases estáveis públicas precisam manter os nomes dos quatro instaladores e
`SHA256SUMS-{linux|macos}-{amd64|arm64}.txt` produzidos pelo build. A verificação é
manual pela API pública do GitHub; não existe feed ou token adicional.

O helper `clipx/scripts/updates/supervisor.sh` é incluído explicitamente como recurso de runtime no PyInstaller.
Ele usa ferramentas do sistema, espera o processo principal encerrar e reabre o
ClipX como o usuário original. A substituição macOS usa staging no mesmo filesystem
e rollback do bundle; a instalação DEB usa APT via pkexec. Bibliotecas de runtime
injetadas pelo PyInstaller são removidas do ambiente dos comandos do sistema.
O DEB depende de `ca-certificates` e recomenda `pkexec`; sem este último, continua
disponível o download para instalação manual.

O smoke test verifica helper, página de atualizações sem consulta automática e
certificados HTTPS. Assinatura Developer ID/notarização continuam dependendo das
credenciais Apple; a atualização não remove quarentena nem contorna Gatekeeper.

## Fontes técnicas

- [PyInstaller: builds específicos por sistema](https://pyinstaller.org/en/stable/operating-mode.html)
- [PyInstaller: assinatura macOS](https://pyinstaller.org/en/stable/feature-notes.html#macos-binary-code-signing)
- [GitHub: runners disponíveis](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
- [uv no Docker](https://docs.astral.sh/uv/guides/integration/docker/)

## Validação local desta implementação

Em 21/10/2026 foram gerados e verificados de ponta a ponta o DMG macOS arm64 e o DEB
Linux amd64. O DMG foi montado e teve seu binário testado; o DEB foi instalado, executado
e removido em um container Ubuntu limpo. Ambos passaram no smoke test de subprocesso,
SQLite, socket local, recursos, driver e interface offscreen. O smoke macOS usa uma
pasteboard privada, sem ler/escrever o clipboard global. Checksums foram conferidos.

Suíte comum: 117 testes, com 106 aprovados/11 ignorados no macOS e 107 aprovados/10
ignorados no Linux. Separadamente, os 9 testes nativos macOS passaram. Compose foi
validado e o workflow passou no actionlint 1.7.12.

Na validação inicial acima, as variantes Linux arm64/macOS Intel e o workflow remoto
ainda não haviam sido executados. Posteriormente, a matriz das quatro arquiteturas
passou no GitHub Actions. Assinatura Developer ID e notarização não são utilizadas
na distribuição gratuita.
