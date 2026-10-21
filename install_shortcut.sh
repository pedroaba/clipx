#!/usr/bin/env bash
set -e

if [[ "$(uname -s)" != "Linux" ]]; then
    echo "Este instalador é exclusivo do Linux/GNOME. No macOS, execute: uv sync && uv run clipx" >&2
    exit 1
fi
for tool in uv gsettings systemctl; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "Ferramenta obrigatória ausente: $tool" >&2
        exit 1
    fi
done
gsettings get org.gnome.settings-daemon.plugins.media-keys custom-keybindings >/dev/null
systemctl --user show-environment >/dev/null


REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_PATH="$REPO_DIR/bin/clipx"
USER_BIN="$HOME/.local/bin/clipx"

echo "=== Configurando ClipX para Ubuntu / GNOME com uv ==="

# 0. Sincroniza dependências com a versão mais recente do Python via uv
if command -v uv >/dev/null 2>&1; then
    echo "Sincronizando ambiente com uv (Python 3.14+)..."
    uv sync --frozen --project "$REPO_DIR"
    echo "✔ Dependências sincronizadas com sucesso via uv!"
fi

# 1. Cria link simbólico em ~/.local/bin/clipx
mkdir -p "$HOME/.local/bin"
ln -sf "$BIN_PATH" "$USER_BIN"
echo "✔ Link criado: $USER_BIN -> $BIN_PATH"

# Register the same desktop identity used by Qt/Wayland for window activation.
APPLICATIONS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$APPLICATIONS_DIR"
cat << EOF > "$APPLICATIONS_DIR/clipx.desktop"
[Desktop Entry]
Type=Application
Name=ClipX
Comment=Clipboard history manager
Exec="$BIN_PATH" show
Icon=$REPO_DIR/clipx/assets/branding/clipx-icon.png
Terminal=false
StartupNotify=true
StartupWMClass=ClipX
Categories=Utility;
EOF

# 2. Configura serviço em segundo plano (systemd user daemon)
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
mkdir -p "$SYSTEMD_USER_DIR"

cat << EOF > "$SYSTEMD_USER_DIR/clipx-daemon.service"
[Unit]
Description=ClipX Clipboard Manager and Tray
After=graphical-session.target
PartOf=graphical-session.target

[Service]
Type=simple
ExecStart=$BIN_PATH tray
Restart=on-failure
RestartSec=3

[Install]
WantedBy=graphical-session.target
EOF

systemctl --user daemon-reload || true
systemctl --user enable clipx-daemon.service || true
systemctl --user restart clipx-daemon.service || true
echo "✔ Serviço de background ativado: clipx-daemon.service"

# 3. Configura o atalho global sem sobrescrever a escolha do usuário
echo "Configurando atalho global no GNOME..."

BINDINGS=$(gsettings get org.gnome.settings-daemon.plugins.media-keys custom-keybindings)
NEW_PATH="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/clipx/"

# Adiciona o caminho caso ainda não exista na lista
if [[ "$BINDINGS" != *"$NEW_PATH"* ]]; then
    # Only use the default on first install. An empty existing binding is intentional.
    gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:$NEW_PATH binding "<Super>v"
    if [[ "$BINDINGS" == "@as []" || "$BINDINGS" == "[]" ]]; then
        gsettings set org.gnome.settings-daemon.plugins.media-keys custom-keybindings "['$NEW_PATH']"
    else
        MODIFIED_BINDINGS=$(echo "$BINDINGS" | sed "s/]/, '$NEW_PATH']/")
        gsettings set org.gnome.settings-daemon.plugins.media-keys custom-keybindings "$MODIFIED_BINDINGS"
    fi
fi

gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:$NEW_PATH name "ClipX Clipboard Manager"
gsettings set org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:$NEW_PATH command "$USER_BIN show"

echo "✔ Atalho global registrado no GNOME (combinação existente preservada)."
echo ""
echo "Tudo pronto! Use seu atalho global ou rode 'clipx' para abrir o histórico."
echo "Para mudar as combinações, abra Atalhos no menu da bandeja."
