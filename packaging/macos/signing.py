"""Import a release certificate into an ephemeral CI keychain, or remove it.

Reads the base64-encoded ``MACOS_CERTIFICATE_P12`` and its
``MACOS_CERTIFICATE_PASSWORD`` from the environment and installs the certificate
in a temporary keychain under ``RUNNER_TEMP``. Invoking the script with
``cleanup`` deletes that keychain instead. Without a certificate the script
reports that ad-hoc signing is in use, unless a signing identity is also set.
"""
import base64
import os
from pathlib import Path
import secrets
import shlex
import subprocess
import sys


def command(*arguments, capture=False):
    """Run a macOS ``security`` command.

    Args:
        *arguments (str): Command and arguments; the first item is the executable.
        capture (bool): Whether to capture stdout and stderr as text. Defaults to False.

    Returns:
        subprocess.CompletedProcess: The finished process.

    Raises:
        subprocess.CalledProcessError: If the command exits with a non-zero status.
    """
    return subprocess.run(arguments, check=True, text=True, capture_output=capture)


def main():
    """Create or delete the ephemeral signing keychain for the current CI run.

    With ``cleanup`` as the only argument, deletes the keychain if it exists. With
    ``MACOS_CERTIFICATE_P12`` set, decodes the archive into ``RUNNER_TEMP``,
    creates and unlocks a temporary keychain, imports the certificate and makes it
    available to ``codesign``. The temporary archive is always removed afterwards.

    Raises:
        KeyError: If ``RUNNER_TEMP`` is not set.
        RuntimeError: If an identity is set without a certificate, or if the
            certificate is present without ``MACOS_SIGNING_IDENTITY`` and
            ``MACOS_CERTIFICATE_PASSWORD``.
        subprocess.CalledProcessError: If a ``security`` command fails.
    """
    temporary = Path(os.environ['RUNNER_TEMP'])
    keychain = temporary / 'clipx-signing.keychain-db'
    if sys.argv[1:] == ['cleanup']:
        if keychain.exists():
            command('security', 'delete-keychain', str(keychain))
        return
    certificate = os.environ.get('MACOS_CERTIFICATE_P12', '')
    if not certificate:
        if os.environ.get('MACOS_SIGNING_IDENTITY'):
            raise RuntimeError('MACOS_SIGNING_IDENTITY foi definido sem MACOS_CERTIFICATE_P12.')
        print('Build de teste com assinatura ad-hoc; notarização não configurada.')
        return
    identity = os.environ.get('MACOS_SIGNING_IDENTITY')
    password = os.environ.get('MACOS_CERTIFICATE_PASSWORD')
    if not identity or password is None:
        raise RuntimeError('Certificado requer MACOS_SIGNING_IDENTITY e MACOS_CERTIFICATE_PASSWORD.')
    archive = temporary / 'clipx-certificate.p12'
    keychain_password = secrets.token_urlsafe(32)
    try:
        archive.write_bytes(base64.b64decode(''.join(certificate.split()), validate=True))
        archive.chmod(0o600)
        previous = shlex.split(command('security', 'list-keychains', '-d', 'user', capture=True).stdout)
        command('security', 'create-keychain', '-p', keychain_password, str(keychain))
        command('security', 'set-keychain-settings', '-lut', '21600', str(keychain))
        command('security', 'unlock-keychain', '-p', keychain_password, str(keychain))
        command('security', 'import', str(archive), '-k', str(keychain), '-P', password,
                '-T', '/usr/bin/codesign')
        command('security', 'set-key-partition-list', '-S', 'apple-tool:,apple:,codesign:',
                '-s', '-k', keychain_password, str(keychain))
        command('security', 'list-keychains', '-d', 'user', '-s', str(keychain), *previous)
    finally:
        archive.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
