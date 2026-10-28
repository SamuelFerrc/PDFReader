import json
import queue
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from leitor.storage import Library
from leitor.sync import SyncClient, SyncError
from leitor.sync_server import create_server


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.token = "test-secret-key"
        self.server = create_server("127.0.0.1", 0, self.root / "server", self.token)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=2)
        self.tmp.cleanup()

    def library(self, name):
        return Library(self.root / name)

    def add_book(self, library, name="livro", content=b"%PDF-sync-test"):
        source = self.root / f"{name}.pdf"
        source.write_bytes(content)
        return library.import_file(source, 12)[0]

    def test_two_devices_exchange_all_library_data_and_pdf(self):
        first = self.library("first")
        book_id = self.add_book(first)
        folder_id = first.add_folder("Estudos")
        first.edit_book(book_id, "Nome compartilhado", ["tag", "leitura"], folder_id, True)
        first.save_progress(book_id, 7)
        first.save_bookmark(book_id, 7, "Continuar", "Trecho importante", "blue")
        note_id = first.add_annotation(book_id, 7, "Minha anotação")
        first.set_setting("theme", "dark")
        digest = first.book(book_id)["digest"]
        first.configure_sync(True, self.url, self.token)
        first.close()

        sent = SyncClient(self.root / "first").sync_once()
        self.assertEqual(sent["uploaded"], 1)

        second = self.library("second")
        second.configure_sync(True, self.url, self.token)
        second.close()
        received = SyncClient(self.root / "second").sync_once()
        self.assertEqual(received["downloaded"], 1)

        second = self.library("second")
        try:
            book = second.book(book_id)
            self.assertEqual(book["title"], "Nome compartilhado")
            self.assertEqual(book["tags"], ["tag", "leitura"])
            self.assertEqual(book["folder_id"], folder_id)
            self.assertEqual(book["last_page"], 7)
            self.assertEqual(second.bookmarks(book_id)[0]["note"], "Trecho importante")
            self.assertEqual(second.annotations(book_id)[0]["id"], note_id)
            self.assertEqual(second.setting("theme"), "dark")
            self.assertEqual((second.files / book["filename"]).read_bytes(), b"%PDF-sync-test")
            self.assertEqual(book["digest"], digest)
            second.edit_annotation(note_id, "Editada no segundo computador")
            second.save_progress(book_id, 9)
        finally:
            second.close()

        SyncClient(self.root / "second").sync_once()
        SyncClient(self.root / "first").sync_once()
        first = self.library("first")
        try:
            self.assertEqual(first.book(book_id)["last_page"], 9)
            self.assertEqual(first.annotations(book_id)[0]["text"], "Editada no segundo computador")
            first.delete_book(book_id)
        finally:
            first.close()

        SyncClient(self.root / "first").sync_once()
        self.assertEqual(list((self.root / "server" / "pdfs").glob("*.pdf")), [])
        SyncClient(self.root / "second").sync_once()
        second = self.library("second")
        try:
            self.assertIsNone(second.book(book_id))
            self.assertEqual(second.bookmarks(), [])
            self.assertEqual(list(second.files.glob("*.pdf")), [])
        finally:
            second.close()

    def test_outbox_coalesces_repeated_page_updates(self):
        library = self.library("coalesce")
        try:
            book_id = self.add_book(library, "progress")
            library.save_progress(book_id, 1)
            library.save_progress(book_id, 2)
            library.save_progress(book_id, 3)
            changes = [event for event in library.pending_sync_events()
                       if event["entity_type"] == "book" and event["entity_id"] == book_id]
            self.assertEqual(len(changes), 1)
            self.assertEqual(changes[0]["payload"]["last_page"], 3)
        finally:
            library.close()

    def test_same_pdf_imported_offline_on_two_devices_is_merged(self):
        first = self.library("duplicate-first")
        first_id = self.add_book(first, "same-first", b"same-pdf")
        first.add_annotation(first_id, 1, "Nota do primeiro")
        first.configure_sync(True, self.url, self.token); first.close()

        second = self.library("duplicate-second")
        second_id = self.add_book(second, "same-second", b"same-pdf")
        self.assertNotEqual(first_id, second_id)
        second.add_annotation(second_id, 2, "Nota do segundo")
        second.configure_sync(True, self.url, self.token); second.close()

        SyncClient(self.root / "duplicate-first").sync_once()
        SyncClient(self.root / "duplicate-second").sync_once()
        SyncClient(self.root / "duplicate-first").sync_once()

        for name in ("duplicate-first", "duplicate-second"):
            library = self.library(name)
            try:
                self.assertEqual(len(library.books()), 1)
                local_id = library.books()[0]["id"]
                self.assertEqual({note["text"] for note in library.annotations(local_id)},
                                 {"Nota do primeiro", "Nota do segundo"})
            finally:
                library.close()

        first = self.library("duplicate-first")
        try:
            first.delete_book(first.books()[0]["id"])
        finally:
            first.close()
        SyncClient(self.root / "duplicate-first").sync_once()
        SyncClient(self.root / "duplicate-second").sync_once()
        second = self.library("duplicate-second")
        try:
            self.assertEqual(second.books(), [])
        finally:
            second.close()

    def test_server_rejects_wrong_key(self):
        library = self.library("invalid-key")
        try:
            library.configure_sync(True, self.url, "wrong-key")
        finally:
            library.close()
        with self.assertRaisesRegex(SyncError, "Chave da biblioteca inválida"):
            SyncClient(self.root / "invalid-key").sync_once()

    def test_server_health_is_public_but_sync_is_private(self):
        with urlopen(self.url + "/health") as response:
            self.assertTrue(json.loads(response.read())["ok"])
        request = Request(self.url + "/v1/sync", data=b"{}", method="POST",
                          headers={"Content-Type": "application/json"})
        with self.assertRaises(HTTPError) as caught:
            urlopen(request)
        self.assertEqual(caught.exception.code, 401)

    def test_live_channel_announces_a_new_revision_immediately(self):
        revisions = queue.Queue()
        ready = threading.Event()

        def listen():
            request = Request(self.url + "/v1/live", headers={
                "Authorization": "Bearer " + self.token,
                "Accept": "text/event-stream",
            })
            with urlopen(request, timeout=5) as response:
                for line in response:
                    if line.startswith(b"data:"):
                        revisions.put(int(line.split(b":", 1)[1]))
                        if revisions.qsize() >= 1:
                            return

        # Consume the initial state on one short connection.
        listener = threading.Thread(target=listen, daemon=True); listener.start()
        self.assertEqual(revisions.get(timeout=2), 0); listener.join(timeout=2)

        def listen_for_change():
            request = Request(self.url + "/v1/live", headers={"Authorization": "Bearer " + self.token})
            with urlopen(request, timeout=5) as response:
                seen_initial = False
                for line in response:
                    if line.startswith(b"data:"):
                        revision = int(line.split(b":", 1)[1])
                        if seen_initial and revision > 0:
                            revisions.put(revision); return
                        seen_initial = True
                        ready.set()

        listener = threading.Thread(target=listen_for_change, daemon=True); listener.start()
        self.assertTrue(ready.wait(timeout=2))
        library = self.library("live")
        try:
            library.set_setting("theme", "dark")
            library.configure_sync(True, self.url, self.token)
        finally:
            library.close()
        SyncClient(self.root / "live").sync_once()
        self.assertGreater(revisions.get(timeout=2), 0)
        listener.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
