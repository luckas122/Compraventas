# app/database.py
import os, sys
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from app.models import Base

APP_DIRNAME = "CompraventasV2"
DB_FILENAME = "appcomprasventas.db"

def _user_data_dir() -> Path:
    """
    Retorna la carpeta donde se guarda la DB en modo frozen.
    Si la app se instaló en %LOCALAPPDATA%\Compraventas\app\, usa esa misma carpeta.
    Sino, usa %APPDATA%\CompraventasV2 (legacy).
    """
    if getattr(sys, "frozen", False):
        # En frozen, intentar usar la misma carpeta donde está el ejecutable
        exe_parent = Path(sys.executable).parent

        # Verificar si estamos en la estructura esperada (%LOCALAPPDATA%\Compraventas\app\)
        localappdata = os.environ.get("LOCALAPPDATA")
        if localappdata and "Compraventas" in str(exe_parent):
            # Migración automática: copiar DB de ubicación legacy si existe
            new_db_path = exe_parent / DB_FILENAME
            appdata = os.environ.get("APPDATA")
            if appdata:
                legacy_db_path = Path(appdata) / APP_DIRNAME / DB_FILENAME

                # Si no existe DB en nueva ubicación pero sí en legacy, copiar
                if not new_db_path.exists() and legacy_db_path.exists():
                    try:
                        import shutil
                        shutil.copy2(legacy_db_path, new_db_path)
                        print(f"[DB MIGRATION] Migrada DB de {legacy_db_path} a {new_db_path}")
                    except Exception as e:
                        print(f"[DB MIGRATION] Error al migrar DB: {e}")

            # Usar la misma carpeta del ejecutable
            return exe_parent

    # Fallback: usar %APPDATA%\CompraventasV2 (legacy)
    appdata = os.environ.get("APPDATA")
    if appdata:
        base = Path(appdata) / APP_DIRNAME
    else:
        base = Path.home() / f".{APP_DIRNAME.lower()}"
    base.mkdir(parents=True, exist_ok=True)
    return base

def _dev_root_dir() -> Path:
    # Carpeta raíz del proyecto cuando NO está frozen
    # .../app/database.py -> .parent -> /app -> .parent -> /<root>
    return Path(__file__).resolve().parent.parent

def _db_path() -> Path:
    if getattr(sys, "frozen", False):
        # Ejecutable PyInstaller -> usar %APPDATA%\CompraventasV2
        return _user_data_dir() / DB_FILENAME
    else:
        # Desarrollo -> mantener BD en la raíz del proyecto (como tenías)
        return _dev_root_dir() / DB_FILENAME

DB_PATH = _db_path()

# Construir URL sqlite compatible
DB_URL = f"sqlite:///{DB_PATH.as_posix()}"

engine = create_engine(
    DB_URL,
    echo=False,
    connect_args={'check_same_thread': False}
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

@event.listens_for(engine, 'connect')
def _set_pragmas(dbapi_connection, connection_record):
    cur = dbapi_connection.cursor()
    try:
        cur.execute('PRAGMA journal_mode=WAL;')
        cur.execute('PRAGMA synchronous=NORMAL;')
        cur.execute('PRAGMA temp_store=MEMORY;')
        cur.execute('PRAGMA cache_size=-64000;')
    finally:
        cur.close()

def init_db():
    # Si la BD no existe, se crea con las tablas al vuelo
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
