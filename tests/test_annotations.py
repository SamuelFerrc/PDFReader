import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QPushButton

from leitor.app import MainWindow
from leitor.smoke import create_fixture
from leitor.storage import Library
from leitor.widgets import AnnotationDialog


class AnnotationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        QFontDatabase.addApplicationFont(str(Path(os.environ["WINDIR"]) / "Fonts/segoeui.ttf"))

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.library = Library(self.root / "library")
        path = self.root / "Leitura.pdf"; create_fixture(path)
        self.book_id, _ = self.library.import_file(path, 8)
        self.window = MainWindow(self.library); self.window.show()
        self.window.open_book(self.book_id); QTest.qWait(100)

    def tearDown(self):
        self.window.close(); self.window.deleteLater()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        QTest.qWait(30)
        self.library.close(); self.tmp.cleanup()

    def fill_dialog(self, trigger, text, *, cancel=False, navigate_to=None):
        observed = {}
        def respond():
            dialog = QApplication.activeModalWidget()
            observed["type"] = type(dialog)
            if isinstance(dialog, AnnotationDialog):
                observed["page"] = dialog.page_label.text()
                dialog.text.setPlainText(text)
                if navigate_to is not None:
                    self.window.go_page(navigate_to)
                if cancel:
                    dialog.reject()
                else:
                    dialog.save_button.click()
            elif dialog:
                dialog.reject()
        QTimer.singleShot(30, respond)
        trigger()
        self.assertEqual(observed.get("type"), AnnotationDialog)
        return observed

    def test_create_edit_visit_cancel_and_delete_in_all_reading_modes(self):
        window = self.window
        for mode, page in (("normal", 0), ("full", 3), ("focus", 7)):
            with self.subTest(mode=mode):
                window.set_reading_mode(mode); QTest.qWait(80); window.go_page(page)
                panel = window.annotation_panel if mode == "normal" else window.immersive_annotation_panel
                trigger = window.annotate_button.click if mode == "normal" else next(
                    b for b in window.reading_controls.findChildren(QPushButton) if b.text() == "Anotar").click
                observed = self.fill_dialog(trigger, "Primeira anotação\nCom várias linhas.", navigate_to=1)
                self.assertIn(f"Página {page+1} do PDF", observed["page"])
                first = self.library.annotations(self.book_id)[0]
                self.assertEqual(first["page"], page)
                self.assertEqual(panel.list.count(), 1)
                window.go_page(page)
                self.fill_dialog(panel.add_button.click, "Segunda na mesma página")
                self.assertEqual(len(self.library.annotations(self.book_id)), 2)
                self.assertEqual({n["page"] for n in self.library.annotations(self.book_id)}, {page})
                window.go_page(1)
                panel.list.setCurrentRow(0)
                observed = self.fill_dialog(panel.edit_button.click, "Texto revisado")
                self.assertIn(f"Página {page+1} do PDF", observed["page"])
                edited = next(n for n in self.library.annotations(self.book_id) if n["id"] == first["id"])
                self.assertEqual(edited["page"], page)
                self.assertEqual(edited["created_at"], first["created_at"])
                self.assertEqual(edited["text"], "Texto revisado")
                self.fill_dialog(panel.edit_button.click, "Descartar mudança", cancel=True)
                self.fill_dialog(panel.add_button.click, "Descartar nova", cancel=True)
                self.assertEqual(len(self.library.annotations(self.book_id)), 2)
                self.assertEqual(self.library.annotations(self.book_id)[0]["text"], "Texto revisado")
                QTest.qWait(30)
                item = panel.list.item(0)
                self.assertTrue(item.text().startswith(f"Página {page+1}\n"))
                QTest.mouseClick(panel.list.viewport(), Qt.MouseButton.LeftButton,
                                 pos=panel.list.visualItemRect(item).center())
                self.assertEqual(window.pdf_view.pageNavigator().currentPage(), page)
                self.assertEqual(window.reading_mode, mode)
                with patch("leitor.app.QMessageBox.question", return_value=QMessageBox.StandardButton.No):
                    panel.delete_button.click()
                self.assertEqual(len(self.library.annotations(self.book_id)), 2)
                with patch("leitor.app.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
                    panel.delete_button.click()
                    panel.list.setCurrentRow(0); panel.delete_button.click()
                self.assertEqual(self.library.annotations(self.book_id), [])
                self.assertEqual(window.annotation_panel.list.count(), 0)
                self.assertEqual(window.immersive_annotation_panel.list.count(), 0)
                self.assertFalse(panel.edit_button.isEnabled())

    def test_dialog_rejects_blank_text(self):
        dialog = AnnotationDialog(0, parent=self.window)
        self.assertFalse(dialog.save_button.isEnabled())
        dialog.text.setPlainText(" \n\t "); dialog.accept()
        self.assertFalse(dialog.save_button.isEnabled())
        self.assertNotEqual(dialog.result(), QDialog.DialogCode.Accepted)
        dialog.text.setPlainText("Uma observação")
        self.assertTrue(dialog.save_button.isEnabled())
        dialog.save_button.click()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)

    def test_keyboard_shortcut_and_switching_books(self):
        window = self.window
        window.go_page(4); window.activateWindow(); window.pdf_view.setFocus(); QTest.qWait(50)
        self.fill_dialog(lambda: QTest.keyClick(window, Qt.Key.Key_N, Qt.KeyboardModifier.ControlModifier), "Atalho")
        path = self.root / "Outro.pdf"; create_fixture(path, title="Outro livro", pages=2)
        other_id, _ = self.library.import_file(path, 2)
        window.open_book(other_id); QTest.qWait(50)
        self.assertEqual(window.annotation_panel.list.count(), 0)
        self.assertEqual(window.immersive_annotation_panel.list.count(), 0)
        window.open_book(self.book_id); QTest.qWait(50)
        self.assertEqual(window.annotation_panel.list.item(0).text(), "Página 5\nAtalho")
        window.back_to_library()
        with patch("leitor.app.AnnotationDialog") as dialog:
            window.add_annotation()
            dialog.assert_not_called()


if __name__ == "__main__":
    unittest.main()
