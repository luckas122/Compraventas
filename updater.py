#updater.py
"""
Sistema de actualización automática desde GitHub Releases.
- Prefiere ZIP (carpeta ONEDIR completa) para actualizar.
- Si no hay ZIP, cae a EXE (instalador/onefile).
"""
import sys
import os
import json
import zipfile
import urllib.request
import urllib.error
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Tuple

import ssl
try:
    import certifi
except Exception:
    certifi = None


def _get_ssl_context():
    """
    Devuelve un SSLContext que use el bundle de certifi si está disponible.
    Esto evita errores de CERTIFICATE_VERIFY_FAILED en ejecutables PyInstaller.
    """
    try:
        if certifi is not None:
            return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        pass
    # Fallback: contexto por defecto del sistema
    return ssl.create_default_context()

from PyQt5.QtWidgets import QMessageBox, QProgressDialog
from PyQt5.QtCore import QThread, pyqtSignal, Qt

try:
    from version import __version__, __release_url__, __app_name__
except ImportError:
    __version__ = "1.0.0"
    __release_url__ = ""
    __app_name__ = "TuLocalV12025"


# ----------------------------- Descarga en hilo ------------------------------ #
class DownloadThread(QThread):
    """Thread para descargar actualizaciones sin bloquear la UI."""
    progress = pyqtSignal(int)
    finished = pyqtSignal(str)  # ruta del archivo descargado
    error = pyqtSignal(str)

    def __init__(self, url: str, filename: str):
        super().__init__()
        self.url = url
        self.filename = filename
        self.cancelled = False

    def run(self):
        try:
            temp_dir = Path(tempfile.gettempdir()) / __app_name__
            temp_dir.mkdir(parents=True, exist_ok=True)
            download_path = temp_dir / self.filename

            def reporthook(block_num, block_size, total_size):
                if self.cancelled:
                    raise Exception("Download cancelled")
                if total_size > 0:
                    percent = int((block_num * block_size / total_size) * 100)
                    self.progress.emit(min(percent, 100))

            # Cabecera + contexto SSL para evitar problemas de certificados
            ctx = _get_ssl_context()
            opener = urllib.request.build_opener(
                urllib.request.HTTPSHandler(context=ctx)
            )
            opener.addheaders = [('User-Agent', f'{__app_name__}/{__version__}')]
            urllib.request.install_opener(opener)

            urllib.request.urlretrieve(self.url, download_path, reporthook)
            self.finished.emit(str(download_path))

        except Exception as e:
            self.error.emit(str(e))

    def cancel(self):
        self.cancelled = True


