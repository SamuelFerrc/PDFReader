from pathlib import Path

from PySide6.QtCore import Qt, QSize, QRectF, Signal
from PySide6.QtGui import QColor, QDrag, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QProgressBar, QPushButton,
    QSpinBox, QStyledItemDelegate, QStyle, QTextEdit, QVBoxLayout, QWidget,
)

COLORS = {"sage": "#53796b", "amber": "#b68132", "rose": "#ae6679", "blue": "#5e82aa"}


def icon(name, color="#52776a", size=24):
    pix = QPixmap(size * 2, size * 2)
    pix.fill(Qt.GlobalColor.transparent)
    pix.setDevicePixelRatio(2)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size / 24, size / 24)
    p.setPen(QPen(QColor(color), 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    if name in ("book", "logo"):
        p.drawRoundedRect(QRectF(4, 3, 16, 18), 2, 2)
        p.drawLine(8, 3, 8, 21)
        p.drawLine(12, 8, 17, 8)
        p.drawLine(12, 12, 17, 12)
    elif name == "folder":
        path = QPainterPath()
        path.moveTo(3, 6); path.lineTo(10, 6); path.lineTo(12, 9)
        path.lineTo(21, 9); path.lineTo(21, 20); path.lineTo(3, 20); path.closeSubpath()
        p.drawPath(path)
    elif name == "bookmark":
        path = QPainterPath()
        path.moveTo(6, 3); path.lineTo(18, 3); path.lineTo(18, 21)
        path.lineTo(12, 16); path.lineTo(6, 21); path.closeSubpath()
        p.drawPath(path)
    elif name == "star":
        import math
        path = QPainterPath()
        for i in range(10):
            radius = 9 if i % 2 == 0 else 4
            x, y = 12 + radius * math.sin(i * math.pi / 5), 12 - radius * math.cos(i * math.pi / 5)
            path.moveTo(x, y) if i == 0 else path.lineTo(x, y)
        path.closeSubpath(); p.drawPath(path)
    elif name == "plus":
        p.drawLine(12, 5, 12, 19); p.drawLine(5, 12, 19, 12)
    elif name == "search":
        p.drawEllipse(QRectF(4, 3, 12, 12)); p.drawLine(15, 14, 21, 20)
    elif name == "clock":
        p.drawEllipse(QRectF(3, 3, 18, 18)); p.drawLine(12, 7, 12, 12); p.drawLine(12, 12, 16, 14)
    elif name == "progress":
        p.drawEllipse(QRectF(3, 3, 18, 18)); p.drawLine(12, 12, 12, 4); p.drawLine(12, 12, 19, 12)
        p.drawArc(QRectF(5, 5, 14, 14), 90 * 16, -235 * 16)
    elif name in ("left", "right"):
        x = 15 if name == "left" else 9
        tip = 8 if name == "left" else 16
        p.drawLine(x, 5, tip, 12); p.drawLine(tip, 12, x, 19)
    elif name == "settings":
        for y, x in ((6, 8), (12, 16), (18, 10)):
            p.drawLine(3, y, 21, y)
            p.setBrush(QColor(color)); p.drawEllipse(QRectF(x - 2, y - 2, 4, 4)); p.setBrush(Qt.BrushStyle.NoBrush)
    elif name == "grid":
        for x in (4, 14):
            for y in (4, 14):
                p.drawRoundedRect(QRectF(x, y, 6, 6), 1, 1)
    elif name == "tag":
        path = QPainterPath(); path.moveTo(3, 3); path.lineTo(13, 3); path.lineTo(22, 12)
        path.lineTo(12, 22); path.lineTo(3, 13); path.closeSubpath(); p.drawPath(path)
        p.drawEllipse(QRectF(7, 7, 2, 2))
    p.end()
    return QIcon(pix)


def button(text, callback=None, kind="", glyph=None):
    item = QPushButton(text)
    if kind:
        item.setProperty("kind", kind)
    if glyph:
        item.setIcon(icon(glyph, "#ffffff" if kind == "primary" else "#668b7a"))
    item.setCursor(Qt.CursorShape.PointingHandCursor)
    if callback:
        item.clicked.connect(callback)
    return item


def stylesheet(dark=False):
    bg, surface, text, muted, border, hover, selected = (
        ("#202724", "#29332e", "#eef1e9", "#a6b4aa", "#3d4a42", "#35443b", "#3b5547") if dark else
        ("#f7f7f2", "#ffffff", "#263d33", "#758279", "#e1e6dc", "#edf1e8", "#e1eddf"))
    return f"""
        QWidget {{ color: {text}; font-family: 'Segoe UI'; font-size: 13px; }}
        QMainWindow, QDialog {{ background: {bg}; }}
        QFrame#sidebar {{ background: {surface}; border-right: 1px solid {border}; }}
        QLabel#brand {{ font-size: 23px; font-weight: 700; letter-spacing: -1px; }}
        QLabel#eyebrow {{ font-size: 10px; font-weight: 700; color: {muted}; letter-spacing: 2px; }}
        QLabel#heading {{ font-size: 30px; font-weight: 700; letter-spacing: -1px; }}
        QLabel#muted {{ color: {muted}; }}
        QLabel#readerTitle {{ font-size: 17px; font-weight: 600; }}
        QFrame#resume {{ background: {selected}; border: 1px solid {border}; border-radius: 12px; }}
        QFrame#progressCard {{ background: {surface}; border: 1px solid {border}; border-radius: 12px; }}
        QPushButton {{ background: {surface}; border: 1px solid {border}; border-radius: 7px; padding: 9px 13px; }}
        QPushButton:hover {{ background: {hover}; border-color: #91aa95; }}
        QPushButton:pressed {{ background: {selected}; }}
        QPushButton:disabled {{ color: {muted}; background: {bg}; }}
        QPushButton[kind='primary'] {{ background: #38664e; color: white; border: 1px solid #38664e; font-weight: 600; }}
        QPushButton[kind='primary']:hover {{ background: #467b5d; }}
        QPushButton[kind='primary']:disabled {{ background: {bg}; color: {muted}; border-color: {border}; }}
        QPushButton[kind='nav'] {{ text-align: left; background: transparent; border: none; padding: 11px 13px; }}
        QPushButton[kind='nav']:hover, QPushButton[kind='nav']:checked {{ background: {selected}; color: {text}; }}
        QPushButton[kind='quiet'] {{ background: transparent; border: none; }}
        QPushButton[kind='quiet']:hover {{ background: {hover}; }}
        QLineEdit, QTextEdit, QSpinBox, QComboBox {{ background: {surface}; border: 1px solid {border}; border-radius: 6px; padding: 8px; selection-background-color: #658e72; }}
        QLineEdit:focus, QTextEdit:focus, QSpinBox:focus {{ border-color: #678b73; }}
        QComboBox::drop-down {{ border: none; width: 22px; }}
        QComboBox QAbstractItemView {{ background: {surface}; selection-background-color: {selected}; }}
        QProgressBar {{ background: {bg}; border: 1px solid {border}; border-radius: 6px; height: 12px; text-align: center; }}
        QProgressBar::chunk {{ background: #5e8a6c; border-radius: 5px; }}
        QListWidget, QTreeWidget, QTreeView {{ background: transparent; border: none; outline: none; }}
        QListWidget::item, QTreeWidget::item, QTreeView::item {{ padding: 8px; border-radius: 6px; }}
        QListWidget::item:selected, QTreeWidget::item:selected, QTreeView::item:selected {{ background: {selected}; color: {text}; }}
        QListWidget::item:hover, QTreeWidget::item:hover {{ background: {hover}; }}
        QTabWidget::pane {{ border: 1px solid {border}; border-radius: 6px; background: {surface}; }}
        QTabBar::tab {{ background: {bg}; padding: 10px 15px; }}
        QTabBar::tab:selected {{ background: {surface}; border-bottom: 2px solid #648f72; }}
        QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
        QScrollBar::handle:vertical {{ background: #a9b6ab; border-radius: 5px; min-height: 28px; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar:horizontal {{ height: 10px; background: transparent; }}
        QScrollBar::handle:horizontal {{ background: #a9b6ab; border-radius: 5px; min-width: 28px; }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
        QMenu {{ background: {surface}; border: 1px solid {border}; padding: 6px; }}
        QMenu::item {{ padding: 8px 24px; border-radius: 4px; }}
        QMenu::item:selected {{ background: {selected}; }}
        QStatusBar {{ color: {muted}; background: {bg}; border-top: 1px solid {border}; }}
        QToolTip {{ background: {surface}; color: {text}; border: 1px solid {border}; padding: 6px; }}
        QSplitter::handle {{ background: {border}; width: 1px; }}
    """


class BookGrid(QListWidget):
    reordered = Signal()
    filesDropped = Signal(list)

    def __init__(self):
        super().__init__()
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setMovement(QListWidget.Movement.Snap)
        self.setFlow(QListWidget.Flow.LeftToRight)
        self.setWrapping(True)
        self.setSpacing(12)
        self.setGridSize(QSize(214, 300))
        self.setIconSize(QSize(160, 180))
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setAcceptDrops(True)

    def startDrag(self, supported_actions):
        if not self.currentItem() or not self.dragEnabled():
            return
        # Own the drag lifecycle: QListView's default cleanup would remove a second
        # row after our dropEvent has already moved the item in the model.
        drag = QDrag(self)
        drag.setMimeData(self.model().mimeData(self.selectedIndexes()))
        preview = self.viewport().grab(self.visualItemRect(self.currentItem()))
        drag.setPixmap(preview)
        drag.exec(Qt.DropAction.MoveAction)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            self.filesDropped.emit([u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()])
            event.acceptProposedAction()
            return
        # IconMode's default drop only changes pixel positions. Move model rows explicitly.
        source = self.currentRow()
        target = self.indexAt(event.position().toPoint()).row()
        if target < 0:
            target = self.count() - 1
        if source >= 0 and source != target and self.dragEnabled():
            item = self.takeItem(source)
            self.insertItem(target, item)
            self.setCurrentItem(item)
            event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()
            self.reordered.emit()
        else:
            event.ignore()


class BookDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.dark = False
        self.cache = {}

    def sizeHint(self, option, index):
        return QSize(214, 300)

    def paint(self, painter, option, index):
        book = index.data(Qt.ItemDataRole.UserRole)
        if not book:
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = option.rect.adjusted(3, 3, -3, -3)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        surface = "#29332e" if self.dark else "#ffffff"
        painter.setBrush(QColor(surface))
        painter.setPen(QPen(QColor("#6c9778" if selected else ("#3d4a42" if self.dark else "#e2e7dd")), 2 if selected else 1))
        painter.drawRoundedRect(r, 10, 10)
        cover = QRectF(r.left() + 12, r.top() + 12, r.width() - 24, 171)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#dfe7d9" if not self.dark else "#3a493e"))
        painter.drawRoundedRect(cover, 5, 5)
        path = book.get("cover", "")
        if path not in self.cache:
            self.cache[path] = QPixmap(path) if Path(path).is_file() else QPixmap()
        pix = self.cache[path]
        if not pix.isNull():
            scaled = pix.scaled(150, 159, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            painter.drawPixmap(int(cover.center().x() - scaled.width()/2), int(cover.center().y() - scaled.height()/2), scaled)
        else:
            icon("book", "#76907b", 52).paint(painter, int(cover.center().x()-26), int(cover.center().y()-26), 52, 52)
        if book["favorite"]:
            painter.setBrush(QColor(surface)); painter.drawEllipse(QRectF(r.right()-39, r.top()+19, 27, 27))
            icon("star", "#b58b3c", 17).paint(painter, r.right()-34, r.top()+24, 17, 17)
        foreground = QColor("#edf1e8" if self.dark else "#283e32")
        painter.setPen(foreground)
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
        title = painter.fontMetrics().elidedText(book["title"], Qt.TextElideMode.ElideRight, r.width()-28)
        painter.drawText(r.adjusted(14, 190, -14, -77), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, title)
        painter.setFont(QFont("Segoe UI", 8))
        painter.setPen(QColor("#a7b6aa" if self.dark else "#7a877b"))
        tags = "  ·  ".join(book["tags"]) or f'{book["pages"]} páginas'
        tags = painter.fontMetrics().elidedText(tags, Qt.TextElideMode.ElideRight, r.width()-28)
        painter.drawText(r.adjusted(14, 220, -14, -48), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, tags)
        pct = (book["last_page"]+1) / book["pages"] if book["last_read"] else 0
        y = r.bottom()-31
        painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(QColor("#3e4c42" if self.dark else "#eaf0e6"))
        painter.drawRoundedRect(QRectF(r.left()+14, y, r.width()-28, 4), 2, 2)
        painter.setBrush(QColor("#75977a")); painter.drawRoundedRect(QRectF(r.left()+14, y, (r.width()-28)*pct, 4), 2, 2)
        painter.setPen(QColor("#a7b6aa" if self.dark else "#7a877b"))
        progress = f'Página {book["last_page"]+1} de {book["pages"]}' if book["last_read"] else "Pronto para começar"
        painter.drawText(r.adjusted(14, 268, -14, -5), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, progress)
        painter.restore()


def folder_options(combo, library, selected=None):
    combo.addItem("Sem pasta", None)
    folders = library.folders()
    def add(parent=None, depth=0):
        for folder in folders:
            if folder["parent_id"] == parent:
                combo.addItem("    " * depth + folder["name"], folder["id"])
                add(folder["id"], depth+1)
    add()
    combo.setCurrentIndex(max(0, combo.findData(selected)))


class BookDialog(QDialog):
    def __init__(self, library, book, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Organizar livro")
        self.setMinimumWidth(440)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.title = QLineEdit(book["title"])
        self.tags = QLineEdit(", ".join(book["tags"]))
        self.tags.setPlaceholderText("Ex.: literatura, estudo, favoritos")
        self.folder = QComboBox(); folder_options(self.folder, library, book["folder_id"])
        self.favorite = QCheckBox("Adicionar aos favoritos")
        self.favorite.setChecked(bool(book["favorite"]))
        form.addRow("Nome na biblioteca", self.title)
        form.addRow("Tags (separadas por vírgula)", self.tags)
        form.addRow("Pasta", self.folder)
        form.addRow("", self.favorite)
        layout.addLayout(form)
        info = QLabel(f'Arquivo original: {book["original_name"]}')
        info.setWordWrap(True); info.setObjectName("muted"); layout.addWidget(info)
        actions = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        actions.button(QDialogButtonBox.StandardButton.Save).setText("Salvar")
        actions.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        actions.accepted.connect(self.accept); actions.rejected.connect(self.reject)
        self.title.textChanged.connect(lambda t: actions.button(QDialogButtonBox.StandardButton.Save).setEnabled(bool(t.strip())))
        layout.addWidget(actions)


class CustomProgressDialog(QDialog):
    def __init__(self, item=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Editar livro" if item else "Adicionar livro customizado")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        intro = QLabel("Este livro será usado somente para acompanhar a página e o percentual de leitura.")
        intro.setWordWrap(True); intro.setObjectName("muted"); layout.addWidget(intro)
        form = QFormLayout()
        self.title = QLineEdit(item["title"] if item else "")
        self.title.setPlaceholderText("Ex.: Dom Casmurro")
        self.pages = QSpinBox(); self.pages.setRange(1, 1_000_000)
        self.pages.setValue(item["pages"] if item else 1)
        self.current_page = QSpinBox(); self.current_page.setRange(0, self.pages.value())
        self.current_page.setValue(item["current_page"] if item else 0)
        self.current_page.setSpecialValueText("Ainda não iniciado")
        self.pages.valueChanged.connect(self._pages_changed)
        form.addRow("Título", self.title)
        form.addRow("Número de páginas", self.pages)
        form.addRow("Página atual", self.current_page)
        layout.addLayout(form)
        actions = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        actions.button(QDialogButtonBox.StandardButton.Save).setText("Salvar livro")
        actions.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        actions.accepted.connect(self.accept); actions.rejected.connect(self.reject)
        self.title.textChanged.connect(
            lambda text: actions.button(QDialogButtonBox.StandardButton.Save).setEnabled(bool(text.strip())))
        actions.button(QDialogButtonBox.StandardButton.Save).setEnabled(bool(self.title.text().strip()))
        layout.addWidget(actions)
        self.title.setFocus(); self.title.selectAll()

    def _pages_changed(self, pages):
        self.current_page.setMaximum(pages)


class ProgressCard(QFrame):
    progressChanged = Signal(str, int)
    openRequested = Signal(str)
    editRequested = Signal(str)
    deleteRequested = Signal(str)

    def __init__(self, item, parent=None):
        super().__init__(parent)
        self.item = item
        self.setObjectName("progressCard")
        self.setMinimumHeight(126)
        outer = QHBoxLayout(self); outer.setContentsMargins(18, 14, 14, 14); outer.setSpacing(16)
        symbol = QLabel(); symbol.setPixmap(icon("book", "#4e7a61", 42).pixmap(42, 42))
        symbol.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter); outer.addWidget(symbol)

        details = QVBoxLayout(); details.setSpacing(5)
        title = QLabel(item["title"]); title.setFont(QFont("Segoe UI", 12, QFont.Weight.DemiBold))
        title.setWordWrap(True); details.addWidget(title)
        source = "PDF da biblioteca" if item["book_id"] else "Livro customizado"
        metadata = QLabel(f'{source}  ·  {item["pages"]} páginas')
        metadata.setObjectName("muted"); details.addWidget(metadata)
        self.progress = QProgressBar(); self.progress.setRange(0, item["pages"])
        self.progress.setValue(item["current_page"])
        self._update_progress_text(item["current_page"])
        details.addWidget(self.progress)
        outer.addLayout(details, 1)

        controls = QVBoxLayout(); controls.setSpacing(7)
        page_row = QHBoxLayout(); page_row.setSpacing(6)
        page_row.addWidget(QLabel("Página"))
        self.page = QSpinBox(); self.page.setRange(0, item["pages"])
        self.page.setValue(item["current_page"]); self.page.setSpecialValueText("Não iniciado")
        self.page.setKeyboardTracking(False); self.page.setMinimumWidth(105)
        self.page.valueChanged.connect(self._page_preview)
        page_row.addWidget(self.page); page_row.addWidget(QLabel(f'/ {item["pages"]}'))
        controls.addLayout(page_row)
        action_row = QHBoxLayout(); action_row.setSpacing(6)
        self.save = button("Salvar página", self._save, "primary")
        self.save.setEnabled(False); action_row.addWidget(self.save)
        if item["book_id"]:
            action_row.addWidget(button("Abrir PDF", lambda: self.openRequested.emit(item["id"])))
        else:
            action_row.addWidget(button("Editar", lambda: self.editRequested.emit(item["id"])))
        remove = button("Remover", lambda: self.deleteRequested.emit(item["id"]), "quiet")
        remove.setToolTip("Remover somente deste controle de progresso")
        action_row.addWidget(remove); controls.addLayout(action_row)
        outer.addLayout(controls)

    def _page_preview(self, page):
        self.progress.setValue(page)
        self._update_progress_text(page)
        self.save.setEnabled(page != self.item["current_page"])

    def _update_progress_text(self, page):
        percent = round(page * 100 / self.item["pages"])
        self.progress.setFormat(f"{percent}% concluído")

    def _save(self):
        self.progressChanged.emit(self.item["id"], self.page.value())


class AnnotationDialog(QDialog):
    def __init__(self, page, existing=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f'Anotação · página {page+1}')
        self.resize(500, 350)
        layout = QVBoxLayout(self)
        self.page_label = QLabel(f"Página {page+1} do PDF · registrada ao criar a anotação")
        self.page_label.setWordWrap(True)
        layout.addWidget(self.page_label)
        self.text = QTextEdit()
        self.text.setAcceptRichText(False)
        self.text.setPlaceholderText("Escreva suas ideias, dúvidas ou observações sobre esta página…")
        self.text.setPlainText(existing["text"] if existing else "")
        layout.addWidget(self.text, 1)
        self.actions = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.save_button = self.actions.button(QDialogButtonBox.StandardButton.Save)
        self.save_button.setText("Salvar anotação")
        self.actions.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        self.actions.accepted.connect(self.accept); self.actions.rejected.connect(self.reject)
        self.text.textChanged.connect(lambda: self.save_button.setEnabled(bool(self.text.toPlainText().strip())))
        self.save_button.setEnabled(bool(self.text.toPlainText().strip()))
        layout.addWidget(self.actions)
        self.text.setFocus()

    def accept(self):
        if self.text.toPlainText().strip():
            super().accept()


class AnnotationPanel(QWidget):
    addRequested = Signal()
    editRequested = Signal(dict)
    deleteRequested = Signal(dict)
    pageRequested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self); layout.setContentsMargins(8, 10, 8, 8)
        hint = QLabel("Anotações deste livro, por página. Clique para voltar; duplo clique para editar.")
        hint.setWordWrap(True); hint.setObjectName("muted"); layout.addWidget(hint)
        self.add_button = button("Anotar página atual", lambda: self.addRequested.emit())
        self.add_button.setToolTip("Criar uma anotação na página atual (Ctrl+N)")
        layout.addWidget(self.add_button)
        self.list = QListWidget(); self.list.setWordWrap(True)
        self.list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.itemClicked.connect(lambda item: self.pageRequested.emit(item.data(Qt.ItemDataRole.UserRole)["page"]))
        self.list.itemDoubleClicked.connect(lambda item: self.editRequested.emit(item.data(Qt.ItemDataRole.UserRole)))
        self.list.itemSelectionChanged.connect(self.update_actions)
        layout.addWidget(self.list, 1)
        self.empty = QLabel("Ainda não há anotações.\nUse “Anotar página atual” ou Ctrl+N.")
        self.empty.setWordWrap(True); self.empty.setObjectName("muted"); layout.addWidget(self.empty)
        actions = QHBoxLayout()
        self.edit_button = button("Editar", lambda: self.emit_selected(self.editRequested))
        self.delete_button = button("Excluir", lambda: self.emit_selected(self.deleteRequested))
        actions.addWidget(self.edit_button); actions.addWidget(self.delete_button); layout.addLayout(actions)
        self.update_actions()

    def emit_selected(self, signal):
        item = self.list.currentItem()
        if item:
            signal.emit(item.data(Qt.ItemDataRole.UserRole))

    def update_actions(self):
        selected = bool(self.list.selectedItems())
        self.edit_button.setEnabled(selected); self.delete_button.setEnabled(selected)

    def set_annotations(self, annotations, selected_id=None):
        current = self.list.currentItem()
        if selected_id is None and current:
            selected_id = current.data(Qt.ItemDataRole.UserRole)["id"]
        self.list.clear()
        for annotation in annotations:
            preview = annotation["text"]
            if len(preview) > 240:
                preview = preview[:240].rstrip() + "…"
            item = QListWidgetItem(f'Página {annotation["page"]+1}\n{preview}')
            item.setData(Qt.ItemDataRole.UserRole, annotation)
            self.list.addItem(item)
            if annotation["id"] == selected_id:
                self.list.setCurrentItem(item)
        self.empty.setVisible(not annotations)
        self.update_actions()


class BookmarkDialog(QDialog):
    def __init__(self, page, existing=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f'Marcador · página {page+1}')
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        heading = QLabel(f"Volte à página {page+1} quando quiser.")
        layout.addWidget(heading)
        form = QFormLayout()
        self.title = QLineEdit(existing["title"] if existing else f"Página {page+1}")
        self.note = QTextEdit()
        self.note.setPlainText(existing["note"] if existing else "")
        self.note.setPlaceholderText("O que você quer lembrar deste trecho?")
        self.note.setMaximumHeight(140)
        self.color = QComboBox()
        for text, key in (("Verde · leitura", "sage"), ("Âmbar · importante", "amber"), ("Rosa · rever", "rose"), ("Azul · referência", "blue")):
            self.color.addItem(icon("bookmark", COLORS[key]), text, key)
        if existing:
            self.color.setCurrentIndex(max(0, self.color.findData(existing["color"])))
        form.addRow("Nome", self.title); form.addRow("Nota", self.note); form.addRow("Cor", self.color)
        layout.addLayout(form)
        actions = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        actions.button(QDialogButtonBox.StandardButton.Save).setText("Salvar marcador")
        actions.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        actions.accepted.connect(self.accept); actions.rejected.connect(self.reject)
        layout.addWidget(actions)
        self.title.selectAll()
