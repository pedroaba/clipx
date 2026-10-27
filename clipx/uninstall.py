"""Uninstall from an independent temporary runtime, never from root's home.

Frozen builds copy their one-directory runtime before removing the installed
application. The OS-only supervisor displays the outcome and removes the copy.
Source runs retain the repository and interpreter.
"""
import argparse
import ast
import os
from pathlib import Path
import plistlib
import shlex
import shutil
import sqlite3
import subprocess
import sys
import tempfile

from clipx.maintenance import MaintenanceResult, validate_path
from clipx.maintenance_lock import activity, cleanup_runtime, stop_registered, process_identity, wait_for_process_exit
from clipx.platforms.paths import PlatformPaths
from clipx.update_install import native_environment


def data_roots(paths=None):
    include_temporaries = paths is None
    paths = paths or PlatformPaths()
    roots = [paths.data, paths.config]
    if paths.platform == 'darwin':
        roots += [paths.home / '.local/share/clipx', paths.home / '.config/clipx',
                  Path(os.environ.get('XDG_DATA_HOME', paths.home / '.local/share')) / 'clipx',
                  Path(os.environ.get('XDG_CONFIG_HOME', paths.home / '.config')) / 'clipx']
    if include_temporaries:
        for directory in Path(tempfile.gettempdir()).glob('clipx-update-*'):
            marker = directory / '.clipx-owned'
            try:
                validate_path(directory)
                validate_path(marker)
                if directory.is_dir() and marker.is_file() and marker.read_text() == 'update\n':
                    roots.append(directory)
            except OSError:
                continue
    return sorted({Path(os.path.abspath(root)) for root in roots}, key=str)


def installation(original=None, kind=None):
    original = Path(original or sys.executable).absolute()
    if kind is None:
        kind = ('macos' if sys.platform == 'darwin' else 'deb') if getattr(sys, 'frozen', False) else 'source'
    if kind == 'source':
        return kind, None
    if kind == 'macos':
        bundle = original.parents[2]
        validate_path(bundle, allow_root=True)
        if bundle.suffix != '.app' or original != bundle / 'Contents/MacOS/clipx' or str(bundle).startswith('/Volumes/'):
            raise OSError('Instale o ClipX em Applications antes de desinstalar pelo aplicativo.')
        with (bundle / 'Contents/Info.plist').open('rb') as stream:
            if plistlib.load(stream).get('CFBundleIdentifier') != 'org.clipx.ClipX':
                raise OSError('O bundle não pertence ao ClipX.')
        return kind, bundle
    if kind != 'deb' or original != Path('/opt/clipx/clipx'):
        raise OSError('A remoção integrada exige uma instalação DEB reconhecida.')
    result = subprocess.run(['dpkg-query', '-W', '-f=${db:Status-Status}', 'clipx'],
                            capture_output=True, text=True, timeout=10, env=native_environment())
    if result.returncode or result.stdout != 'installed':
        raise OSError('O pacote clipx não está instalado pelo gerenciador de pacotes.')
    return kind, Path('/opt/clipx')


def inventory(paths=None, original=None, kind=None):
    result = MaintenanceResult()
    for root in data_roots(paths):
        validate_path(root)
        if not root.exists():
            continue
        result.paths.append(str(root))
        # Do not follow symbolic links, including nested image references.
        for parent, directories, files in os.walk(root, followlinks=False):
            for name in files:
                file = Path(parent) / name
                if not file.is_symlink():
                    result.files += 1
                    result.bytes += file.stat().st_size
    _, app = installation(original, kind)
    if app:
        result.paths.append(str(app))
    return result


def clear_clipboard():
    if sys.platform == 'darwin':
        from AppKit import NSPasteboard
        NSPasteboard.generalPasteboard().clearContents()
        return
    commands = []
    if os.environ.get('WAYLAND_DISPLAY'):
        commands.append(['wl-copy', '--clear'])
    if os.environ.get('DISPLAY'):
        commands.append(['xclip', '-selection', 'clipboard', '-i'])
    if not commands:
        raise OSError('Sem sessão gráfica para limpar a área de transferência.')
    errors = []
    for command in commands:
        try:
            subprocess.run(command, input=b'', check=True, timeout=5, env=native_environment())
        except (OSError, subprocess.SubprocessError) as exc:
            errors.append(str(exc))
    if errors:
        raise OSError('Falha ao limpar a área de transferência: ' + '; '.join(errors))


def legacy_service(paths):
    unit = paths.home / '.config/systemd/user/clipx-daemon.service'
    if unit.exists():
        validate_path(unit)
        content = unit.read_text()
        if 'Description=ClipX Clipboard Manager and Tray' not in content or '/bin/clipx tray' not in content:
            raise OSError('Serviço clipx-daemon.service não reconhecido; remoção cancelada.')
    return unit


