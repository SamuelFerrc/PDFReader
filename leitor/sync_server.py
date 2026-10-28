from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


ENTITY_TYPES = {"folder", "book", "bookmark", "annotation", "setting"}
MAX_METADATA_BYTES = 8 * 1024 * 1024
DEFAULT_MAX_PDF_BYTES = 1024 * 1024 * 1024


class SyncStore:
    def __init__(self, root: Path | str, token: str, max_pdf_bytes=DEFAULT_MAX_PDF_BYTES):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.blobs = self.root / "pdfs"
        self.blobs.mkdir(exist_ok=True)
        self.database = self.root / "sync.sqlite3"
        self.token = token
        self.max_pdf_bytes = int(max_pdf_bytes)
        self.changed = threading.Condition()
        self._initialize()

    def connect(self):
        connection = sqlite3.connect(self.database, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    @contextmanager
    def connection(self):
        database = self.connect()
        try:
            with database:
                yield database
        finally:
            database.close()

    def _initialize(self):
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS events (
                    revision INTEGER PRIMARY KEY AUTOINCREMENT,
                    operation_id TEXT NOT NULL UNIQUE,
                    device_id TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    payload TEXT,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f','now'))
                );
                CREATE TABLE IF NOT EXISTS entities (
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    payload TEXT,
                    revision INTEGER NOT NULL,
                    PRIMARY KEY(entity_type, entity_id)
                );
                CREATE INDEX IF NOT EXISTS event_revision ON events(revision);
            """)

    def revision(self):
        with self.connection() as db:
            return int(db.execute("SELECT COALESCE(MAX(revision),0) FROM events").fetchone()[0])

    def sync(self, request):
        device_id = str(request.get("device_id", ""))[:128]
        if not device_id:
            raise ValueError("device_id ausente")
        since = max(0, int(request.get("since", 0)))
        incoming = request.get("events", [])
        if not isinstance(incoming, list) or len(incoming) > 10000:
            raise ValueError("lote de alterações inválido")
        accepted = []
        inserted = False
        with self.connection() as db:
            for event in incoming:
                operation_id = str(event.get("operation_id", ""))[:128]
                entity_type = str(event.get("entity_type", ""))
                entity_id = str(event.get("entity_id", ""))[:256]
                operation = str(event.get("operation", ""))
                payload = event.get("payload")
                if (not operation_id or not entity_id or entity_type not in ENTITY_TYPES
                        or operation not in {"upsert", "delete"}):
                    raise ValueError("alteração inválida")
                encoded = None if payload is None else json.dumps(
                    payload, ensure_ascii=False, separators=(",", ":"))
                if encoded and len(encoded.encode("utf-8")) > 1024 * 1024:
                    raise ValueError("registro de metadados grande demais")
                existing = db.execute(
                    "SELECT revision FROM events WHERE operation_id=?", (operation_id,)
                ).fetchone()
                if existing:
                    accepted.append(operation_id)
                    continue
                cursor = db.execute("""INSERT INTO events
                    (operation_id,device_id,entity_type,entity_id,operation,payload)
                    VALUES (?,?,?,?,?,?)""",
                    (operation_id, device_id, entity_type, entity_id, operation, encoded))
                revision = cursor.lastrowid
                db.execute("""INSERT INTO entities
                    (entity_type,entity_id,operation,payload,revision) VALUES (?,?,?,?,?)
                    ON CONFLICT(entity_type,entity_id) DO UPDATE SET operation=excluded.operation,
                    payload=excluded.payload,revision=excluded.revision""",
                    (entity_type, entity_id, operation, encoded, revision))
                accepted.append(operation_id)
                inserted = True
            rows = db.execute("""SELECT revision,operation_id,device_id,entity_type,entity_id,
                operation,payload,created_at FROM events WHERE revision>? ORDER BY revision""", (since,)).fetchall()
            revision = int(db.execute("SELECT COALESCE(MAX(revision),0) FROM events").fetchone()[0])
        if inserted:
            self.collect_unused_blobs()
            with self.changed:
                self.changed.notify_all()
        events = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item["payload"]) if item["payload"] else None
            events.append(item)
        known = request.get("known_blobs", [])
        if not isinstance(known, list):
            raise ValueError("lista de PDFs inválida")
        missing = [digest for digest in known if self.valid_digest(digest) and not self.blob_path(digest).is_file()]
        return {"revision": revision, "accepted": accepted, "events": events, "missing_blobs": missing}

    def collect_unused_blobs(self):
        active = set()
        with self.connection() as db:
            for row in db.execute("SELECT payload FROM entities WHERE entity_type='book' AND operation='upsert'"):
                try:
                    digest = json.loads(row[0]).get("digest")
                except (TypeError, json.JSONDecodeError):
                    continue
                if self.valid_digest(digest):
                    active.add(digest)
        for path in self.blobs.glob("*.pdf"):
            if path.stem not in active:
                try:
                    path.unlink()
                except OSError:
                    pass

    @staticmethod
    def valid_digest(digest):
        return isinstance(digest, str) and len(digest) == 64 and all(c in "0123456789abcdef" for c in digest)

    def blob_path(self, digest):
        if not self.valid_digest(digest):
            raise ValueError("identificador de PDF inválido")
        return self.blobs / f"{digest}.pdf"

    def store_blob(self, digest, stream, length):
        if length < 0 or length > self.max_pdf_bytes:
            raise ValueError("PDF grande demais para este servidor")
        destination = self.blob_path(digest)
        temporary = destination.with_suffix(".part")
        hasher = hashlib.sha256()
        remaining = length
        try:
            with temporary.open("wb") as output:
                while remaining:
                    chunk = stream.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ValueError("upload interrompido")
                    output.write(chunk)
                    hasher.update(chunk)
                    remaining -= len(chunk)
            if hasher.hexdigest() != digest:
                raise ValueError("conteúdo do PDF não corresponde ao identificador")
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        with self.changed:
            self.changed.notify_all()


class SyncRequestHandler(BaseHTTPRequestHandler):
    server_version = "EntrelinhasSync/1"

    @property
    def store(self):
        return self.server.store

    def log_message(self, format, *args):
        print(f"{self.address_string()} - {format % args}")

    def _authorized(self):
        supplied = self.headers.get("Authorization", "")
        expected = "Bearer " + self.store.token
        return hmac.compare_digest(supplied, expected)

    def _require_auth(self):
        if self._authorized():
            return True
        self._json(HTTPStatus.UNAUTHORIZED, {"error": "Chave da biblioteca inválida."})
        return False

    def _json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/health":
            self._json(HTTPStatus.OK, {"ok": True, "revision": self.store.revision()})
            return
        if not self._require_auth():
            return
        if path == "/v1/live":
            self._live()
            return
        if path.startswith("/v1/blobs/"):
            self._download(path.rsplit("/", 1)[-1])
            return
        self._json(HTTPStatus.NOT_FOUND, {"error": "Rota não encontrada."})

    def do_POST(self):
        if urlparse(self.path).path != "/v1/sync":
            self._json(HTTPStatus.NOT_FOUND, {"error": "Rota não encontrada."})
            return
        if not self._require_auth():
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_METADATA_BYTES:
                raise ValueError("requisição de sincronização grande demais")
            request = json.loads(self.rfile.read(length).decode("utf-8"))
            self._json(HTTPStatus.OK, self.store.sync(request))
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception:
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Falha interna ao sincronizar."})

    def do_PUT(self):
        path = urlparse(self.path).path
        if not path.startswith("/v1/blobs/"):
            self._json(HTTPStatus.NOT_FOUND, {"error": "Rota não encontrada."})
            return
        if not self._require_auth():
            return
        try:
            length = int(self.headers.get("Content-Length", "-1"))
            self.store.store_blob(path.rsplit("/", 1)[-1], self.rfile, length)
            self._json(HTTPStatus.OK, {"ok": True})
        except (ValueError, OSError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    def _download(self, digest):
        try:
            path = self.store.blob_path(digest)
        except ValueError as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        if not path.is_file():
            self._json(HTTPStatus.NOT_FOUND, {"error": "PDF ainda não disponível."})
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/pdf")
        self.send_header("Content-Length", str(path.stat().st_size))
        self.send_header("Cache-Control", "private, max-age=31536000, immutable")
        self.end_headers()
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                self.wfile.write(chunk)

    def _live(self):
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        last = -1
        try:
            while True:
                current = self.store.revision()
                if current != last:
                    self.wfile.write(f"event: changed\ndata: {current}\n\n".encode("ascii"))
                    self.wfile.flush()
                    last = current
                with self.store.changed:
                    self.store.changed.wait(timeout=20)
                if self.store.revision() == last:
                    self.wfile.write(b": keep-alive\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass


class SyncHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, store):
        self.store = store
        super().__init__(address, SyncRequestHandler)


def create_server(host, port, root, token, max_pdf_bytes=DEFAULT_MAX_PDF_BYTES):
    return SyncHTTPServer((host, int(port)), SyncStore(root, token, max_pdf_bytes))


def load_or_create_token(root, supplied=None):
    if supplied:
        return supplied
    from_environment = os.environ.get("ENTRELINHAS_SYNC_TOKEN", "").strip()
    if from_environment:
        return from_environment
    path = Path(root) / "chave-do-servidor.txt"
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    token = secrets.token_urlsafe(32)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(token + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    print(f"Chave criada em: {path}")
    return token


def main(argv=None):
    parser = argparse.ArgumentParser(description="Servidor privado de sincronização do Entrelinhas")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-dir", default="sync-data")
    parser.add_argument("--token", help="Chave compartilhada; prefira ENTRELINHAS_SYNC_TOKEN em produção")
    parser.add_argument("--max-pdf-mb", type=int, default=1024)
    args = parser.parse_args(argv)
    root = Path(args.data_dir).resolve()
    token = load_or_create_token(root, args.token)
    server = create_server(args.host, args.port, root, token, args.max_pdf_mb * 1024 * 1024)
    print(f"Entrelinhas Sync ouvindo em http://{args.host}:{server.server_port}")
    print(f"Chave da biblioteca: {token}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
