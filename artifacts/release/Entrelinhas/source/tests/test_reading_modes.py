import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QEvent, QObject, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton
from leitor.app import MainWindow
from leitor.smoke import create_fixture
from leitor.storage import Library
from leitor.widgets import BookmarkDialog


class FakeScreen(QObject):
    geometryChanged = Signal(QRect)

    def __init__(self, rectangle):
        super().__init__()
        self.rectangle = rectangle

    def geometry(self):
        return self.rectangle


class ReadingModeTests(unittest.TestCase):
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
        self.window.go_page(4); QTest.qWait(50)

    def tearDown(self):
        self.window.close(); self.window.deleteLater()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        QTest.qWait(50)
        self.library.close(); self.tmp.cleanup()

    def test_fullscreen_fills_viewport_and_restores_window_zoom_and_page(self):
        window = self.window
        window.zoom.setCurrentIndex(window.zoom.findData(1.25))
        QTest.qWait(50); window.go_page(4)
        old_zoom = window.pdf_view.zoomFactor()
        old_size = window.size()
        window.set_reading_mode("full"); QTest.qWait(100)
        self.assertTrue(window.isFullScreen())
        for widget in (window.sidebar, window.reader_header, window.reader_toolbar, window.reader_panel, window.statusBar()):
            self.assertFalse(widget.isVisible())
        self.assertEqual(window.pdf_view.viewport().size(), window.size())
        self.assertEqual(window.pdf_view.pageNavigator().currentPage(), 4)
        self.assertEqual(window.blackouts.covers, {})
        window.set_reading_mode("focus"); QTest.qWait(50)
        self.assertTrue(window.isFullScreen())
        window.escape(); QTest.qWait(50)
        self.assertFalse(window.isFullScreen()); self.assertEqual(window.reading_mode, "normal")
        self.assertTrue(window.sidebar.isVisible()); self.assertTrue(window.reader_panel.isVisible())
        self.assertEqual(window.size(), old_size)
        self.assertEqual(window.pdf_view.zoomFactor(), old_zoom)
        self.assertEqual(window.pdf_view.pageNavigator().currentPage(), 4)

    def test_add_and_visit_bookmarks_in_both_immersive_modes(self):
        window = self.window
        for mode, page in (("full", 2), ("focus", 5)):
            window.set_reading_mode(mode); QTest.qWait(50); window.go_page(page)
            def accept():
                dialog = QApplication.activeModalWidget()
                self.assertIsInstance(dialog, BookmarkDialog)
                dialog.title.setText(f"Marcador {mode}"); dialog.note.setPlainText("Minha nota"); dialog.accept()
            QTimer.singleShot(20, accept)
            next(b for b in window.reading_controls.findChildren(QPushButton) if b.text() == "Marcar").click()
            self.assertIsNotNone(self.library.bookmark_at(self.book_id, page))
            if window.reading_markers.isHidden():
                window.toggle_reading_markers()
            window.go_page(0); QTest.qWait(50)
            item = next(window.immersive_markers.item(i) for i in range(window.immersive_markers.count())
                        if window.immersive_markers.item(i).data(Qt.ItemDataRole.UserRole)["page"] == page)
            QTest.mouseClick(window.immersive_markers.viewport(), Qt.MouseButton.LeftButton,
                             pos=window.immersive_markers.visualItemRect(item).center())
            self.assertEqual(window.pdf_view.pageNavigator().currentPage(), page)
            self.assertTrue(window.isFullScreen()); self.assertEqual(window.reading_mode, mode)
        window.back_to_library()
        self.assertEqual(window.reading_mode, "normal")
        self.assertFalse(window.reading_markers.isVisible())

    def test_requested_keyboard_shortcuts(self):
        window = self.window
        window.activateWindow(); window.pdf_view.setFocus(); QTest.qWait(50)
        QTest.keyClick(window, Qt.Key.Key_F11); QTest.qWait(50)
        self.assertEqual(window.reading_mode, "full")
        QTest.keyClick(window, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier); QTest.qWait(50)
        self.assertEqual(window.reading_mode, "focus")
        QTest.keyClick(window, Qt.Key.Key_Escape); QTest.qWait(50)
        self.assertEqual(window.reading_mode, "normal")
        QTest.keyClick(window, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
        self.assertTrue(window.pdf_search.hasFocus())

    def test_explicit_navigation_overrides_pending_layout_restore(self):
        window = self.window
        window.set_reading_mode("full")
        window.go_page(2); QTest.qWait(100)
        self.assertIsNone(window.reading_page_restore)
        # A later layout must not navigate back to the page before the mode change.
        self.assertEqual(window.pdf_view.pageNavigator().currentPage(), 2)
        window.go_page(2)
        window.set_reading_mode("focus"); window.set_reading_mode("normal")
        QTest.qWait(100)
        self.assertEqual(window.pdf_view.pageNavigator().currentPage(), 2)
        self.assertEqual(self.library.book(self.book_id)["last_page"], 2)

    def test_monitor_routing_activation_and_disconnection(self):
        first = FakeScreen(QRect(0, 0, 1920, 1080))
        second = FakeScreen(QRect(1920, 0, 2560, 1440))
        left = FakeScreen(QRect(-1280, 0, 1280, 1024))
        mirrored = FakeScreen(first.geometry())
        controller = self.window.blackouts
        with patch("leitor.reading_modes.QApplication.screens", return_value=[first, second, left, mirrored]) as screens, \
             patch.object(self.window, "screen", return_value=first) as current, \
             patch.object(controller, "is_reading_active", return_value=True) as active, \
             patch("leitor.reading_modes.BlackoutWindow") as factory:
            factory.side_effect = lambda *_: MagicMock()
            controller.set_enabled(True)
            self.assertEqual(set(controller.covers), {second, left})
            for screen, cover in controller.covers.items():
                cover.cover.assert_called_with(screen)
            old_covers = list(controller.covers.values())
            active.return_value = False; controller.refresh()
            self.assertEqual(controller.covers, {})
            for cover in old_covers:
                cover.close.assert_called_once()
            active.return_value = True; current.return_value = second; controller.refresh()
            self.assertIn(first, controller.covers); self.assertNotIn(second, controller.covers)
            screens.return_value = [second]; controller.refresh()
            self.assertEqual(controller.covers, {})
            controller.set_enabled(False)


if __name__ == "__main__":
    unittest.main()
