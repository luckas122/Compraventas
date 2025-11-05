# app/database.py
import os, sys
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from app.models import Base

APP_DIRNAME = "CompraventasV2"
DB_FILENAME = "appcomprasventas.db"

def _user_data_dir() -> Path:
    # %APPDATA% (Roaming) en Windows; si no existe, cae a HOME/.CompraventasV2
    appdata = os.environ.get("APPDATA")
    if appdata:
        base = Path(appdata) / APP_DIRNAME
    else:
        base = Path.home() / f".{APP_DIRNAME.lower()}"
    base.mkdir(parents=True, exist_ok=True)
    return base

def _dev_root_dir() -> Path:
    # Carpeta raíz del proyecto cuando NO está frozen
    # .../app/database.py -> /app -> /<root>
    return Path(__file__).resolve().parent.parent.parent

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