def disable_linux_service(paths):
    if legacy_service(paths).exists():
        subprocess.run(['systemctl', '--user', 'disable', '--now', 'clipx-daemon.service'],
                       check=True, capture_output=True, timeout=15, env=native_environment())


def remove_linux_integrations(paths):
    unit = legacy_service(paths)
    had_service = unit.exists()
    if had_service:
        unit.unlink()
        subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True,
                       capture_output=True, timeout=10, env=native_environment())
    launcher = paths.home / '.local/bin/clipx'
    if launcher.is_symlink():
        target = launcher.resolve()
        # The old script links only to the repository's bin/clipx launcher.
        if target.name == 'clipx' and target.parent.name == 'bin' and (target.parent.parent / 'pyproject.toml').is_file():
            launcher.unlink()
    desktop = paths.data.parent / 'applications/clipx.desktop'
    if desktop.exists():
        validate_path(desktop)
        if 'Name=ClipX\n' in desktop.read_text() and 'clipx' in desktop.read_text():
            desktop.unlink()
    if not shutil.which('gsettings') or not os.environ.get('DBUS_SESSION_BUS_ADDRESS'):
        if had_service or 'gnome' in os.environ.get('XDG_CURRENT_DESKTOP', '').lower():
            raise OSError('Sem acesso ao GNOME para remover o atalho do ClipX.')
        return
    schema = 'org.gnome.settings-daemon.plugins.media-keys'
    binding = '/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/clipx/'
    def settings(*args):
        return subprocess.run(['gsettings', *args], check=True, capture_output=True,
                              text=True, timeout=5, env=native_environment()).stdout.strip()
    available = settings('list-schemas').splitlines()
    if schema not in available:
        return
    bindings = ast.literal_eval(settings('get', schema, 'custom-keybindings').removeprefix('@as '))
    if binding in bindings:
        custom = schema + '.custom-keybinding:' + binding
        command = ast.literal_eval(settings('get', custom, 'command'))
        parts = shlex.split(command)
        if parts and Path(parts[0]).name == 'clipx':
            settings('set', schema, 'custom-keybindings', repr([item for item in bindings if item != binding]))
            settings('reset-recursively', custom)


def remove_app(kind, app):
    if kind == 'macos':
        validate_path(app, allow_root=True)
        if os.access(app.parent, os.W_OK) and os.access(app, os.W_OK):
            shutil.rmtree(app)
        else:
            command = shlex.join(['/bin/rm', '-rf', '--', str(app)])
            subprocess.run(['/usr/bin/osascript', '-e', 'on run argv', '-e',
                            'do shell script (item 1 of argv) with administrator privileges',
                            '-e', 'end run', command], check=True, timeout=180, env=native_environment())
    elif kind == 'deb':
        subprocess.run(['/usr/bin/pkexec', '/usr/bin/apt-get', '--assume-yes', 'purge', '--', 'clipx'],
                       check=True, timeout=180, env=native_environment())


def report(message):
    print(message, flush=True)


def execute(original, kind, exclude_pid=0, paths=None, progress=report, parent_pid=0, parent_identity=''):
    system_paths = paths is None
    paths = paths or PlatformPaths()
    result = MaintenanceResult()
    if parent_pid:
        progress('Aguardando o encerramento do ClipX e da captura…')
        # Shutdown handlers may still persist geometry or stop update workers.
        # Let them finish before acquiring the exclusive data barrier.
        wait_for_process_exit(parent_pid, parent_identity)
    # Hold the barrier until every deletion and package operation completes.
    with activity(exclusive=True, timeout=5):
        kind, app = installation(original, kind)
        roots = data_roots() if system_paths else data_roots(paths)
        for root in roots:
            validate_path(root)
        if kind == 'deb' and not Path('/usr/bin/pkexec').is_file():
            raise OSError('Instale pkexec para autorizar a remoção do DEB.')
        progress('Encerrando instâncias e captura…')
        # Disable restart before stopping the GUI/standalone daemon.
        if paths.platform == 'linux':
            disable_linux_service(paths)
        stop_registered(exclude=(exclude_pid,))
        progress('Limpando a área de transferência…')
        clear_clipboard()
        if paths.platform == 'linux':
            remove_linux_integrations(paths)
        progress('Apagando histórico, imagens próprias, bancos e preferências…')
        for root in roots:
            try:
                validate_path(root)
                if root.exists():
                    for parent, directories, files in os.walk(root, followlinks=False):
                        for name in (*directories, *files):
                            file = Path(parent) / name
                            if file.lstat().st_uid != os.getuid():
                                raise OSError(f'Arquivo pertence a outra conta: {file}')
                    sizes = [file.stat().st_size for file in root.rglob('*') if file.is_file() and not file.is_symlink()]
                    shutil.rmtree(root)
                    result.files += len(sizes)
                    result.bytes += sum(sizes)
            except OSError as exc:
                result.errors.append(str(exc))
        if result.errors:
            return result
        progress('Dados apagados. Removendo o aplicativo…')
        try:
            remove_app(kind, app)
        except (OSError, subprocess.SubprocessError) as exc:
            result.errors.append('Os dados foram apagados, mas o aplicativo permanece instalado: ' + str(exc))
        if result.ok and system_paths:
            try:
                cleanup_runtime()
            except (OSError, ValueError, KeyError) as exc:
                result.errors.append('Aplicativo e dados removidos; falha ao limpar runtime: ' + str(exc))
    return result


