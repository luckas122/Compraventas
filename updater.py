# updater.py
"""
Sistema de actualización automática desde GitHub Releases.
Usa exclusivamente instalador Inno Setup (.exe Setup).
"""
import sys
import os
import json
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
    return ssl.create_default_context()

from PyQt5.QtWidgets import QMessageBox, QProgressDialog
from PyQt5.QtCore import QThread, pyqtSignal, Qt

try:
    from version import __version__, __release_url__, __app_name__
except ImportError:
    __version__ = "1.0.0"
    __release_url__ = ""
    __app_name__ = "Tu local 2025"

try:
    from app.config import get_log_dir
except Exception:
    get_log_dir = None


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
            temp_dir = Path(tempfile.gettempdir()) / __app_name__.replace(" ", "_")
            temp_dir.mkdir(parents=True, exist_ok=True)
            download_path = temp_dir / self.filename

            def reporthook(block_num, block_size, total_size):
                if self.cancelled:
                    raise Exception("Download cancelled")
                if total_size > 0:
                    percent = int((block_num * block_size / total_size) * 100)
                    self.progress.emit(min(percent, 100))

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
    """Gestor de actualizaciones desde GitHub Releases (solo Inno Setup)."""

    def __init__(self, parent_widget=None):
        self.parent = parent_widget
        self.current_version = self._parse_version(__version__)
        self._pending_update_info = None
        self._dl_thread = None

    @staticmethod
    def _parse_version(version_str: str) -> Tuple[int, ...]:
        """Convierte string de versión a tupla de enteros (ignora 'v')."""
        try:
            v = version_str.strip().lstrip('vV')
            return tuple(int(p) for p in v.split('.'))
        except Exception:
            return (0, 0, 0)

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

            # Buscar Setup.exe en los assets
            assets = data.get('assets', []) or []
            setup_asset = None
            for asset in assets:
                name = (asset.get('name') or '').lower()
                if 'setup.exe' in name:
                    setup_asset = asset
                    break

            if not setup_asset:
                if not silent:
                    QMessageBox.information(self.parent, "Actualizaciones",
                                            "Hay una versión nueva, pero no se encontró el instalador.")
                return None

            return {
                'version': tag_name,
                'tag_name': tag_name,
                'name': data.get('name') or tag_name,
                'body': data.get('body', ''),
                'download_url': setup_asset['browser_download_url'],
                'filename': setup_asset['name'],
                'size': setup_asset.get('size', 0),
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

    def download_and_install(self, update_info: dict):
        """Descarga e instala la actualización usando Inno Setup."""
        size_mb = (update_info.get('size', 0) or 0) / (1024 * 1024)
        message = (
            f"Nueva versión disponible: {update_info['version']}\n\n"
            f"{update_info.get('name','')}\n\n"
            f"Tamaño aprox.: {size_mb:.1f} MB\n\n"
            f"¿Deseas descargar e instalar la actualización?\n"
            f"La aplicación se cerrará durante la instalación."
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

        # Guardar info y lanzar hilo de descarga
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
        new_version = info.get("version", "v0.0.0").strip().lstrip('vV')

        try:
            msg = QMessageBox(self.parent)
            msg.setIcon(QMessageBox.Information)
            msg.setWindowTitle("Actualización descargada")
            msg.setText(
                f"La actualización v{new_version} se ha descargado correctamente.\n\n"
                "El instalador se ejecutará automáticamente y preservará:\n"
                "  - Tu base de datos\n"
                "  - Tu configuración (SMTP, AFIP, tickets, etc.)\n\n"
                "La aplicación se cerrará y el instalador se iniciará.\n\n"
                "¿Continuar con la instalación?"
            )
            msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            msg.setDefaultButton(QMessageBox.Yes)

            if msg.exec_() != QMessageBox.Yes:
                return

            # Obtener carpeta de logs persistente
            if get_log_dir:
                logs_dir = Path(get_log_dir()) / "updates"
            else:
                logs_dir = Path(tempfile.gettempdir()) / "TuLocal_Logs"
            logs_dir.mkdir(parents=True, exist_ok=True)
            log_file = logs_dir / f"update_{new_version}.log"

            # Ejecutar instalador Inno Setup
            installer_args = [
                str(download_path),
                '/SILENT',               # Instalación con barra de progreso visible
                '/NORESTART',            # No reiniciar Windows
                '/CLOSEAPPLICATIONS',    # Cerrar app si está abierta
                '/RESTARTAPPLICATIONS',  # Reabrir app después de instalar
                '/TASKS=backupconfig',   # Forzar backup de configuración
                f'/LOG={log_file}',      # Log en carpeta de la app
            ]

            try:
                subprocess.Popen(installer_args, shell=False)

                # Dar tiempo a que el instalador inicie
                import time
                time.sleep(1)

                # Cerrar la aplicación
                sys.exit(0)

            except Exception as e:
                QMessageBox.critical(
                    self.parent,
                    "Error al ejecutar instalador",
                    f"No se pudo ejecutar el instalador:\n{e}\n\n"
                    f"Puedes ejecutarlo manualmente desde:\n{download_path}"
                )

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
