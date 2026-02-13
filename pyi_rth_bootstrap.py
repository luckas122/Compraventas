# pyi_rth_bootstrap.py
import os
import sys
import subprocess
import tempfile
from pathlib import Path

try:
    from version import __app_name__, __version__
except Exception:
    __app_name__ = "Tu local 2025"
    __version__ = "0.0.0"

APP_DIRNAME = "Compraventas"     # carpeta raiz de la app de usuario
SUBDIR_APP  = "app"              # donde vive ONEDIR
# Destino final: %LocalAppData%\Compraventas\app\
def _target_root() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / APP_DIRNAME / SUBDIR_APP

def _ensure_user_install():
    """
    Fallback: si el ejecutable NO esta en %LocalAppData%\\Compraventas\\app,
    copia la carpeta ONEDIR ahi y relanza desde ese lugar.
    Usa /E (no destructivo) para no borrar la DB ni otros archivos del usuario.
    """
    if sys.platform != "win32":
        return  # solo hacemos esto en Windows

    cur_exe  = Path(sys.executable)
    cur_dir  = cur_exe.parent
    tgt_dir  = _target_root()

    # Normaliza a minusculas para comparar rutas en Windows
    if str(cur_dir).lower() == str(tgt_dir).lower():
        return  # ya estamos en el lugar correcto

    # Crear destino
    tgt_dir.mkdir(parents=True, exist_ok=True)

    # Script temporal para copiar y relanzar
    temp_dir = Path(tempfile.gettempdir()) / __app_name__
    temp_dir.mkdir(parents=True, exist_ok=True)
    script = temp_dir / "self_install.bat"

    # Relanzar el mismo exe pero desde el destino
    relaunch_exe = tgt_dir / cur_exe.name

    # /E = copia recursiva incluyendo subdirectorios vacios
    # /IS /IT = sobreescribe archivos iguales y mas nuevos
    # NO usa /MIR para no borrar archivos del usuario (DB, backups, etc.)
    script.write_text(f"""@echo off
echo Instalando {__app_name__} en %LocalAppData%...
timeout /t 2 /nobreak >nul
robocopy "{cur_dir}" "{tgt_dir}" /E /IS /IT /NFL /NDL /NJH /NJS /NP
echo Instalacion completada

REM Actualizar acceso directo existente para apuntar a la ubicacion correcta
powershell -NoProfile -Command "$lnk = [Environment]::GetFolderPath('Desktop') + '\\{__app_name__}.lnk'; if (Test-Path $lnk) {{ $ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut($lnk); $s.TargetPath = '{relaunch_exe}'; $s.WorkingDirectory = '{tgt_dir}'; $s.Save() }}"

start "" "{relaunch_exe}"
del "%~f0"
""", encoding="utf-8")

    # Ejecutar y salir del proceso actual
    subprocess.Popen(['cmd', '/c', str(script)], creationflags=subprocess.CREATE_NO_WINDOW)
    sys.exit(0)

# --- Ejecutar auto-instalacion al inicio ---
_ensure_user_install()