def prepare_helper(gui=False, values=None):
    """Copy the frozen runtime before promising that uninstall can start."""
    original = Path(sys.executable).absolute()
    kind, app = installation(original)
    if kind == 'deb' and not Path('/usr/bin/pkexec').is_file():
        raise OSError('Instale pkexec para autorizar a remoção do DEB.')
    if gui and sys.platform == 'linux' and not shutil.which('zenity'):
        raise OSError('Instale zenity para exibir o resultado da desinstalação.')
    folder = Path(tempfile.mkdtemp(prefix='clipx-uninstall-')).resolve()
    try:
        if kind == 'macos':
            copied = folder / 'ClipX.app'
            shutil.copytree(app, copied, symlinks=True)
            command = [str(copied / 'Contents/MacOS/clipx'), '_uninstall']
        elif kind == 'deb':
            copied = folder / 'runtime'
            shutil.copytree(app, copied, symlinks=True)
            command = [str(copied / 'clipx'), '_uninstall']
        else:
            command = [sys.executable, '-m', 'clipx.uninstall']
        command += ['--original', str(original), '--kind', kind]
        if gui:
            identity = process_identity(os.getpid())
            if not identity:
                raise OSError('Não foi possível identificar a instância que será encerrada.')
            values = values or {'theme': 'dark', 'scale': 100}
            command += ['--gui', '--helper-folder', str(folder), '--parent-pid', str(os.getpid()),
                        '--parent-identity', identity, '--theme', values['theme'], '--scale', str(values['scale'])]
        else:
            command += ['--exclude-pid', str(os.getpid())]
        script = folder / 'supervisor.sh'
        template = Path(__file__).parent / 'scripts/maintenance/supervisor.sh'
        shutil.copyfile(template, script)
        script.chmod(0o700)
        environment = native_environment()
        if kind == 'source':
            environment['PYTHONPATH'] = str(Path(__file__).resolve().parent.parent)
        return folder, ['/bin/sh', str(script), str(folder), 'gui' if gui else 'cli', *command], environment
    except BaseException:
        shutil.rmtree(folder)
        raise


def launch_helper(prepared, detached=False):
    folder, command, environment = prepared
    if detached:
        return subprocess.Popen(command, env=environment, cwd='/', start_new_session=True,
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return subprocess.run(command, env=environment, cwd='/', check=False).returncode


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--original', required=True)
    parser.add_argument('--kind', choices=('source', 'macos', 'deb'), required=True)
    parser.add_argument('--exclude-pid', type=int, default=0)
    parser.add_argument('--gui', action='store_true')
    parser.add_argument('--helper-folder', type=Path)
    parser.add_argument('--parent-pid', type=int, default=0)
    parser.add_argument('--parent-identity', default='')
    parser.add_argument('--theme', choices=('dark', 'light', 'system'), default='dark')
    parser.add_argument('--scale', type=int, choices=(100, 110, 125, 150), default=100)
    args = parser.parse_args()
    if args.gui:
        if args.helper_folder is None or not args.parent_pid or not args.parent_identity:
            parser.error('A interface do desinstalador exige a identificação da instância original.')
        from clipx.ui.organisms.uninstall_progress import run_uninstall_progress
        return run_uninstall_progress(args)
    try:
        result = execute(args.original, args.kind, args.exclude_pid,
                         parent_pid=args.parent_pid, parent_identity=args.parent_identity)
        print(result.summary(), flush=True)
        if result.ok:
            print('ClipX desinstalado. Repositório e interpretador preservados.' if args.kind == 'source' else 'ClipX desinstalado.', flush=True)
        return 0 if result.ok else 1
    except (OSError, ValueError, sqlite3.Error, subprocess.SubprocessError) as exc:
        print('Desinstalação interrompida: ' + str(exc), flush=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
