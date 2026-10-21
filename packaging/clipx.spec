# Build on the target OS. One-directory output keeps startup and capture workers fast.
import os
from pathlib import Path
import sys
from PyInstaller.utils.hooks import collect_submodules, copy_metadata

root = Path(SPECPATH).parent
macos = sys.platform == 'darwin'
hidden = collect_submodules('clipx') + collect_submodules('pygments.lexers') + collect_submodules('pygments.styles')
if not macos:
    hidden += collect_submodules('Xlib')
a = Analysis(
    [str(root / 'packaging/entrypoint.py')], pathex=[str(root)],
    datas=[(str(root / 'clipx/assets'), 'clipx/assets'), *copy_metadata('clipx')],
    hiddenimports=hidden,
    excludes=['tkinter', 'PyQt5', 'PySide2', 'PySide6', 'IPython', 'pytest', 'yaml'],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name='clipx',
    debug=False, strip=False, upx=False, console=True,
    # stdout is required when the same executable runs as a capture subprocess.
    codesign_identity=os.environ.get('MACOS_SIGNING_IDENTITY') or None,
)
folder = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='clipx')
if macos:
    app = BUNDLE(
        folder, name='ClipX.app', icon=os.environ['CLIPX_ICNS'],
        bundle_identifier='org.clipx.ClipX',
        info_plist={
            'CFBundleName': 'ClipX', 'CFBundleDisplayName': 'ClipX',
            'CFBundleShortVersionString': os.environ['CLIPX_VERSION'],
            'CFBundleVersion': os.environ['CLIPX_VERSION'],
            'LSMinimumSystemVersion': '14.0', 'LSUIElement': True,
            'NSHighResolutionCapable': True,
            'NSAppleEventsUsageDescription': 'O ClipX pode colar o item escolhido no aplicativo ativo.',
        },
    )
