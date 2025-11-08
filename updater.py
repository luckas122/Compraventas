# updater.py
"""
Sistema de actualización automática desde GitHub Releases.
"""
import sys
import os
import zipfile
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
            assets = data.get('assets', [])

            # 1) Preferir ZIP ONEDIR
            zip_asset = None
            for asset in assets:
                name = asset.get('name', '').lower()
                if name.endswith('.zip'):
                    # idealmente nombre estilo: Compraventas-vX.Y.Z-onedir.zip
                    zip_asset = asset
                    break

            # 2) Fallback: EXE (instalador o onefile)
            exe_asset = None
            if not zip_asset:
                for asset in assets:
                    name = asset.get('name', '').lower()
                    if name.endswith('.exe'):
                        exe_asset = asset
                        break

            chosen = zip_asset or exe_asset
            if chosen:
                filetype = 'zip' if zip_asset else 'exe'
                return {
                    'version': data['tag_name'],
                    'name': data.get('name') or data['tag_name'],
                    'body': data.get('body', ''),
                    'download_url': chosen['browser_download_url'],
                    'filename': chosen['name'],
                    'size': chosen.get('size', 0),
                    'filetype': filetype
        }

    
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
        
        
        self._pending_update_info = update_info
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
        info = getattr(self, "_pending_update_info", None)
        filetype = (info or {}).get("filetype", "exe")
        new_version_tag = (info or {}).get("version", "v0.0.0")
        new_version = new_version_tag.strip().lstrip('vV')

        try:
            if filetype == "zip":
                # --- INSTALACIÓN POR CARPETA (ZIP ONEDIR) ---
                exe_path = Path(sys.executable)
                install_dir = exe_path.parent  # carpeta ONEDIR actual
                temp_dir = Path(tempfile.gettempdir()) / __app_name__ / f"upd_{new_version}"
                extract_dir = temp_dir / "unzip"
                extract_dir.mkdir(parents=True, exist_ok=True)

                # Descomprimir ZIP
                with zipfile.ZipFile(download_path, 'r') as zf:
                    zf.extractall(extract_dir)

                # El ZIP contiene directamente los archivos ONEDIR (exe, dlls, etc.)
                # Preparamos script que MIRROREA con ROBOCOPY y relanza.
                expected_new_exe = install_dir / f"{__app_name__}-v{new_version}.exe"
                update_script = self._create_update_script_dir(
                    source_dir=str(extract_dir),
                    dest_dir=str(install_dir),
                    relaunch_exe=str(expected_new_exe)
                )

                QMessageBox.information(
                    self.parent,
                    "Descarga completada",
                    "Se instalará la actualización y se relanzará la aplicación."
                )

                # Ejecutar script y salir
                if sys.platform == 'win32':
                    subprocess.Popen(['cmd', '/c', update_script], creationflags=subprocess.CREATE_NO_WINDOW)
                else:
                    subprocess.Popen(['sh', update_script])

                sys.exit(0)

            else:
                # --- Fallback EXE (comportamiento original de reemplazo de archivo) ---
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
                    subprocess.Popen(['cmd', '/c', update_script], creationflags=subprocess.CREATE_NO_WINDOW)
                else:
                    subprocess.Popen(['sh', update_script])

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
    
    def _create_update_script_dir(self, source_dir: str, dest_dir: str, relaunch_exe: str) -> str:
        """
        Crea un script para actualizar la carpeta ONEDIR completa (ROBOCOPY /MIR) y relanzar.
        """
        temp_dir = Path(tempfile.gettempdir()) / __app_name__
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