"""
Runtime hook para copiar delete_db_and_restart.bat desde _internal/ a la raíz del directorio.
PyInstaller copia los 'datas' a _internal/, pero necesitamos el .bat en la raíz.
"""
import sys
import os
from pathlib import Path

if getattr(sys, 'frozen', False):
    # Estamos en modo frozen (ejecutable)
    exe_dir = Path(sys.executable).parent
    internal_dir = exe_dir / "_internal"

    # Archivo fuente (dentro de _internal)
    bat_source = internal_dir / "delete_db_and_restart.bat"

    # Archivo destino (raíz del directorio)
    bat_dest = exe_dir / "delete_db_and_restart.bat"

    # Si el .bat existe en _internal pero no en la raíz, copiarlo
    if bat_source.exists() and not bat_dest.exists():
        try:
            import shutil
            shutil.copy2(str(bat_source), str(bat_dest))
            print(f"[RUNTIME HOOK] Copiado {bat_source.name} a la raíz del directorio")
        except Exception as e:
            print(f"[RUNTIME HOOK] Error al copiar {bat_source.name}: {e}")
