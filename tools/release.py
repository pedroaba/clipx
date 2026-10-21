"""Build, smoke-test and package the current OS; never cross-compile a macOS app."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def project_version():
    return tomllib.loads((ROOT / 'pyproject.toml').read_text())['project']['version']


def validate_tag(tag):
    expected = 'v' + project_version()
    if tag and tag != expected:
        raise ValueError(f'A tag {tag!r} precisa coincidir com {expected!r} do pyproject.toml.')


def architecture():
    machine = platform.machine().lower()
    names = {'x86_64': 'amd64', 'amd64': 'amd64', 'aarch64': 'arm64', 'arm64': 'arm64'}
    if machine not in names:
        raise ValueError(f'Arquitetura não suportada: {machine}')
    return names[machine]


def run(command, **kwargs):
    # Do not log command arguments: signing/notarization commands may contain credentials.
    print('Executando:', Path(str(command[0])).name, flush=True)
    return subprocess.run(list(map(str, command)), cwd=ROOT, check=True, **kwargs)


def retry_run(command, attempts=3, delay=15, **kwargs):
    # Managed macOS runners sporadically fail hdiutil with "Resource busy"
    # while diskimagesd/Spotlight hold resources; a retry usually succeeds.
    for attempt in range(attempts):
        try:
            return run(command, **kwargs)
        except subprocess.CalledProcessError as error:
            if attempt == attempts - 1:
                raise
            print(f'hdiutil falhou (código {error.returncode}); nova tentativa em {delay} s.', flush=True)
            time.sleep(delay)


def smoke(binary):
    environment = {**os.environ, 'QT_QPA_PLATFORM': 'offscreen'}
    run([binary, '--version'], env=environment, timeout=30)
    run([binary, '_self-test'], env=environment, timeout=90)


def freeze(work, macos):
    output = work / 'frozen'
    environment = {**os.environ, 'CLIPX_VERSION': project_version()}
    if macos:
        iconset = work / 'ClipX.iconset'
        iconset.mkdir()
        original = ROOT / 'clipx/assets/branding/clipx-icon.png'
        for size in (16, 32, 128, 256, 512):
            for scale in (1, 2):
                name = f'icon_{size}x{size}' + ('@2x' if scale == 2 else '') + '.png'
                run(['sips', '-z', size * scale, size * scale, original, '--out', iconset / name], stdout=subprocess.DEVNULL)
        icns = work / 'ClipX.icns'
        run(['iconutil', '-c', 'icns', iconset, '-o', icns])
        environment['CLIPX_ICNS'] = str(icns)
        environment.setdefault('MACOSX_DEPLOYMENT_TARGET', '14.0')
    run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
         '--distpath', output, '--workpath', work / 'pyinstaller', ROOT / 'packaging/clipx.spec'], env=environment)
    binary = output / ('ClipX.app/Contents/MacOS/clipx' if macos else 'clipx/clipx')
    smoke(binary)
    return output


def checksums(artifacts, output, suffix):
    path = output / f'SHA256SUMS-{suffix}.txt'
    entries = []
    for file in artifacts:
        with file.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        entries.append(f'{digest}  {file.name}\n')
    path.write_text(''.join(entries))
    return path


def linux_package(frozen, work, output):
    arch = architecture()
    version = project_version()
    stage = work / 'deb'
    (stage / 'opt').mkdir(parents=True)
    shutil.copytree(frozen / 'clipx', stage / 'opt/clipx', symlinks=True)
    for source, destination in (
        ('packaging/linux/clipx', 'usr/bin/clipx'),
        ('packaging/linux/clipx.desktop', 'usr/share/applications/clipx.desktop'),
        ('packaging/linux/postinst', 'DEBIAN/postinst'),
        ('packaging/linux/postrm', 'DEBIAN/postrm'),
    ):
        target = stage / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / source, target)
        target.chmod(0o644 if target.suffix == '.desktop' else 0o755)
    icon = stage / 'usr/share/icons/hicolor/256x256/apps/clipx.png'
    icon.parent.mkdir(parents=True, exist_ok=True)
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QImage
    image = QImage(str(ROOT / 'clipx/assets/branding/clipx-icon.png'))
    if image.isNull() or not image.scaled(256, 256, Qt.AspectRatioMode.KeepAspectRatio,
                                          Qt.TransformationMode.SmoothTransformation).save(str(icon)):
        raise RuntimeError('Não foi possível exportar o ícone Linux.')
    installed_size = sum(file.stat().st_size for file in stage.rglob('*') if file.is_file()) // 1024
    maintainer = os.environ.get('DEB_MAINTAINER', 'ClipX contributors <maintainers@example.invalid>')
    if '\n' in maintainer or '\r' in maintainer:
        raise ValueError('DEB_MAINTAINER inválido.')
    (stage / 'DEBIAN/control').write_text(f'''Package: clipx
Version: {version}
Section: utils
Priority: optional
Architecture: {arch}
Maintainer: {maintainer}
Installed-Size: {installed_size}
Depends: libc6 (>= 2.39), libglib2.0-0t64, libgssapi-krb5-2, libglib2.0-bin, libgl1, libegl1, libopengl0, libdbus-1-3, libfontconfig1, libfreetype6, libx11-6, libx11-xcb1, libxext6, libxrender1, libxi6, libsm6, libice6, libxcb1, libxcb-cursor0, libxcb-icccm4, libxcb-image0, libxcb-keysyms1, libxcb-render-util0, libxcb-xinerama0, libxcb-xkb1, libxkbcommon0, libxkbcommon-x11-0, libwayland-client0, libwayland-cursor0, libwayland-egl1, wl-clipboard, xclip
Recommends: desktop-file-utils
Suggests: gnome-shell-extension-appindicator, wtype, ydotool
Description: Histórico local da área de transferência
 Pesquisa, prévia, atalhos e preferências. Python e Qt incluídos.
''')
    artifact = output / f'clipx_{version}_{arch}.deb'
    run(['dpkg-deb', '--root-owner-group', '--build', stage, artifact])
    run(['dpkg-deb', '--info', artifact])
    # Execute the files extracted from the actual installer, not just the build tree.
    extracted = work / 'extracted'
    run(['dpkg-deb', '--extract', artifact, extracted])
    smoke(extracted / 'opt/clipx/clipx')
    checksums([artifact], output, f'linux-{arch}')
    return artifact


def notarize(app):
    identity = os.environ.get('MACOS_SIGNING_IDENTITY')
    credentials = [os.environ.get(key) for key in ('APPLE_ID', 'APPLE_TEAM_ID', 'APPLE_APP_PASSWORD')]
    if not identity:
        raise ValueError('Notarização requer MACOS_SIGNING_IDENTITY e certificado instalado no chaveiro.')
    if not all(credentials):
        raise ValueError('Configure APPLE_ID, APPLE_TEAM_ID e APPLE_APP_PASSWORD para notarizar.')
    with tempfile.TemporaryDirectory(prefix='clipx-notary-') as folder:
        archive = Path(folder) / 'ClipX.zip'
        if app.suffix == '.dmg':
            archive = app
        else:
            run(['ditto', '-c', '-k', '--keepParent', app, archive])
        result = run(['xcrun', 'notarytool', 'submit', archive, '--apple-id', credentials[0],
                      '--team-id', credentials[1], '--password', credentials[2], '--wait', '--output-format', 'json'],
                     capture_output=True, text=True)
        report = json.loads(result.stdout)
        if report.get('status') != 'Accepted':
            raise RuntimeError(f'Notarização recusada. ID da submissão: {report.get("id")}')
        run(['xcrun', 'stapler', 'staple', app])
        run(['xcrun', 'stapler', 'validate', app])


def macos_package(frozen, work, output, notarized):
    app = frozen / 'ClipX.app'
    run(['codesign', '--verify', '--deep', '--strict', app])
    if notarized:
        notarize(app)
    stage = work / 'dmg'
    stage.mkdir()
    run(['ditto', app, stage / 'ClipX.app'])
    (stage / 'Applications').symlink_to('/Applications')
    (stage / 'Instalar.txt').write_text('Arraste ClipX.app para Applications.\nRequer macOS 14 ou posterior.\n')
    artifact = output / f'ClipX-{project_version()}-macos-{architecture()}.dmg'
    retry_run(['hdiutil', 'create', '-volname', 'ClipX', '-srcfolder', stage, '-format', 'UDZO', '-ov', artifact])
    if os.environ.get('MACOS_SIGNING_IDENTITY'):
        run(['codesign', '--sign', os.environ['MACOS_SIGNING_IDENTITY'], '--timestamp', artifact])
    if notarized:
        notarize(artifact)
    retry_run(['hdiutil', 'verify', artifact])
    # A DMG is mounted read-only and its installed executable is exercised too.
    mount = work / 'mounted'
    retry_run(['hdiutil', 'attach', '-readonly', '-nobrowse', '-mountpoint', mount, artifact])
    try:
        smoke(mount / 'ClipX.app/Contents/MacOS/clipx')
    finally:
        # Retry with force: a failed detach leaves volumes behind that busy
        # the next image operation on the runner.
        try:
            retry_run(['hdiutil', 'detach', mount], attempts=2, delay=10)
        except subprocess.CalledProcessError:
            run(['hdiutil', 'detach', '-force', mount])
    checksums([artifact], output, f'macos-{architecture()}')
    return artifact


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', choices=('linux', 'macos', 'test'))
    parser.add_argument('--output', type=Path, default=ROOT / 'dist')
    parser.add_argument('--notarize', action='store_true')
    args = parser.parse_args()
    validate_tag(os.environ.get('RELEASE_TAG', ''))
    if args.notarize and args.target != 'macos':
        parser.error('--notarize está disponível somente para macos.')
    if args.target == 'test':
        run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'])
        return
    required = 'darwin' if args.target == 'macos' else 'linux'
    if sys.platform != required:
        parser.error(f'{args.target} precisa ser gerado no sistema nativo ({required}); use Docker para Linux.')
    if not re.fullmatch(r'\d+\.\d+\.\d+', project_version()):
        parser.error('A versão de release deve usar MAJOR.MINOR.PATCH.')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='clipx-build-') as temporary:
        work = Path(temporary)
        frozen = freeze(work, args.target == 'macos')
        artifact = (macos_package(frozen, work, output, args.notarize) if args.target == 'macos'
                    else linux_package(frozen, work, output))
        print('Instalador validado:', artifact)


if __name__ == '__main__':
    main()
