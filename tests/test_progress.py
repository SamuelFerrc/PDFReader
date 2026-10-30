import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from leitor.app import MainWindow
from leitor.smoke import create_fixture
from leitor.storage import Library
from leitor.widgets import ProgressCard


class ProgressUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.library = Library(self.root / "library")
        source = self.root / "Leitura.pdf"; create_fixture(source)
        self.book_id, _ = self.library.import_file(source, 8)
        self.window = MainWindow(self.library); self.window.show(); QTest.qWait(50)

    def tearDown(self):
        self.window.close(); self.window.deleteLater()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete); QTest.qWait(30)
        self.library.close(); self.tmp.cleanup()

    def test_progress_page_renders_cards_and_saves_inline_page(self):
        progress_id = self.library.add_custom_progress("Livro físico", 200)
        self.window.navigate("progress"); QTest.qWait(20)
        self.assertEqual(self.window.stack.currentIndex(), 3)
        self.assertTrue(self.window.nav["progress"].isChecked())
        self.assertEqual(self.window.progress_list.count(), 1)
        card = self.window.progress_list.itemWidget(self.window.progress_list.item(0))
        self.assertIsInstance(card, ProgressCard)
        card.page.setValue(75); card.save.click(); QTest.qWait(20)
        self.assertEqual(self.library.progress_item(progress_id)["current_page"], 75)

    def test_linked_pdf_progress_opens_at_saved_page(self):
        progress_id, _ = self.library.add_progress_book(self.book_id)
        self.library.update_progress_item(progress_id, 6)
        self.window.open_progress_pdf(progress_id); QTest.qWait(80)
        self.assertEqual(self.window.stack.currentIndex(), 1)
        self.assertEqual(self.window.current_book, self.book_id)
        self.assertEqual(self.window.pdf_view.pageNavigator().currentPage(), 5)


if __name__ == "__main__":
    unittest.main()
