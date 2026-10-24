#!/bin/sh
# Runs as the original desktop user, including when installation needs elevation.
# No dependency on the interpreter or files inside the installed application.
set -u
parent_pid=$1
folder=$2
result=$3
transaction=$4
privileged_command=$5
shift 5
umask 077
remaining=60
while kill -0 "$parent_pid" 2>/dev/null; do
    remaining=$((remaining - 1))
    if [ "$remaining" -eq 0 ]; then
        printf '%s\n' 'Não foi possível encerrar o ClipX. A atualização foi cancelada.' > "$result"
        exit 1
    fi
    sleep 1
done
code=0
if [ -n "$privileged_command" ]; then
    /usr/bin/osascript -e 'on run argv' -e 'do shell script (item 1 of argv) with administrator privileges' -e 'end run' "$privileged_command" || code=$?
else
    /bin/sh "$transaction" || code=$?
fi
if [ "$code" -eq 0 ]; then
    printf '%s\n' 'Atualização instalada. O ClipX foi reiniciado.' > "$result"
else
    printf '%s\n' 'Não foi possível instalar a atualização ou a autorização foi cancelada. Verifique a instalação e tente novamente; você também pode baixar o instalador.' > "$result"
    if [ -f "$folder/helper.log" ]; then
        cp "$folder/helper.log" "$(dirname "$result")/update-install.log"
    fi
fi
# Relaunch as the desktop user; never run the GUI through pkexec/administrator.
"$@" >/dev/null 2>&1 &
rm -rf "$folder"
