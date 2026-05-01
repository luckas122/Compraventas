# sync_version_files.py
# -*- coding: utf-8 -*-
"""
Sincroniza version_info.txt e installer.iss desde version.py (single source of truth).

Llamado por build.bat antes de compilar:
    python sync_version_files.py

Lee app_name y version desde version.py y reescribe:
    - version_info.txt  -> "{app_name} v{version}\n"
    - installer.iss     -> reemplaza la línea `#define MyAppVersion "X.Y.Z"`

Es idempotente: si los archivos ya tienen la versión correcta, no toca nada.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))


def main() -> int:
    # 1) Leer fuente de verdad
    sys.path.insert(0, ROOT)
    try:
        from version import __version__, __app_name__
    except ImportError as e:
        print(f"[sync_version] ERROR: no se pudo importar version.py: {e}", file=sys.stderr)
        return 1

    print(f"[sync_version] fuente: version.py -> {__app_name__} v{__version__}")

    # 2) Sincronizar version_info.txt
    vi_path = os.path.join(ROOT, "version_info.txt")
    expected_vi = f"{__app_name__} v{__version__}\n"
    try:
        current_vi = open(vi_path, "r", encoding="utf-8").read() if os.path.exists(vi_path) else ""
    except Exception:
        current_vi = ""
    if current_vi != expected_vi:
        with open(vi_path, "w", encoding="utf-8") as f:
            f.write(expected_vi)
        print(f"[sync_version] OK: version_info.txt actualizado")
    else:
        print(f"[sync_version] OK: version_info.txt ya estaba sincronizado")

    # 3) Sincronizar installer.iss
    iss_path = os.path.join(ROOT, "installer.iss")
    if not os.path.exists(iss_path):
        print(f"[sync_version] WARN: installer.iss no existe, salteando")
        return 0

    with open(iss_path, "r", encoding="utf-8") as f:
        iss_content = f.read()

    # Reemplazar `#define MyAppVersion "X.Y.Z"` por la versión actual
    pattern = re.compile(r'(#define\s+MyAppVersion\s+)"[^"]*"')
    new_content, n = pattern.subn(rf'\1"{__version__}"', iss_content)

    if n == 0:
        print(f"[sync_version] WARN: no se encontró '#define MyAppVersion' en installer.iss")
        return 0

    if new_content != iss_content:
        with open(iss_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"[sync_version] OK: installer.iss actualizado ({n} reemplazo)")
    else:
        print(f"[sync_version] OK: installer.iss ya estaba sincronizado")

    return 0


if __name__ == "__main__":
    sys.exit(main())
