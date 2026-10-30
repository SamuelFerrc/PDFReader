from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QByteArray, QEventLoop, QMargins, QPointF, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QColor, QCursor, QDesktopServices, QFont, QKeySequence, QPalette, QShortcut
from PySide6.QtPdf import QPdfBookmarkModel, QPdfDocument, QPdfSearchModel
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import (
    QAbstractSpinBox, QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMenu, QMessageBox, QProgressDialog, QPushButton,
    QSizePolicy, QSpinBox, QSplitter, QStackedWidget, QSystemTrayIcon, QTabWidget, QTreeView,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from .storage import Library
from .sync import SyncService
from .reading_modes import ReadingModesMixin
from .widgets import (
    COLORS, AnnotationDialog, AnnotationPanel, BookDelegate, BookDialog, BookGrid, BookmarkDialog,
    CustomProgressDialog, ProgressCard, button, folder_options, icon, stylesheet,
)


def label(text, name=""):
    result = QLabel(text)
    result.setTextFormat(Qt.TextFormat.PlainText)
    if name:
        result.setObjectName(name)
    return result


class MainWindow(ReadingModesMixin, QMainWindow):
    def __init__(self, library: Library):
        super().__init__()
        self.library = library
        self.current_book = None
        self.scope, self.folder_id, self.tag = "all", None, None
        self.loading = False
        self.reading_mode = "normal"
        self.search_index = -1
        self.navigation_revision = 0
        self.external_requests = []
        self.external_request_active = False
        self.document = QPdfDocument(self)
        self.setWindowTitle("Entrelinhas · Leitor de PDF")
        self.setWindowIcon(icon("book", "#38664e", 48))
        self.setMinimumSize(1050, 700)
        self.resize(1360, 880)
        self.setAcceptDrops(True)
        self._build()
        self.init_reading_modes()
        self._shortcuts()
        self.apply_preferences()
        self.refresh_sidebar()
        self.refresh_library()
        self.refresh_progress()
        self._setup_tray()
        self.sync_status = label("", "muted")
        self.statusBar().addPermanentWidget(self.sync_status)
        self.sync_service = SyncService(library, self)
        self.sync_service.statusChanged.connect(self.on_sync_status)
        self.sync_service.dataChanged.connect(self.on_sync_data_changed)
        self.sync_service.start()
        geometry = library.setting("window_geometry")
        if geometry:
            self.restoreGeometry(QByteArray.fromBase64(geometry.encode()))
        self.statusBar().showMessage("Sua biblioteca fica salva neste computador.")

    def _build(self):
        root = QWidget(); root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0); root_layout.setSpacing(0)
        self.setCentralWidget(root)
        self.sidebar = QFrame(); self.sidebar.setObjectName("sidebar"); self.sidebar.setFixedWidth(224)
        side = QVBoxLayout(self.sidebar); side.setContentsMargins(18, 28, 18, 18); side.setSpacing(6)
        brand = QHBoxLayout()
        symbol = QLabel(); symbol.setPixmap(icon("logo", "#3c7050", 30).pixmap(30, 30))
        brand.addWidget(symbol); brand.addWidget(label("entrelinhas", "brand")); brand.addStretch()
        side.addLayout(brand)
        side.addWidget(label("UM LIVRO. SEU TEMPO.", "eyebrow")); side.addSpacing(28)
        side.addWidget(label("BIBLIOTECA", "eyebrow"))
        self.nav = {}
        for key, text, glyph in (("all", "Todos os livros", "grid"), ("reading", "Em leitura", "clock"),
                                 ("favorites", "Favoritos", "star"), ("bookmarks", "Páginas marcadas", "bookmark"),
                                 ("progress", "Progresso de leitura", "progress"),
                                 ("unfiled", "Sem pasta", "folder")):
            nav = button(text, lambda checked=False, key=key: self.navigate(key), "nav", glyph)
            nav.setCheckable(True); self.nav[key] = nav; side.addWidget(nav)
        side.addSpacing(20)
        folder_header = QHBoxLayout(); folder_header.addWidget(label("PASTAS", "eyebrow")); folder_header.addStretch()
        folder_header.addWidget(button("+", self.new_folder, "quiet"))
        side.addLayout(folder_header)
        self.folder_tree = QTreeWidget(); self.folder_tree.setHeaderHidden(True); self.folder_tree.setIndentation(14)
        self.folder_tree.setMinimumHeight(90)
        self.folder_tree.itemClicked.connect(lambda item, col: self.navigate("folder", item.data(0, Qt.ItemDataRole.UserRole)))
        self.folder_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.folder_tree.customContextMenuRequested.connect(self.folder_menu)
        side.addWidget(self.folder_tree, 2)
        side.addWidget(label("TAGS", "eyebrow"))
        self.tag_list = QListWidget(); self.tag_list.setMinimumHeight(60); self.tag_list.setMaximumHeight(155)
        self.tag_list.itemClicked.connect(lambda item: self.navigate("all", tag=item.data(Qt.ItemDataRole.UserRole)))
        side.addWidget(self.tag_list, 1)
        side.addSpacing(8)
        side.addWidget(button("Preferências", self.preferences, "nav", "settings"))
        side.addWidget(label("Local. Pessoal. Sempre seu.", "muted"))
        root_layout.addWidget(self.sidebar)
        self.stack = QStackedWidget(); root_layout.addWidget(self.stack, 1)
        self._build_library()
        self._build_reader()
        self._build_markers()
        self._build_progress()

    def _build_library(self):
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(30, 30, 30, 20); layout.setSpacing(16)
        header = QHBoxLayout(); title = QVBoxLayout(); title.setSpacing(4)
        title.addWidget(label("SEU ESPAÇO DE LEITURA", "eyebrow"))
        self.library_title = label("Sua biblioteca", "heading"); title.addWidget(self.library_title)
        self.library_count = label("", "muted"); title.addWidget(self.library_count)
        header.addLayout(title); header.addStretch()
        header.addWidget(button("Importar PDFs", self.choose_import, "primary", "plus"))
        layout.addLayout(header)
        self.resume = QFrame(); self.resume.setObjectName("resume")
        resume_layout = QHBoxLayout(self.resume); resume_layout.setContentsMargins(20, 15, 20, 15)
        resume_text = QVBoxLayout(); resume_text.setSpacing(4)
        resume_text.addWidget(label("RETOME DE ONDE PAROU", "eyebrow"))
        self.resume_title = label(""); self.resume_title.setFont(QFont("Segoe UI", 12, QFont.Weight.DemiBold))
        self.resume_detail = label("", "muted")
        resume_text.addWidget(self.resume_title); resume_text.addWidget(self.resume_detail)
        resume_layout.addLayout(resume_text, 1)
        resume_layout.addWidget(button("Continuar leitura  →", self.continue_reading, "primary"))
        layout.addWidget(self.resume)
        tools = QHBoxLayout(); tools.setSpacing(12)
        self.library_search = QLineEdit(); self.library_search.setPlaceholderText("Buscar por nome, arquivo ou tag…")
        self.library_search.setClearButtonEnabled(True)
        self.library_search.addAction(icon("search"), QLineEdit.ActionPosition.LeadingPosition)
        self.library_search.textChanged.connect(self.refresh_library)
        tools.addWidget(self.library_search, 1)
        self.sort = QComboBox()
        for text, key in (("Minha ordem", "manual"), ("Nome do livro", "title"), ("Lidos recentemente", "recent"), ("Adicionados recentemente", "added")):
            self.sort.addItem(text, key)
        self.sort.setCurrentIndex(max(0, self.sort.findData(self.library.setting("sort", "manual"))))
        self.sort.currentIndexChanged.connect(self.sort_changed); tools.addWidget(self.sort)
        layout.addLayout(tools)
        self.library_body = QStackedWidget()
        self.grid = BookGrid(); self.delegate = BookDelegate(self.grid); self.grid.setItemDelegate(self.delegate)
        self.grid.itemDoubleClicked.connect(lambda item: self.open_book(item.data(Qt.ItemDataRole.UserRole)["id"]))
        self.grid.itemSelectionChanged.connect(self.update_actions)
        self.grid.reordered.connect(self.save_order); self.grid.filesDropped.connect(self.import_paths)
        self.grid.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.grid.customContextMenuRequested.connect(self.book_menu)
        self.library_body.addWidget(self.grid)
        empty = QWidget(); empty_layout = QVBoxLayout(empty); empty_layout.addStretch()
        empty_icon = QLabel(); empty_icon.setPixmap(icon("book", "#789b79", 80).pixmap(80, 80)); empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_icon); empty_layout.addSpacing(18)
        self.empty_title = label("Sua próxima leitura começa aqui."); self.empty_title.setFont(QFont("Segoe UI", 20, QFont.Weight.DemiBold)); self.empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_description = label("Importe seus PDFs, organize suas leituras e guarde as páginas que importam.", "muted")
        self.empty_description.setWordWrap(True); self.empty_description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(self.empty_title); empty_layout.addWidget(self.empty_description); empty_layout.addSpacing(14)
        empty_action = QHBoxLayout(); empty_action.addStretch(); empty_action.addWidget(button("Escolher PDFs", self.choose_import, "primary", "plus")); empty_action.addStretch()
        empty_layout.addLayout(empty_action); empty_layout.addStretch()
        self.library_body.addWidget(empty); layout.addWidget(self.library_body, 1)
        actions = QHBoxLayout(); self.book_actions = []
        for text, callback, glyph in (("Abrir livro", self.open_selected, "book"), ("Organizar", self.edit_selected, None),
                                      ("Favoritar", self.favorite_selected, "star"), ("←", lambda: self.move_selected(-1), None),
                                      ("→", lambda: self.move_selected(1), None)):
            item = button(text, callback, glyph=glyph); actions.addWidget(item); self.book_actions.append(item)
        actions.addStretch(); layout.addLayout(actions)
        self.order_hint = label("Duplo clique para ler · Arraste os livros para mudar a ordem · Ctrl+O para importar", "muted")
        layout.addWidget(self.order_hint)
        self.stack.addWidget(page)

    def _build_reader(self):
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(18, 18, 18, 12); layout.setSpacing(12)
        self.reader_layout = layout
        self.reader_header = QWidget()
        header = QHBoxLayout(self.reader_header); header.setContentsMargins(0, 0, 0, 0)
        header.addWidget(button("Biblioteca", self.back_to_library, glyph="left"))
        self.reader_title = label("", "readerTitle"); self.reader_title.setMinimumWidth(90); self.reader_title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        header.addWidget(self.reader_title, 1)
        self.annotate_button = button("Anotar", self.add_annotation)
        self.annotate_button.setToolTip("Criar uma anotação na página atual (Ctrl+N)")
        header.addWidget(self.annotate_button)
        self.mark_button = button("Marcar página", self.add_bookmark, "primary", "bookmark")
        self.mark_button.setToolTip("Salvar um marcador nesta página (Ctrl+D)")
        header.addWidget(self.mark_button); layout.addWidget(self.reader_header)
        self.reader_toolbar = QWidget()
        toolbar = QHBoxLayout(self.reader_toolbar); toolbar.setContentsMargins(0, 0, 0, 0); toolbar.setSpacing(6)
        self.previous_button = button("", lambda: self.change_page(-1), glyph="left"); self.previous_button.setToolTip("Página anterior")
        self.next_button = button("", lambda: self.change_page(1), glyph="right"); self.next_button.setToolTip("Próxima página")
        toolbar.addWidget(self.previous_button)
        self.page_number = QSpinBox(); self.page_number.setMinimum(1); self.page_number.setFixedWidth(80)
        self.page_number.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.page_number.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_number.setKeyboardTracking(False); self.page_number.valueChanged.connect(lambda n: self.go_page(n-1))
        toolbar.addWidget(self.page_number); self.total_pages = label("/ 0", "muted"); toolbar.addWidget(self.total_pages)
        toolbar.addWidget(self.next_button); toolbar.addSpacing(8)
        self.zoom = QComboBox()
        for text, data in (("Ajustar largura", "width"), ("Página inteira", "page"), ("75%", .75), ("100%", 1.), ("125%", 1.25), ("150%", 1.5), ("200%", 2.)):
            self.zoom.addItem(text, data)
        self.zoom.currentIndexChanged.connect(self.change_zoom); toolbar.addWidget(self.zoom)
        toolbar.addStretch()
        self.pdf_search = QLineEdit(); self.pdf_search.setPlaceholderText("Buscar no livro…"); self.pdf_search.setClearButtonEnabled(True); self.pdf_search.setMaximumWidth(190)
        self.search_timer = QTimer(self); self.search_timer.setSingleShot(True); self.search_timer.setInterval(250)
        self.search_timer.timeout.connect(self.perform_search)
        self.pdf_search.textChanged.connect(lambda: self.search_timer.start())
        self.pdf_search.returnPressed.connect(lambda: self.find_result(1))
        toolbar.addWidget(self.pdf_search)
        self.search_count = label("", "muted"); toolbar.addWidget(self.search_count)
        toolbar.addWidget(button("↑", lambda: self.find_result(-1), "quiet"))
        toolbar.addWidget(button("↓", lambda: self.find_result(1), "quiet"))
        self.mode_selector = self.make_mode_selector(); toolbar.addWidget(self.mode_selector)
        layout.addWidget(self.reader_toolbar)
        self.reader_splitter = QSplitter()
        self.pdf_view = QPdfView(); self.pdf_view.setDocument(self.document)
        self.pdf_view.setDocumentMargins(QMargins(20, 20, 20, 20)); self.pdf_view.setPageSpacing(20)
        self.pdf_view.pageNavigator().currentPageChanged.connect(self.on_page_changed)
        self.search_model = QPdfSearchModel(self); self.search_model.setDocument(self.document)
        self.search_model.countChanged.connect(self.search_count_changed); self.pdf_view.setSearchModel(self.search_model)
        self.reader_splitter.addWidget(self.pdf_view)
        self.reader_panel = QWidget(); panel = QVBoxLayout(self.reader_panel); panel.setContentsMargins(12, 0, 0, 0)
        panel.addWidget(label("PARA VOLTAR DEPOIS", "eyebrow"))
        tabs = QTabWidget(); self.reader_tabs = tabs; panel.addWidget(tabs, 1)
        marks = QWidget(); mark_layout = QVBoxLayout(marks); mark_layout.setContentsMargins(8, 10, 8, 8)
        hint = label("Clique em um marcador para voltar à página.", "muted"); hint.setWordWrap(True); mark_layout.addWidget(hint)
        self.marker_list = QListWidget(); self.marker_list.setWordWrap(True)
        self.marker_list.itemClicked.connect(lambda item: self.go_page(item.data(Qt.ItemDataRole.UserRole)["page"]))
        self.marker_list.itemDoubleClicked.connect(lambda item: self.edit_marker(item.data(Qt.ItemDataRole.UserRole)))
        mark_layout.addWidget(self.marker_list, 1)
        self.marker_empty = label("Ainda não há marcadores.\nUse “Marcar página” ou Ctrl+D.", "muted")
        self.marker_empty.setWordWrap(True); mark_layout.addWidget(self.marker_empty)
        mark_actions = QHBoxLayout(); mark_actions.addWidget(button("Editar", self.edit_selected_marker)); mark_actions.addWidget(button("Excluir", self.delete_selected_marker)); mark_layout.addLayout(mark_actions)
        tabs.addTab(marks, "Marcadores")
        self.annotation_panel = self.make_annotation_panel()
        tabs.addTab(self.annotation_panel, "Anotações")
        self.outline_model = QPdfBookmarkModel(self); self.outline_model.setDocument(self.document)
        self.outline = QTreeView(); self.outline.setHeaderHidden(True); self.outline.setModel(self.outline_model)
        self.outline.clicked.connect(self.follow_outline); tabs.addTab(self.outline, "Sumário")
        self.reader_panel.setMinimumWidth(290); self.reader_panel.setMaximumWidth(380)
        self.reader_splitter.addWidget(self.reader_panel); self.reader_splitter.setSizes([800, 310]); self.reader_splitter.setCollapsible(0, False)
        layout.addWidget(self.reader_splitter, 1)
        self.reader_status = label("", "muted"); layout.addWidget(self.reader_status)
        self.stack.addWidget(page)

    def _build_markers(self):
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(32, 32, 32, 24)
        layout.addWidget(label("SEUS PONTOS DE RETORNO", "eyebrow"))
        layout.addWidget(label("Páginas marcadas", "heading"))
        layout.addWidget(label("Trechos que você quer reencontrar. Clique para abrir o livro na página salva.", "muted"))
        self.all_markers_search = QLineEdit(); self.all_markers_search.setPlaceholderText("Buscar marcador, nota ou livro…")
        self.all_markers_search.textChanged.connect(self.refresh_all_markers); layout.addWidget(self.all_markers_search)
        self.all_markers = QListWidget(); self.all_markers.setWordWrap(True)
        self.all_markers.itemClicked.connect(lambda item: self.open_book(item.data(Qt.ItemDataRole.UserRole)["book_id"], item.data(Qt.ItemDataRole.UserRole)["page"]))
        layout.addWidget(self.all_markers, 1)
        self.all_markers_empty = label("Marque uma página durante a leitura usando Ctrl+D. Ela aparecerá aqui.", "muted")
        layout.addWidget(self.all_markers_empty); self.stack.addWidget(page)

    def _build_progress(self):
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(32, 32, 32, 24); layout.setSpacing(14)
        header = QHBoxLayout(); heading = QVBoxLayout(); heading.setSpacing(4)
        heading.addWidget(label("SEU RITMO DE LEITURA", "eyebrow"))
        heading.addWidget(label("Progresso dos livros", "heading"))
        header.addLayout(heading, 1)
        header.addWidget(button("Adicionar PDF", self.add_pdf_progress, glyph="book"))
        header.addWidget(button("Livro customizado", self.add_custom_progress, "primary", "plus"))
        layout.addLayout(header)
        description = label("Acompanhe PDFs da biblioteca ou qualquer livro pelo título e número de páginas.", "muted")
        description.setWordWrap(True); layout.addWidget(description)
        self.progress_search = QLineEdit(); self.progress_search.setPlaceholderText("Buscar no controle de progresso…")
        self.progress_search.setClearButtonEnabled(True); self.progress_search.addAction(icon("search"), QLineEdit.ActionPosition.LeadingPosition)
        self.progress_search.textChanged.connect(self.refresh_progress); layout.addWidget(self.progress_search)
        self.progress_list = QListWidget(); self.progress_list.setSpacing(8)
        self.progress_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(self.progress_list, 1)
        self.progress_empty = label("Nenhum livro acompanhado ainda. Adicione um PDF da biblioteca ou crie um livro customizado.", "muted")
        self.progress_empty.setWordWrap(True); layout.addWidget(self.progress_empty)
        self.stack.addWidget(page)

    def _shortcuts(self):
        self.shortcuts = []
        for key, callback in (("Ctrl+O", self.choose_import), ("Ctrl+D", self.add_bookmark),
                              ("Ctrl+N", self.add_annotation),
                              ("Ctrl+Shift+F", self.focus_search), ("Ctrl+F", self.toggle_focus),
                              ("F11", self.toggle_fullscreen),
                              ("F3", lambda: self.find_result(1)), ("Shift+F3", lambda: self.find_result(-1)),
                              ("Esc", self.escape), ("Alt+Left", self.back_to_library),
                              ("Ctrl+G", self.focus_reading_page),
                              ("Ctrl+Right", lambda: self.change_page(1)),
                              ("Ctrl+Left", lambda: self.change_page(-1))):
            shortcut = QShortcut(QKeySequence(key), self); shortcut.activated.connect(callback); self.shortcuts.append(shortcut)
        open_action = QAction(self.grid); open_action.setShortcut(QKeySequence("Return")); open_action.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
        open_action.triggered.connect(self.open_selected); self.grid.addAction(open_action)

    def navigate(self, scope="all", folder_id=None, tag=None):
        self.persist_progress()
        if self.reading_mode != "normal":
            self.set_reading_mode("normal")
        self.scope, self.folder_id, self.tag = scope, folder_id, tag
        for key, nav in self.nav.items():
            nav.setChecked(key == scope and tag is None)
        if scope == "bookmarks":
            self.refresh_all_markers(); self.stack.setCurrentIndex(2)
        elif scope == "progress":
            self.refresh_progress(); self.stack.setCurrentIndex(3)
        else:
            self.refresh_library(); self.stack.setCurrentIndex(0)

    def refresh_progress(self, *_):
        if not hasattr(self, "progress_list"):
            return
        items = self.library.progress_items(self.progress_search.text())
        self.progress_list.clear()
        for progress in items:
            row = QListWidgetItem(); row.setSizeHint(QSize(0, 138))
            row.setData(Qt.ItemDataRole.UserRole, progress["id"])
            self.progress_list.addItem(row)
            card = ProgressCard(progress, self.progress_list)
            card.progressChanged.connect(self.save_progress_item)
            card.openRequested.connect(self.open_progress_pdf)
            card.editRequested.connect(self.edit_progress_item)
            card.deleteRequested.connect(self.delete_progress_item)
            self.progress_list.setItemWidget(row, card)
        self.progress_empty.setVisible(not items)
        if hasattr(self, "tray_icon"):
            self.refresh_tray_menu()

    def add_pdf_progress(self):
        tracked = {item["book_id"] for item in self.library.progress_items() if item["book_id"]}
        available = [book for book in self.library.books(order="title") if book["id"] not in tracked]
        if not available:
            message = ("Todos os PDFs da biblioteca já estão no controle de progresso."
                       if self.library.books() else "Importe um PDF para a biblioteca antes de adicioná-lo ao progresso.")
            QMessageBox.information(self, "Adicionar PDF", message)
            return
        choices = [f'{book["title"]}  ·  {book["pages"]} páginas  ·  {book["original_name"]}' for book in available]
        selected, accepted = QInputDialog.getItem(
            self, "Adicionar PDF ao progresso", "Livro da biblioteca:", choices, 0, False)
        if accepted and selected:
            index = choices.index(selected)
            self.library.add_progress_book(available[index]["id"])
            self.refresh_progress(); self.statusBar().showMessage("PDF adicionado ao controle de progresso.", 4500)

    def add_custom_progress(self):
        dialog = CustomProgressDialog(parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            progress_id = self.library.add_custom_progress(dialog.title.text(), dialog.pages.value())
            if dialog.current_page.value():
                self.library.update_progress_item(progress_id, dialog.current_page.value())
            self.refresh_progress(); self.statusBar().showMessage("Livro customizado adicionado.", 4500)

    def save_progress_item(self, progress_id, current_page):
        try:
            self.library.update_progress_item(progress_id, current_page)
        except ValueError as exc:
            QMessageBox.warning(self, "Não foi possível salvar", str(exc))
            return
        self.refresh_progress(); self.refresh_library()
        item = self.library.progress_item(progress_id)
        if item:
            self.statusBar().showMessage(f'Progresso salvo: página {item["current_page"]} de {item["pages"]}.', 4500)

    def edit_progress_item(self, progress_id):
        item = self.library.progress_item(progress_id)
        if not item:
            return
        if item["book_id"]:
            self.open_progress_pdf(progress_id)
            return
        dialog = CustomProgressDialog(item, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.library.update_progress_item(progress_id, dialog.current_page.value(),
                                              title=dialog.title.text(), pages=dialog.pages.value())
            self.refresh_progress()

    def delete_progress_item(self, progress_id):
        item = self.library.progress_item(progress_id)
        if not item:
            return
        detail = "O PDF continuará na biblioteca." if item["book_id"] else "O livro será removido somente desta lista."
        answer = QMessageBox.question(
            self, "Remover do progresso?", f'Remover “{item["title"]}” do controle de progresso?\n\n{detail}',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            self.library.delete_progress_item(progress_id); self.refresh_progress()

    def open_progress_pdf(self, progress_id):
        item = self.library.progress_item(progress_id)
        if item and item["book_id"] and self.library.book(item["book_id"]):
            self.open_book(item["book_id"], max(0, item["current_page"] - 1))

    def _setup_tray(self):
        self.tray_icon = None
        if QApplication.platformName() == "offscreen" or not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray_menu = QMenu(self)
        self.tray_icon = QSystemTrayIcon(self.windowIcon(), self)
        self.tray_icon.setToolTip("Entrelinhas · progresso de leitura")
        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.activated.connect(self.tray_activated)
        self.refresh_tray_menu(); self.tray_icon.show()

    def refresh_tray_menu(self):
        if not getattr(self, "tray_icon", None):
            return
        self.tray_menu.clear()
        heading = self.tray_menu.addAction("PROGRESSO RECENTE"); heading.setEnabled(False)
        recent = self.library.progress_items(limit=5)
        if not recent:
            empty = self.tray_menu.addAction("Nenhum livro acompanhado"); empty.setEnabled(False)
        for item in recent:
            percent = round(item["current_page"] * 100 / item["pages"])
            action = self.tray_menu.addAction(
                icon("progress", "#52776a", 18),
                f'{item["title"]}  ·  pág. {item["current_page"]}/{item["pages"]}  ·  {percent}%')
            action.triggered.connect(lambda checked=False, progress_id=item["id"]: self.show_progress(progress_id))
        self.tray_menu.addSeparator()
        self.tray_menu.addAction(icon("progress"), "Abrir progresso", lambda: self.show_progress())
        self.tray_menu.addAction("Mostrar Entrelinhas", self.show_from_tray)
        self.tray_menu.addSeparator(); self.tray_menu.addAction("Sair do Entrelinhas", self.close)

    def tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.refresh_tray_menu(); self.tray_menu.popup(QCursor.pos())
        elif reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_progress()

    def show_from_tray(self):
        if self.isMinimized():
            self.showNormal()
        else:
            self.show()
        self.raise_(); self.activateWindow()

    def show_progress(self, progress_id=None):
        self.show_from_tray(); self.navigate("progress")
        if progress_id:
            for row in range(self.progress_list.count()):
                item = self.progress_list.item(row)
                if item.data(Qt.ItemDataRole.UserRole) == progress_id:
                    self.progress_list.scrollToItem(item); break

    def refresh_sidebar(self):
        self.folder_tree.clear()
        folders = self.library.folders()
        def add(parent=None, item=None):
            for folder in folders:
                if folder["parent_id"] == parent:
                    row = QTreeWidgetItem([folder["name"]]); row.setIcon(0, icon("folder")); row.setData(0, Qt.ItemDataRole.UserRole, folder["id"])
                    if item:
                        item.addChild(row)
                    else:
                        self.folder_tree.addTopLevelItem(row)
                    row.setExpanded(True)
                    add(folder["id"], row)
        add()
        self.tag_list.clear()
        for tag in self.library.tags():
            item = QListWidgetItem(icon("tag", "#81927d", 16), tag); item.setData(Qt.ItemDataRole.UserRole, tag); self.tag_list.addItem(item)
        if not self.library.tags():
            item = QListWidgetItem("Adicione tags em Organizar"); item.setFlags(Qt.ItemFlag.NoItemFlags); self.tag_list.addItem(item)

    def refresh_library(self, *_):
        selected = self.selected_id()
        self.grid.clear()
        books = self.library.books(scope=self.scope, folder_id=self.folder_id, tag=self.tag,
                                   query=self.library_search.text(), order=self.sort.currentData())
        titles = {"all": "Sua biblioteca", "reading": "Em leitura", "favorites": "Favoritos", "unfiled": "Sem pasta"}
        title = titles.get(self.scope, "Sua biblioteca")
        if self.scope == "folder":
            title = next((f["name"] for f in self.library.folders() if f["id"] == self.folder_id), "Pasta")
        if self.tag:
            title = f"Tag: {self.tag}"
        self.library_title.setText(title)
        self.library_count.setText(f'{len(books)} {"livro" if len(books) == 1 else "livros"} · suas leituras, no seu ritmo')
        for book in books:
            book["cover"] = str(self.library.covers / f'{book["id"]}.png')
            item = QListWidgetItem(); item.setData(Qt.ItemDataRole.UserRole, book)
            item.setToolTip(book["title"] + "\n" + ", ".join(book["tags"]))
            self.grid.addItem(item)
            if book["id"] == selected:
                self.grid.setCurrentItem(item)
        self.library_body.setCurrentIndex(0 if books else 1)
        has_library = bool(self.library.books())
        self.empty_title.setText("Nenhum livro por aqui ainda." if has_library else "Sua próxima leitura começa aqui.")
        self.empty_description.setText("Ajuste a busca ou importe PDFs para esta coleção." if has_library else "Importe seus PDFs, organize suas leituras e guarde as páginas que importam.")
        recent = self.library.books(scope="reading", order="recent")
        self.resume.setVisible(bool(recent) and self.scope == "all" and not self.tag and not self.library_search.text())
        if recent:
            book = recent[0]; self.resume_title.setText(book["title"][:75])
            self.resume_detail.setText(f'Página {book["last_page"]+1} de {book["pages"]} · seu lugar está guardado')
        self.grid.setDragEnabled(self.sort.currentData() == "manual")
        self.update_actions()
        self.nav["all"].setChecked(self.scope == "all" and not self.tag)

    def sort_changed(self, *_):
        self.library.set_setting("sort", self.sort.currentData()); self.refresh_library()

    def selected_id(self):
        item = self.grid.currentItem()
        return item.data(Qt.ItemDataRole.UserRole)["id"] if item else None

    def update_actions(self):
        enabled = self.grid.currentItem() is not None
        for item in self.book_actions:
            item.setEnabled(enabled)
        for item in self.book_actions[-2:]:
            item.setEnabled(enabled and self.sort.currentData() == "manual")
        if enabled:
            book = self.grid.currentItem().data(Qt.ItemDataRole.UserRole)
            self.book_actions[2].setText("Desfavoritar" if book["favorite"] else "Favoritar")

    def save_order(self):
        ids = [self.grid.item(i).data(Qt.ItemDataRole.UserRole)["id"] for i in range(self.grid.count())]
        self.library.reorder(ids); self.statusBar().showMessage("Ordem dos livros salva.", 3500)

    def move_selected(self, delta):
        if self.sort.currentData() != "manual":
            return
        row = self.grid.currentRow(); new_row = row + delta
        if row >= 0 and 0 <= new_row < self.grid.count():
            item = self.grid.takeItem(row); self.grid.insertItem(new_row, item); self.grid.setCurrentItem(item); self.save_order()

    def choose_import(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Importar PDFs para sua biblioteca", "", "Documentos PDF (*.pdf)")
        if paths:
            self.import_paths(paths)

    def load_document(self, doc, path, ask_password=True):
        error = doc.load(str(path))
        while error == QPdfDocument.Error.IncorrectPassword and ask_password:
            password, accepted = QInputDialog.getText(self, "PDF protegido", f"Senha de {Path(path).name}:", QLineEdit.EchoMode.Password)
            if not accepted:
                return False
            doc.close(); doc.setPassword(password); error = doc.load(str(path))
        return error == QPdfDocument.Error.None_ and doc.pageCount() > 0

    def import_paths(self, paths, *, from_shell=False):
        requested_paths = list(paths)
        paths = [Path(p) for p in requested_paths if Path(p).suffix.lower() == ".pdf" and Path(p).is_file()]
        if not paths:
            if from_shell:
                QMessageBox.warning(self, "PDF não encontrado", "O arquivo recebido não existe ou não é um PDF. Verifique se ele ainda está disponível no computador.")
            else:
                self.statusBar().showMessage("Escolha arquivos com a extensão .pdf.", 5000)
            return []
        progress = QProgressDialog("Guardando seus PDFs…", "Parar", 0, len(paths), self)
        progress.setWindowTitle("Importar livros"); progress.setWindowModality(Qt.WindowModality.WindowModal); progress.setMinimumDuration(0)
        added, repeated, failures, imported = 0, 0, [], []
        if from_shell:
            failures.extend(f"{p}: arquivo inexistente ou extensão diferente de PDF." for p in requested_paths if Path(p) not in paths)
        for i, path in enumerate(paths):
            progress.setValue(i); progress.setLabelText(f"Importando {path.name}")
            QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
            if progress.wasCanceled():
                break
            document = QPdfDocument(self)
            try:
                if not self.load_document(document, path):
                    raise ValueError("PDF inválido, danificado ou senha não informada.")
                book_id, is_new = self.library.import_file(path, document.pageCount(), self.folder_id if self.scope == "folder" and not from_shell else None)
                imported.append(book_id)
                cover = self.library.covers / f"{book_id}.png"
                if not cover.exists():
                    size = document.pagePointSize(0)
                    if size.width() > 0 and size.height() > 0:
                        scale = min(300 / size.width(), 420 / size.height())
                        image = document.render(0, QSize(max(1, round(size.width()*scale)), max(1, round(size.height()*scale))))
                        image.save(str(cover))
                added += int(is_new); repeated += int(not is_new)
            except (OSError, ValueError) as exc:
                failures.append(f"{path.name}: {exc}")
            finally:
                document.close(); document.deleteLater()
        progress.close(); self.delegate.cache.clear(); self.refresh_sidebar(); self.refresh_library()
        self.statusBar().showMessage(f"{added} PDF(s) importado(s). {repeated} já estava(m) na biblioteca.", 8000)
        if failures:
            QMessageBox.warning(self, "Alguns PDFs não foram importados", "\n\n".join(failures[:10]))
        return imported

    def receive_external_files(self, paths):
        self.external_requests.append(list(paths))
        if not self.external_request_active:
            self.external_request_active = True
            QTimer.singleShot(0, self, self.process_external_files)

    def process_external_files(self):
        # A shell request must not interrupt editing a note or asking for a password.
        if QApplication.activeModalWidget() is not None:
            QTimer.singleShot(150, self, self.process_external_files)
            return
        try:
            paths = self.external_requests.pop(0)
            if self.isMinimized():
                self.showNormal() if self.reading_mode == "normal" else self.showFullScreen()
            self.show(); self.raise_(); self.activateWindow()
            if paths:
                imported = self.import_paths(paths, from_shell=True)
                if imported:
                    self.open_book(imported[0])
        finally:
            if self.external_requests:
                QTimer.singleShot(0, self, self.process_external_files)
            else:
                self.external_request_active = False

    def open_selected(self):
        if self.selected_id():
            self.open_book(self.selected_id())

    def edit_selected(self):
        book_id = self.selected_id()
        if not book_id:
            return
        book = self.library.book(book_id); dialog = BookDialog(self.library, book, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.library.edit_book(book_id, dialog.title.text(), dialog.tags.text().split(","), dialog.folder.currentData(), dialog.favorite.isChecked())
            self.refresh_sidebar(); self.refresh_library(); self.refresh_progress()
            if self.current_book == book_id:
                self.reader_title.setText(dialog.title.text())

    def favorite_selected(self):
        if self.selected_id():
            self.library.toggle_favorite(self.selected_id()); self.refresh_library()

    def book_menu(self, position):
        item = self.grid.itemAt(position)
        if not item:
            return
        self.grid.setCurrentItem(item); menu = QMenu(self)
        menu.addAction("Abrir livro", self.open_selected); menu.addAction("Nome, tags e pasta…", self.edit_selected)
        menu.addAction("Alternar favorito", self.favorite_selected); menu.addSeparator()
        menu.addAction("Exportar uma cópia…", self.export_selected); menu.addAction("Remover da biblioteca…", self.delete_selected)
        menu.exec(self.grid.mapToGlobal(position))

    def export_selected(self):
        import shutil
        book = self.library.book(self.selected_id())
        if book:
            destination, _ = QFileDialog.getSaveFileName(self, "Exportar cópia do PDF", book["original_name"], "PDF (*.pdf)")
            if destination:
                try:
                    shutil.copyfile(self.library.files / book["filename"], destination)
                    self.statusBar().showMessage("Cópia exportada.", 4000)
                except OSError as exc:
                    QMessageBox.warning(self, "Não foi possível exportar", str(exc))

    def delete_selected(self):
        book_id = self.selected_id(); book = self.library.book(book_id)
        if not book:
            return
        answer = QMessageBox.question(self, "Remover livro?", f'Remover “{book["title"]}”, seus marcadores e anotações da biblioteca?\n\nA cópia importada será excluída. O arquivo original permanece onde estava.', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            if self.current_book == book_id:
                self.loading = True; self.document.close(); self.current_book = None; self.loading = False
            try:
                self.library.delete_book(book_id); self.refresh_library(); self.refresh_sidebar(); self.refresh_progress()
            except OSError as exc:
                QMessageBox.warning(self, "Não foi possível remover", str(exc))

    def new_folder(self, checked=False, parent_id=None):
        dialog = QDialog(self); dialog.setWindowTitle("Nova pasta"); dialog.setMinimumWidth(360)
        layout = QVBoxLayout(dialog); form = QFormLayout(); name = QLineEdit(); parent = QComboBox()
        folder_options(parent, self.library, parent_id)
        form.addRow("Nome", name); form.addRow("Dentro de", parent); layout.addLayout(form)
        actions = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        actions.button(QDialogButtonBox.StandardButton.Ok).setText("Criar pasta"); actions.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        actions.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        name.textChanged.connect(lambda text: actions.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(text.strip())))
        actions.accepted.connect(dialog.accept); actions.rejected.connect(dialog.reject); layout.addWidget(actions)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            folder = self.library.add_folder(name.text(), parent.currentData()); self.refresh_sidebar(); self.navigate("folder", folder)

    def folder_menu(self, position):
        item = self.folder_tree.itemAt(position)
        if not item:
            return
        folder_id = item.data(0, Qt.ItemDataRole.UserRole); menu = QMenu(self)
        menu.addAction("Criar subpasta", lambda: self.new_folder(parent_id=folder_id))
        menu.addAction("Renomear", lambda: self.rename_folder(folder_id, item.text(0)))
        menu.addAction("Excluir pasta…", lambda: self.delete_folder(folder_id)); menu.exec(self.folder_tree.mapToGlobal(position))

    def rename_folder(self, folder_id, name):
        name, ok = QInputDialog.getText(self, "Renomear pasta", "Nome:", text=name)
        if ok and name.strip():
            self.library.rename_folder(folder_id, name); self.refresh_sidebar(); self.refresh_library()

    def delete_folder(self, folder_id):
        answer = QMessageBox.question(self, "Excluir pasta?", "Excluir esta pasta e suas subpastas? Os PDFs e marcadores serão preservados em “Sem pasta”.", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            self.library.delete_folder(folder_id); self.refresh_sidebar(); self.navigate()

    def open_book(self, book_id, page=None):
        book = self.library.book(book_id)
        if not book:
            return
        self.persist_progress()
        self.loading = True
        self.current_book = None
        self.document.close(); self.document.setPassword("")
        self.pdf_search.clear(); self.search_model.setSearchString(""); self.search_index = -1
        try:
            if not self.load_document(self.document, self.library.files / book["filename"]):
                QMessageBox.warning(self, "Não foi possível abrir", "O PDF não pôde ser aberto. Se a cópia foi removida da pasta de dados, importe o original novamente.")
                self.set_reading_mode("normal")
                self.stack.setCurrentIndex(0)
                return
            self.current_book = book_id
            self.reader_title.setText(book["title"]); self.reader_title.setToolTip(book["title"])
            self.setWindowTitle(f'{book["title"]} · Entrelinhas')
            self.page_number.setMaximum(self.document.pageCount()); self.total_pages.setText(f"/ {self.document.pageCount()}")
            self.stack.setCurrentIndex(1)
            target = page if page is not None else (book["last_page"] if self.library.setting("resume", True) else 0)
            target = max(0, min(target, self.document.pageCount()-1))
            self.go_page(target)
            self.refresh_markers(); self.refresh_annotations(); self.outline.expandToDepth(0)
        finally:
            self.loading = False
        if self.current_book:
            self.on_page_changed(target)
            # Navigate again after layout has assigned the PDF viewport its final size.
            revision = self.navigation_revision
            QTimer.singleShot(0, self, lambda bid=book_id, target=target, revision=revision: self.go_page(target)
                              if self.current_book == bid and self.navigation_revision == revision else None)

    def go_page(self, page):
        if not self.current_book or self.document.pageCount() == 0:
            return
        page = max(0, min(int(page), self.document.pageCount()-1))
        if self.reading_page_restore:
            if self.reading_page_restore[0] == self.current_book:
                self.reading_page_restore = (self.current_book, page)
                self.reading_restore_timer.start()
            else:
                self.reading_page_restore = None
        self.navigation_revision += 1
        self.pdf_view.pageNavigator().jump(page, QPointF(0, 0))
        self.page_number.blockSignals(True); self.page_number.setValue(page+1); self.page_number.blockSignals(False)

    def change_page(self, delta):
        if self.stack.currentIndex() == 1:
            self.go_page(self.pdf_view.pageNavigator().currentPage()+delta)

    def on_page_changed(self, page):
        if self.loading or not self.current_book or self.reading_page_restore:
            return
        self.navigation_revision += 1
        self.library.save_progress(self.current_book, page)
        if getattr(self, "tray_icon", None):
            self.refresh_tray_menu()
        self.page_number.blockSignals(True); self.page_number.setValue(page+1); self.page_number.blockSignals(False)
        self.previous_button.setEnabled(page > 0); self.next_button.setEnabled(page < self.document.pageCount()-1)
        exists = self.library.bookmark_at(self.current_book, page)
        self.mark_button.setText("Página marcada · editar" if exists else "Marcar página")
        self.reader_status.setText(f"Página {page+1} de {self.document.pageCount()}  ·  Posição salva automaticamente  ·  Ctrl+D para marcar")
        self.sync_reading_controls(page)

    def persist_progress(self):
        if self.current_book and not self.loading and self.stack.currentIndex() == 1:
            page = (self.reading_page_restore[1] if self.reading_page_restore
                    else self.pdf_view.pageNavigator().currentPage())
            self.library.save_progress(self.current_book, page)

    def back_to_library(self):
        self.setWindowTitle("Entrelinhas · Leitor de PDF"); self.navigate("all")

    def continue_reading(self):
        recent = self.library.books(scope="reading", order="recent")
        if recent:
            self.open_book(recent[0]["id"])

    def change_zoom(self, *_):
        mode = self.zoom.currentData()
        if mode == "width":
            self.pdf_view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        elif mode == "page":
            self.pdf_view.setZoomMode(QPdfView.ZoomMode.FitInView)
        else:
            self.pdf_view.setZoomMode(QPdfView.ZoomMode.Custom); self.pdf_view.setZoomFactor(float(mode))

    def add_bookmark(self):
        if self.current_book and self.stack.currentIndex() == 1:
            page = self.pdf_view.pageNavigator().currentPage()
            self.edit_marker(self.library.bookmark_at(self.current_book, page), page)

    def make_annotation_panel(self):
        panel = AnnotationPanel()
        panel.addRequested.connect(self.add_annotation)
        panel.editRequested.connect(self.edit_annotation)
        panel.deleteRequested.connect(self.delete_annotation)
        panel.pageRequested.connect(self.go_page)
        return panel

    def add_annotation(self):
        if self.current_book and self.stack.currentIndex() == 1:
            page = (self.reading_page_restore[1] if self.reading_page_restore
                    else self.pdf_view.pageNavigator().currentPage())
            self.edit_annotation(page=page)

    def edit_annotation(self, existing=None, page=None):
        if not self.current_book or self.stack.currentIndex() != 1:
            return
        book_id = self.current_book
        page = existing["page"] if existing else page
        dialog = AnnotationDialog(page, existing, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if existing:
                annotation_id = existing["id"]
                self.library.edit_annotation(annotation_id, dialog.text.toPlainText())
            else:
                annotation_id = self.library.add_annotation(book_id, page, dialog.text.toPlainText())
            self.refresh_annotations(annotation_id)
            if self.reading_mode == "normal":
                self.reader_tabs.setCurrentWidget(self.annotation_panel)
            else:
                self.show_reading_panel(self.immersive_annotation_panel)
            self.statusBar().showMessage(f"Anotação da página {page+1} salva.", 4500)

    def refresh_annotations(self, selected_id=None):
        annotations = self.library.annotations(self.current_book) if self.current_book else []
        self.annotation_panel.set_annotations(annotations, selected_id)
        if hasattr(self, "immersive_annotation_panel"):
            self.immersive_annotation_panel.set_annotations(annotations, selected_id)

    def delete_annotation(self, annotation):
        if QMessageBox.question(self, "Excluir anotação?", f'Excluir esta anotação da página {annotation["page"]+1}?',
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.library.delete_annotation(annotation["id"])
            self.refresh_annotations()

    def edit_marker(self, existing=None, page=None):
        if not self.current_book:
            return
        page = existing["page"] if existing else page
        dialog = BookmarkDialog(page, existing, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.library.save_bookmark(self.current_book, page, dialog.title.text(), dialog.note.toPlainText(), dialog.color.currentData())
            self.refresh_markers(); self.on_page_changed(self.pdf_view.pageNavigator().currentPage())
            self.statusBar().showMessage(f"Marcador da página {page+1} salvo.", 4500)

    def refresh_markers(self):
        self.marker_list.clear()
        if not self.current_book:
            return
        bookmarks = self.library.bookmarks(self.current_book)
        for mark in bookmarks:
            item = QListWidgetItem(icon("bookmark", COLORS.get(mark["color"], COLORS["sage"])), f'Pág. {mark["page"]+1}  ·  {mark["title"]}' + (f'\n{mark["note"]}' if mark["note"] else ""))
            item.setData(Qt.ItemDataRole.UserRole, mark); item.setToolTip(mark["note"]); self.marker_list.addItem(item)
        self.marker_empty.setVisible(not bookmarks)
        self.refresh_reading_markers()

    def edit_selected_marker(self):
        item = self.marker_list.currentItem()
        if item:
            self.edit_marker(item.data(Qt.ItemDataRole.UserRole))

    def delete_selected_marker(self):
        item = self.marker_list.currentItem()
        if item:
            self.delete_marker(item.data(Qt.ItemDataRole.UserRole))

    def delete_marker(self, mark):
        if QMessageBox.question(self, "Excluir marcador?", f'Excluir “{mark["title"]}”, da página {mark["page"]+1}?', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.library.delete_bookmark(mark["id"]); self.refresh_markers(); self.on_page_changed(self.pdf_view.pageNavigator().currentPage())

    def refresh_all_markers(self, *_):
        from .storage import normalize
        self.all_markers.clear(); query = normalize(self.all_markers_search.text().strip())
        for mark in self.library.bookmarks():
            if query and query not in normalize(" ".join([mark["book_title"], mark["title"], mark["note"]])):
                continue
            text = f'{mark["title"]}   ·   Página {mark["page"]+1}\n{mark["book_title"]}'
            if mark["note"]:
                text += f'\n{mark["note"]}'
            item = QListWidgetItem(icon("bookmark", COLORS.get(mark["color"], COLORS["sage"])), text)
            item.setData(Qt.ItemDataRole.UserRole, mark); self.all_markers.addItem(item)
        self.all_markers_empty.setVisible(self.all_markers.count() == 0)

    def follow_outline(self, index):
        page = index.data(int(QPdfBookmarkModel.Role.Page))
        if page is not None:
            self.go_page(page)

    def perform_search(self):
        self.search_index = -1; self.search_model.setSearchString(self.pdf_search.text().strip())
        self.search_count_changed()

    def search_count_changed(self):
        count = self.search_model.count()
        self.search_count.setText(f"{count} trecho(s)" if self.pdf_search.text().strip() else "")

    def find_result(self, delta):
        if self.search_timer.isActive():
            self.search_timer.stop(); self.perform_search()
        count = self.search_model.count()
        if not count:
            return
        self.search_index = (self.search_index + delta) % count
        result = self.search_model.resultAtIndex(self.search_index)
        self.reading_page_restore = None
        self.pdf_view.pageNavigator().jump(result)
        self.pdf_view.setCurrentSearchResultIndex(self.search_index)
        self.search_count.setText(f"{self.search_index+1}/{count}")

    def focus_search(self):
        if self.reading_mode != "normal":
            self.focus_immersive_search()
            return
        field = (self.pdf_search if self.stack.currentIndex() == 1 else
                 self.all_markers_search if self.stack.currentIndex() == 2 else
                 self.progress_search if self.stack.currentIndex() == 3 else self.library_search)
        field.setFocus(); field.selectAll()

    def toggle_focus(self):
        self.set_reading_mode("normal" if self.focus_mode else "focus")

    def escape(self):
        if self.reading_mode != "normal":
            self.set_reading_mode("normal")
        elif self.stack.currentIndex() == 1 and self.pdf_search.text():
            self.pdf_search.clear()

    def preferences(self):
        dialog = QDialog(self); dialog.setWindowTitle("Preferências"); dialog.setMinimumWidth(480)
        layout = QVBoxLayout(dialog); form = QFormLayout()
        theme = QComboBox(); theme.addItem("Claro · papel e verde", "light"); theme.addItem("Escuro · interface", "dark")
        theme.setCurrentIndex(max(0, theme.findData(self.library.setting("theme", "light"))))
        zoom = QComboBox(); zoom.addItem("Ajustar à largura", "width"); zoom.addItem("Página inteira", "page")
        zoom.setCurrentIndex(max(0, zoom.findData(self.library.setting("zoom", "width"))))
        continuous = QCheckBox("Rolar por todas as páginas"); continuous.setChecked(self.library.setting("continuous", True))
        resume = QCheckBox("Abrir livros na última página lida"); resume.setChecked(self.library.setting("resume", True))
        form.addRow("Tema", theme); form.addRow("Zoom inicial", zoom); form.addRow("Leitura", continuous); form.addRow("", resume)
        sync_config = self.library.sync_config()
        online = QCheckBox("Sincronizar esta biblioteca entre computadores")
        online.setChecked(bool(sync_config["enabled"]))
        server_url = QLineEdit(sync_config["server_url"]); server_url.setPlaceholderText("https://seu-servidor.example.com")
        sync_token = QLineEdit(sync_config["token"]); sync_token.setEchoMode(QLineEdit.EchoMode.Password)
        sync_token.setPlaceholderText("Chave privada da biblioteca")
        form.addRow("Nuvem", online); form.addRow("Servidor", server_url); form.addRow("Chave", sync_token)
        layout.addLayout(form)
        sync_hint = label("Quando ativada, a biblioteca continua funcionando offline. PDFs, páginas lidas, controle de progresso, marcadores, anotações, nomes, tags, pastas, favoritos, ordem e preferências são trocados automaticamente.", "muted")
        sync_hint.setWordWrap(True); layout.addWidget(sync_hint)
        if sync_config["last_error"]:
            layout.addWidget(label(f'Última tentativa: {sync_config["last_error"]}', "muted"))
        elif sync_config["last_success"]:
            layout.addWidget(label(f'Última sincronização concluída: {sync_config["last_success"]}', "muted"))
        info = label(f"Seus PDFs, progresso, marcadores e anotações ficam em:\n{self.library.root}", "muted"); info.setWordWrap(True); info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse); layout.addWidget(info)
        storage_actions = QHBoxLayout(); storage_actions.addWidget(button("Abrir pasta de dados", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.library.root)))))
        storage_actions.addWidget(button("Criar backup…", self.create_backup)); layout.addLayout(storage_actions)
        if sys.platform == "win32":
            layout.addWidget(button("Adicionar ao “Abrir com” do Windows", self.register_windows_integration))
        shortcuts = label("Ctrl+O  Importar    ·    Ctrl+D  Marcar página    ·    Ctrl+N  Anotar    ·    Ctrl+Shift+F  Buscar\nCtrl+G  Ir à página    ·    F11  Tela cheia    ·    Ctrl+F  Foco    ·    Esc  Normal", "muted")
        layout.addWidget(shortcuts)
        actions = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        actions.button(QDialogButtonBox.StandardButton.Save).setText("Salvar"); actions.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        def update_save_enabled(*_):
            actions.button(QDialogButtonBox.StandardButton.Save).setEnabled(
                not online.isChecked() or (bool(server_url.text().strip()) and bool(sync_token.text().strip())))
        online.toggled.connect(update_save_enabled); server_url.textChanged.connect(update_save_enabled)
        sync_token.textChanged.connect(update_save_enabled); update_save_enabled()
        actions.accepted.connect(dialog.accept); actions.rejected.connect(dialog.reject); layout.addWidget(actions)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                self.library.configure_sync(online.isChecked(), server_url.text(), sync_token.text())
                for key, value in (("theme", theme.currentData()), ("zoom", zoom.currentData()), ("continuous", continuous.isChecked()), ("resume", resume.isChecked())):
                    self.library.set_setting(key, value)
                self.apply_preferences(); self.sync_service.request_sync()
            except ValueError as exc:
                QMessageBox.warning(self, "Sincronização online", str(exc))

    def on_sync_status(self, message, healthy):
        self.sync_status.setText(message)
        self.sync_status.setToolTip(message)
        self.sync_status.setStyleSheet("color: #557765;" if healthy else "color: #a85d55;")

    def on_sync_data_changed(self):
        if self.current_book and not self.library.book(self.current_book):
            self.loading = True
            self.document.close(); self.current_book = None
            self.loading = False
            self.navigate("all")
        synced_sort = self.library.setting("sort", "manual")
        self.sort.blockSignals(True)
        self.sort.setCurrentIndex(max(0, self.sort.findData(synced_sort)))
        self.sort.blockSignals(False)
        self.ensure_synced_covers()
        self.delegate.cache.clear()
        self.refresh_sidebar()
        if self.stack.currentIndex() == 2:
            self.refresh_all_markers()
        elif self.stack.currentIndex() == 3:
            self.refresh_progress()
        else:
            self.refresh_library()
        if self.current_book:
            self.reader_title.setText(self.library.book(self.current_book)["title"])
            self.refresh_markers(); self.refresh_annotations()
        self.refresh_tray_menu()
        self.apply_preferences()

    def ensure_synced_covers(self):
        for book in self.library.books():
            source = self.library.files / book["filename"]
            cover = self.library.covers / f'{book["id"]}.png'
            if cover.exists() or not source.exists():
                continue
            document = QPdfDocument(self)
            try:
                if not self.load_document(document, source, ask_password=False):
                    continue
                size = document.pagePointSize(0)
                if size.width() > 0 and size.height() > 0:
                    scale = min(300 / size.width(), 420 / size.height())
                    image = document.render(0, QSize(max(1, round(size.width()*scale)), max(1, round(size.height()*scale))))
                    image.save(str(cover))
            finally:
                document.close(); document.deleteLater()

    def apply_preferences(self):
        dark = self.library.setting("theme", "light") == "dark"
        app = QApplication.instance(); app.setStyleSheet(stylesheet(dark))
        palette = app.style().standardPalette()
        if dark:
            for role, color in ((QPalette.ColorRole.Window, "#202724"), (QPalette.ColorRole.WindowText, "#eef1e9"), (QPalette.ColorRole.Base, "#29332e"), (QPalette.ColorRole.Text, "#eef1e9"), (QPalette.ColorRole.Button, "#29332e"), (QPalette.ColorRole.ButtonText, "#eef1e9"), (QPalette.ColorRole.Highlight, "#486b53"), (QPalette.ColorRole.HighlightedText, "#ffffff")):
                palette.setColor(role, QColor(color))
        app.setPalette(palette)
        pdf_palette = self.pdf_view.palette(); pdf_palette.setColor(QPalette.ColorRole.Dark, QColor("#151b18" if dark else "#dce2d8")); self.pdf_view.setPalette(pdf_palette)
        self.delegate.dark = dark; self.grid.viewport().update()
        self.pdf_view.setPageMode(QPdfView.PageMode.MultiPage if self.library.setting("continuous", True) else QPdfView.PageMode.SinglePage)
        self.zoom.setCurrentIndex(max(0, self.zoom.findData(self.library.setting("zoom", "width")))); self.change_zoom()

    def register_windows_integration(self):
        from .windows_integration import register_shell
        try:
            register_shell()
            QMessageBox.information(self, "Integração com o Windows", "Entrelinhas foi adicionado ao menu Abrir com dos PDFs. Ao usá-lo, o arquivo será adicionado à biblioteca e aberto para leitura.")
        except OSError as exc:
            QMessageBox.warning(self, "Não foi possível registrar", str(exc))

    def create_backup(self):
        from datetime import datetime
        destination, _ = QFileDialog.getSaveFileName(self, "Guardar backup da biblioteca", f'Entrelinhas-backup-{datetime.now():%Y-%m-%d}.zip', "Arquivo ZIP (*.zip)")
        if destination:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                self.persist_progress(); self.library.backup(Path(destination))
                self.statusBar().showMessage("Backup criado com PDFs, progresso, marcadores, anotações, pastas e preferências.", 8000)
            except (OSError, ValueError) as exc:
                QMessageBox.warning(self, "Não foi possível criar o backup", str(exc))
            finally:
                QApplication.restoreOverrideCursor()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        self.import_paths([url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]); event.acceptProposedAction()

    def closeEvent(self, event):
        self.persist_progress()
        if self.reading_mode != "normal":
            self.set_reading_mode("normal")
        self.blackouts.set_enabled(False)
        QApplication.instance().removeEventFilter(self)
        self.library.set_setting("window_geometry", bytes(self.saveGeometry().toBase64()).decode())
        self.sync_service.stop()
        if getattr(self, "tray_icon", None):
            self.tray_icon.hide()
        self.loading = True; self.current_book = None; self.document.close(); event.accept()


def run(data_dir=None, files=None):
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Entrelinhas"); app.setOrganizationName("LeitorPDF"); app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    from .storage import default_data_dir
    from .instance import InstanceServer, forward_files
    root = Path(data_dir).resolve() if data_dir else default_data_dir().resolve()
    root.mkdir(parents=True, exist_ok=True)
    paths = [str(Path(path).resolve()) for path in (files or [])]
    from PySide6.QtCore import QLockFile
    lock = QLockFile(str(root / "app.lock")); lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        if sys.platform == "win32":
            import ctypes
            pid, _, _ = lock.getLockInfo()
            if pid > 0:
                ctypes.windll.user32.AllowSetForegroundWindow(pid)
        if forward_files(root, paths):
            return 0
        QMessageBox.warning(None, "Entrelinhas", "A biblioteca já está aberta, mas não respondeu. Feche e abra o Entrelinhas novamente e tente abrir o PDF outra vez.")
        return 1
    library = None
    server = InstanceServer(root)
    try:
        server.listen()
        library = Library(root)
        window = MainWindow(library)
        server.requested.connect(window.receive_external_files)
        window.show()
        if paths:
            window.receive_external_files(paths)
        return app.exec()
    finally:
        server.close()
        if library:
            library.close()
        lock.unlock()
