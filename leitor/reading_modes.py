"""Fullscreen reading controls and temporary covers for secondary displays."""
from PySide6.QtCore import QEvent, QMargins, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIntValidator, QPainter, QPalette
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import (
    QAbstractSpinBox, QApplication, QComboBox, QFrame, QHBoxLayout, QInputDialog,
    QLabel, QLayout, QLineEdit, QListWidget, QListWidgetItem, QPushButton,
    QTabWidget, QVBoxLayout, QWidget,
)

from .widgets import COLORS, button, icon


class BlackoutWindow(QWidget):
    exitRequested = Signal()

    def __init__(self, owner, screen):
        flags = (Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                 Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        super().__init__(owner, flags)
        self.setWindowTitle("Entrelinhas · modo foco")
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.winId()
        self.windowHandle().setScreen(screen)
        self.setGeometry(screen.geometry())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)

    def cover(self, screen):
        self.windowHandle().setScreen(screen)
        # On Windows the first show of an owned tool window can move it to
        # its owner's monitor. Apply the desktop rectangle after showing it.
        self.show()
        self.setGeometry(screen.geometry())

    def mousePressEvent(self, event):
        self.exitRequested.emit()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.exitRequested.emit()
        else:
            super().keyPressEvent(event)


class BlackoutController(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.enabled = False
        self.covers = {}
        self.watched_screens = set()
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.refresh)
        app = QApplication.instance()
        app.screenAdded.connect(self.schedule)
        app.screenRemoved.connect(self.schedule)
        app.applicationStateChanged.connect(self.schedule)
        app.aboutToQuit.connect(self.clear)
        window.winId()
        window.windowHandle().screenChanged.connect(self.schedule)

    def schedule(self, *_):
        self.timer.start(0)

    def set_enabled(self, enabled):
        self.enabled = enabled
        self.refresh()

    def clear(self):
        for cover in self.covers.values():
            cover.close()
            cover.deleteLater()
        self.covers.clear()

    def is_reading_active(self):
        return (self.window.isVisible() and not self.window.isMinimized() and
                QApplication.applicationState() == Qt.ApplicationState.ApplicationActive)

    def target_screens(self):
        reader_screen = self.window.screen()
        if reader_screen is None:
            return []
        # Mirrored outputs share the same desktop rectangle and cannot be covered independently.
        return [screen for screen in QApplication.screens()
                if screen != reader_screen and screen.geometry() != reader_screen.geometry()]

    def refresh(self):
        if not self.enabled:
            self.clear()
            return
        screens = QApplication.screens()
        for screen in screens:
            if screen not in self.watched_screens:
                screen.geometryChanged.connect(self.schedule)
        self.watched_screens = set(screens)
        targets = self.target_screens() if self.is_reading_active() else []
        for screen in list(self.covers):
            if screen not in targets:
                cover = self.covers.pop(screen)
                cover.close(); cover.deleteLater()
        for screen in targets:
            cover = self.covers.get(screen)
            if cover is None:
                cover = BlackoutWindow(self.window, screen)
                cover.exitRequested.connect(lambda: self.window.set_reading_mode("normal"))
                self.covers[screen] = cover
            cover.cover(screen)


OVERLAY_STYLE = """
QFrame { background: #26392f; border: 1px solid #526a59; border-radius: 10px; }
QLabel { color: #f1f4ed; border: none; background: transparent; }
QPushButton { background: #344c3d; color: #f1f4ed; border: 1px solid #5d7965; padding: 8px 10px; }
QPushButton:hover { background: #496b52; }
QLineEdit, QSpinBox, QComboBox { background: #f5f6f0; color: #26392f; }
QComboBox QAbstractItemView { background: #f5f6f0; color: #26392f; }
QListWidget { background: transparent; color: #f1f4ed; border: none; }
QListWidget::item:selected { background: #496b52; color: white; }
QListWidget::item:hover { background: #344c3d; }
QTabWidget::pane { background: #26392f; border: none; }
QTabBar::tab { background: #344c3d; color: #f1f4ed; padding: 8px; }
QTabBar::tab:selected { background: #496b52; color: white; }
QLabel#muted { color: #d5dfd5; }
"""


