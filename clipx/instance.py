"""Keep the tray and shortcut in the same desktop process.

The module implements a single-desktop-instance guard: the first process owns a
lock file and a local socket server, while later launches detect the running
instance, forward a command such as ``show``, and exit.
"""

import os
import json
import time

from PyQt6.QtCore import QLockFile, QStandardPaths
from PyQt6.QtNetwork import QLocalServer, QLocalSocket


class DesktopInstance:
    """Coordinate a single ClipX desktop process per user session.

    The instance uses a lock file for ownership and a local socket for command
    delivery. Only the lock owner removes a stale socket and listens for
    connections.
    """

    def __init__(self, runtime=None):
        """Prepare the lock file and local socket server.

        Args:
            runtime: Optional runtime directory. When omitted, the platform
                runtime directory is used. The socket name includes the user
                ID so sessions from different users do not collide.
        """
        from clipx.platforms.paths import PlatformPaths
        runtime = str(runtime or PlatformPaths().runtime)
        self.name = os.path.join(runtime, f"clipx-{os.getuid()}")
        self.lock = QLockFile(self.name + ".lock")
        self.server = QLocalServer()
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)

    def acquire(self, show=True, activation_token="", startup_id=""):
        """Claim ownership of the desktop instance or notify the running one.

        The method tries to take the instance lock. On success it returns True
        and the caller becomes the primary process. If another process already
        holds the lock, it connects to that process's socket, retrying briefly
        while the primary sets the socket up, and forwards a ``show`` or
        ``ping`` command. A JSON command carrying the activation token is sent
        when ``show`` and a token are given.

        Args:
            show (bool): Whether to ask the running instance to open search.
            activation_token (str): Optional token forwarded to the running
                instance for window activation.
            startup_id (str): Separate startup announcement to finish after show.

        Returns:
            bool: True when this process acquired the lock, False when another
            instance was notified.

        Raises:
            RuntimeError: If the lock cannot be created, or the lock is held but
            no socket connection can be established.
        """
        if self.lock.tryLock(0):
            return True
        if self.lock.error() != QLockFile.LockError.LockFailedError:
            raise RuntimeError(f"Cannot create the ClipX instance lock: {self.name}.lock")
        # The primary process can still be setting up its socket.
        for _ in range(20):
            socket = QLocalSocket()
            socket.connectToServer(self.name)
            if socket.waitForConnected(100):
                if show and (activation_token or startup_id):
                    message = json.dumps({"command": "show", "activation_token": activation_token, "startup_id": startup_id})
                    written = socket.write(message.encode("utf-8") + b"\n")
                else:
                    written = socket.write(b"show\n" if show else b"ping\n")
                if written < 0:
                    raise RuntimeError('Could not send the ClipX activation request')
                socket.flush()
                if socket.bytesToWrite() and not socket.waitForBytesWritten(1000):
                    raise RuntimeError('Could not deliver the ClipX activation request')
                socket.disconnectFromServer()
                return False
            time.sleep(0.05)
        raise RuntimeError("ClipX is running but its desktop connection is unavailable.")

    def listen(self, open_search):
        """Listen for commands from subsequently launched processes.

        Any socket left behind by a crashed process is removed before listening.
        Incoming ``show`` commands call ``open_search`` immediately; JSON
        messages with a ``show`` command and string activation token call it
        with that token. Invalid JSON is ignored. Connections are closed after
        their command is read.

        Args:
            open_search: Callable invoked to open search, accepting an optional
                ``activation_token`` keyword argument.

        Raises:
            RuntimeError: If the local socket server cannot listen.
        """
        # Only the lock owner may remove a socket left behind after a crash.
        QLocalServer.removeServer(self.name)
        if not self.server.listen(self.name):
            raise RuntimeError(self.server.errorString())

        def receive_connections():
            """Accept and service every pending client connection.

            Each connection gets a line reader that dispatches ``show`` and
            JSON commands, disconnects after reading, and schedules itself for
            deletion when the client disconnects. Any command already buffered
            is processed immediately after connecting the handler.
            """
            while self.server.hasPendingConnections():
                socket = self.server.nextPendingConnection()

                def read_command(connection=socket):
                    """Handle one pending line from a client connection.

                    Args:
                        connection: Socket to read from; bound per connection so
                            each handler closes over its own socket.
                    """
                    if connection.canReadLine():
                        message = bytes(connection.readLine()).strip()
                        if message == b"show":
                            open_search()
                        elif message.startswith(b"{"):
                            try:
                                request = json.loads(message)
                                token = request.get("activation_token", "")
                                if request.get("command") == "show" and isinstance(token, str):
                                    startup_id = request.get('startup_id', '')
                                    if isinstance(startup_id, str) and startup_id:
                                        open_search(activation_token=token, startup_id=startup_id)
                                    elif isinstance(startup_id, str):
                                        open_search(activation_token=token)
                            except (ValueError, AttributeError):
                                pass
                        connection.disconnectFromServer()

                socket.readyRead.connect(read_command)
                socket.disconnected.connect(socket.deleteLater)
                read_command()

        self.server.newConnection.connect(receive_connections)

    def close(self):
        """Stop listening and release the instance lock.

        The local socket server is closed and the lock file is unlocked,
        allowing another process to become the primary instance.
        """
        self.server.close()
        self.lock.unlock()
