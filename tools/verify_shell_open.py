"""Run real processes in a temporary library; optionally invoke registered Windows verbs."""
import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication
from leitor.smoke import create_fixture
from leitor.storage import Library


def wait_until(condition, description):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(.05)
    raise AssertionError(description)


def shell_open(path, *, direct=False):
    class ShellExecuteInfo(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("fMask", wintypes.ULONG),
                    ("hwnd", wintypes.HWND), ("lpVerb", wintypes.LPCWSTR),
                    ("lpFile", wintypes.LPCWSTR), ("lpParameters", wintypes.LPCWSTR),
                    ("lpDirectory", wintypes.LPCWSTR), ("nShow", ctypes.c_int),
                    ("hInstApp", wintypes.HINSTANCE), ("lpIDList", ctypes.c_void_p),
                    ("lpClass", wintypes.LPCWSTR), ("hkeyClass", wintypes.HKEY),
                    ("dwHotKey", wintypes.DWORD), ("hIcon", wintypes.HANDLE),
                    ("hProcess", wintypes.HANDLE)]
    info = ShellExecuteInfo(); info.cbSize = ctypes.sizeof(info)
    info.fMask = 0x40 | 0x100 | 0x400 | (0 if direct else 0x1)
    info.lpVerb = "Entrelinhas" if direct else "open"
    info.lpFile = str(path); info.lpClass = None if direct else "Entrelinhas.PDF"
    info.nShow = 0
    execute = ctypes.windll.shell32.ShellExecuteExW
    execute.argtypes = [ctypes.POINTER(ShellExecuteInfo)]; execute.restype = wintypes.BOOL
    if not execute(ctypes.byref(info)):
        raise ctypes.WinError()
    if info.hProcess:
        wait = ctypes.windll.kernel32.WaitForSingleObject; wait.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        close = ctypes.windll.kernel32.CloseHandle; close.argtypes = [wintypes.HANDLE]
        try:
            if wait(info.hProcess, 15000) != 0:
                raise AssertionError("O pedido pelo Explorer não terminou.")
            code = wintypes.DWORD()
            get_code = ctypes.windll.kernel32.GetExitCodeProcess
            get_code.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
            get_code(info.hProcess, ctypes.byref(code))
            assert code.value == 0, f"Shell exit code: {code.value}"
        finally:
            close(info.hProcess)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", type=Path)
    parser.add_argument("--registered", action="store_true")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    command = [str(args.exe.resolve())] if args.exe else [sys.executable, str(ROOT / "main.py")]
    app = QApplication([])
    QFontDatabase.addApplicationFont(str(Path(os.environ["WINDIR"]) / "Fonts/segoeui.ttf"))
    checks = []
    with tempfile.TemporaryDirectory(prefix="entrelinhas-shell-") as tmp:
        root = Path(tmp)
        os.environ["LOCALAPPDATA"] = str(root)
        library = Library(root / "LeitorPDF")
        first = root / "Primeiro livro com espaços & acentuação.pdf"
        second = root / "Outro livro de teste.pdf"
        third = root / "Livro aberto pelo Explorer.pdf"
        fourth = root / "Livro pelo menu direto.pdf"
        for number, path in enumerate((first, second, third, fourth)):
            create_fixture(path, title=f"Livro de teste {number}")
        process = subprocess.Popen([*command, str(first)], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            wait_until(lambda: len(library.books()) == 1 and library.books()[0]["last_read"], "A primeira execução não importou e abriu o PDF")
            first_id = library.books()[0]["id"]
            checks.append("Primeira execução importa e abre PDF com espaços, acentos e & no caminho")
            child = subprocess.run([*command, str(second)], capture_output=True, timeout=15)
            assert child.returncode == 0, child.stderr.decode(errors="replace")
            wait_until(lambda: len(library.books(scope="reading")) == 2, "A janela aberta não recebeu o segundo PDF")
            assert process.poll() is None
            checks.append("Segunda execução encaminha e abre o novo PDF na instância existente")
            library.save_progress(first_id, 4)
            library.save_bookmark(first_id, 4, "Página importante")
            library.edit_book(first_id, "Meu nome personalizado", ["estudo"], None, True)
            before = library.book(first_id)["last_read"]
            child = subprocess.run([*command, str(first)], capture_output=True, timeout=15)
            assert child.returncode == 0
            wait_until(lambda: library.book(first_id)["last_read"] != before, "Livro existente não foi reaberto")
            assert len(library.books()) == 2
            assert library.book(first_id)["last_page"] == 4
            assert library.book(first_id)["title"] == "Meu nome personalizado"
            assert len(library.bookmarks(first_id)) == 1
            checks.append("Reabertura não duplica e preserva nome, marcador e página 5")
            if args.registered:
                shell_open(third)
                wait_until(lambda: len(library.books(scope="reading")) == 3, "O handler registrado não abriu o PDF")
                checks.append("ShellExecuteEx com o ProgID de Abrir com importa e abre o PDF")
                shell_open(fourth, direct=True)
                wait_until(lambda: len(library.books(scope="reading")) == 4, "O menu de contexto registrado não abriu o PDF")
                checks.append("Verbo Abrir com Entrelinhas do menu de contexto importa e abre o PDF")
            for book in library.books():
                assert (library.files / book["filename"]).is_file()
        finally:
            # Only this harness's own isolated background process is terminated.
            process.terminate(); process.wait(timeout=10)
            errors = process.stderr.read().decode(errors="replace")
            process.stderr.close(); library.close()
        assert "Traceback" not in errors, errors
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps({"ok": True, "checks": checks}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(args.report.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