class ReadingModesMixin:
    @property
    def focus_mode(self):
        return self.reading_mode == "focus"

    def make_mode_selector(self):
        selector = QComboBox()
        selector.setToolTip("Normal · Tela cheia (F11) · Foco (Ctrl+F)")
        for name, mode in (("Normal", "normal"), ("Tela cheia", "full"), ("Foco", "focus")):
            selector.addItem(name, mode)
        selector.currentIndexChanged.connect(lambda: self.set_reading_mode(selector.currentData()))
        return selector

    def init_reading_modes(self):
        self.normal_reading_state = None
        self.reading_page_restore = None
        self.reading_restore_timer = QTimer(self)
        self.reading_restore_timer.setSingleShot(True)
        self.reading_restore_timer.setInterval(25)
        self.reading_restore_timer.timeout.connect(self.restore_reading_page)
        self.blackouts = BlackoutController(self)
        self.controls_timer = QTimer(self)
        self.controls_timer.setSingleShot(True)
        self.controls_timer.timeout.connect(self.hide_reading_controls)
        self.reading_controls = QFrame(self)
        self.reading_controls.setObjectName("readingControls")
        self.reading_controls.setStyleSheet(OVERLAY_STYLE)
        row = QHBoxLayout(self.reading_controls)
        row.setContentsMargins(12, 10, 12, 10); row.setSpacing(6)
        row.addWidget(button("‹", lambda: self.change_page(-1)))
        self.immersive_page = QLineEdit("1")
        self.immersive_page.setValidator(QIntValidator(1, 1, self.immersive_page))
        self.immersive_page.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.immersive_page.setFixedWidth(62)
        self.immersive_page.editingFinished.connect(self.go_immersive_page)
        row.addWidget(self.immersive_page)
        row.addWidget(button("›", lambda: self.change_page(1)))
        row.addWidget(button("Marcar", self.add_bookmark, glyph="bookmark"))
        row.addWidget(button("Marcadores", self.toggle_reading_markers))
        row.addWidget(button("Anotar", self.add_annotation))
        row.addWidget(button("Anotações", self.toggle_reading_annotations))
        self.immersive_mode = self.make_mode_selector(); row.addWidget(self.immersive_mode)
        self.immersive_search = QLineEdit()
        self.immersive_search.setPlaceholderText("Buscar no PDF…")
        self.immersive_search.setMinimumWidth(110); self.immersive_search.setMaximumWidth(170)
        self.immersive_search.textChanged.connect(self.pdf_search.setText)
        self.pdf_search.textChanged.connect(self.immersive_search.setText)
        self.immersive_search.returnPressed.connect(lambda: self.find_result(1))
        row.addWidget(self.immersive_search, 1)
        self.immersive_find = button("↓", lambda: self.find_result(1)); row.addWidget(self.immersive_find)
        row.addWidget(button("Sair · Esc", lambda: self.set_reading_mode("normal")))
        self.reading_controls.hide()

        self.reading_markers = QFrame(self)
        self.reading_markers.setObjectName("readingMarkers")
        self.reading_markers.setStyleSheet(OVERLAY_STYLE)
        panel = QVBoxLayout(self.reading_markers); panel.setContentsMargins(14, 14, 14, 14)
        title_row = QHBoxLayout(); title_row.addWidget(QLabel("Suas páginas e anotações"), 1)
        title_row.addWidget(button("×", self.reading_markers.hide)); panel.addLayout(title_row)
        self.reading_panel_tabs = QTabWidget(); panel.addWidget(self.reading_panel_tabs, 1)
        self.immersive_marker_panel = QWidget()
        panel = QVBoxLayout(self.immersive_marker_panel); panel.setContentsMargins(8, 10, 8, 8)
        panel.addWidget(button("Marcar página atual · Ctrl+D", self.add_bookmark))
        self.immersive_markers = QListWidget(); self.immersive_markers.setWordWrap(True)
        self.immersive_markers.itemClicked.connect(lambda item: self.go_page(item.data(Qt.ItemDataRole.UserRole)["page"]))
        self.immersive_markers.itemDoubleClicked.connect(lambda item: self.edit_marker(item.data(Qt.ItemDataRole.UserRole)))
        panel.addWidget(self.immersive_markers, 1)
        self.immersive_empty = QLabel("Nenhuma página marcada ainda."); self.immersive_empty.setWordWrap(True)
        panel.addWidget(self.immersive_empty)
        actions = QHBoxLayout()
        actions.addWidget(button("Editar", self.edit_immersive_marker))
        actions.addWidget(button("Excluir", self.delete_immersive_marker))
        panel.addLayout(actions)
        self.reading_panel_tabs.addTab(self.immersive_marker_panel, "Marcadores")
        self.immersive_annotation_panel = self.make_annotation_panel()
        self.reading_panel_tabs.addTab(self.immersive_annotation_panel, "Anotações")
        self.reading_markers.hide()
        self.pdf_view.setMouseTracking(True); self.pdf_view.viewport().setMouseTracking(True)
        QApplication.instance().installEventFilter(self)

    def set_reading_mode(self, mode):
        if mode not in ("normal", "full", "focus"):
            raise ValueError("Modo de leitura inválido")
        if mode != "normal" and (not self.current_book or self.stack.currentIndex() != 1):
            return
        if mode == self.reading_mode:
            return
        page = (self.reading_page_restore[1] if self.reading_page_restore
                else self.pdf_view.pageNavigator().currentPage())
        previous = self.reading_mode
        self.reading_mode = mode
        self.blackouts.set_enabled(False)
        if previous == "normal":
            self.normal_reading_state = {
                "geometry": self.saveGeometry(), "maximized": self.isMaximized(),
                "rectangle": self.geometry(), "screen": self.screen(),
                "minimum": self.minimumSize(), "zoom_mode": self.pdf_view.zoomMode(),
                "zoom_factor": self.pdf_view.zoomFactor(), "palette": self.pdf_view.palette(),
                "frame": self.pdf_view.frameShape(), "splitter": self.reader_splitter.sizes(),
                "constraint": self.centralWidget().layout().sizeConstraint(),
            }
        self.loading = True
        try:
            normal = mode == "normal"
            for widget in (self.sidebar, self.reader_header, self.reader_toolbar, self.reader_panel,
                           self.reader_status, self.statusBar()):
                widget.setVisible(normal)
            self.reader_layout.setContentsMargins(18, 18, 18, 12) if normal else self.reader_layout.setContentsMargins(0, 0, 0, 0)
            self.reader_layout.setSpacing(12 if normal else 0)
            self.pdf_view.setDocumentMargins(QMargins(20, 20, 20, 20) if normal else QMargins())
            self.pdf_view.setFrameShape(self.normal_reading_state["frame"] if normal else QFrame.Shape.NoFrame)
            policy = Qt.ScrollBarPolicy.ScrollBarAsNeeded if normal else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            self.pdf_view.setHorizontalScrollBarPolicy(policy); self.pdf_view.setVerticalScrollBarPolicy(policy)
            if normal:
                self.controls_timer.stop(); self.reading_controls.hide(); self.reading_markers.hide()
                state = self.normal_reading_state
                self.centralWidget().layout().setSizeConstraint(state["constraint"])
                self.setMinimumSize(state["minimum"])
                self.showNormal(); self.restoreGeometry(state["geometry"])
                if state["maximized"]:
                    self.showMaximized()
                elif state["screen"] in QApplication.screens():
                    self.setGeometry(state["rectangle"])
                self.reader_splitter.setSizes(state["splitter"])
                self.pdf_view.setZoomMode(state["zoom_mode"])
                if state["zoom_mode"] == QPdfView.ZoomMode.Custom:
                    self.pdf_view.setZoomFactor(state["zoom_factor"])
                self.pdf_view.setPalette(state["palette"])
            else:
                self.centralWidget().layout().setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
                if previous == "normal":
                    self.setMinimumSize(0, 0)
                # Reissuing showFullScreen while switching between the two immersive
                # modes can make the Windows/offscreen backend restore the window.
                if not self.isFullScreen():
                    self.showFullScreen()
                if previous == "normal":
                    self.pdf_view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
                palette = QPalette(self.normal_reading_state["palette"])
                if mode == "focus":
                    palette.setColor(QPalette.ColorRole.Dark, QColor("#000000"))
                    palette.setColor(QPalette.ColorRole.Window, QColor("#000000"))
                self.pdf_view.setPalette(palette)
                self.show_reading_controls()
            for selector in (self.mode_selector, self.immersive_mode):
                selector.blockSignals(True); selector.setCurrentIndex(selector.findData(mode)); selector.blockSignals(False)
        finally:
            self.loading = False
        self.go_page(page)
        # Qt updates the viewport after the window-state change. Wait for the
        # resize events to settle; explicit navigation updates this target.
        self.reading_page_restore = (self.current_book, page)
        self.reading_restore_timer.start()
        self.sync_reading_controls(page)
        self.blackouts.set_enabled(mode == "focus")
        if mode != "normal":
            self.pdf_view.setFocus()

    def restore_reading_page(self):
        pending = self.reading_page_restore
        self.reading_page_restore = None
        if pending and self.current_book == pending[0]:
            self.go_page(pending[1])
            self.on_page_changed(pending[1])

    def toggle_fullscreen(self):
        self.set_reading_mode("normal" if self.reading_mode == "full" else "full")

    def sync_reading_controls(self, page):
        if not hasattr(self, "immersive_page"):
            return
        self.immersive_page.blockSignals(True)
        self.immersive_page.validator().setTop(max(1, self.document.pageCount()))
        self.immersive_page.setText(str(page+1))
        self.immersive_page.blockSignals(False)
        self.immersive_page.setToolTip(f"Página {page+1} de {self.document.pageCount()} · Ctrl+G")

    def go_immersive_page(self):
        if self.immersive_page.hasAcceptableInput():
            self.go_page(int(self.immersive_page.text())-1)
        else:
            self.sync_reading_controls(self.pdf_view.pageNavigator().currentPage())

    def position_reading_overlays(self):
        if not hasattr(self, "reading_controls"):
            return
        show_search = self.width() >= 1120
        self.immersive_search.setVisible(show_search)
        self.immersive_find.setVisible(show_search)
        width = min(1160, self.width()-24)
        self.reading_controls.setGeometry((self.width()-width)//2, 12, width, 64)
        width = min(340, self.width()-24)
        self.reading_markers.setGeometry(self.width()-width-12, 88, width, max(160, self.height()-104))

    def show_reading_controls(self):
        if self.reading_mode == "normal":
            return
        self.position_reading_overlays()
        self.reading_controls.show(); self.reading_controls.raise_()
        self.controls_timer.start(2500)

    def hide_reading_controls(self):
        if self.reading_mode == "normal":
            return
        focus = QApplication.focusWidget()
        editing = isinstance(focus, (QLineEdit, QAbstractSpinBox)) and self.reading_controls.isAncestorOf(focus)
        if (self.reading_controls.underMouse() or editing
                or QApplication.activeModalWidget() or QApplication.activePopupWidget()):
            self.controls_timer.start(1200)
        else:
            self.reading_controls.hide()

    def refresh_reading_markers(self):
        if not hasattr(self, "immersive_markers"):
            return
        self.immersive_markers.clear()
        bookmarks = self.library.bookmarks(self.current_book) if self.current_book else []
        for mark in bookmarks:
            text = f'Pág. {mark["page"]+1} · {mark["title"]}' + (f'\n{mark["note"]}' if mark["note"] else "")
            item = QListWidgetItem(icon("bookmark", COLORS.get(mark["color"], COLORS["sage"])), text)
            item.setData(Qt.ItemDataRole.UserRole, mark); self.immersive_markers.addItem(item)
        self.immersive_empty.setVisible(not bookmarks)

    def toggle_reading_markers(self):
        self.toggle_reading_panel(self.immersive_marker_panel)

    def toggle_reading_annotations(self):
        self.toggle_reading_panel(self.immersive_annotation_panel)

    def toggle_reading_panel(self, panel):
        if self.reading_markers.isVisible() and self.reading_panel_tabs.currentWidget() == panel:
            self.reading_markers.hide()
        else:
            self.show_reading_panel(panel)

    def show_reading_panel(self, panel):
        self.refresh_reading_markers(); self.refresh_annotations(); self.position_reading_overlays()
        self.reading_panel_tabs.setCurrentWidget(panel)
        self.reading_markers.show(); self.reading_markers.raise_()

    def edit_immersive_marker(self):
        item = self.immersive_markers.currentItem()
        if item:
            self.edit_marker(item.data(Qt.ItemDataRole.UserRole))

    def delete_immersive_marker(self):
        item = self.immersive_markers.currentItem()
        if item:
            self.delete_marker(item.data(Qt.ItemDataRole.UserRole))

    def focus_reading_page(self):
        field = self.page_number
        if self.reading_mode != "normal":
            self.show_reading_controls(); field = self.immersive_page
        field.setFocus(); field.selectAll()

    def focus_immersive_search(self):
        self.show_reading_controls()
        if self.immersive_search.isVisible():
            self.immersive_search.setFocus(); self.immersive_search.selectAll()
        else:
            text, accepted = QInputDialog.getText(self, "Buscar no PDF", "Texto (F3 vai ao próximo resultado):", text=self.pdf_search.text())
            if accepted:
                self.pdf_search.setText(text)

    def eventFilter(self, watched, event):
        if (self.reading_page_restore and watched == self.pdf_view.viewport()
                and event.type() == QEvent.Type.Resize):
            self.reading_restore_timer.start()
        if getattr(self, "reading_mode", "normal") != "normal" and isinstance(watched, QWidget):
            if watched == self or self.isAncestorOf(watched):
                if event.type() == QEvent.Type.MouseMove:
                    point = self.mapFromGlobal(event.globalPosition().toPoint())
                    if point.y() < 70:
                        self.show_reading_controls()
        return super().eventFilter(watched, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if getattr(self, "reading_mode", "normal") != "normal":
            self.position_reading_overlays()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange and hasattr(self, "blackouts"):
            self.blackouts.schedule()
