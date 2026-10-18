"""Exercise native fullscreen and blackout windows on every connected monitor."""
import json
import sys
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QFont
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from leitor.app import MainWindow
from leitor.smoke import create_fixture
from leitor.storage import Library


def verify(output):
    app = QApplication.instance() or QApplication([])
    assert app.platformName() != "offscreen", "Use the native Windows platform for this test."
    app.setStyle("Fusion"); app.setFont(QFont("Segoe UI", 10))
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {"ok": False, "screens": [], "checks": []}
    temporary = tempfile.TemporaryDirectory(prefix="entrelinhas-monitors-", ignore_cleanup_errors=True)
    window, library = None, None
    try:
        root = Path(temporary.name)
        fixture = root / "Leitura de teste.pdf"; create_fixture(fixture)
        library = Library(root / "library")
        book_id, _ = library.import_file(fixture, 8)
        library.save_bookmark(book_id, 4, "Voltar a esta página", "Marcador disponível em todos os modos.", "sage")
        window = MainWindow(library); window.show(); window.open_book(book_id)
        QTest.qWait(200)
        for index, screen in enumerate(app.screens()):
            window.set_reading_mode("normal"); QTest.qWait(100)
            window.windowHandle().setScreen(screen)
            window.move(screen.geometry().topLeft() + QPoint(100, 70))
            window.activateWindow(); window.raise_(); window.pdf_view.setFocus()
            QTest.qWait(150)
            assert window.screen() == screen
            window.go_page(4)
            normal_geometry = window.geometry()
            QTest.keyClick(window, Qt.Key.Key_F11); QTest.qWait(150)
            assert window.isFullScreen() and window.reading_mode == "full"
            assert window.geometry() == screen.geometry()
            assert window.pdf_view.viewport().size() == screen.geometry().size()
            assert window.pdf_view.pageNavigator().currentPage() == 4
            assert not window.blackouts.covers
            QTest.keyClick(window, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
            QTest.qWait(200)
            assert window.isFullScreen() and window.reading_mode == "focus"
            assert window.blackouts.is_reading_active()
            targets = set(window.blackouts.target_screens())
            assert set(window.blackouts.covers) == targets
            covered = []
            for target, cover in window.blackouts.covers.items():
                assert cover.isVisible() and cover.geometry() == target.geometry(), (cover.isVisible(), cover.geometry(), target.geometry(), cover.screen().name())
                pixels = cover.grab().toImage()
                for x in (0, pixels.width() // 2, pixels.width()-1):
                    for y in (0, pixels.height() // 2, pixels.height()-1):
                        assert pixels.pixelColor(x, y).name() == "#000000"
                covered.append(target.name())
            window.toggle_reading_markers(); QTest.qWait(100)
            window.grab().save(str(output.parent / f"foco-monitor-{index+1}.png"))
            window.showMinimized(); QTest.qWait(120)
            assert not window.blackouts.covers
            window.showFullScreen(); window.activateWindow(); QTest.qWait(150)
            assert set(window.blackouts.covers) == targets
            QTest.keyClick(window, Qt.Key.Key_Escape); QTest.qWait(150)
            assert window.reading_mode == "normal" and not window.isFullScreen()
            assert window.geometry() == normal_geometry
            assert not window.blackouts.covers
            assert window.pdf_view.pageNavigator().currentPage() == 4
            report["screens"].append({"reader": screen.name(), "geometry": list(screen.geometry().getRect()), "blackouts": covered})
        window.showMaximized(); QTest.qWait(100)
        window.go_page(4); window.toggle_fullscreen(); QTest.qWait(100)
        window.escape(); QTest.qWait(100)
        assert window.isMaximized() and window.pdf_view.pageNavigator().currentPage() == 4
        report["checks"] = ["F11 e Ctrl+F em cada monitor", "PDF preenche o monitor", "Outro monitor coberto de preto",
                            "Marcadores sobre o PDF", "Minimizar retira as coberturas", "Restaurar recria as coberturas",
                            "Esc restaura geometria e página", "Janela maximizada restaurada"]
        report["ok"] = True
    except Exception:
        report["error"] = traceback.format_exc()
    finally:
        if window:
            window.close(); QTest.qWait(50)
        if library:
            library.close()
        temporary.cleanup()
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    destination = Path(sys.argv[1] if len(sys.argv) > 1 else "artifacts/native-modes/report.json").resolve()
    raise SystemExit(verify(destination))
