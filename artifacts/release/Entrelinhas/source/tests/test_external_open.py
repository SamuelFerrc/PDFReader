import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog
from leitor.app import MainWindow
from leitor.smoke import create_fixture
from leitor.storage import Library
from leitor.windows_integration import registration_entries
from main import parse_args


class ExternalOpenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.library = Library(self.root / "library")
        self.window = MainWindow(self.library); self.window.show()
        self.pdf = self.root / "Leitura com acentuação & espaços.pdf"
        create_fixture(self.pdf)

    def tearDown(self):
        self.window.close(); self.window.deleteLater()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        QTest.qWait(50)
        self.library.close(); self.tmp.cleanup()

    def wait_for_requests(self):
        for _ in range(50):
            QTest.qWait(20)
            if not self.window.external_request_active:
                return
        self.fail("O pedido do Windows não foi processado.")

    def test_shell_imports_copy_opens_and_keeps_existing_metadata(self):
        folder = self.library.add_folder("Estudos")
        self.window.navigate("folder", folder)
        self.window.receive_external_files([str(self.pdf)])
        self.wait_for_requests()
        book = self.library.books()[0]
        self.assertIsNone(book["folder_id"])
        self.assertEqual(self.window.stack.currentIndex(), 1)
        self.assertEqual(self.window.current_book, book["id"])
        managed = self.library.files / book["filename"]
        self.assertEqual(managed.read_bytes(), self.pdf.read_bytes())
        self.window.go_page(4)
        self.library.save_bookmark(book["id"], 4, "Retomar")
        self.library.edit_book(book["id"], "Nome escolhido", ["estudo"], folder, True)
        self.window.receive_external_files([str(self.pdf)]); self.wait_for_requests()
        self.assertEqual(len(self.library.books()), 1)
        self.assertEqual(self.library.book(book["id"])["title"], "Nome escolhido")
        self.assertEqual(self.library.book(book["id"])["folder_id"], folder)
        self.assertEqual(self.library.bookmarks(book["id"])[0]["page"], 4)
        self.assertEqual(self.window.pdf_view.pageNavigator().currentPage(), 4)
        self.pdf.unlink(); self.assertTrue(managed.exists())

    def test_shell_request_waits_for_open_dialog(self):
        dialog = QDialog(self.window); dialog.setModal(True); dialog.show(); QTest.qWait(30)
        self.window.receive_external_files([str(self.pdf)]); QTest.qWait(50)
        self.assertEqual(self.library.books(), [])
        dialog.accept(); self.wait_for_requests()
        self.assertEqual(len(self.library.books()), 1)

    def test_missing_file_does_not_import_or_erase_current_book(self):
        self.window.receive_external_files([str(self.pdf)]); self.wait_for_requests()
        book_id = self.window.current_book
        with patch("leitor.app.QMessageBox.warning") as warning:
            self.window.receive_external_files([str(self.root / "missing.pdf")]); self.wait_for_requests()
        warning.assert_called_once()
        self.assertEqual(self.window.current_book, book_id)
        self.assertEqual(len(self.library.books()), 1)

    def test_cli_and_registration_quote_paths_without_changing_default(self):
        args = parse_args(["--", str(self.pdf)])
        self.assertEqual(args.files, [str(self.pdf)])
        entries = registration_entries(self.root / "Uma pasta" / "Entrelinhas.exe")
        commands = [value for key, name, value in entries if key.endswith("\\command")]
        self.assertEqual(len(commands), 3)
        self.assertTrue(all(c.startswith('"') and c.endswith('" -- "%1"') for c in commands))
        self.assertFalse(any("UserChoice" in key or (key == r"Software\Classes\.pdf" and not name) for key, name, _ in entries))


if __name__ == "__main__":
    unittest.main()
