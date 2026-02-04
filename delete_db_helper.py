"""
Script helper para eliminar la base de datos y reiniciar la aplicación.
Este script se ejecuta DESPUÉS de que la aplicación principal se cierra.
"""
import sys
import os
import time
import subprocess
from pathlib import Path


def main():
    if len(sys.argv) < 3:
        print("Uso: delete_db_helper.py <db_path> <main_script_or_exe>")
        sys.exit(1)

    db_path = sys.argv[1]
    app_path = sys.argv[2]

    print(f"[DELETE_DB_HELPER] Esperando a que la aplicación se cierre...")
    # Esperar un poco para asegurar que la aplicación se cerró completamente
    time.sleep(2)

    # Intentar eliminar la base de datos
    print(f"[DELETE_DB_HELPER] Eliminando base de datos: {db_path}")
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
            print(f"[DELETE_DB_HELPER] ✓ Base de datos eliminada exitosamente")
        else:
            print(f"[DELETE_DB_HELPER] ⚠ La base de datos no existe en: {db_path}")
    except Exception as e:
        print(f"[DELETE_DB_HELPER] ✗ Error al eliminar la base de datos: {e}")
        input("Presione Enter para salir...")
        sys.exit(1)

    # Reiniciar la aplicación
    print(f"[DELETE_DB_HELPER] Reiniciando aplicación: {app_path}")
    try:
        if app_path.endswith('.exe'):
            # Ejecutable
            subprocess.Popen([app_path], cwd=str(Path(app_path).parent))
        else:
            # Script Python - necesita el directorio del script para imports
            app_dir = str(Path(app_path).parent)
            # En Windows, crear nuevo proceso sin consola visible
            if os.name == 'nt':
                subprocess.Popen(
                    [sys.executable, app_path],
                    cwd=app_dir,
                    creationflags=subprocess.CREATE_NEW_CONSOLE
                )
            else:
                subprocess.Popen([sys.executable, app_path], cwd=app_dir)
        print(f"[DELETE_DB_HELPER] ✓ Aplicación reiniciada")
    except Exception as e:
        print(f"[DELETE_DB_HELPER] ✗ Error al reiniciar la aplicación: {e}")
        import traceback
        traceback.print_exc()
        input("Presione Enter para salir...")
        sys.exit(1)


if __name__ == "__main__":
    main()
