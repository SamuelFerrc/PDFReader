import importlib.metadata
import os
import shutil
import sys
import urllib.request
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication

root = Path(__file__).resolve().parent.parent
app = QApplication([])
pixmap = QPixmap(256, 256); pixmap.fill(Qt.GlobalColor.transparent)
painter = QPainter(pixmap); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(QColor("#38664e")); painter.drawRoundedRect(QRectF(4, 4, 248, 248), 54, 54)
painter.setPen(QPen(QColor("#f5f3e8"), 10, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)); painter.setBrush(Qt.BrushStyle.NoBrush)
painter.drawRoundedRect(QRectF(65, 46, 131, 163), 12, 12)
painter.drawLine(101, 46, 101, 209); painter.drawLine(127, 93, 169, 93); painter.drawLine(127, 124, 169, 124)
painter.end()
(root / "assets").mkdir(exist_ok=True); pixmap.save(str(root / "assets/entrelinhas.ico"))
licenses = root / "licenses"; licenses.mkdir(exist_ok=True)
python_license = Path(sys.base_prefix) / "LICENSE.txt"
if python_license.is_file():
    shutil.copyfile(python_license, licenses / "Python-LICENSE.txt")
for name in ("LGPL-3.0-only.txt", "GPL-3.0-only.txt", "GPL-2.0-only.txt"):
    destination = licenses / name
    if not destination.exists():
        with urllib.request.urlopen(f"https://raw.githubusercontent.com/qt/qtbase/v6.12.0/LICENSES/{name}", timeout=30) as response:
            destination.write_bytes(response.read())
for name in ("PySide6-Essentials", "PySide6-Pdf", "shiboken6", "PyInstaller"):
    package = importlib.metadata.distribution(name)
    for file in package.files or []:
        if "license" in str(file).lower() or "copying" in str(file).lower():
            source = Path(package.locate_file(file))
            if source.is_file():
                destination = licenses / name / Path(str(file)).name
                destination.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(source, destination)
(licenses / "NOTICE.txt").write_text(
    "Entrelinhas uses dynamically linked Qt/PySide6 and Qt PDF (PDFium), Python, and the PyInstaller bootloader.\n"
    "The application source is included alongside this distribution under the MIT license.\n"
    "Dependency notices and license texts are included in the subfolders. Qt DLLs reside in _internal/PySide6.\n"
    "Upstream source and licensing: https://code.qt.io/ | https://www.qt.io/licensing/ | https://www.python.org/ | https://pyinstaller.org/\n",
    encoding="utf-8")
