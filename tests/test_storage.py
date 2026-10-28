import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

from leitor.storage import Library


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.library = Library(self.root / "library")

    def tearDown(self):
        self.library.close(); self.tmp.cleanup()

    def add(self, name="livro", content=b"fixture"):
        path = self.root / f"{name}.pdf"; path.write_bytes(content)
        return self.library.import_file(path, 12)[0], path

    def test_import_copies_source_and_deduplicates_and_repairs(self):
        book_id, source = self.add()
        book = self.library.book(book_id); managed = self.library.files / book["filename"]
        self.assertEqual(source.read_bytes(), managed.read_bytes())
        self.assertEqual(self.library.import_file(source, 12), (book_id, False))
        managed.unlink(); self.library.import_file(source, 12)
        self.assertTrue(managed.exists())
        source.unlink(); self.assertTrue(managed.exists())

    def test_page_and_bookmark_persist_on_reopen(self):
        book_id, _ = self.add()
        self.library.save_progress(book_id, 8)
        self.library.save_bookmark(book_id, 8, "Revisar", "Minha nota", "blue")
        self.library.save_bookmark(book_id, 8, "Revisado", "Outra nota", "rose")
        self.library.close(); self.library = Library(self.root / "library")
        self.assertEqual(self.library.book(book_id)["last_page"], 8)
        markers = self.library.bookmarks(book_id)
        self.assertEqual(len(markers), 1); self.assertEqual(markers[0]["title"], "Revisado")
        self.assertEqual(markers[0]["note"], "Outra nota")
        with self.assertRaises(ValueError):
            self.library.save_bookmark(book_id, 12, "Inválido")
        self.library.save_progress(book_id, 999)
        self.assertEqual(self.library.book(book_id)["last_page"], 11)

    def test_deleting_nested_folders_preserves_books_and_markers(self):
        book_id, _ = self.add(); parent = self.library.add_folder("Livros"); child = self.library.add_folder("Estudo", parent)
        self.library.edit_book(book_id, "Anotações", ["ficção", "ficção", " matemática "], child, True)
        self.library.save_bookmark(book_id, 4, "Continua aqui")
        self.assertEqual(len(self.library.books(scope="folder", folder_id=parent)), 1)
        self.library.delete_folder(parent)
        self.assertEqual(self.library.folders(), []); self.assertIsNone(self.library.book(book_id)["folder_id"])
        self.assertEqual(len(self.library.bookmarks(book_id)), 1)
        self.assertEqual(len(self.library.books(query="anotacoes matematica")), 1)
        self.assertEqual(self.library.book(book_id)["tags"], ["ficção", "matemática"])

    def test_reordering_filtered_subset_preserves_hidden_positions(self):
        ids = [self.add(str(i), str(i).encode())[0] for i in range(5)]
        self.library.reorder([ids[4], ids[0], ids[2]])
        self.assertEqual([b["id"] for b in self.library.books()], [ids[4], ids[1], ids[0], ids[3], ids[2]])

    def test_delete_removes_only_managed_copy_and_cascades_markers(self):
        book_id, source = self.add(); managed = self.library.files / self.library.book(book_id)["filename"]
        self.library.save_bookmark(book_id, 0, "Começo"); self.library.delete_book(book_id)
        self.assertTrue(source.exists()); self.assertFalse(managed.exists()); self.assertEqual(self.library.bookmarks(), [])

    def test_backup_contains_a_consistent_recoverable_database(self):
        book_id, _ = self.add(); self.library.save_bookmark(book_id, 3, "Leitura")
        destination = self.root / "backup.zip"; self.library.backup(destination)
        with zipfile.ZipFile(destination) as archive:
            archive.extractall(self.root / "restored")
        restored = Library(self.root / "restored")
        try:
            self.assertEqual(restored.bookmarks()[0]["page"], 3)
            self.assertTrue((restored.files / restored.book(book_id)["filename"]).exists())
        finally:
            restored.close()
        with self.assertRaises(ValueError):
            self.library.backup(self.library.root / "recursive.zip")

    def test_failed_import_does_not_leave_a_managed_file(self):
        source = self.root / "book.pdf"; source.write_bytes(b"fixture")
        with self.assertRaises(sqlite3.IntegrityError):
            self.library.import_file(source, 5, "nonexistent-folder")
        self.assertEqual(list(self.library.files.iterdir()), [])
        self.assertEqual(self.library.books(), [])

    def test_annotations_allow_multiple_per_page_and_persist_original_page_on_edit(self):
        book_id, _ = self.add()
        first = self.library.add_annotation(book_id, 4, "Primeira ideia\nCom acentuação.")
        second = self.library.add_annotation(book_id, 4, "Outra ideia na mesma página")
        self.library.add_annotation(book_id, 0, "Capa")
        before = next(n for n in self.library.annotations(book_id) if n["id"] == first)
        self.library.save_progress(book_id, 9)
        self.library.edit_annotation(first, "  Texto revisado  ")
        self.library.close(); self.library = Library(self.root / "library")
        notes = self.library.annotations(book_id)
        self.assertEqual([n["page"] for n in notes], [0, 4, 4])
        edited = next(n for n in notes if n["id"] == first)
        self.assertEqual(edited["text"], "Texto revisado")
        self.assertEqual(edited["created_at"], before["created_at"])
        self.assertEqual(next(n for n in notes if n["id"] == second)["text"], "Outra ideia na mesma página")

    def test_annotations_validate_page_and_text(self):
        book_id, _ = self.add()
        for invalid_book, page in ((book_id, -1), (book_id, 12), ("missing", 0)):
            with self.assertRaises(ValueError):
                self.library.add_annotation(invalid_book, page, "Nota")
        for text in ("", " \n\t "):
            with self.assertRaises(ValueError):
                self.library.add_annotation(book_id, 0, text)
        annotation = self.library.add_annotation(book_id, 11, "Última página")
        with self.assertRaises(ValueError):
            self.library.edit_annotation(annotation, " \n ")
        self.assertEqual(self.library.annotations(book_id)[0]["text"], "Última página")

    def test_annotations_are_scoped_to_books_and_cascade_on_delete(self):
        first, source = self.add()
        second, _ = self.add("outro", b"other")
        note = self.library.add_annotation(first, 0, "Apagar só esta")
        self.library.add_annotation(first, 0, "Manter até excluir livro")
        self.library.add_annotation(second, 0, "Outro livro")
        self.library.save_bookmark(first, 0, "Marcador", "Nota do marcador")
        self.library.delete_annotation(note)
        self.assertEqual(len(self.library.annotations(first)), 1)
        self.assertEqual(self.library.bookmarks(first)[0]["note"], "Nota do marcador")
        self.library.delete_book(first)
        self.assertEqual(self.library.annotations(first), [])
        self.assertEqual(self.library.annotations(second)[0]["text"], "Outro livro")
        self.assertTrue(source.exists())

    def test_annotations_survive_backup_restore(self):
        book_id, _ = self.add()
        self.library.add_annotation(book_id, 7, "Observação\nOutra linha.")
        self.library.backup(self.root / "notes.zip")
        with zipfile.ZipFile(self.root / "notes.zip") as archive:
            archive.extractall(self.root / "restored")
        restored = Library(self.root / "restored")
        try:
            self.assertEqual(restored.annotations(book_id), self.library.annotations(book_id))
        finally:
            restored.close()

    def test_existing_library_upgrades_without_changing_books_or_bookmarks(self):
        book_id, _ = self.add()
        self.library.save_progress(book_id, 5)
        self.library.save_bookmark(book_id, 5, "Já existia", "Preservar esta nota")
        # Recreate the schema of the previously shipped version.
        self.library.db.executescript("DROP TABLE annotations; PRAGMA user_version=1;")
        self.library.close(); self.library = Library(self.root / "library")
        self.assertEqual(self.library.book(book_id)["last_page"], 5)
        self.assertEqual(self.library.bookmarks(book_id)[0]["note"], "Preservar esta nota")
        self.library.add_annotation(book_id, 5, "Nova anotação")
        self.assertEqual(len(self.library.annotations(book_id)), 1)


if __name__ == "__main__":
    unittest.main()
