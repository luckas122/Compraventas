"""
Módulo para gestionar la eliminación de la base de datos y reinicio de la aplicación.
Este módulo puede ejecutarse tanto como script independiente como módulo importado.
"""
import os
import sys
import time
import subprocess
from pathlib import Path


def delete_and_restart(db_path: str, app_path: str):
    """
    Elimina la base de datos y reinicia la aplicación.

    Args:
        db_path: Ruta completa a la base de datos
        app_path: Ruta completa al ejecutable o script principal
    """
    print(f"[DELETE_DB_MANAGER] Esperando a que la aplicación se cierre...")
    # Esperar un poco para asegurar que la aplicación se cerró completamente
    time.sleep(2)

    # Intentar eliminar la base de datos
    print(f"[DELETE_DB_MANAGER] Eliminando base de datos: {db_path}")
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
            print(f"[DELETE_DB_MANAGER] ✓ Base de datos eliminada exitosamente")
        else:
            print(f"[DELETE_DB_MANAGER] ⚠ La base de datos no existe en: {db_path}")
    except Exception as e:
        print(f"[DELETE_DB_MANAGER] ✗ Error al eliminar la base de datos: {e}")
        return False

    # Reiniciar la aplicación
    print(f"[DELETE_DB_MANAGER] Reiniciando aplicación: {app_path}")
    try:
        if app_path.endswith('.exe'):
            # Ejecutable
            subprocess.Popen([app_path], cwd=str(Path(app_path).parent))
        else:
            # Script Python - necesita el directorio del script para imports
            app_dir = str(Path(app_path).parent)
            # En Windows, crear nuevo proceso con consola nueva
            if os.name == 'nt':
                subprocess.Popen(
                    [sys.executable, app_path],
                    cwd=app_dir,
                    creationflags=subprocess.CREATE_NEW_CONSOLE
                )
            else:
                subprocess.Popen([sys.executable, app_path], cwd=app_dir)
        print(f"[DELETE_DB_MANAGER] ✓ Aplicación reiniciada")
        return True
    except Exception as e:
        print(f"[DELETE_DB_MANAGER] ✗ Error al reiniciar la aplicación: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Punto de entrada cuando se ejecuta como script independiente."""
    if len(sys.argv) < 3:
        print("Uso: python -m app.delete_db_manager <db_path> <main_script_or_exe>")
        sys.exit(1)

    db_path = sys.argv[1]
    app_path = sys.argv[2]

    success = delete_and_restart(db_path, app_path)

    if not success:
        input("Presione Enter para salir...")
        sys.exit(1)


if __name__ == "__main__":
    main()