# --------------------------------- Updater ---------------------------------- #
class Updater:
    """Gestor de actualizaciones desde GitHub Releases."""

    def __init__(self, parent_widget=None):
        self.parent = parent_widget
        self.current_version = self._parse_version(__version__)
        self._pending_update_info = None
        self._dl_thread = None  # evitar GC

    # ---- Utilidades de versión ---- #
    @staticmethod
    def _parse_version(version_str: str) -> Tuple[int, ...]:
        """Convierte string de versión a tupla de enteros (ignora 'v')."""
        try:
            v = version_str.strip().lstrip('vV')
            return tuple(int(p) for p in v.split('.'))
        except Exception:
            return (0, 0, 0)

    # ---- Consulta de updates ---- #
    def check_for_updates(self, silent: bool = False) -> Optional[dict]:
        """
        Verifica si hay actualizaciones disponibles.

        Args:
            silent: Si True, no muestra mensaje cuando no hay actualizaciones.

        Returns:
            Dict con info de la release si hay actualización, None si no hay.
        """
        if not __release_url__:
            if not silent:
                QMessageBox.information(self.parent, "Actualizaciones",
                                        "No se configuró la URL de releases.")
            return None

        try:
            req = urllib.request.Request(
                __release_url__,
                headers={'User-Agent': f'{__app_name__}/{__version__}'}
            )
            ctx = _get_ssl_context()
            with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
                data = json.loads(resp.read().decode('utf-8'))

            tag_name = data.get('tag_name', '').strip()
            if not tag_name:
                if not silent:
                    QMessageBox.information(self.parent, "Actualizaciones",
                                            "No se encontró ninguna release.")
                return None

            latest_version = self._parse_version(tag_name)
            if latest_version <= self.current_version:
                if not silent:
                    QMessageBox.information(self.parent, "Actualizaciones",
                                            "Ya tienes la última versión.")
                return None

            # Buscar assets: preferir Setup.exe (instalador), luego ZIP (legacy), luego cualquier EXE
            assets = data.get('assets', []) or []
            setup_asset = None
            zip_asset = None
            exe_asset = None
            for asset in assets:
                name = (asset.get('name') or '').lower()
                if 'setup.exe' in name and not setup_asset:
                    setup_asset = asset
                elif name.endswith('.zip') and not zip_asset:
                    zip_asset = asset
                elif name.endswith('.exe') and not exe_asset:
                    exe_asset = asset

            # Prioridad: Setup.exe > ZIP > EXE
            chosen = setup_asset or zip_asset or exe_asset
            if not chosen:
                if not silent:
                    QMessageBox.information(self.parent, "Actualizaciones",
                                            "Hay una versión nueva, pero no se encontraron archivos para descargar.")
                return None

            # Determinar tipo de archivo
            if setup_asset:
                filetype = 'setup'
            elif zip_asset:
                filetype = 'zip'
            else:
                filetype = 'exe'

            return {
                'version': tag_name,
                'tag_name': tag_name,
                'name': data.get('name') or tag_name,
                'body': data.get('body', ''),
                'download_url': chosen['browser_download_url'],
                'filename': chosen['name'],
                'size': chosen.get('size', 0),
                'filetype': filetype,
                'repo': '/'.join(__release_url__.split('/')[-4:-2])  # owner/repo
            }

        except urllib.error.URLError as e:
            if not silent:
                QMessageBox.critical(self.parent, "Actualizaciones",
                                     f"Error de red consultando releases:\n{e}")
        except Exception as e:
            if not silent:
                QMessageBox.critical(self.parent, "Actualizaciones",
                                     f"Error verificando actualizaciones:\n{e}")
        return None

    # ---- Descarga e instalación ---- #
    def download_and_install(self, update_info: dict):
        """Descarga e instala la actualización."""
        # Confirmar con el usuario
        size_mb = (update_info.get('size', 0) or 0) / (1024 * 1024)
        message = (
            f"Nueva versión disponible: {update_info['version']}\n\n"
            f"{update_info.get('name','')}\n\n"
            f"Tamaño aprox.: {size_mb:.1f} MB\n\n"
            f"¿Deseas descargar e instalar la actualización?\n"
            f"La aplicación se cerrará después de la descarga."
        )
        reply = QMessageBox.question(
            self.parent,
            "Actualización disponible",
            message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        if reply != QMessageBox.Yes:
            return

        # ========================================================================
        # NUEVA POLÍTICA: Desde v2.8.0 usamos INSTALADOR INNO SETUP
        # Las actualizaciones se hacen descargando y ejecutando el Setup.exe
        # ========================================================================
        from version import __version__, get_version_tuple
        current_version_tuple = get_version_tuple()

        # Obtener versión de destino
        import re
        latest_tag = update_info.get('tag_name', '')
        match = re.search(r'v?(\d+)\.(\d+)\.(\d+)', latest_tag)
        if match:
            target_version = tuple(map(int, match.groups()))
        else:
            target_version = (9, 9, 9)  # Fallback alto

        # Si la versión de destino es >= 2.8.0 Y tenemos Setup.exe, usar instalador
        if target_version >= (2, 8, 0) and update_info.get('filetype') == 'setup':
            # Descarga automática del instalador
            # El resto del flujo se maneja en _on_download_complete()
            pass  # Continuar con la descarga normal

        # Diálogo de progreso
        progress = QProgressDialog(
            "Descargando actualización...",
            "Cancelar",
            0, 100,
            self.parent
        )
        progress.setWindowModality(Qt.WindowModal)
        progress.setWindowTitle("Actualizando")
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.setMinimumDuration(0)
        progress.setValue(0)

        # Guardar info y lanzar hilo
        self._pending_update_info = update_info
        self._dl_thread = DownloadThread(update_info['download_url'],
                                         update_info['filename'])
        self._dl_thread.progress.connect(progress.setValue)
        self._dl_thread.finished.connect(lambda p: self._on_download_complete(p, progress))
        self._dl_thread.error.connect(lambda err: self._on_download_error(err, progress))
        progress.canceled.connect(self._dl_thread.cancel)
        self._dl_thread.start()

    def _on_download_complete(self, download_path: str, progress_dialog: QProgressDialog):
        """Callback cuando la descarga se completa."""
        progress_dialog.close()
        info = self._pending_update_info or {}
        filetype = info.get("filetype", "exe")
        new_version_tag = info.get("version", "v0.0.0")
        new_version = new_version_tag.strip().lstrip('vV')

        try:
            if filetype == "setup":
                # --- INSTALACIÓN CON INNO SETUP (v2.8.0+) ---
                msg = QMessageBox(self.parent)
                msg.setIcon(QMessageBox.Information)
                msg.setWindowTitle("Actualización descargada")
                msg.setText(
                    f"La actualización v{new_version} se ha descargado correctamente.\n\n"
                    "El instalador se ejecutará automáticamente y preservará:\n"
                    "  ✓ Tu base de datos\n"
                    "  ✓ Tu configuración (SMTP, AFIP, tickets, etc.)\n\n"
                    "La aplicación se cerrará y el instalador se iniciará.\n\n"
                    "¿Continuar con la instalación?"
                )
                msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
                msg.setDefaultButton(QMessageBox.Yes)

                if msg.exec_() != QMessageBox.Yes:
                    return

                # Ejecutar instalador con interfaz mínima
                import subprocess

                # Obtener carpeta de logs dentro de la app
                if getattr(sys, 'frozen', False):
                    app_dir = Path(sys.executable).parent
                else:
                    app_dir = Path.cwd()

                logs_dir = app_dir / "logs_instalador"
                logs_dir.mkdir(exist_ok=True)
                log_file = logs_dir / f"update_{new_version}.log"

                installer_args = [
                    str(download_path),
                    '/SILENT',               # Instalación con barra de progreso visible
                    '/NORESTART',            # No reiniciar Windows
                    '/CLOSEAPPLICATIONS',    # Cerrar app si está abierta
                    '/RESTARTAPPLICATIONS',  # Reabrir app después de instalar
                    f'/LOG={log_file}',      # Log en carpeta de la app
                ]

                try:
                    # Iniciar instalador
                    subprocess.Popen(installer_args, shell=False)

                    # Dar tiempo a que el instalador inicie
                    import time
                    time.sleep(1)

                    # Cerrar la aplicación actual para permitir que el instalador reemplace archivos
                    import sys
                    sys.exit(0)

                except Exception as e:
                    QMessageBox.critical(
                        self.parent,
                        "Error al ejecutar instalador",
                        f"No se pudo ejecutar el instalador:\n{e}\n\n"
                        f"Puedes ejecutarlo manualmente desde:\n{download_path}"
                    )
                    return

            elif filetype == "zip":
                # --- INSTALACIÓN POR CARPETA (ZIP ONEDIR) ---
                # CORRECCIÓN: En PyInstaller ONEDIR, sys.executable apunta al ejecutable principal
                # Si estamos en un ejecutable frozen, buscar correctamente la carpeta base
                if getattr(sys, 'frozen', False):
                    # Modo frozen (ejecutable): sys.executable es el .exe principal
                    exe_path = Path(sys.executable)
                    install_dir = exe_path.parent
                else:
                    # Modo development: usar carpeta actual
                    install_dir = Path.cwd()

                temp_dir = Path(tempfile.gettempdir()) / __app_name__.replace(" ", "_") / f"upd_{new_version}"
                extract_dir = temp_dir / "unzip"
                extract_dir.mkdir(parents=True, exist_ok=True)

                # Descomprimir ZIP (contiene la carpeta ONEDIR: Tu local 2025/*.*)
                with zipfile.ZipFile(download_path, 'r') as zf:
                    zf.extractall(extract_dir)

                # 🔄 El ZIP contiene una carpeta con el nombre de la app
                # Buscar la carpeta extraída (debería ser la única)
                extracted_folders = [d for d in extract_dir.iterdir() if d.is_dir()]
                if not extracted_folders:
                    raise Exception("El ZIP no contiene ninguna carpeta")

                source_dir = extracted_folders[0]  # "Tu local 2025" folder

                # 🔄 Buscar el ejecutable dentro de source_dir
                # Puede llamarse igual que __app_name__ o tener otro nombre
                # Buscar recursivamente en caso de que esté en subcarpetas
                exe_files = list(source_dir.glob("*.exe"))

                # Si no se encuentra en la raíz, buscar en subcarpetas
                if not exe_files:
                    exe_files = list(source_dir.rglob("*.exe"))

                # Filtrar archivos internos de PyInstaller (pythonw.exe, python.exe, etc.)
                exe_files = [e for e in exe_files if e.stem.lower() not in ('python', 'pythonw', 'pythoncom')]

                if not exe_files:
                    raise Exception(
                        "No se encontró ningún archivo .exe en el ZIP descargado.\n\n"
                        f"Contenido de {source_dir}:\n" +
                        "\n".join([f"  - {p.name}" for p in source_dir.iterdir()][:20])
                    )

                # Usar el primer .exe encontrado (preferir el que esté en la raíz)
                exe_files_root = [e for e in exe_files if e.parent == source_dir]
                source_exe_name = (exe_files_root[0] if exe_files_root else exe_files[0]).name

                # El ejecutable destino mantiene el mismo nombre
                relaunch_exe = install_dir / source_exe_name
                update_script = self._create_update_script_dir(
                    source_dir=str(source_dir),
                    dest_dir=str(install_dir),
                    relaunch_exe=str(relaunch_exe)
                )

                QMessageBox.information(
                    self.parent,
                    "Descarga completada",
                    "Se instalará la actualización y se relanzará la aplicación."
                )

                if sys.platform == 'win32':
                    # Lanzar script de actualización CON ventana visible para debugging
                    subprocess.Popen(['cmd', '/c', update_script],
                                     creationflags=subprocess.CREATE_NEW_CONSOLE)
                else:
                    subprocess.Popen(['sh', update_script])

                # CRÍTICO: Usar os._exit(0) para forzar cierre INMEDIATO del proceso
                # sys.exit(0) no cierra inmediatamente en PyQt5, deja DLLs cargadas
                import os
                os._exit(0)

            else:
                # --- Fallback EXE (reemplazo de ejecutable) ---
                exe_path = Path(sys.executable)
                temp_path = Path(download_path)
                backup_path = exe_path.parent / f"{exe_path.stem}_old{exe_path.suffix}"

                update_script = self._create_update_script(
                    str(temp_path),
                    str(exe_path),
                    str(backup_path)
                )

                QMessageBox.information(
                    self.parent,
                    "Descarga completada",
                    "La actualización se instalará al cerrar la aplicación.\n"
                    "La aplicación se cerrará ahora."
                )

                if sys.platform == 'win32':
                    subprocess.Popen(['cmd', '/c', update_script],
                                     creationflags=subprocess.CREATE_NO_WINDOW)
                else:
                    subprocess.Popen(['sh', update_script])

                # CRÍTICO: Usar os._exit(0) para forzar cierre INMEDIATO del proceso
                import os
                os._exit(0)

        except Exception as e:
            QMessageBox.critical(
                self.parent,
                "Error al instalar",
                f"No se pudo instalar la actualización:\n{str(e)}"
            )

    def _on_download_error(self, error: str, progress_dialog: QProgressDialog):
        """Callback cuando hay un error en la descarga."""
        progress_dialog.close()
        QMessageBox.critical(
            self.parent,
            "Error de descarga",
            f"No se pudo descargar la actualización:\n{error}"
        )

    # ---- Scripts de actualización ---- #
    def _create_update_script(self, new_exe: str, current_exe: str, backup: str) -> str:
        """Crea un script para reemplazar el ejecutable (fallback EXE)."""
        temp_dir = Path(tempfile.gettempdir()) / __app_name__
        temp_dir.mkdir(parents=True, exist_ok=True)

        if sys.platform == 'win32':
            script_path = temp_dir / "update.bat"
            script_content = f"""@echo off
echo Actualizando {__app_name__}...
echo Esperando a que la aplicacion se cierre...
timeout /t 5 /nobreak >nul

REM Verificar que la app se cerró, si no, matarla
tasklist /FI "IMAGENAME eq Tu local 2025.exe" 2>NUL | find /I /N "Tu local 2025.exe">NUL
if "%ERRORLEVEL%"=="0" (
    echo Forzando cierre de la aplicacion...
    taskkill /F /IM "Tu local 2025.exe" >nul 2>&1
    timeout /t 2 /nobreak >nul
)

move /y "{current_exe}" "{backup}" 2>nul
move /y "{new_exe}" "{current_exe}"
echo Actualizacion completada
start "" "{current_exe}"
del "%~f0"
"""
        else:
            script_path = temp_dir / "update.sh"
            script_content = f"""#!/bin/bash
echo "Actualizando {__app_name__}..."
echo "Esperando a que la aplicacion se cierre..."
sleep 5

# Verificar que la app se cerró, si no, matarla
if pgrep -x "Tu local 2025" > /dev/null; then
    echo "Forzando cierre de la aplicacion..."
    pkill -9 "Tu local 2025"
    sleep 2
fi

mv "{current_exe}" "{backup}" 2>/dev/null
mv "{new_exe}" "{current_exe}"
chmod +x "{current_exe}"
echo "Actualizacion completada"
"{current_exe}" &
rm "$0"
"""
        script_path.write_text(script_content, encoding='utf-8')
        if sys.platform != 'win32':
            script_path.chmod(0o755)
        return str(script_path)

    def _create_update_script_dir(self, source_dir: str, dest_dir: str, relaunch_exe: str) -> str:
        """
        Crea un script para actualizar mediante RENOMBRADO de carpetas (evita ERROR 32).

        Estrategia:
        1. Esperar cierre de app
        2. Respaldar config y BD
        3. RENOMBRAR carpeta actual → carpeta_backup
        4. MOVER carpeta nueva → ubicación actual
        5. Restaurar config y BD
        6. Relanzar app
        """
        temp_dir = Path(tempfile.gettempdir()) / __app_name__.replace(" ", "_")
        temp_dir.mkdir(parents=True, exist_ok=True)

        if sys.platform == 'win32':
            script_path = temp_dir / "update_dir.bat"

            # Rutas para el script
            dest_path = Path(dest_dir)
            parent_dir = dest_path.parent
            current_folder_name = dest_path.name
            backup_folder_name = f"{current_folder_name}_backup_{int(__import__('time').time())}"
            backup_path = parent_dir / backup_folder_name

            # Escapar comillas para PowerShell
            ps_exe = relaunch_exe.replace('"', '`"')
            ps_dest = dest_dir.replace('"', '`"')

            script_content = f"""@echo off
echo ========================================
echo   ACTUALIZANDO {__app_name__}
echo   Metodo: Renombrado de carpetas
echo ========================================
echo.

REM ========================================
REM PASO 0: Esperar cierre de aplicacion
REM ========================================
echo [1/6] Esperando cierre de aplicacion...
timeout /t 5 /nobreak >nul

tasklist /FI "IMAGENAME eq Tu local 2025.exe" 2>NUL | find /I /N "Tu local 2025.exe">NUL
if "%ERRORLEVEL%"=="0" (
    echo Forzando cierre de procesos...
    taskkill /F /IM "Tu local 2025.exe" >nul 2>&1
    timeout /t 2 /nobreak >nul
)

REM ========================================
REM PASO 1: Respaldar configuracion y BD
REM ========================================
echo [2/6] Respaldando configuracion y base de datos...
set "CONFIG_FILE={dest_dir}\\_internal\\app\\app_config.json"
set "DB_FILE={dest_dir}\\appcomprasventas.db"
set "TEMP_BACKUP=%TEMP%\\compraventas_config_%RANDOM%"

mkdir "%TEMP_BACKUP%" 2>nul

if exist "%CONFIG_FILE%" (
    copy /Y "%CONFIG_FILE%" "%TEMP_BACKUP%\\app_config.json" >nul 2>&1
    if exist "%TEMP_BACKUP%\\app_config.json" (
        echo   - Configuracion respaldada OK
    ) else (
        echo   - ADVERTENCIA: No se pudo respaldar configuracion
    )
) else (
    echo   - No se encontro configuracion previa
)

if exist "%DB_FILE%" (
    copy /Y "%DB_FILE%" "%TEMP_BACKUP%\\appcomprasventas.db" >nul 2>&1
    if exist "%TEMP_BACKUP%\\appcomprasventas.db" (
        echo   - Base de datos respaldada OK
    ) else (
        echo   - ADVERTENCIA: No se pudo respaldar BD
    )
) else (
    echo   - No se encontro BD previa
)

REM ========================================
REM PASO 2: Renombrar carpeta actual → backup
REM ========================================
echo [3/6] Renombrando carpeta actual a backup...
if exist "{dest_dir}" (
    move "{dest_dir}" "{backup_path}" >nul 2>&1
    if exist "{backup_path}" (
        echo   - Carpeta renombrada: {backup_folder_name}
    ) else (
        echo ERROR: No se pudo renombrar carpeta actual
        pause
        exit /b 1
    )
)

REM ========================================
REM PASO 3: Mover carpeta nueva a ubicacion final
REM ========================================
echo [4/6] Instalando nueva version...
move "{source_dir}" "{dest_dir}" >nul 2>&1
if exist "{dest_dir}" (
    echo   - Nueva version instalada OK
) else (
    echo ERROR: No se pudo mover carpeta nueva
    echo Intentando restaurar backup...
    move "{backup_path}" "{dest_dir}" >nul 2>&1
    pause
    exit /b 1
)

REM ========================================
REM PASO 4: Restaurar configuracion y BD
REM ========================================
echo [5/6] Restaurando configuracion y base de datos...
set "NEW_CONFIG_FILE={dest_dir}\\_internal\\app\\app_config.json"
set "NEW_DB_FILE={dest_dir}\\appcomprasventas.db"

if exist "%TEMP_BACKUP%\\app_config.json" (
    copy /Y "%TEMP_BACKUP%\\app_config.json" "%NEW_CONFIG_FILE%" >nul 2>&1
    if exist "%NEW_CONFIG_FILE%" (
        echo   - Configuracion restaurada OK
    ) else (
        echo   - ADVERTENCIA: No se pudo restaurar configuracion
    )
)

if exist "%TEMP_BACKUP%\\appcomprasventas.db" (
    copy /Y "%TEMP_BACKUP%\\appcomprasventas.db" "%NEW_DB_FILE%" >nul 2>&1
    if exist "%NEW_DB_FILE%" (
        echo   - Base de datos restaurada OK
    ) else (
        echo   - ADVERTENCIA: No se pudo restaurar BD
    )
)

REM Limpiar backup temporal
rd /s /q "%TEMP_BACKUP%" 2>nul

REM ========================================
REM PASO 5: Crear acceso directo
REM ========================================
echo [6/6] Creando acceso directo en escritorio...
powershell -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\\{__app_name__}.lnk'); $s.TargetPath = '{ps_exe}'; $s.WorkingDirectory = '{ps_dest}'; $s.Save()" 2>nul

REM ========================================
REM Relanzar aplicacion
REM ========================================
echo.
echo ========================================
echo   ACTUALIZACION COMPLETADA
echo ========================================
echo.
echo Reiniciando aplicacion...
cd /d "{dest_dir}"
start "" "{relaunch_exe}"

REM Nota: La carpeta backup se eliminará en proxima actualizacion
echo.
echo NOTA: Carpeta antigua guardada en:
echo {backup_path}
echo (Se puede eliminar manualmente si la app funciona correctamente)

timeout /t 3 /nobreak >nul
del "%~f0"
"""
        else:
            script_path = temp_dir / "update_dir.sh"

            # Rutas para el script
            dest_path = Path(dest_dir)
            parent_dir = dest_path.parent
            current_folder_name = dest_path.name
            backup_folder_name = f"{current_folder_name}_backup_{int(__import__('time').time())}"
            backup_path = parent_dir / backup_folder_name

            script_content = f"""#!/bin/bash
echo "========================================"
echo "  ACTUALIZANDO {__app_name__}"
echo "  Metodo: Renombrado de carpetas"
echo "========================================"
echo ""

# ========================================
# PASO 0: Esperar cierre de aplicacion
# ========================================
echo "[1/6] Esperando cierre de aplicacion..."
sleep 5

if pgrep -x "Tu local 2025" > /dev/null; then
    echo "Forzando cierre de procesos..."
    pkill -9 "Tu local 2025"
    sleep 2
fi

# ========================================
# PASO 1: Respaldar configuracion y BD
# ========================================
echo "[2/6] Respaldando configuracion y base de datos..."
CONFIG_FILE="{dest_dir}/_internal/app/app_config.json"
DB_FILE="{dest_dir}/appcomprasventas.db"
TEMP_BACKUP="/tmp/compraventas_config_$$"

mkdir -p "$TEMP_BACKUP"

if [ -f "$CONFIG_FILE" ]; then
    cp "$CONFIG_FILE" "$TEMP_BACKUP/app_config.json" 2>/dev/null
    if [ -f "$TEMP_BACKUP/app_config.json" ]; then
        echo "  - Configuracion respaldada OK"
    else
        echo "  - ADVERTENCIA: No se pudo respaldar configuracion"
    fi
else
    echo "  - No se encontro configuracion previa"
fi

if [ -f "$DB_FILE" ]; then
    cp "$DB_FILE" "$TEMP_BACKUP/appcomprasventas.db" 2>/dev/null
    if [ -f "$TEMP_BACKUP/appcomprasventas.db" ]; then
        echo "  - Base de datos respaldada OK"
    else
        echo "  - ADVERTENCIA: No se pudo respaldar BD"
    fi
else
    echo "  - No se encontro BD previa"
fi

# ========================================
# PASO 2: Renombrar carpeta actual → backup
# ========================================
echo "[3/6] Renombrando carpeta actual a backup..."
if [ -d "{dest_dir}" ]; then
    mv "{dest_dir}" "{backup_path}" 2>/dev/null
    if [ -d "{backup_path}" ]; then
        echo "  - Carpeta renombrada: {backup_folder_name}"
    else
        echo "ERROR: No se pudo renombrar carpeta actual"
        exit 1
    fi
fi

# ========================================
# PASO 3: Mover carpeta nueva a ubicacion final
# ========================================
echo "[4/6] Instalando nueva version..."
mv "{source_dir}" "{dest_dir}" 2>/dev/null
if [ -d "{dest_dir}" ]; then
    echo "  - Nueva version instalada OK"
else
    echo "ERROR: No se pudo mover carpeta nueva"
    echo "Intentando restaurar backup..."
    mv "{backup_path}" "{dest_dir}" 2>/dev/null
    exit 1
fi

# ========================================
# PASO 4: Restaurar configuracion y BD
# ========================================
echo "[5/6] Restaurando configuracion y base de datos..."
NEW_CONFIG_FILE="{dest_dir}/_internal/app/app_config.json"
NEW_DB_FILE="{dest_dir}/appcomprasventas.db"

if [ -f "$TEMP_BACKUP/app_config.json" ]; then
    cp "$TEMP_BACKUP/app_config.json" "$NEW_CONFIG_FILE" 2>/dev/null
    if [ -f "$NEW_CONFIG_FILE" ]; then
        echo "  - Configuracion restaurada OK"
    else
        echo "  - ADVERTENCIA: No se pudo restaurar configuracion"
    fi
fi

if [ -f "$TEMP_BACKUP/appcomprasventas.db" ]; then
    cp "$TEMP_BACKUP/appcomprasventas.db" "$NEW_DB_FILE" 2>/dev/null
    if [ -f "$NEW_DB_FILE" ]; then
        echo "  - Base de datos restaurada OK"
    else
        echo "  - ADVERTENCIA: No se pudo restaurar BD"
    fi
fi

# Limpiar backup temporal
rm -rf "$TEMP_BACKUP"

# ========================================
# Relanzar aplicacion
# ========================================
echo ""
echo "========================================"
echo "  ACTUALIZACION COMPLETADA"
echo "========================================"
echo ""
echo "Reiniciando aplicacion..."
echo ""
echo "NOTA: Carpeta antigua guardada en:"
echo "{backup_path}"
echo "(Se puede eliminar manualmente si la app funciona correctamente)"
echo ""

"{relaunch_exe}" &
sleep 2
rm "$0"
"""
        script_path.write_text(script_content, encoding='utf-8')
        if sys.platform != 'win32':
            script_path.chmod(0o755)
        return str(script_path)


# ------------------------------ Helper público ------------------------------- #
def check_updates_on_startup(parent_widget=None, auto_install: bool = False):
    """
    Verifica actualizaciones al iniciar la app.
    Si auto_install=True, descarga e instala sin preguntar.
    """
    updater = Updater(parent_widget)
    update_info = updater.check_for_updates(silent=True)

    if update_info:
        if auto_install:
            updater.download_and_install(update_info)
        else:
            reply = QMessageBox.question(
                parent_widget,
                "Actualización disponible",
                f"Hay una nueva versión disponible: {update_info['version']}\n\n"
                f"¿Deseas actualizarla ahora?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                updater.download_and_install(update_info)
