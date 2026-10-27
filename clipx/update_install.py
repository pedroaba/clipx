"""Validate native installers and hand replacement to a detached OS-only helper.

The helper uses /bin/sh and native tools, so it keeps working after PyInstaller's
running files have been replaced. It never needs a system Python installation.
"""
from dataclasses import dataclass
import os
from pathlib import Path
import plistlib
import shlex
import shutil
import subprocess
import sys
from clipx.maintenance_lock import writer

from clipx.platforms.paths import PlatformPaths
from clipx.updates import UpdateError, architecture


def native_environment():
    """Keep PyInstaller's bundled libraries out of system installation tools."""
    environment = os.environ.copy()
    for key in ('LD_LIBRARY_PATH', 'DYLD_LIBRARY_PATH'):
        original = environment.get(key + '_ORIG')
        if original is None:
            environment.pop(key, None)
        else:
            environment[key] = original
    return environment


def run_checked(arguments, timeout=60):
    """Run validation without a shell, preserving useful diagnostic errors."""
    try:
        return subprocess.run(list(map(str, arguments)), check=True, capture_output=True,
                              text=True, timeout=timeout, env=native_environment()).stdout.strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise UpdateError('Não foi possível validar o instalador: ' + str(arguments[0])) from exc


@dataclass(frozen=True)
class PreparedInstall:
    """Paths owned by the detached helper once the application exits."""
    folder: Path
    result: Path
    restart: tuple
    transaction: Path
    privileged_command: str = ''


def macos_transaction(staged, destination, version, folder):
    """Build a transaction with sibling staging and rollback on replacement failure."""
    quote = shlex.quote
    script = Path(folder) / 'replace.sh'
    script.write_text('''#!/bin/sh
set -eu
''' + f'''source_app={quote(str(staged))}
destination={quote(str(destination))}
expected_version={quote(version)}
''' + '''parent=$(dirname "$destination")
transaction=$(mktemp -d "$parent/.clipx-update.XXXXXXXX")
previous="$transaction/previous.app"
replacement="$transaction/ClipX.app"
replaced=0
rollback() {
    code=$?
    if [ "$code" -ne 0 ] && [ -d "$previous" ]; then
        if [ "$replaced" -eq 1 ]; then rm -rf "$destination"; fi
        mv "$previous" "$destination" || exit 1
    fi
    rm -rf "$transaction"
    exit "$code"
}
trap rollback EXIT
/usr/bin/ditto "$source_app" "$replacement"
/usr/bin/codesign --verify --deep --strict "$replacement"
actual=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$replacement/Contents/Info.plist")
[ "$actual" = "$expected_version" ]
identity=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$replacement/Contents/Info.plist")
[ "$identity" = 'org.clipx.ClipX' ]
mv "$destination" "$previous"
mv "$replacement" "$destination"
replaced=1
/usr/bin/codesign --verify --deep --strict "$destination"
"$destination/Contents/MacOS/clipx" --version >/dev/null
''')
    script.chmod(0o700)
    return script


