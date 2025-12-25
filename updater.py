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

            # Buscar assets: preferir ZIP, luego EXE
            assets = data.get('assets', []) or []
            zip_asset = None
            exe_asset = None
            for asset in assets:
                name = (asset.get('name') or '').lower()
                if name.endswith('.zip') and not zip_asset:
                    zip_asset = asset
                if name.endswith('.exe') and not exe_asset:
                    exe_asset = asset

            chosen = zip_asset or exe_asset
            if not chosen:
                if not silent:
                    QMessageBox.information(self.parent, "Actualizaciones",
                                            "Hay una versión nueva, pero no se encontraron archivos para descargar.")
                return None

            filetype = 'zip' if zip_asset else 'exe'
            return {
                'version': tag_name,
                'name': data.get('name') or tag_name,
                'body': data.get('body', ''),
                'download_url': chosen['browser_download_url'],
                'filename': chosen['name'],
                'size': chosen.get('size', 0),
                'filetype': filetype
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
            if filetype == "zip":
                # --- INSTALACIÓN POR CARPETA (ZIP ONEDIR) ---
                exe_path = Path(sys.executable)
                install_dir = exe_path.parent  # carpeta ONEDIR actual
                temp_dir = Path(tempfile.gettempdir()) / __app_name__ / f"upd_{new_version}"
                extract_dir = temp_dir / "unzip"
                extract_dir.mkdir(parents=True, exist_ok=True)

                # Descomprimir ZIP (contiene la carpeta ONEDIR plana)
                with zipfile.ZipFile(download_path, 'r') as zf:
                    zf.extractall(extract_dir)

                # 🔄 Nombre sin versión para mantener accesos directos funcionando
                relaunch_exe = install_dir / f"{__app_name__}.exe"
                update_script = self._create_update_script_dir(
                    source_dir=str(extract_dir),
                    dest_dir=str(install_dir),
                    relaunch_exe=str(relaunch_exe)
                )

                QMessageBox.information(
                    self.parent,
                    "Descarga completada",
                    "Se instalará la actualización y se relanzará la aplicación."
                )

                if sys.platform == 'win32':
                    subprocess.Popen(['cmd', '/c', update_script],
                                     creationflags=subprocess.CREATE_NO_WINDOW)
                else:
                    subprocess.Popen(['sh', update_script])
                sys.exit(0)

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
                sys.exit(0)

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
timeout /t 2 /nobreak >nul
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
sleep 2
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
        Crea un script para actualizar la carpeta ONEDIR completa (ROBOCOPY/rsync) y relanzar.
        """
        temp_dir = Path(tempfile.gettempdir()) / __app_name__
        temp_dir.mkdir(parents=True, exist_ok=True)

        if sys.platform == 'win32':
            script_path = temp_dir / "update_dir.bat"
            script_content = f"""@echo off
echo Actualizando {__app_name__} (carpeta)...
timeout /t 2 /nobreak >nul
robocopy "{source_dir}" "{dest_dir}" /MIR /NFL /NDL /NJH /NJS /NP
echo Actualizacion completada
start "" "{relaunch_exe}"
del "%~f0"
"""
        else:
            script_path = temp_dir / "update_dir.sh"
            script_content = f"""#!/bin/bash
echo "Actualizando {__app_name__} (carpeta)..."
sleep 2
rsync -a --delete "{source_dir}/" "{dest_dir}/"
echo "Actualizacion completada"
"{relaunch_exe}" &
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
