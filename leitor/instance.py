"""Forward shell file-open requests to the current library's running process."""
import hashlib
import json
import os
import time

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


def server_name(root):
    path = os.path.normcase(os.path.realpath(root))
    return "Entrelinhas-" + hashlib.sha256(path.encode("utf-8")).hexdigest()[:32]


class InstanceServer(QObject):
    requested = Signal(list)

    def __init__(self, root, parent=None):
        super().__init__(parent)
        self.name = server_name(root)
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.server.newConnection.connect(self.accept_connections)
        self.buffers = {}

    def listen(self):
        if not self.server.listen(self.name):
            raise OSError("Não foi possível receber arquivos de outras janelas: " + self.server.errorString())

    def accept_connections(self):
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            self.buffers[socket] = bytearray()
            socket.readyRead.connect(lambda socket=socket: self.receive(socket))
            socket.disconnected.connect(lambda socket=socket: self.release(socket))
            self.receive(socket)

    def receive(self, socket):
        if socket not in self.buffers:
            return
        buffer = self.buffers[socket]
        buffer.extend(bytes(socket.readAll()))
        if len(buffer) > 1024 * 1024:
            socket.abort(); return
        if b"\n" not in buffer:
            return
        try:
            data = json.loads(bytes(buffer).split(b"\n", 1)[0])
            paths = data["files"]
            if not isinstance(paths, list) or len(paths) > 256 or not all(isinstance(p, str) for p in paths):
                raise ValueError("Invalid file list")
        except (KeyError, ValueError, TypeError):
            socket.abort(); return
        # Acknowledge receipt before scheduling UI work (which may request a PDF password).
        self.buffers.pop(socket, None)
        socket.write(b"OK\n"); socket.flush(); socket.disconnectFromServer()
        QTimer.singleShot(0, self, lambda paths=paths: self.requested.emit(paths))

    def release(self, socket):
        self.buffers.pop(socket, None)
        socket.deleteLater()

    def close(self):
        self.server.close()
        for socket in list(self.buffers):
            socket.abort()


def forward_files(root, paths, timeout_ms=5000):
    """Retries cover a second launch while the first process is still starting."""
    payload = (json.dumps({"files": list(paths)}, ensure_ascii=False) + "\n").encode("utf-8")
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        socket = QLocalSocket()
        socket.connectToServer(server_name(root))
        if not socket.waitForConnected(150):
            time.sleep(.05)
            continue
        socket.write(payload)
        remaining = max(1, int((deadline - time.monotonic()) * 1000))
        if socket.bytesToWrite() and not socket.waitForBytesWritten(remaining):
            socket.abort(); return False
        reply = bytearray()
        while time.monotonic() < deadline:
            reply.extend(bytes(socket.readAll()))
            if b"\n" in reply:
                socket.disconnectFromServer()
                return bytes(reply).split(b"\n", 1)[0] == b"OK"
            remaining = max(1, int((deadline - time.monotonic()) * 1000))
            if not socket.waitForReadyRead(remaining):
                reply.extend(bytes(socket.readAll()))
                break
        socket.abort()
        return bytes(reply).split(b"\n", 1)[0] == b"OK"
    return False
