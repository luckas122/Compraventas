# pyi_rth_bootstrap.py
import os
import sys
import shutil
from pathlib import Path

APP_NAME = "TuLocalV12025"

def get_resource_path(relative_path):
    """Obtiene la ruta correcta para recursos empaquetados."""
    if getattr(sys, 'frozen', False):
        # Si está congelado, buscar en _MEIPASS (onefile) o carpeta del exe (onedir)
        if hasattr(sys, '_MEIPASS'):
            # Modo ONEFILE
            base_path = Path(sys._MEIPASS)
        else:
            # Modo ONEDIR
            base_path = Path(sys.executable).parent
    else:
        # Modo desarrollo
        base_path = Path(__file__).resolve().parent
    
    return base_path / relative_path

# Establecer directorio base
if getattr(sys, 'frozen', False):
    if hasattr(sys, '_MEIPASS'):
        # ONEFILE: trabajar desde carpeta temporal
        BASE = Path(sys._MEIPASS)
        EXE_DIR = Path(sys.executable).parent
    else:
        # ONEDIR: trabajar desde carpeta del exe
        BASE = Path(sys.executable).parent
        EXE_DIR = BASE
else:
    BASE = Path(__file__).resolve().parent
    EXE_DIR = BASE

# Cambiar al directorio del ejecutable (importante para rutas relativas)
os.chdir(EXE_DIR)

# 1) Configurar QT_PLUGIN_PATH para plugins de Qt
plugin_candidates = [
    BASE / "PyQt5" / "Qt" / "plugins",
    BASE / "PyQt5" / "Qt5" / "plugins",
    BASE / "_internal" / "PyQt5" / "Qt" / "plugins",
    EXE_DIR / "PyQt5" / "Qt" / "plugins",
]

for plugin_path in plugin_candidates:
    if plugin_path.exists() and plugin_path.is_dir():
        os.environ.setdefault("QT_PLUGIN_PATH", str(plugin_path))
        break

# 2) En ONEFILE, copiar recursos críticos al directorio del exe si es necesario
if hasattr(sys, '_MEIPASS') and getattr(sys, 'frozen', False):
    # Copiar assets e icons si no existen en la carpeta del exe
    for resource_dir in ['assets', 'icons']:
        src = BASE / resource_dir
        dst = EXE_DIR / resource_dir
        if src.exists() and not dst.exists():
            try:
                if src.is_dir():
                    shutil.copytree(src, dst, dirs_exist_ok=True)
            except Exception as e:
                pass  # Silencioso en producción

# 3) Manejar base de datos - copiar a APPDATA si no existe
def get_appdata_dir() -> Path:
    """Obtiene el directorio de datos de aplicación."""
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "CompraventasV2"
    return Path.home() / ".compraventasv2"

# Buscar DB semilla
db_candidates = [
    BASE / "db",
    BASE / "_internal" / "db",
    EXE_DIR / "db",
]

seed_db = None
for db_dir in db_candidates:
    if db_dir.exists() and db_dir.is_dir():
        # Buscar appcomprasventas.db o cualquier .db
        db_files = list(db_dir.glob("appcomprasventas.db"))
        if not db_files:
            db_files = list(db_dir.glob("*.db"))
        if db_files:
            seed_db = db_files[0]
            break

if seed_db and seed_db.exists():
    target_dir = get_appdata_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    target_db = target_dir / "appcomprasventas.db"
    
    if not target_db.exists():
        try:
            shutil.copy2(seed_db, target_db)
        except Exception:
            pass
    
    # Establecer variable de entorno
    os.environ.setdefault("TULOCAL_DB_PATH", str(target_db))

# 4) Log de diagnóstico
try:
    log_file = EXE_DIR / "startup.log"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"\n{'='*60}\n")
        f.write(f"Fecha: {__import__('datetime').datetime.now()}\n")
        f.write(f"Frozen: {getattr(sys, 'frozen', False)}\n")
        f.write(f"_MEIPASS: {getattr(sys, '_MEIPASS', 'N/A')}\n")
        f.write(f"EXE: {sys.executable}\n")
        f.write(f"CWD: {os.getcwd()}\n")
        f.write(f"BASE: {BASE}\n")
        f.write(f"EXE_DIR: {EXE_DIR}\n")
        f.write(f"Assets exists: {(BASE / 'assets').exists()}\n")
        f.write(f"Icons exists: {(BASE / 'icons').exists()}\n")
        f.write(f"QT_PLUGIN_PATH: {os.environ.get('QT_PLUGIN_PATH', 'N/A')}\n")
        f.write(f"TULOCAL_DB_PATH: {os.environ.get('TULOCAL_DB_PATH', 'N/A')}\n")
except Exception:
    pass

# 5) Añadir función helper global para que tu código la use
sys.get_resource_path = get_resource_path