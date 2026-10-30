"""End-to-end checks in an isolated library, also executable inside the frozen app."""
import json
import os
import tempfile
import traceback
from pathlib import Path

from PySide6.QtCore import QRect, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPainter, QPdfWriter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QLineEdit, QPushButton

from .app import MainWindow
from .storage import Library
from .widgets import AnnotationDialog, BookmarkDialog


def create_fixture(path, title="Uma vida entre livros", subtitle="CADERNO DE LEITURA", pages=8, color="#3f6652"):
    writer = QPdfWriter(str(path)); writer.setResolution(96); writer.setTitle(title)
    painter = QPainter(writer)
    width, height = writer.width(), writer.height()
    for page in range(pages):
        if page:
            writer.newPage()
        painter.fillRect(0, 0, width, height, QColor("#f4f0e5"))
        painter.setPen(QColor(color))
        if page == 0:
            painter.fillRect(45, 45, width-90, height-90, QColor(color))
            painter.setPen(QColor("#eee7d4")); painter.setFont(QFont("Georgia", 34))
            painter.drawText(QRect(80, 220, width-160, 260), Qt.TextFlag.TextWordWrap, title)
            painter.setFont(QFont("Segoe UI", 12)); painter.drawText(80, 120, subtitle)
            painter.drawLine(80, height-180, width-80, height-180)
            painter.drawText(80, height-130, "ENTRELINHAS  /  BIBLIOTECA DE TESTE")
        else:
            painter.setFont(QFont("Georgia", 27)); painter.drawText(55, 100, f"Capítulo {page} · O tempo de ler")
            painter.setPen(QColor("#303b32")); painter.setFont(QFont("Georgia", 14))
            text = ("Ler é uma forma de guardar encontros. A cada página, uma ideia abre espaço para outra. "
                    "Este documento demonstra a leitura, a pesquisa e os marcadores do Entrelinhas.\n\n"
                    "Algumas palavras merecem uma pausa. Você pode marcar esta página, dar um nome ao trecho "
                    "e escrever uma nota para encontrá-lo depois.\n\n"
                    "A biblioteca preserva uma cópia de cada PDF. Pastas e tags ajudam a organizar seus livros, "
                    "enquanto a última página lida fica salva automaticamente.\n\n"
                    "Pesquisar a palavra encontros permite testar a navegação pelos resultados de busca.")
            painter.drawText(QRect(55, 150, width-110, height-280), Qt.TextFlag.TextWordWrap, text)
        painter.drawText(width//2, height-25, str(page+1))
    painter.end()


def smoke_test(report_path):
    report_path = Path(report_path).resolve(); report_path.parent.mkdir(parents=True, exist_ok=True)
    report = {"ok": False, "checks": []}
    app = QApplication.instance() or QApplication([]); app.setStyle("Fusion")
    # The offscreen Windows plugin does not discover system fonts automatically.
    for font in ("segoeui.ttf", "segoeuib.ttf", "georgia.ttf"):
        path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / font
        if path.is_file():
            QFontDatabase.addApplicationFont(str(path))
    app.setFont(QFont("Segoe UI", 10))
    window, library = None, None
    temporary_context = tempfile.TemporaryDirectory(prefix="entrelinhas-test-", ignore_cleanup_errors=True)
    try:
        with temporary_context as temporary:
            root = Path(temporary); fixture = root / "livro.pdf"; create_fixture(fixture)
            library = Library(root / "library"); window = MainWindow(library); window.show(); QTest.qWait(100)
            window.grab().save(str(report_path.parent / "biblioteca-vazia.png"))
            window.import_paths([str(fixture)])
            assert len(library.books()) == 1
            book_id = library.books()[0]["id"]
            window.import_paths([str(fixture)]); assert len(library.books()) == 1
            report["checks"].append("Importação real, cópia local, capa e deduplicação")
            folder = library.add_folder("Literatura"); child = library.add_folder("Para reler", folder)
            library.edit_book(book_id, "Uma vida entre livros", ["literatura", "reflexões"], child, True)
            for name, title, color in (("outro.pdf", "O hábito da atenção", "#aa754c"), ("terceiro.pdf", "Pequenas descobertas", "#4f6d82")):
                path = root / name; create_fixture(path, title=title, color=color, pages=4); window.import_paths([str(path)])
            window.refresh_sidebar(); window.navigate(); window.grid.setCurrentRow(0)
            original_order = [b["id"] for b in library.books()]
            window.move_selected(1)
            assert [b["id"] for b in library.books()] == [original_order[1], original_order[0], original_order[2]]
            window.move_selected(-1)
            assert len(library.books(scope="folder", folder_id=folder)) == 1
            window.library_search.setText("reflexoes"); assert window.grid.count() == 1
            window.library_search.clear(); window.navigate("favorites"); assert window.grid.count() == 1
            report["checks"].append("Pastas aninhadas, tags, filtro sem acento, favoritos e ordem persistida")
            window.open_book(book_id); QTest.qWait(250)
            window.go_page(4); QTest.qWait(150)
            assert window.pdf_view.pageNavigator().currentPage() == 4
            assert library.book(book_id)["last_page"] == 4

            def accept_marker():
                dialog = app.activeModalWidget()
                assert isinstance(dialog, BookmarkDialog)
                dialog.title.setText("Uma ideia para guardar")
                dialog.note.setPlainText("Retomar este trecho na próxima leitura.")
                dialog.color.setCurrentIndex(1); dialog.accept()

            QTimer.singleShot(80, accept_marker); window.mark_button.click()
            assert len(library.bookmarks(book_id)) == 1
            assert library.bookmarks(book_id)[0]["page"] == 4
            window.go_page(1); QTest.qWait(100)
            item = window.marker_list.item(0)
            QTest.mouseClick(window.marker_list.viewport(), Qt.MouseButton.LeftButton, pos=window.marker_list.visualItemRect(item).center())
            QTest.qWait(100); assert window.pdf_view.pageNavigator().currentPage() == 4
            report["checks"].append("Botão de marcador, diálogo com nota/cor e clique para voltar à página 5")
            window.pdf_search.setText("encontros"); window.perform_search()
            for _ in range(100):
                if window.search_model.count() > 0:
                    break
                QTest.qWait(20)
            assert window.search_model.count() > 0
            window.find_result(1); QTest.qWait(100)
            assert window.pdf_view.pageNavigator().currentPage() >= 1
            window.pdf_search.clear(); window.go_page(4)
            report["checks"].append("Pesquisa real no texto do PDF e salto para resultado")

            def accept_annotation():
                dialog = app.activeModalWidget()
                assert isinstance(dialog, AnnotationDialog)
                assert "Página 5 do PDF" in dialog.page_label.text()
                dialog.text.setPlainText("Uma ideia para retomar: ler com atenção e relacionar este trecho às páginas anteriores.")
                dialog.grab().save(str(report_path.parent / "anotacao-dialogo.png"))
                dialog.save_button.click()

            for _ in range(2):
                QTimer.singleShot(50, accept_annotation); window.annotate_button.click()
            assert len(library.annotations(book_id)) == 2
            assert all(note["page"] == 4 for note in library.annotations(book_id))
            window.go_page(1)
            window.annotation_panel.list.setCurrentRow(0)
            QTimer.singleShot(50, accept_annotation); window.annotation_panel.edit_button.click()
            assert all(note["page"] == 4 for note in library.annotations(book_id))
            item = window.annotation_panel.list.item(0)
            QTest.mouseClick(window.annotation_panel.list.viewport(), Qt.MouseButton.LeftButton,
                             pos=window.annotation_panel.list.visualItemRect(item).center())
            assert window.pdf_view.pageNavigator().currentPage() == 4
            report["checks"].append("Duas anotações na página 5, edição a partir de outra página e clique para voltar à origem")
            window.close(); library.close(); window = None; library = None
            library = Library(root / "library"); window = MainWindow(library); window.show()
            window.open_book(book_id); QTest.qWait(200)
            assert window.pdf_view.pageNavigator().currentPage() == 4
            assert window.marker_list.count() == 1
            assert window.annotation_panel.list.count() == 2
            assert all(note["page"] == 4 for note in library.annotations(book_id))
            window.reader_tabs.setCurrentWidget(window.annotation_panel)
            report["checks"].append("Fechamento e reabertura preservam página, nome, pasta, tags, marcador e anotações")
            window.grab().save(str(report_path.parent / "leitor.png"))
            library.set_setting("theme", "dark"); window.apply_preferences(); QTest.qWait(100)
            window.grab().save(str(report_path.parent / "leitor-escuro.png"))
            library.set_setting("theme", "light"); window.apply_preferences()
            window.activateWindow(); window.pdf_view.setFocus(); QTest.qWait(50)
            for mode, key, modifiers, page in (
                ("full", Qt.Key.Key_F11, Qt.KeyboardModifier.NoModifier, 2),
                ("focus", Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier, 6),
            ):
                window.activateWindow(); window.pdf_view.setFocus(); QTest.qWait(50)
                QTest.keyClick(window, key, modifiers); QTest.qWait(100)
                assert window.reading_mode == mode and window.isFullScreen(), (mode, window.reading_mode, window.isActiveWindow(), app.activeWindow())
                assert window.pdf_view.viewport().size() == window.size()
                def accept_immersive_annotation():
                    dialog = app.activeModalWidget()
                    assert isinstance(dialog, AnnotationDialog)
                    dialog.text.setPlainText(f"Anotação criada em {mode}, na página {page+1}.")
                    dialog.save_button.click()
                window.go_page(page); QTimer.singleShot(50, accept_immersive_annotation)
                next(b for b in window.reading_controls.findChildren(QPushButton) if b.text() == "Anotar").click()
                assert any(note["page"] == page for note in library.annotations(book_id))
                assert window.reading_panel_tabs.currentWidget() == window.immersive_annotation_panel
                window.go_page(0); QTest.qWait(50)
                item = next(window.immersive_annotation_panel.list.item(i)
                            for i in range(window.immersive_annotation_panel.list.count())
                            if window.immersive_annotation_panel.list.item(i).data(Qt.ItemDataRole.UserRole)["page"] == page)
                QTest.mouseClick(window.immersive_annotation_panel.list.viewport(), Qt.MouseButton.LeftButton,
                                 pos=window.immersive_annotation_panel.list.visualItemRect(item).center())
                QTest.qWait(50)
                assert window.pdf_view.pageNavigator().currentPage() == page
                window.grab().save(str(report_path.parent / f"anotacoes-{mode}.png"))
                window.go_page(page); QTimer.singleShot(50, accept_marker)
                next(b for b in window.reading_controls.findChildren(QPushButton) if b.text() == "Marcar").click()
                assert library.bookmark_at(book_id, page)
                if window.reading_markers.isHidden() or window.reading_panel_tabs.currentWidget() != window.immersive_marker_panel:
                    window.toggle_reading_markers()
                window.go_page(0); QTest.qWait(50)
                item = next(window.immersive_markers.item(i) for i in range(window.immersive_markers.count())
                            if window.immersive_markers.item(i).data(Qt.ItemDataRole.UserRole)["page"] == page)
                QTest.mouseClick(window.immersive_markers.viewport(), Qt.MouseButton.LeftButton,
                                 pos=window.immersive_markers.visualItemRect(item).center())
                QTest.qWait(100)
                assert window.pdf_view.pageNavigator().currentPage() == page
                assert window.isFullScreen()
                window.grab().save(str(report_path.parent / f"leitor-{mode}.png"))
            window.activateWindow(); window.pdf_view.setFocus(); QTest.qWait(50)
            QTest.keyClick(window, Qt.Key.Key_Escape); QTest.qWait(100)
            assert window.reading_mode == "normal"
            for page in (2, 6):
                library.delete_bookmark(library.bookmark_at(book_id, page)["id"])
            window.refresh_markers()
            report["checks"].append("F11 tela cheia, Ctrl+F foco, Esc normal, criação e retorno aos marcadores e anotações nos dois modos")
            window.navigate("bookmarks"); assert window.all_markers.count() == 1
            window.grab().save(str(report_path.parent / "marcadores.png"))
            mark = window.all_markers.item(0)
            QTest.mouseClick(window.all_markers.viewport(), Qt.MouseButton.LeftButton, pos=window.all_markers.visualItemRect(mark).center())
            QTest.qWait(100); assert window.pdf_view.pageNavigator().currentPage() == 4
            report["checks"].append("Tema escuro, modo foco e retorno pela lista global de marcadores")
            linked_progress_id, _ = library.add_progress_book(book_id)
            custom_progress_id = library.add_custom_progress("Cem anos de solidão · edição impressa", 417)
            library.update_progress_item(custom_progress_id, 126)
            window.navigate("progress"); QTest.qWait(100)
            assert window.progress_list.count() == 2
            assert library.progress_item(linked_progress_id)["current_page"] == 5
            window.grab().save(str(report_path.parent / "progresso.png"))
            report["checks"].append("Progresso de PDF e livro customizado, página atual, percentual e persistência")
            window.back_to_library(); QTest.qWait(100); window.grab().save(str(report_path.parent / "biblioteca.png"))
            library.backup(root / "backup.zip"); assert (root / "backup.zip").stat().st_size > 1000
            report["checks"].append("Backup ZIP com banco e arquivos")
            window.close(); window = None; library.close(); library = None
        report["ok"] = True
    except Exception:
        report["error"] = traceback.format_exc()
        if window:
            window.close()
        if library:
            library.close()
    temporary_context.cleanup()
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["ok"] else 1
