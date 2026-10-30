from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import unicodedata
import uuid
from pathlib import Path


def normalize(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text.casefold())
                   if not unicodedata.combining(c))


def default_data_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local/share"))) / "LeitorPDF"


class Library:
    """The database owns metadata; imported files always live inside this library."""

    SYNC_ENTITY_TYPES = ("folder", "book", "bookmark", "annotation", "progress", "setting")

    def __init__(self, root: Path | str | None = None):
        self.root = Path(root) if root else default_data_dir()
        self.files = self.root / "pdfs"
        self.covers = self.root / "capas"
        self.files.mkdir(parents=True, exist_ok=True)
        self.covers.mkdir(exist_ok=True)
        self.db = sqlite3.connect(self.root / "biblioteca.sqlite3", timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.change_callback = None
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS folders (
                id TEXT PRIMARY KEY, name TEXT NOT NULL,
                parent_id TEXT REFERENCES folders(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS books (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, original_name TEXT NOT NULL,
                filename TEXT NOT NULL UNIQUE, digest TEXT NOT NULL UNIQUE,
                pages INTEGER NOT NULL CHECK(pages > 0),
                folder_id TEXT REFERENCES folders(id) ON DELETE SET NULL,
                tags TEXT NOT NULL DEFAULT '[]', favorite INTEGER NOT NULL DEFAULT 0,
                position INTEGER NOT NULL DEFAULT 0, last_page INTEGER NOT NULL DEFAULT 0,
                last_read TEXT, added_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f','now'))
            );
            CREATE TABLE IF NOT EXISTS bookmarks (
                id TEXT PRIMARY KEY, book_id TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
                page INTEGER NOT NULL CHECK(page >= 0), title TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '', color TEXT NOT NULL DEFAULT 'sage',
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f','now')),
                UNIQUE(book_id, page)
            );
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS annotations (
                id TEXT PRIMARY KEY, book_id TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
                page INTEGER NOT NULL CHECK(page >= 0), text TEXT NOT NULL CHECK(length(trim(text)) > 0),
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f','now'))
            );
            CREATE TABLE IF NOT EXISTS reading_progress (
                id TEXT PRIMARY KEY,
                book_id TEXT UNIQUE REFERENCES books(id) ON DELETE SET NULL,
                title TEXT NOT NULL CHECK(length(trim(title)) > 0),
                pages INTEGER NOT NULL CHECK(pages > 0),
                current_page INTEGER NOT NULL DEFAULT 0 CHECK(current_page >= 0 AND current_page <= pages),
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f','now')),
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f','now'))
            );
            CREATE INDEX IF NOT EXISTS bookmark_book ON bookmarks(book_id);
            CREATE INDEX IF NOT EXISTS annotation_book_page ON annotations(book_id, page);
            CREATE INDEX IF NOT EXISTS reading_progress_updated ON reading_progress(updated_at DESC);
            CREATE TABLE IF NOT EXISTS sync_config (
                singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                enabled INTEGER NOT NULL DEFAULT 0,
                server_url TEXT NOT NULL DEFAULT '', token TEXT NOT NULL DEFAULT '',
                device_id TEXT NOT NULL, last_revision INTEGER NOT NULL DEFAULT 0,
                last_success TEXT, last_error TEXT
            );
            CREATE TABLE IF NOT EXISTS sync_outbox (
                operation_id TEXT PRIMARY KEY,
                entity_type TEXT NOT NULL, entity_id TEXT NOT NULL,
                operation TEXT NOT NULL CHECK(operation IN ('upsert','delete')),
                payload TEXT,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f','now')),
                UNIQUE(entity_type, entity_id)
            );
            CREATE TABLE IF NOT EXISTS sync_book_aliases (
                remote_id TEXT PRIMARY KEY,
                local_id TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS sync_book_alias_local ON sync_book_aliases(local_id);
            PRAGMA user_version=5;
        """)
        self.db.execute("INSERT OR IGNORE INTO sync_book_aliases (remote_id,local_id) SELECT id,id FROM books")
        self.db.execute(
            "INSERT OR IGNORE INTO sync_config (singleton,device_id) VALUES (1,?)",
            (uuid.uuid4().hex,),
        )
        self.db.commit()

    def close(self):
        self.db.close()

    def setting(self, key, default=None):
        row = self.db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_setting(self, key, value):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, json.dumps(value)))
            self._queue_sync("setting", key, "upsert", {"key": key, "value": value})

    def book(self, book_id):
        row = self.db.execute("SELECT * FROM books WHERE id=?", (book_id,)).fetchone()
        if not row:
            return None
        data = dict(row)
        data["tags"] = json.loads(data["tags"])
        return data

    def books(self, *, scope="all", folder_id=None, tag=None, query="", order="manual"):
        orders = {"manual": "position, added_at", "title": "title COLLATE NOCASE",
                  "recent": "last_read DESC, added_at DESC", "added": "added_at DESC"}
        rows = self.db.execute("SELECT id FROM books ORDER BY " + orders.get(order, orders["manual"]))
        result = [self.book(row[0]) for row in rows.fetchall()]
        if scope == "favorites":
            result = [b for b in result if b["favorite"]]
        elif scope == "reading":
            result = [b for b in result if b["last_read"]]
        elif scope == "unfiled":
            result = [b for b in result if b["folder_id"] is None]
        elif scope == "folder":
            ids = self.descendants(folder_id)
            result = [b for b in result if b["folder_id"] in ids]
        if tag:
            result = [b for b in result if tag in b["tags"]]
        if query.strip():
            words = normalize(query).split()
            result = [b for b in result if all(w in normalize(" ".join(
                [b["title"], b["original_name"], *b["tags"]])) for w in words)]
        return result

    def import_file(self, source: Path, pages: int, folder_id=None):
        """Copy first, then commit. An interrupted import never replaces another PDF."""
        source = Path(source)
        if pages <= 0:
            raise ValueError("O PDF não contém páginas legíveis.")
        digest = hashlib.sha256()
        with source.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        value = digest.hexdigest()
        existing = self.db.execute("SELECT id, filename FROM books WHERE digest=?", (value,)).fetchone()
        if existing:
            # Reimport can also repair a missing managed file.
            destination = self.files / existing["filename"]
            if not destination.exists():
                temporary = destination.with_suffix(".part")
                try:
                    shutil.copyfile(source, temporary)
                    os.replace(temporary, destination)
                finally:
                    temporary.unlink(missing_ok=True)
            return existing["id"], False
        book_id = uuid.uuid4().hex
        filename = book_id + ".pdf"
        destination = self.files / filename
        temporary = destination.with_suffix(".part")
        try:
            shutil.copyfile(source, temporary)
            os.replace(temporary, destination)
            with self.db:
                position = self.db.execute("SELECT COALESCE(MAX(position), -1)+1 FROM books").fetchone()[0]
                self.db.execute("""INSERT INTO books
                    (id,title,original_name,filename,digest,pages,folder_id,position)
                    VALUES (?,?,?,?,?,?,?,?)""",
                    (book_id, source.stem, source.name, filename, value, pages, folder_id, position))
                self.db.execute("INSERT OR REPLACE INTO sync_book_aliases VALUES (?,?)", (book_id, book_id))
                self._queue_sync("book", book_id, "upsert", self._book_payload(book_id))
        except Exception:
            temporary.unlink(missing_ok=True)
            destination.unlink(missing_ok=True)
            raise
        return book_id, True

    def edit_book(self, book_id, title, tags, folder_id, favorite):
        title = title.strip()
        if not title:
            raise ValueError("Digite um nome para o livro.")
        cleaned = list(dict.fromkeys(t.strip() for t in tags if t.strip()))
        with self.db:
            self.db.execute("UPDATE books SET title=?, tags=?, folder_id=?, favorite=? WHERE id=?",
                            (title, json.dumps(cleaned, ensure_ascii=False), folder_id, int(favorite), book_id))
            progress_ids = [row[0] for row in self.db.execute(
                "SELECT id FROM reading_progress WHERE book_id=?", (book_id,))]
            self.db.execute("UPDATE reading_progress SET title=? WHERE book_id=?", (title, book_id))
            self._queue_sync("book", book_id, "upsert", self._book_payload(book_id))
            for progress_id in progress_ids:
                self._queue_sync("progress", progress_id, "upsert", self._progress_payload(progress_id))

    def toggle_favorite(self, book_id):
        with self.db:
            self.db.execute("UPDATE books SET favorite=1-favorite WHERE id=?", (book_id,))
            self._queue_sync("book", book_id, "upsert", self._book_payload(book_id))

    def save_progress(self, book_id, page):
        book = self.book(book_id)
        if book is None:
            return
        page = max(0, min(page, book["pages"] - 1))
        with self.db:
            self.db.execute("UPDATE books SET last_page=?, last_read=strftime('%Y-%m-%dT%H:%M:%f','now') WHERE id=?",
                            (page, book_id))
            progress_ids = [row[0] for row in self.db.execute(
                "SELECT id FROM reading_progress WHERE book_id=?", (book_id,))]
            self.db.execute("""UPDATE reading_progress SET current_page=?,
                updated_at=strftime('%Y-%m-%dT%H:%M:%f','now') WHERE book_id=?""",
                (page + 1, book_id))
            self._queue_sync("book", book_id, "upsert", self._book_payload(book_id))
            for progress_id in progress_ids:
                self._queue_sync("progress", progress_id, "upsert", self._progress_payload(progress_id))

    def reorder(self, ordered_ids):
        # Reorder only the visible subset, preserving hidden books' positions.
        ids = list(ordered_ids)
        if len(set(ids)) != len(ids):
            raise ValueError("A ordem contém livros repetidos.")
        slots = sorted(self.book(i)["position"] for i in ids)
        with self.db:
            self.db.executemany("UPDATE books SET position=? WHERE id=?", zip(slots, ids))
            for book_id in ids:
                self._queue_sync("book", book_id, "upsert", self._book_payload(book_id))

    def delete_book(self, book_id):
        book = self.book(book_id)
        if book:
            remote_ids = [row[0] for row in self.db.execute(
                "SELECT remote_id FROM sync_book_aliases WHERE local_id=?", (book_id,))] or [book_id]
            bookmarks = [row[0] for row in self.db.execute("SELECT id FROM bookmarks WHERE book_id=?", (book_id,))]
            annotations = [row[0] for row in self.db.execute("SELECT id FROM annotations WHERE book_id=?", (book_id,))]
            progress_ids = [row[0] for row in self.db.execute(
                "SELECT id FROM reading_progress WHERE book_id=?", (book_id,))]
            # Unlink before removing metadata so a locked file cannot orphan the record.
            (self.files / book["filename"]).unlink(missing_ok=True)
            with self.db:
                self.db.execute("DELETE FROM books WHERE id=?", (book_id,))
                for entity_id in bookmarks:
                    self._queue_sync("bookmark", entity_id, "delete")
                for entity_id in annotations:
                    self._queue_sync("annotation", entity_id, "delete")
                for progress_id in progress_ids:
                    self._queue_sync("progress", progress_id, "upsert", self._progress_payload(progress_id))
                self.db.execute("DELETE FROM sync_book_aliases WHERE local_id=?", (book_id,))
                for remote_id in remote_ids:
                    self._queue_sync("book", remote_id, "delete")
            (self.covers / f"{book_id}.png").unlink(missing_ok=True)

    def folders(self):
        return [dict(r) for r in self.db.execute("SELECT * FROM folders ORDER BY name COLLATE NOCASE")]

    def descendants(self, folder_id):
        ids = {folder_id}
        folders = self.folders()
        changed = True
        while changed:
            more = {f["id"] for f in folders if f["parent_id"] in ids}
            changed = not more.issubset(ids)
            ids.update(more)
        return ids

    def add_folder(self, name, parent_id=None):
        name = name.strip()
        if not name:
            raise ValueError("Digite um nome para a pasta.")
        folder_id = uuid.uuid4().hex
        with self.db:
            self.db.execute("INSERT INTO folders VALUES (?,?,?)", (folder_id, name, parent_id))
            self._queue_sync("folder", folder_id, "upsert", self._folder_payload(folder_id))
        return folder_id

    def rename_folder(self, folder_id, name):
        if not name.strip():
            raise ValueError("Digite um nome para a pasta.")
        with self.db:
            self.db.execute("UPDATE folders SET name=? WHERE id=?", (name.strip(), folder_id))
            self._queue_sync("folder", folder_id, "upsert", self._folder_payload(folder_id))

    def delete_folder(self, folder_id):
        folder_ids = self.descendants(folder_id)
        affected_books = [row[0] for row in self.db.execute(
            f"SELECT id FROM books WHERE folder_id IN ({','.join('?' for _ in folder_ids)})",
            tuple(folder_ids),
        )]
        with self.db:
            self.db.execute("DELETE FROM folders WHERE id=?", (folder_id,))
            for entity_id in folder_ids:
                self._queue_sync("folder", entity_id, "delete")
            for book_id in affected_books:
                self._queue_sync("book", book_id, "upsert", self._book_payload(book_id))

    def tags(self):
        return sorted({t for b in self.books() for t in b["tags"]}, key=normalize)

    def bookmarks(self, book_id=None):
        sql = """SELECT m.*, b.title AS book_title FROM bookmarks m JOIN books b ON b.id=m.book_id"""
        params = ()
        if book_id:
            sql += " WHERE book_id=?"
            params = (book_id,)
        sql += " ORDER BY b.title COLLATE NOCASE, page"
        return [dict(r) for r in self.db.execute(sql, params)]

    def bookmark_at(self, book_id, page):
        return next((b for b in self.bookmarks(book_id) if b["page"] == page), None)

    def save_bookmark(self, book_id, page, title, note="", color="sage"):
        book = self.book(book_id)
        if book is None or not 0 <= page < book["pages"]:
            raise ValueError("Página inválida para este livro.")
        with self.db:
            self.db.execute("""INSERT INTO bookmarks (id,book_id,page,title,note,color)
                VALUES (?,?,?,?,?,?) ON CONFLICT(book_id,page) DO UPDATE SET
                title=excluded.title,note=excluded.note,color=excluded.color""",
                (uuid.uuid4().hex, book_id, page, title.strip() or f"Página {page + 1}", note.strip(), color))
            bookmark = self.db.execute("SELECT * FROM bookmarks WHERE book_id=? AND page=?", (book_id, page)).fetchone()
            self._queue_sync("bookmark", bookmark["id"], "upsert", dict(bookmark))

    def delete_bookmark(self, bookmark_id):
        with self.db:
            self.db.execute("DELETE FROM bookmarks WHERE id=?", (bookmark_id,))
            self._queue_sync("bookmark", bookmark_id, "delete")

    def annotations(self, book_id):
        return [dict(row) for row in self.db.execute(
            "SELECT * FROM annotations WHERE book_id=? ORDER BY page, created_at, rowid", (book_id,))]

    def add_annotation(self, book_id, page, text):
        book = self.book(book_id)
        if book is None or not 0 <= page < book["pages"]:
            raise ValueError("Página inválida para este livro.")
        if not text.strip():
            raise ValueError("Escreva uma anotação antes de salvar.")
        annotation_id = uuid.uuid4().hex
        with self.db:
            self.db.execute("INSERT INTO annotations (id,book_id,page,text) VALUES (?,?,?,?)",
                            (annotation_id, book_id, page, text.strip()))
            annotation = self.db.execute("SELECT * FROM annotations WHERE id=?", (annotation_id,)).fetchone()
            self._queue_sync("annotation", annotation_id, "upsert", dict(annotation))
        return annotation_id

    def edit_annotation(self, annotation_id, text):
        # Editing the text must keep the page and date captured at creation.
        if not text.strip():
            raise ValueError("Escreva uma anotação antes de salvar.")
        with self.db:
            self.db.execute("UPDATE annotations SET text=? WHERE id=?", (text.strip(), annotation_id))
            annotation = self.db.execute("SELECT * FROM annotations WHERE id=?", (annotation_id,)).fetchone()
            if annotation:
                self._queue_sync("annotation", annotation_id, "upsert", dict(annotation))

    def delete_annotation(self, annotation_id):
        with self.db:
            self.db.execute("DELETE FROM annotations WHERE id=?", (annotation_id,))
            self._queue_sync("annotation", annotation_id, "delete")

    def progress_item(self, progress_id):
        row = self.db.execute("SELECT * FROM reading_progress WHERE id=?", (progress_id,)).fetchone()
        return dict(row) if row else None

    def progress_items(self, query="", limit=None):
        sql = "SELECT * FROM reading_progress ORDER BY updated_at DESC, created_at DESC, title COLLATE NOCASE"
        params = ()
        if limit is not None:
            sql += " LIMIT ?"
            params = (max(0, int(limit)),)
        result = [dict(row) for row in self.db.execute(sql, params)]
        if query.strip():
            words = normalize(query).split()
            result = [item for item in result if all(word in normalize(item["title"]) for word in words)]
        return result

    def add_progress_book(self, book_id):
        book = self.book(book_id)
        if book is None:
            raise ValueError("Escolha um PDF da biblioteca.")
        existing = self.db.execute("SELECT id FROM reading_progress WHERE book_id=?", (book_id,)).fetchone()
        if existing:
            return existing[0], False
        progress_id = uuid.uuid4().hex
        current_page = book["last_page"] + 1 if book["last_read"] else 0
        with self.db:
            self.db.execute("""INSERT INTO reading_progress
                (id,book_id,title,pages,current_page) VALUES (?,?,?,?,?)""",
                (progress_id, book_id, book["title"], book["pages"], current_page))
            self._queue_sync("progress", progress_id, "upsert", self._progress_payload(progress_id))
        return progress_id, True

    def add_custom_progress(self, title, pages):
        title = title.strip()
        pages = int(pages)
        if not title:
            raise ValueError("Digite o título do livro.")
        if pages <= 0:
            raise ValueError("O número de páginas deve ser maior que zero.")
        progress_id = uuid.uuid4().hex
        with self.db:
            self.db.execute("""INSERT INTO reading_progress
                (id,title,pages,current_page) VALUES (?,?,?,0)""", (progress_id, title, pages))
            self._queue_sync("progress", progress_id, "upsert", self._progress_payload(progress_id))
        return progress_id

    def update_progress_item(self, progress_id, current_page, *, title=None, pages=None):
        item = self.progress_item(progress_id)
        if item is None:
            raise ValueError("Este livro não está mais no controle de progresso.")
        new_title = item["title"] if item["book_id"] else (title.strip() if title is not None else item["title"])
        new_pages = item["pages"] if item["book_id"] else (int(pages) if pages is not None else item["pages"])
        if not new_title:
            raise ValueError("Digite o título do livro.")
        if new_pages <= 0:
            raise ValueError("O número de páginas deve ser maior que zero.")
        current_page = max(0, min(int(current_page), new_pages))
        with self.db:
            self.db.execute("""UPDATE reading_progress SET title=?,pages=?,current_page=?,
                updated_at=strftime('%Y-%m-%dT%H:%M:%f','now') WHERE id=?""",
                (new_title, new_pages, current_page, progress_id))
            if item["book_id"]:
                if current_page:
                    self.db.execute("""UPDATE books SET last_page=?,
                        last_read=strftime('%Y-%m-%dT%H:%M:%f','now') WHERE id=?""",
                        (current_page - 1, item["book_id"]))
                else:
                    self.db.execute("UPDATE books SET last_page=0,last_read=NULL WHERE id=?", (item["book_id"],))
                self._queue_sync("book", item["book_id"], "upsert", self._book_payload(item["book_id"]))
            self._queue_sync("progress", progress_id, "upsert", self._progress_payload(progress_id))

    def delete_progress_item(self, progress_id):
        with self.db:
            self.db.execute("DELETE FROM reading_progress WHERE id=?", (progress_id,))
            self._queue_sync("progress", progress_id, "delete")

    def sync_config(self):
        return dict(self.db.execute("SELECT * FROM sync_config WHERE singleton=1").fetchone())

    def configure_sync(self, enabled, server_url, token):
        server_url = server_url.strip().rstrip("/")
        token = token.strip()
        if enabled and (not server_url or not token):
            raise ValueError("Informe o endereço do servidor e a chave da biblioteca.")
        before = self.sync_config()
        changed_server = before["server_url"] != server_url or before["token"] != token
        with self.db:
            self.db.execute(
                "UPDATE sync_config SET enabled=?,server_url=?,token=?,last_revision=?,last_error=NULL WHERE singleton=1",
                (int(enabled), server_url, token, 0 if changed_server else before["last_revision"]),
            )
            if enabled and (changed_server or not before["enabled"]):
                self._queue_full_snapshot_locked()
        self._notify_change()

    def update_sync_result(self, *, revision=None, success=None, error=None):
        fields, values = [], []
        if revision is not None:
            fields.append("last_revision=?"); values.append(int(revision))
        if success is not None:
            fields.append("last_success=?"); values.append(success)
        fields.append("last_error=?"); values.append(error)
        values.append(1)
        with self.db:
            self.db.execute(f"UPDATE sync_config SET {', '.join(fields)} WHERE singleton=?", values)

    def queue_full_snapshot(self):
        with self.db:
            self._queue_full_snapshot_locked()
        self._notify_change()

    def _queue_full_snapshot_locked(self):
        for row in self.db.execute("SELECT id FROM folders"):
            self._queue_sync("folder", row[0], "upsert", self._folder_payload(row[0]), notify=False)
        for row in self.db.execute("SELECT id FROM books"):
            self._queue_sync("book", row[0], "upsert", self._book_payload(row[0]), notify=False)
        for table, entity_type in (("bookmarks", "bookmark"), ("annotations", "annotation"),
                                   ("reading_progress", "progress")):
            for row in self.db.execute(f"SELECT * FROM {table}"):
                self._queue_sync(entity_type, row["id"], "upsert", dict(row), notify=False)
        for row in self.db.execute("SELECT key,value FROM settings"):
            self._queue_sync("setting", row["key"], "upsert",
                             {"key": row["key"], "value": json.loads(row["value"])}, notify=False)

    def pending_sync_events(self):
        result = []
        for row in self.db.execute("SELECT * FROM sync_outbox ORDER BY created_at, rowid"):
            item = dict(row)
            item["payload"] = json.loads(item["payload"]) if item["payload"] else None
            result.append(item)
        return result

    def acknowledge_sync_events(self, operation_ids):
        ids = list(operation_ids)
        if not ids:
            return
        with self.db:
            self.db.executemany("DELETE FROM sync_outbox WHERE operation_id=?", ((value,) for value in ids))

    def local_blob_digests(self):
        return [book["digest"] for book in self.books()
                if (self.files / book["filename"]).is_file()]

    def blob_path(self, digest):
        row = self.db.execute("SELECT filename FROM books WHERE digest=?", (digest,)).fetchone()
        return self.files / row[0] if row else None

    def missing_blobs(self):
        return [(book["digest"], self.files / book["filename"]) for book in self.books()
                if not (self.files / book["filename"]).is_file()]

    def install_blob(self, digest, content):
        path = self.blob_path(digest)
        if path is None:
            return False
        if hashlib.sha256(content).hexdigest() != digest:
            raise ValueError("O PDF recebido não corresponde ao arquivo anunciado pelo servidor.")
        temporary = path.with_suffix(".part")
        try:
            temporary.write_bytes(content)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        return True

    def apply_sync_events(self, events, revision):
        latest = {}
        for event in events:
            if event.get("entity_type") in self.SYNC_ENTITY_TYPES:
                key = (event["entity_type"], event["entity_id"])
                if key not in latest or int(event["revision"]) > int(latest[key]["revision"]):
                    latest[key] = event
        pending = {(row["entity_type"], row["entity_id"])
                   for row in self.db.execute("SELECT entity_type,entity_id FROM sync_outbox")}
        usable = [event for key, event in latest.items() if key not in pending]
        upsert_order = {"folder": 0, "book": 1, "bookmark": 2, "annotation": 3, "progress": 4, "setting": 5}
        delete_order = {"bookmark": 0, "annotation": 1, "progress": 2, "book": 3, "folder": 4, "setting": 5}
        usable.sort(key=lambda event: (
            0 if event["operation"] == "upsert" else 1,
            (upsert_order if event["operation"] == "upsert" else delete_order)[event["entity_type"]],
            int(event["revision"]),
        ))
        changed = False
        with self.db:
            for event in usable:
                changed = self._apply_sync_event(event) or changed
            self.db.execute("UPDATE sync_config SET last_revision=? WHERE singleton=1", (int(revision),))
        if changed:
            self._cleanup_orphan_files()
        return changed

    def _apply_sync_event(self, event):
        entity_type = event["entity_type"]
        entity_id = event["entity_id"]
        operation = event["operation"]
        payload = event.get("payload") or {}
        if operation == "delete":
            if entity_type == "book":
                alias = self.db.execute(
                    "SELECT local_id FROM sync_book_aliases WHERE remote_id=?", (entity_id,)
                ).fetchone()
                local_id = alias[0] if alias else entity_id
                self.db.execute("DELETE FROM sync_book_aliases WHERE remote_id=?", (entity_id,))
                if self.db.execute("SELECT 1 FROM sync_book_aliases WHERE local_id=?", (local_id,)).fetchone():
                    return bool(alias)
                entity_id = local_id
            table = {"folder": "folders", "book": "books", "bookmark": "bookmarks",
                     "annotation": "annotations", "progress": "reading_progress", "setting": "settings"}[entity_type]
            key = "key" if entity_type == "setting" else "id"
            exists = self.db.execute(f"SELECT 1 FROM {table} WHERE {key}=?", (entity_id,)).fetchone()
            self.db.execute(f"DELETE FROM {table} WHERE {key}=?", (entity_id,))
            return bool(exists)
        if entity_type == "folder":
            parent_id = payload.get("parent_id")
            if parent_id and not self.db.execute("SELECT 1 FROM folders WHERE id=?", (parent_id,)).fetchone():
                parent_id = None
            self.db.execute("""INSERT INTO folders (id,name,parent_id) VALUES (?,?,?)
                ON CONFLICT(id) DO UPDATE SET name=excluded.name,parent_id=excluded.parent_id""",
                (entity_id, payload["name"], parent_id))
        elif entity_type == "book":
            duplicate = self.db.execute("SELECT id,filename FROM books WHERE digest=?", (payload["digest"],)).fetchone()
            local_id = duplicate["id"] if duplicate else entity_id
            filename = duplicate["filename"] if duplicate else payload["filename"]
            self.db.execute("INSERT OR REPLACE INTO sync_book_aliases (remote_id,local_id) VALUES (?,?)",
                            (entity_id, local_id))
            folder_id = payload.get("folder_id")
            if folder_id and not self.db.execute("SELECT 1 FROM folders WHERE id=?", (folder_id,)).fetchone():
                folder_id = None
            tags = payload.get("tags", [])
            self.db.execute("""INSERT INTO books
                (id,title,original_name,filename,digest,pages,folder_id,tags,favorite,position,last_page,last_read,added_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                title=excluded.title,original_name=excluded.original_name,filename=excluded.filename,
                digest=excluded.digest,pages=excluded.pages,folder_id=excluded.folder_id,tags=excluded.tags,
                favorite=excluded.favorite,position=excluded.position,last_page=excluded.last_page,
                last_read=excluded.last_read,added_at=excluded.added_at""",
                (local_id, payload["title"], payload["original_name"], filename, payload["digest"],
                 int(payload["pages"]), folder_id, json.dumps(tags, ensure_ascii=False), int(payload.get("favorite", 0)),
                 int(payload.get("position", 0)), int(payload.get("last_page", 0)), payload.get("last_read"),
                 payload["added_at"]))
        elif entity_type == "bookmark":
            book_id = self._local_book_id(payload["book_id"])
            if not self.db.execute("SELECT 1 FROM books WHERE id=?", (book_id,)).fetchone():
                return False
            self.db.execute("DELETE FROM bookmarks WHERE book_id=? AND page=? AND id<>?",
                            (book_id, int(payload["page"]), entity_id))
            self.db.execute("""INSERT INTO bookmarks (id,book_id,page,title,note,color,created_at)
                VALUES (?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET book_id=excluded.book_id,page=excluded.page,
                title=excluded.title,note=excluded.note,color=excluded.color,created_at=excluded.created_at""",
                (entity_id, book_id, int(payload["page"]), payload["title"], payload.get("note", ""),
                 payload.get("color", "sage"), payload["created_at"]))
        elif entity_type == "annotation":
            book_id = self._local_book_id(payload["book_id"])
            if not self.db.execute("SELECT 1 FROM books WHERE id=?", (book_id,)).fetchone():
                return False
            self.db.execute("""INSERT INTO annotations (id,book_id,page,text,created_at) VALUES (?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET book_id=excluded.book_id,page=excluded.page,
                text=excluded.text,created_at=excluded.created_at""",
                (entity_id, book_id, int(payload["page"]), payload["text"], payload["created_at"]))
        elif entity_type == "progress":
            book_id = payload.get("book_id")
            if book_id:
                book_id = self._local_book_id(book_id)
                if not self.db.execute("SELECT 1 FROM books WHERE id=?", (book_id,)).fetchone():
                    book_id = None
            if book_id:
                self.db.execute("DELETE FROM reading_progress WHERE book_id=? AND id<>?", (book_id, entity_id))
            pages = max(1, int(payload["pages"]))
            current_page = max(0, min(int(payload.get("current_page", 0)), pages))
            self.db.execute("""INSERT INTO reading_progress
                (id,book_id,title,pages,current_page,created_at,updated_at) VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET book_id=excluded.book_id,title=excluded.title,
                pages=excluded.pages,current_page=excluded.current_page,created_at=excluded.created_at,
                updated_at=excluded.updated_at""",
                (entity_id, book_id, payload["title"], pages, current_page,
                 payload["created_at"], payload["updated_at"]))
        elif entity_type == "setting":
            self.db.execute("INSERT OR REPLACE INTO settings (key,value) VALUES (?,?)",
                            (entity_id, json.dumps(payload.get("value"))))
        return True

    def _book_payload(self, book_id):
        book = self.book(book_id)
        return book if book else None

    def _folder_payload(self, folder_id):
        row = self.db.execute("SELECT * FROM folders WHERE id=?", (folder_id,)).fetchone()
        return dict(row) if row else None

    def _progress_payload(self, progress_id):
        return self.progress_item(progress_id)

    def _local_book_id(self, remote_id):
        row = self.db.execute("SELECT local_id FROM sync_book_aliases WHERE remote_id=?", (remote_id,)).fetchone()
        return row[0] if row else remote_id

    def _queue_sync(self, entity_type, entity_id, operation, payload=None, *, notify=True):
        if entity_type not in self.SYNC_ENTITY_TYPES:
            raise ValueError("Tipo de dado inválido para sincronização.")
        self.db.execute("""INSERT INTO sync_outbox
            (operation_id,entity_type,entity_id,operation,payload) VALUES (?,?,?,?,?)
            ON CONFLICT(entity_type,entity_id) DO UPDATE SET operation_id=excluded.operation_id,
            operation=excluded.operation,payload=excluded.payload,created_at=strftime('%Y-%m-%dT%H:%M:%f','now')""",
            (uuid.uuid4().hex, entity_type, entity_id, operation,
             json.dumps(payload, ensure_ascii=False, separators=(",", ":")) if payload is not None else None))
        if notify:
            self._notify_change()

    def _notify_change(self):
        if self.change_callback:
            self.change_callback()

    def _cleanup_orphan_files(self):
        referenced = {row[0] for row in self.db.execute("SELECT filename FROM books")}
        for path in self.files.glob("*.pdf"):
            if path.name not in referenced:
                try:
                    path.unlink()
                except OSError:
                    pass

    def backup(self, destination: Path):
        """Snapshot SQLite and managed files to a user-selected ZIP."""
        import tempfile
        import zipfile
        destination = Path(destination)
        if destination.resolve().is_relative_to(self.root.resolve()):
            raise ValueError("Salve o backup fora da pasta de dados da biblioteca.")
        temporary = destination.with_name(destination.name + ".part")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                snapshot = Path(tmp) / "biblioteca.sqlite3"
                connection = sqlite3.connect(snapshot)
                try:
                    self.db.backup(connection)
                finally:
                    connection.close()
                with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
                    archive.write(snapshot, "biblioteca.sqlite3")
                    for folder in (self.files, self.covers):
                        for path in folder.iterdir():
                            if path.is_file() and path.suffix != ".part":
                                archive.write(path, path.relative_to(self.root))
                os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