def prepare_install(installer, version, folder):
    """Validate a DEB or mounted DMG and stage the replacement before quitting."""
    folder = Path(folder).resolve()
    installer = Path(installer).resolve()
    result = PlatformPaths().data / 'update-result.txt'
    if sys.platform == 'darwin':
        destination = Path(sys.executable).resolve().parents[2]
        if destination.suffix != '.app' or str(destination).startswith('/Volumes/'):
            raise UpdateError('Instale o ClipX em Applications antes de atualizar.')
        mount = folder / 'mounted'
        mount.mkdir()
        run_checked(['hdiutil', 'verify', installer])
        run_checked(['hdiutil', 'attach', '-readonly', '-nobrowse', '-mountpoint', mount, installer])
        try:
            app = mount / 'ClipX.app'
            with (app / 'Contents/Info.plist').open('rb') as stream:
                info = plistlib.load(stream)
            if info.get('CFBundleIdentifier') != 'org.clipx.ClipX' or info.get('CFBundleShortVersionString') != version:
                raise UpdateError('A identidade ou versão do aplicativo não confere.')
            run_checked(['codesign', '--verify', '--deep', '--strict', app])
            # A Developer ID installation must retain the same signing team.
            current_signature = run_checked(['sh', '-c', '/usr/bin/codesign -dv "$1" 2>&1', 'codesign', destination])
            new_signature = run_checked(['sh', '-c', '/usr/bin/codesign -dv "$1" 2>&1', 'codesign', app])
            teams = lambda value: next((line.split('=', 1)[1] for line in value.splitlines() if line.startswith('TeamIdentifier=')), '')
            current_team = teams(current_signature)
            if current_team and current_team != 'not set':
                if teams(new_signature) != current_team:
                    raise UpdateError('O instalador não foi assinado pela mesma equipe do aplicativo atual.')
                run_checked(['spctl', '--assess', '--type', 'execute', app])
            output = run_checked([app / 'Contents/MacOS/clipx', '--version'])
            if output != f'ClipX {version}':
                raise UpdateError('A versão do executável não confere.')
            staged = folder / 'ClipX.app'
            run_checked(['ditto', app, staged])
        finally:
            try:
                run_checked(['hdiutil', 'detach', mount])
            except UpdateError:
                run_checked(['hdiutil', 'detach', '-force', mount])
        script = macos_transaction(staged, destination, version, folder)
        command = '' if os.access(destination.parent, os.W_OK) and os.access(destination, os.W_OK) else shlex.join(['/bin/sh', str(script)])
        return PreparedInstall(folder, result, ('/usr/bin/open', '-n', str(destination), '--args', 'tray'), script, command)

    if sys.platform != 'linux' or Path(sys.executable).resolve() != Path('/opt/clipx/clipx'):
        raise UpdateError('A instalação integrada requer o pacote DEB do ClipX.')
    installed = run_checked(['dpkg-query', '-W', '-f=${db:Status-Status} ${Architecture}', 'clipx'])
    if installed != f'installed {architecture()}':
        raise UpdateError('O ClipX não está instalado pelo gerenciador de pacotes nesta arquitetura.')
    fields = run_checked(['dpkg-deb', '--show', '--showformat=${Package}\n${Version}\n${Architecture}', installer]).splitlines()
    if fields != ['clipx', version, architecture()]:
        raise UpdateError('O pacote DEB não corresponde ao ClipX, versão ou arquitetura esperados.')
    script = folder / 'install.sh'
    script.write_text('#!/bin/sh\nexec /usr/bin/pkexec /usr/bin/apt-get --assume-yes install -- ' + shlex.quote(str(installer)) + '\n')
    script.chmod(0o700)
    return PreparedInstall(folder, result, ('/usr/bin/clipx', 'tray'), script)


@writer
def launch_install(prepared):
    """Start an unprivileged supervisor before normal Qt shutdown releases locks."""
    from clipx.maintenance_lock import inherited_activity
    prepared.result.parent.mkdir(parents=True, exist_ok=True)
    prepared.result.unlink(missing_ok=True)
    helper = prepared.folder / 'supervisor.sh'
    template = Path(__file__).parent / 'scripts' / 'updates' / 'supervisor.sh'
    shutil.copyfile(template, helper)
    helper.chmod(0o700)
    arguments = [str(helper), str(os.getpid()), str(prepared.folder), str(prepared.result),
                 str(prepared.transaction), prepared.privileged_command, *prepared.restart]
    try:
        with inherited_activity() as lease, (prepared.folder / 'helper.log').open('a') as log:
            subprocess.Popen(['/bin/sh', *arguments], env=native_environment(),
                             start_new_session=True, stdin=subprocess.DEVNULL,
                             stdout=log, stderr=log, pass_fds=(lease,))
    except OSError as exc:
        raise UpdateError('Não foi possível iniciar o instalador. O ClipX permanece aberto.') from exc


def read_install_result():
    """Consume a fixed, private outcome written by the previous helper."""
    path = PlatformPaths().data / 'update-result.txt'
    try:
        value = path.read_text()[:4096].strip()
        path.unlink()
        return value
    except OSError:
        return ''
