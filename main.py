import argparse
import os
import sys
from pathlib import Path


_dll_handles = []
if sys.platform == "win32" and getattr(sys, "frozen", False):
    # Prefer the Qt and OpenSSL DLLs shipped with the application over unrelated
    # Qt copies that other programs may have added to the user's PATH.
    internal = Path(sys._MEIPASS)
    bundled = [internal / "PySide6", internal]
    os.environ["PATH"] = os.pathsep.join(str(path) for path in bundled) + os.pathsep + os.environ.get("PATH", "")
    if hasattr(os, "add_dll_directory"):
        _dll_handles.extend(os.add_dll_directory(str(path)) for path in bundled)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Entrelinhas · Leitor de PDF para desktop")
    parser.add_argument("files", nargs="*", help="PDFs para adicionar à biblioteca e abrir")
    parser.add_argument("--data-dir", help="Diretório alternativo da biblioteca local")
    parser.add_argument("--smoke-test", metavar="REPORT", help=argparse.SUPPRESS)
    parser.add_argument("--sync-once", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--register-shell", action="store_true", help="Adicionar Entrelinhas ao Abrir com do Windows")
    return parser.parse_args(argv)


def main():
    args = parse_args()
    if args.register_shell:
        from leitor.windows_integration import register_shell
        register_shell()
        return 0
    if args.smoke_test:
        from leitor.smoke import smoke_test
        return smoke_test(args.smoke_test)
    if args.sync_once:
        from leitor.storage import default_data_dir
        from leitor.sync import SyncClient
        root = Path(args.data_dir).resolve() if args.data_dir else default_data_dir().resolve()
        SyncClient(root).sync_once()
        return 0
    from leitor.app import run
    return run(args.data_dir, args.files)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        import traceback
        folder = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "LeitorPDF"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "erro.log").write_text(traceback.format_exc(), encoding="utf-8")
        from PySide6.QtWidgets import QApplication, QMessageBox
        app = QApplication.instance() or QApplication(sys.argv)
        QMessageBox.critical(None, "Entrelinhas", f"O aplicativo encontrou um erro.\nDetalhes salvos em {folder / 'erro.log'}")
        sys.exit(1)
