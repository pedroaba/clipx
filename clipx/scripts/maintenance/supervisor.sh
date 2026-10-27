#!/bin/sh
# Runtime independent from the application being removed. Private output only.
set -u
umask 077
folder=$1
mode=$2
shift 2
code=0
"$@" > "$folder/result.log" 2>&1 || code=$?
if [ "$mode" = gui ] && [ ! -f "$folder/ui-result-shown" ]; then
    # A process exit alone is not evidence that the GUI completed its work.
    code=1
    message="A desinstalação não foi concluída. Consulte os detalhes em $folder/result.log"
    if [ "$(uname -s)" = Darwin ]; then
        /usr/bin/osascript -e 'on run argv' -e 'display dialog (item 1 of argv) buttons {"OK"} default button "OK" with title "ClipX"' -e 'end run' "$message" || true
    else
        zenity --info --title=ClipX --text="$message" || true
    fi
elif [ "$mode" != gui ]; then
    cat "$folder/result.log"
fi
if [ "$code" -eq 0 ]; then
    rm -rf "$folder"
else
    printf 'Detalhes preservados em %s/result.log\n' "$folder"
fi
exit "$code"
