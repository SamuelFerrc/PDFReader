from __future__ import annotations

import hashlib
import http.client
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from PySide6.QtCore import QObject, Signal

from .storage import Library


class SyncError(RuntimeError):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SyncClient:
    """One complete metadata and PDF exchange with the configured server."""

    def __init__(self, root: Path | str, timeout=20):
        self.root = Path(root)
        self.timeout = timeout

    @staticmethod
    def validate_url(value):
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise SyncError("O endereço do servidor deve começar com http:// ou https://.")

    def sync_once(self):
        library = Library(self.root)
        try:
            config = library.sync_config()
            if not config["enabled"]:
                return {"changed": False, "uploaded": 0, "downloaded": 0, "disabled": True}
            server_url = config["server_url"].rstrip("/")
            token = config["token"]
            self.validate_url(server_url)
            events = library.pending_sync_events()
            payload = {
                "device_id": config["device_id"],
                "since": config["last_revision"],
                "events": [{key: event[key] for key in
                            ("operation_id", "entity_type", "entity_id", "operation", "payload")}
                           for event in events],
                "known_blobs": library.local_blob_digests(),
            }
            response = self._json_request(server_url + "/v1/sync", token, payload)
            library.acknowledge_sync_events(response.get("accepted", []))
            changed = library.apply_sync_events(response.get("events", []), response.get("revision", 0))

            uploaded = 0
            for digest in response.get("missing_blobs", []):
                path = library.blob_path(digest)
                if path and path.is_file():
                    self._upload(server_url, token, digest, path)
                    uploaded += 1

            downloaded = 0
            for digest, path in library.missing_blobs():
                if self._download(server_url, token, digest, path):
                    downloaded += 1
            pending_downloads = len(library.missing_blobs())
            library.update_sync_result(revision=response.get("revision", 0), success=_now(), error=None)
            return {"changed": changed or bool(downloaded), "uploaded": uploaded,
                    "downloaded": downloaded, "pending_downloads": pending_downloads, "disabled": False}
        except Exception as exc:
            try:
                library.update_sync_result(error=str(exc))
            except Exception:
                pass
            if isinstance(exc, SyncError):
                raise
            raise SyncError(str(exc)) from exc
        finally:
            library.close()

    def _json_request(self, url, token, payload):
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        request = Request(url, data=body, method="POST", headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
        })
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise SyncError(self._http_error(exc)) from exc
        except URLError as exc:
            raise SyncError(f"Servidor indisponível: {exc.reason}") from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise SyncError("O servidor respondeu em um formato inválido.") from exc

    def _upload(self, server_url, token, digest, path):
        parsed = urlparse(server_url)
        connection_type = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
        connection = connection_type(parsed.hostname, parsed.port, timeout=max(self.timeout, 60))
        target = (parsed.path.rstrip("/") if parsed.path else "") + "/v1/blobs/" + quote(digest)
        size = path.stat().st_size
        try:
            connection.putrequest("PUT", target)
            connection.putheader("Authorization", "Bearer " + token)
            connection.putheader("Content-Type", "application/pdf")
            connection.putheader("Content-Length", str(size))
            connection.endheaders()
            with path.open("rb") as source:
                while chunk := source.read(1024 * 1024):
                    connection.send(chunk)
            response = connection.getresponse()
            content = response.read()
            if response.status >= 400:
                raise SyncError(self._response_error(response.status, content))
        except OSError as exc:
            raise SyncError(f"Não foi possível enviar {path.name}: {exc}") from exc
        finally:
            connection.close()

    def _download(self, server_url, token, digest, destination):
        request = Request(server_url + "/v1/blobs/" + quote(digest), headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/pdf",
        })
        temporary = destination.with_suffix(".part")
        hasher = hashlib.sha256()
        try:
            with urlopen(request, timeout=max(self.timeout, 60)) as response, temporary.open("wb") as output:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
                    hasher.update(chunk)
            if hasher.hexdigest() != digest:
                raise SyncError("O PDF baixado falhou na verificação de integridade.")
            os.replace(temporary, destination)
            return True
        except HTTPError as exc:
            if exc.code == 404:
                return False
            raise SyncError(self._http_error(exc)) from exc
        except URLError as exc:
            raise SyncError(f"Não foi possível baixar um PDF: {exc.reason}") from exc
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _response_error(status, content):
        try:
            message = json.loads(content.decode("utf-8")).get("error")
        except (json.JSONDecodeError, UnicodeDecodeError):
            message = None
        return message or f"O servidor retornou o erro HTTP {status}."

    def _http_error(self, error):
        return self._response_error(error.code, error.read())


class SyncService(QObject):
    statusChanged = Signal(str, bool)
    dataChanged = Signal()

    def __init__(self, library: Library, parent=None):
        super().__init__(parent)
        self.library = library
        self.root = library.root
        self.stop_event = threading.Event()
        self.wake_event = threading.Event()
        self.worker = None
        self.live_worker = None
        self.library.change_callback = self.request_sync

    def start(self):
        if self.worker and self.worker.is_alive():
            return
        self.stop_event.clear()
        self.worker = threading.Thread(target=self._sync_loop, name="EntrelinhasSync", daemon=True)
        self.live_worker = threading.Thread(target=self._live_loop, name="EntrelinhasLive", daemon=True)
        self.worker.start()
        self.live_worker.start()
        self.request_sync()

    def stop(self):
        self.library.change_callback = None
        self.stop_event.set()
        self.wake_event.set()
        for thread in (self.worker, self.live_worker):
            if thread and thread is not threading.current_thread():
                thread.join(timeout=0.5)

    def request_sync(self):
        self.wake_event.set()

    def _sync_loop(self):
        while not self.stop_event.is_set():
            self.wake_event.wait(timeout=15)
            self.wake_event.clear()
            if self.stop_event.wait(0.25):
                break
            try:
                config = self._config()
                if not config["enabled"]:
                    self.statusChanged.emit("Somente neste computador", True)
                    continue
                self.statusChanged.emit("Sincronizando…", True)
                result = SyncClient(self.root).sync_once()
                if result.get("disabled"):
                    self.statusChanged.emit("Somente neste computador", True)
                else:
                    detail = []
                    if result["uploaded"]:
                        detail.append(f'{result["uploaded"]} PDF enviado')
                    if result["downloaded"]:
                        detail.append(f'{result["downloaded"]} PDF recebido')
                    if result["pending_downloads"]:
                        detail.append(f'{result["pending_downloads"]} PDF aguardando envio')
                    title = "Metadados sincronizados" if result["pending_downloads"] else "Nuvem sincronizada"
                    self.statusChanged.emit(title + (" · " + ", ".join(detail) if detail else ""), True)
                    if result["changed"]:
                        self.dataChanged.emit()
            except SyncError as exc:
                self.statusChanged.emit("Sem sincronizar · " + str(exc), False)

    def _live_loop(self):
        while not self.stop_event.is_set():
            config = self._config()
            if not config["enabled"]:
                self.stop_event.wait(2)
                continue
            try:
                SyncClient.validate_url(config["server_url"])
                request = Request(config["server_url"].rstrip("/") + "/v1/live", headers={
                    "Authorization": "Bearer " + config["token"],
                    "Accept": "text/event-stream",
                })
                with urlopen(request, timeout=45) as response:
                    for raw_line in response:
                        if self.stop_event.is_set():
                            return
                        if raw_line.startswith(b"data:"):
                            self.request_sync()
            except (HTTPError, URLError, OSError, SyncError):
                self.stop_event.wait(5)

    def _config(self):
        library = Library(self.root)
        try:
            return library.sync_config()
        finally:
            library.close()
