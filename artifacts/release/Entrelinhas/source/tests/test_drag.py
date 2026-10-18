import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QApplication
from leitor.app import MainWindow
from leitor.storage import Library


class DragOrderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_drop_reorders_and_survives_reopening(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); library = Library(root / "library")
            for number in range(3):
                source = root / f"{number}.pdf"; source.write_bytes(str(number).encode())
                library.import_file(source, 1)
            window = MainWindow(library); window.show(); self.app.processEvents()
            grid = window.grid; before = [b["id"] for b in library.books()]; grid.setCurrentRow(0)
            mime = grid.model().mimeData(grid.selectedIndexes())
            target = grid.visualItemRect(grid.item(2)).center()
            event = QDropEvent(QPointF(target), Qt.DropAction.MoveAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
            grid.dropEvent(event)
            self.assertTrue(event.isAccepted()); self.assertEqual(grid.count(), 3)
            self.assertEqual([b["id"] for b in library.books()], [before[1], before[2], before[0]])
            window.close(); library.close()
            library = Library(root / "library")
            self.assertEqual([b["id"] for b in library.books()], [before[1], before[2], before[0]])
            library.close()


if __name__ == "__main__":
    unittest.main()
