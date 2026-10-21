"""Keep the tray and shortcut in the same desktop process."""

import os
import json
import time

from PyQt6.QtCore import QLockFile, QStandardPaths
from PyQt6.QtNetwork import QLocalServer, QLocalSocket


class DesktopInstance:
    def __init__(self, runtime=None):
        from clipx.platforms.paths import PlatformPaths
        runtime = str(runtime or PlatformPaths().runtime)
        self.name = os.path.join(runtime, f"clipx-{os.getuid()}")
        self.lock = QLockFile(self.name + ".lock")
        self.server = QLocalServer()
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)

    def acquire(self, show=True, activation_token=""):
        if self.lock.tryLock(0):
            return True
        if self.lock.error() != QLockFile.LockError.LockFailedError:
            raise RuntimeError(f"Cannot create the ClipX instance lock: {self.name}.lock")
        # The primary process can still be setting up its socket.
        for _ in range(20):
            socket = QLocalSocket()
            socket.connectToServer(self.name)
            if socket.waitForConnected(100):
                if show and activation_token:
                    message = json.dumps({"command": "show", "activation_token": activation_token})
                    socket.write(message.encode("utf-8") + b"\n")
                else:
                    socket.write(b"show\n" if show else b"ping\n")
                socket.flush()
                if socket.bytesToWrite():
                    socket.waitForBytesWritten(1000)
                socket.disconnectFromServer()
                return False
            time.sleep(0.05)
        raise RuntimeError("ClipX is running but its desktop connection is unavailable.")

    def listen(self, open_search):
        # Only the lock owner may remove a socket left behind after a crash.
        QLocalServer.removeServer(self.name)
        if not self.server.listen(self.name):
            raise RuntimeError(self.server.errorString())

        def receive_connections():
            while self.server.hasPendingConnections():
                socket = self.server.nextPendingConnection()

                def read_command(connection=socket):
                    if connection.canReadLine():
                        message = bytes(connection.readLine()).strip()
                        if message == b"show":
                            open_search()
                        elif message.startswith(b"{"):
                            try:
                                request = json.loads(message)
                                token = request.get("activation_token", "")
                                if request.get("command") == "show" and isinstance(token, str):
                                    open_search(activation_token=token)
                            except (ValueError, AttributeError):
                                pass
                        connection.disconnectFromServer()

                socket.readyRead.connect(read_command)
                socket.disconnected.connect(socket.deleteLater)
                read_command()

        self.server.newConnection.connect(receive_connections)

    def close(self):
        self.server.close()
        self.lock.unlock()
