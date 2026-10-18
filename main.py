import argparse
import sys


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Entrelinhas · Leitor de PDF para desktop")
    parser.add_argument("files", nargs="*", help="PDFs para adicionar à biblioteca e abrir")
    parser.add_argument("--data-dir", help="Diretório alternativo da biblioteca local")
    parser.add_argument("--smoke-test", metavar="REPORT", help=argparse.SUPPRESS)
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
    from leitor.app import run
    return run(args.data_dir, args.files)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        import os
        import traceback
        from pathlib import Path
        folder = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "LeitorPDF"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "erro.log").write_text(traceback.format_exc(), encoding="utf-8")
        from PySide6.QtWidgets import QApplication, QMessageBox
        app = QApplication.instance() or QApplication(sys.argv)
        QMessageBox.critical(None, "Entrelinhas", f"O aplicativo encontrou um erro.\nDetalhes salvos em {folder / 'erro.log'}")
        sys.exit(1)
