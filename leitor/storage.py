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
            CREATE INDEX IF NOT EXISTS bookmark_book ON bookmarks(book_id);
            PRAGMA user_version=1;
        """)

    def close(self):
        self.db.close()

    def setting(self, key, default=None):
        row = self.db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_setting(self, key, value):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, json.dumps(value)))

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

    def toggle_favorite(self, book_id):
        with self.db:
            self.db.execute("UPDATE books SET favorite=1-favorite WHERE id=?", (book_id,))

    def save_progress(self, book_id, page):
        book = self.book(book_id)
        if book is None:
            return
        page = max(0, min(page, book["pages"] - 1))
        with self.db:
            self.db.execute("UPDATE books SET last_page=?, last_read=strftime('%Y-%m-%dT%H:%M:%f','now') WHERE id=?",
                            (page, book_id))

    def reorder(self, ordered_ids):
        # Reorder only the visible subset, preserving hidden books' positions.
        ids = list(ordered_ids)
        if len(set(ids)) != len(ids):
            raise ValueError("A ordem contém livros repetidos.")
        slots = sorted(self.book(i)["position"] for i in ids)
        with self.db:
            self.db.executemany("UPDATE books SET position=? WHERE id=?", zip(slots, ids))

    def delete_book(self, book_id):
        book = self.book(book_id)
        if book:
            # Unlink before removing metadata so a locked file cannot orphan the record.
            (self.files / book["filename"]).unlink(missing_ok=True)
            with self.db:
                self.db.execute("DELETE FROM books WHERE id=?", (book_id,))
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
        return folder_id

    def rename_folder(self, folder_id, name):
        if not name.strip():
            raise ValueError("Digite um nome para a pasta.")
        with self.db:
            self.db.execute("UPDATE folders SET name=? WHERE id=?", (name.strip(), folder_id))

    def delete_folder(self, folder_id):
        with self.db:
            self.db.execute("DELETE FROM folders WHERE id=?", (folder_id,))

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

    def delete_bookmark(self, bookmark_id):
        with self.db:
            self.db.execute("DELETE FROM bookmarks WHERE id=?", (bookmark_id,))

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
