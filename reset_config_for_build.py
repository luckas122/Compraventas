# reset_config_for_build.py
"""
Deja app/app_config.json en estado 'de fábrica' usando DEFAULTS de app.config
y limpia logs + backups antes del build.

Se ejecuta desde build.bat antes de llamar a PyInstaller.
"""

import os
import json
import shutil

from app.config import CONFIG_PATH, DEFAULTS


BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def reset_config():
    base_dir = os.path.dirname(CONFIG_PATH) or "."
    os.makedirs(base_dir, exist_ok=True)

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(DEFAULTS, f, ensure_ascii=False, indent=2)

    print(f"[reset_config_for_build] app_config.json regenerado en: {CONFIG_PATH}")


def clean_logs_and_backups():
    # 1) Limpiar archivos de logs (pero dejando la carpeta)
    logs_dir = os.path.join(BASE_DIR, "logs")
    if os.path.isdir(logs_dir):
        removed_logs = []
        for name in os.listdir(logs_dir):
            path = os.path.join(logs_dir, name)
            if os.path.isfile(path):
                try:
                    os.remove(path)
                    removed_logs.append(path)
                except Exception as e:
                    print(f"[reset_config_for_build] No se pudo borrar log {path}: {e}")
        if removed_logs:
            print("[reset_config_for_build] Logs eliminados:")
            for p in removed_logs:
                print(f"  - {p}")
        else:
            print("[reset_config_for_build] No se encontraron logs para borrar en 'logs/'")
    else:
        print("[reset_config_for_build] Carpeta 'logs/' no existe, nada que borrar.")

    # 2) Borrar carpetas de backups si existen
    backup_dirs = [
        os.path.join(BASE_DIR, "backups"),
        os.path.join(BASE_DIR, "backup"),
        os.path.join(BASE_DIR, "db_backups"),
    ]

    removed_dirs = []
    for d in backup_dirs:
        if os.path.isdir(d):
            try:
                shutil.rmtree(d)
                removed_dirs.append(d)
            except Exception as e:
                print(f"[reset_config_for_build] No se pudo borrar backup {d}: {e}")

    if removed_dirs:
        print("[reset_config_for_build] Carpetas de backup eliminadas:")
        for d in removed_dirs:
            print(f"  - {d}")
    else:
        print("[reset_config_for_build] No se encontraron carpetas de backup para borrar.")


def main():
    reset_config()
    clean_logs_and_backups()


if __name__ == "__main__":
    main()
