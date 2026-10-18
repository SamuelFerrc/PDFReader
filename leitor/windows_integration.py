"""Per-user PDF handlers. Never changes the user's default PDF application."""
import ctypes
import sys
from pathlib import Path

PROG_ID = "Entrelinhas.PDF"


def application_executable():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve()
    return Path(__file__).resolve().parent.parent / "dist/Entrelinhas/Entrelinhas.exe"


def registration_entries(executable):
    executable = Path(executable).resolve()
    command = f'"{executable}" -- "%1"'
    app = r"Software\Classes\Applications\Entrelinhas.exe"
    prog = rf"Software\Classes\{PROG_ID}"
    verb = r"Software\Classes\SystemFileAssociations\.pdf\shell\Entrelinhas"
    capabilities = r"Software\Entrelinhas\Capabilities"
    return [
        (app, "FriendlyAppName", "Entrelinhas"),
        (app + r"\SupportedTypes", ".pdf", ""),
        (app + r"\DefaultIcon", "", f'"{executable}",0'),
        (app + r"\shell\open", "MultiSelectModel", "Document"),
        (app + r"\shell\open\command", "", command),
        (prog, "", "Documento PDF do Entrelinhas"),
        (prog + r"\Application", "ApplicationName", "Entrelinhas"),
        (prog + r"\DefaultIcon", "", f'"{executable}",0'),
        (prog + r"\shell\open", "MultiSelectModel", "Document"),
        (prog + r"\shell\open\command", "", command),
        (r"Software\Classes\.pdf\OpenWithProgids", PROG_ID, ""),
        (verb, "MUIVerb", "Abrir com Entrelinhas"),
        (verb, "Icon", f'"{executable}",0'),
        (verb, "MultiSelectModel", "Document"),
        (verb + r"\command", "", command),
        (r"Software\Microsoft\Windows\CurrentVersion\App Paths\Entrelinhas.exe", "", str(executable)),
        (capabilities, "ApplicationName", "Entrelinhas"),
        (capabilities, "ApplicationDescription", "Biblioteca local e leitor de PDF com marcadores de página"),
        (capabilities, "ApplicationIcon", f'"{executable}",0'),
        (capabilities + r"\FileAssociations", ".pdf", PROG_ID),
        (r"Software\RegisteredApplications", "Entrelinhas", capabilities),
    ]


def register_shell(executable=None):
    if sys.platform != "win32":
        raise OSError("A integração Abrir com está disponível no Windows.")
    import winreg
    executable = Path(executable) if executable else application_executable()
    if not executable.is_file() or executable.suffix.lower() != ".exe":
        raise FileNotFoundError("Gere o executável do Entrelinhas antes de registrar a integração.")
    for path, name, value in registration_entries(executable):
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
    # Refresh association caches without restarting Explorer.
    notify = ctypes.windll.shell32.SHChangeNotify
    notify.argtypes = [ctypes.c_long, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
    notify(0x08000000, 0, None, None)  # SHCNE_ASSOCCHANGED, SHCNF_IDLIST
