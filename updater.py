# updater.py
"""
Sistema de actualización automática desde GitHub Releases.
"""
import sys
import json
import urllib.request
import urllib.error
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import Optional, Tuple
from PyQt5.QtWidgets import QMessageBox, QProgressDialog
from PyQt5.QtCore import QThread, pyqtSignal, Qt

try:
    from version import __version__, __release_url__, __app_name__
except ImportError:
    __version__ = "1.0.0"
    __release_url__ = ""
    __app_name__ = "TuLocalV12025"


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
            temp_dir.mkdir(exist_ok=True)
            download_path = temp_dir / self.filename
            
            def reporthook(block_num, block_size, total_size):
                if self.cancelled:
                    raise Exception("Download cancelled")
                if total_size > 0:
                    percent = int((block_num * block_size / total_size) * 100)
                    self.progress.emit(min(percent, 100))
            
            urllib.request.urlretrieve(self.url, download_path, reporthook)
            self.finished.emit(str(download_path))
            
        except Exception as e:
            self.error.emit(str(e))
    
    def cancel(self):
        self.cancelled = True


class Updater:
    """Gestor de actualizaciones desde GitHub Releases."""
    
    def __init__(self, parent_widget=None):
        self.parent = parent_widget
        self.current_version = self._parse_version(__version__)
    
    @staticmethod
    def _parse_version(version_str: str) -> Tuple[int, ...]:
        """Convierte string de versión a tupla de enteros."""
        try:
            return tuple(map(int, version_str.strip('v').split('.')))
        except:
            return (0, 0, 0)
    
    def check_for_updates(self, silent: bool = False) -> Optional[dict]:
        """
        Verifica si hay actualizaciones disponibles.
        
        Args:
            silent: Si True, no muestra mensaje cuando no hay actualizaciones
            
        Returns:
            Dict con info de la release si hay actualización, None si no hay
        """
        try:
            # Hacer request a GitHub API
            request = urllib.request.Request(
                __release_url__,
                headers={'User-Agent': f'{__app_name__}/{__version__}'}
            )
            
            with urllib.request.urlopen(request, timeout=10) as response:
                data = json.loads(response.read().decode())
            
            # Extraer versión del release
            latest_version = self._parse_version(data['tag_name'])
            
            # Comparar versiones
            if latest_version > self.current_version:
                # Buscar el asset .exe
                exe_asset = None
                for asset in data.get('assets', []):
                    if asset['name'].endswith('.exe'):
                        exe_asset = asset
                        break
                
                if exe_asset:
                    return {
                        'version': data['tag_name'],
                        'name': data['name'],
                        'body': data.get('body', ''),
                        'download_url': exe_asset['browser_download_url'],
                        'filename': exe_asset['name'],
                        'size': exe_asset['size']
                    }
            
            if not silent:
                QMessageBox.information(
                    self.parent,
                    "No hay actualizaciones",
                    f"Ya tienes la versión más reciente ({__version__})"
                )
            
            return None
            
        except urllib.error.URLError:
            if not silent:
                QMessageBox.warning(
                    self.parent,
                    "Error de conexión",
                    "No se pudo conectar al servidor de actualizaciones.\n"
                    "Verifica tu conexión a internet."
                )
            return None
        except Exception as e:
            if not silent:
                QMessageBox.critical(
                    self.parent,
                    "Error",
                    f"Error al verificar actualizaciones:\n{str(e)}"
                )
            return None
    
    def download_and_install(self, update_info: dict):
        """Descarga e instala la actualización."""
        
        # Confirmar con el usuario
        size_mb = update_info['size'] / (1024 * 1024)
        message = (
            f"Nueva versión disponible: {update_info['version']}\n\n"
            f"{update_info['name']}\n\n"
            f"Tamaño: {size_mb:.1f} MB\n\n"
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
        
        # Crear diálogo de progreso
        progress = QProgressDialog(
            "Descargando actualización...",
            "Cancelar",
            0, 100,
            self.parent
        )
        progress.setWindowModality(Qt.WindowModal)
        progress.setWindowTitle("Actualizando")
        progress.setAutoClose(False)
        
        # Crear thread de descarga
        download_thread = DownloadThread(
            update_info['download_url'],
            update_info['filename']
        )
        
        # Conectar señales
        download_thread.progress.connect(progress.setValue)
        download_thread.finished.connect(
            lambda path: self._on_download_complete(path, progress)
        )
        download_thread.error.connect(
            lambda error: self._on_download_error(error, progress)
        )
        progress.canceled.connect(download_thread.cancel)
        
        # Iniciar descarga
        download_thread.start()
    
    def _on_download_complete(self, download_path: str, progress_dialog):
        """Callback cuando la descarga se completa."""
        progress_dialog.close()
        
        # Preparar instalación
        exe_path = Path(sys.executable)
        temp_path = Path(download_path)
        backup_path = exe_path.parent / f"{exe_path.stem}_old{exe_path.suffix}"
        
        try:
            # Crear script de actualización
            update_script = self._create_update_script(
                str(temp_path),
                str(exe_path),
                str(backup_path)
            )
            
            # Informar al usuario
            QMessageBox.information(
                self.parent,
                "Descarga completada",
                "La actualización se instalará al cerrar la aplicación.\n"
                "La aplicación se cerrará ahora."
            )
            
            # Ejecutar script y salir
            if sys.platform == 'win32':
                subprocess.Popen(
                    ['cmd', '/c', update_script],
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            else:
                subprocess.Popen(['sh', update_script])
            
            # Cerrar aplicación
            sys.exit(0)
            
        except Exception as e:
            QMessageBox.critical(
                self.parent,
                "Error al instalar",
                f"No se pudo instalar la actualización:\n{str(e)}"
            )
    
    def _on_download_error(self, error: str, progress_dialog):
        """Callback cuando hay un error en la descarga."""
        progress_dialog.close()
        QMessageBox.critical(
            self.parent,
            "Error de descarga",
            f"No se pudo descargar la actualización:\n{error}"
        )
    
    def _create_update_script(self, new_exe: str, current_exe: str, backup: str) -> str:
        """Crea un script para reemplazar el ejecutable."""
        temp_dir = Path(tempfile.gettempdir()) / __app_name__
        
        if sys.platform == 'win32':
            script_path = temp_dir / "update.bat"
            script_content = f"""@echo off
echo Actualizando {__app_name__}...
timeout /t 2 /nobreak >nul
move /y "{current_exe}" "{backup}" 2>nul
move /y "{new_exe}" "{current_exe}"
echo Actualización completada
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
echo "Actualización completada"
"{current_exe}" &
rm "$0"
"""
        
        script_path.write_text(script_content, encoding='utf-8')
        if sys.platform != 'win32':
            script_path.chmod(0o755)
        
        return str(script_path)


def check_updates_on_startup(parent_widget=None, auto_install: bool = False):
    """
    Función helper para verificar actualizaciones al iniciar la app.
    
    Args:
        parent_widget: Widget padre para los diálogos
        auto_install: Si True, descarga automáticamente sin preguntar
    """
    updater = Updater(parent_widget)
    update_info = updater.check_for_updates(silent=True)
    
    if update_info:
        if auto_install:
            updater.download_and_install(update_info)
        else:
            # Mostrar notificación con opción de actualizar
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