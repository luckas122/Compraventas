# app/database.py
import logging
import os, sys
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from app.models import Base

logger = logging.getLogger(__name__)

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
                        logger.info("[DB MIGRATION] Migrada DB de %s a %s", legacy_db_path, new_db_path)
                    except Exception as e:
                        logger.error("[DB MIGRATION] Error al migrar DB: %s", e)

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
        cur.execute('PRAGMA busy_timeout=15000;')  # esperar hasta 15s si DB está bloqueada
        cur.execute('PRAGMA synchronous=NORMAL;')
        cur.execute('PRAGMA temp_store=MEMORY;')
        cur.execute('PRAGMA cache_size=-64000;')
    finally:
        cur.close()

def _run_migrations():
    """Migraciones incrementales para actualizar esquema existente."""
    from sqlalchemy import inspect, text
    inspector = inspect(engine)

    with engine.connect() as conn:
        # Agregar last_modified a productos si no existe
        if "productos" in inspector.get_table_names():
            cols = [c["name"] for c in inspector.get_columns("productos")]
            if "last_modified" not in cols:
                conn.execute(text("ALTER TABLE productos ADD COLUMN last_modified DATETIME"))
                conn.execute(text("UPDATE productos SET last_modified = datetime('now')"))

        # Agregar last_modified a proveedores si no existe
        if "proveedores" in inspector.get_table_names():
            cols = [c["name"] for c in inspector.get_columns("proveedores")]
            if "last_modified" not in cols:
                conn.execute(text("ALTER TABLE proveedores ADD COLUMN last_modified DATETIME"))
                conn.execute(text("UPDATE proveedores SET last_modified = datetime('now')"))

        # Agregar afip_error a ventas si no existe
        if "ventas" in inspector.get_table_names():
            cols = [c["name"] for c in inspector.get_columns("ventas")]
            if "afip_error" not in cols:
                conn.execute(text("ALTER TABLE ventas ADD COLUMN afip_error VARCHAR"))

        # Agregar version a productos si no existe (optimistic locking v3.4.0)
        if "productos" in inspector.get_table_names():
            cols = [c["name"] for c in inspector.get_columns("productos")]
            if "version" not in cols:
                conn.execute(text("ALTER TABLE productos ADD COLUMN version INTEGER DEFAULT 1 NOT NULL"))

        # Eliminar tabla sync_log si existe (reemplazada por Firebase)
        if "sync_log" in inspector.get_table_names():
            conn.execute(text("DROP TABLE sync_log"))

        # Crear tabla pagos_proveedores si no existe (v3.7.0)
        if "pagos_proveedores" not in inspector.get_table_names():
            from app.models import PagoProveedor
            PagoProveedor.__table__.create(bind=engine)
        else:
            # Migración v6.5.0: agregar incluye_iva
            _pp_cols = conn.execute(text("PRAGMA table_info(pagos_proveedores)")).fetchall()
            _pp_names = [row[1] for row in _pp_cols]
            if "incluye_iva" not in _pp_names:
                conn.execute(text("ALTER TABLE pagos_proveedores ADD COLUMN incluye_iva BOOLEAN DEFAULT 0 NOT NULL"))

        # Crear tabla compradores si no existe (v5.5.0)
        if "compradores" not in inspector.get_table_names():
            from app.models import Comprador
            Comprador.__table__.create(bind=engine)

        # Agregar tipo_comprobante y campos nota de crédito a ventas
        if "ventas" in inspector.get_table_names():
            # Usar PRAGMA directa para evitar caché del inspector
            _pragma_cols = conn.execute(text("PRAGMA table_info(ventas)")).fetchall()
            cols = [row[1] for row in _pragma_cols]
            if "tipo_comprobante" not in cols:
                conn.execute(text("ALTER TABLE ventas ADD COLUMN tipo_comprobante VARCHAR"))
            if "cuit_cliente" not in cols:
                conn.execute(text("ALTER TABLE ventas ADD COLUMN cuit_cliente VARCHAR"))
            if "nombre_cliente" not in cols:
                conn.execute(text("ALTER TABLE ventas ADD COLUMN nombre_cliente VARCHAR"))
            if "domicilio_cliente" not in cols:
                conn.execute(text("ALTER TABLE ventas ADD COLUMN domicilio_cliente VARCHAR"))
            if "localidad_cliente" not in cols:
                conn.execute(text("ALTER TABLE ventas ADD COLUMN localidad_cliente VARCHAR"))
            if "nota_credito_cae" not in cols:
                conn.execute(text("ALTER TABLE ventas ADD COLUMN nota_credito_cae VARCHAR"))
            if "nota_credito_numero" not in cols:
                conn.execute(text("ALTER TABLE ventas ADD COLUMN nota_credito_numero INTEGER"))
            if "numero_ticket_cae" not in cols:
                conn.execute(text("ALTER TABLE ventas ADD COLUMN numero_ticket_cae INTEGER"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ventas_numero_ticket_cae ON ventas (numero_ticket_cae)"))
            if "vendedor" not in cols:
                conn.execute(text("ALTER TABLE ventas ADD COLUMN vendedor VARCHAR"))
            if "codigo_postal_cliente" not in cols:
                conn.execute(text("ALTER TABLE ventas ADD COLUMN codigo_postal_cliente VARCHAR"))
            if "condicion_cliente" not in cols:
                conn.execute(text("ALTER TABLE ventas ADD COLUMN condicion_cliente VARCHAR"))

        # Quitar UNIQUE constraint de numero_ticket en ventas (v5.1.0)
        # Cada sucursal tiene su propia secuencia de tickets.
        # SQLite no permite ALTER TABLE DROP CONSTRAINT, hay que recrear la tabla.
        if "ventas" in inspector.get_table_names():
            # Detectar si numero_ticket tiene UNIQUE en la definición de la tabla
            table_sql = conn.execute(text(
                "SELECT sql FROM sqlite_master WHERE tbl_name='ventas' AND type='table'"
            )).scalar() or ""
            _ts_upper = table_sql.upper()

            # Buscar "numero_ticket ... UNIQUE" en la definición de columna
            needs_rebuild = False
            if "NUMERO_TICKET" in _ts_upper:
                # Extraer la línea de numero_ticket del CREATE TABLE
                for line in table_sql.split(","):
                    _lu = line.upper().strip()
                    if "NUMERO_TICKET" in _lu and "UNIQUE" in _lu:
                        needs_rebuild = True
                        break

            if not needs_rebuild:
                # Verificar también índices explícitos UNIQUE
                idx_rows = conn.execute(text(
                    "SELECT name, sql FROM sqlite_master "
                    "WHERE tbl_name='ventas' AND type='index' AND sql IS NOT NULL"
                )).fetchall()
                for row in idx_rows:
                    idx_sql = (row[1] or "").upper()
                    if "UNIQUE" in idx_sql and "NUMERO_TICKET" in idx_sql:
                        # Drop the explicit index
                        try:
                            conn.execute(text(f'DROP INDEX IF EXISTS "{row[0]}"'))
                        except Exception:
                            pass

            if needs_rebuild:
                logger.info("[MIGRATION] Recreando tabla ventas para quitar UNIQUE de numero_ticket...")
                conn.execute(text("PRAGMA foreign_keys = OFF"))

                # 1) Obtener columnas actuales de la tabla vieja
                old_cols = [c["name"] for c in inspector.get_columns("ventas")]

                # 2) Renombrar tabla original
                conn.execute(text("ALTER TABLE ventas RENAME TO _ventas_old"))

                # 3) Crear nueva tabla SIN UNIQUE en numero_ticket (SQL puro)
                conn.execute(text("""
                    CREATE TABLE ventas (
                        id INTEGER NOT NULL PRIMARY KEY,
                        sucursal VARCHAR NOT NULL,
                        fecha DATETIME NOT NULL,
                        modo_pago VARCHAR NOT NULL,
                        cuotas INTEGER,
                        total FLOAT NOT NULL,
                        subtotal_base FLOAT NOT NULL DEFAULT 0.0,
                        interes_pct FLOAT NOT NULL DEFAULT 0.0,
                        interes_monto FLOAT NOT NULL DEFAULT 0.0,
                        descuento_pct FLOAT NOT NULL DEFAULT 0.0,
                        descuento_monto FLOAT NOT NULL DEFAULT 0.0,
                        pagado FLOAT,
                        vuelto FLOAT,
                        numero_ticket INTEGER NOT NULL,
                        afip_cae VARCHAR,
                        afip_cae_vencimiento VARCHAR,
                        afip_numero_comprobante INTEGER,
                        afip_error VARCHAR,
                        tipo_comprobante VARCHAR,
                        cuit_cliente VARCHAR,
                        nombre_cliente VARCHAR,
                        domicilio_cliente VARCHAR,
                        localidad_cliente VARCHAR,
                        nota_credito_cae VARCHAR,
                        nota_credito_numero INTEGER
                    )
                """))

                # 4) Copiar datos (solo columnas que existen en la nueva tabla)
                new_cols = ["id", "sucursal", "fecha", "modo_pago", "cuotas", "total",
                            "subtotal_base", "interes_pct", "interes_monto",
                            "descuento_pct", "descuento_monto", "pagado", "vuelto",
                            "numero_ticket", "afip_cae", "afip_cae_vencimiento",
                            "afip_numero_comprobante", "afip_error", "tipo_comprobante",
                            "cuit_cliente", "nombre_cliente", "domicilio_cliente",
                            "localidad_cliente", "nota_credito_cae", "nota_credito_numero"]
                common = [c for c in new_cols if c in old_cols]
                cols_csv = ", ".join(common)
                conn.execute(text(f"INSERT INTO ventas ({cols_csv}) SELECT {cols_csv} FROM _ventas_old"))

                # 5) Eliminar tabla vieja
                conn.execute(text("DROP TABLE _ventas_old"))

                # 6) Recrear índices
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ventas_numero_ticket ON ventas (numero_ticket)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ventas_sucursal_fecha ON ventas (sucursal, fecha)"))

                conn.execute(text("PRAGMA foreign_keys = ON"))
                logger.info("[MIGRATION] Tabla ventas recreada exitosamente sin UNIQUE en numero_ticket")
            else:
                # Solo asegurar que existe el índice no-unique
                try:
                    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ventas_numero_ticket ON ventas (numero_ticket)"))
                except Exception:
                    pass

        # ─────────────────────────────────────────────────────────────────
        # v6.9.5: numero_ticket NOT NULL → nullable.
        # Las ventas tarjeta+CAE de OTRAS sucursales tienen numero_ticket=null,
        # numero_ticket_cae=N. Al pull-ear, el INSERT fallaba por NOT NULL y se
        # tragaba el error en silencio (rollback en _apply_venta).
        # SQLite no permite ALTER COLUMN, asi que detectamos el NOT NULL
        # haciendo INSERT de prueba con NULL; si falla, recreamos la tabla.
        # ─────────────────────────────────────────────────────────────────
        if "ventas" in inspector.get_table_names():
            _ventas_pragma = conn.execute(text("PRAGMA table_info(ventas)")).fetchall()
            # Cada row: (cid, name, type, notnull, dflt_value, pk)
            _nt_row = next((r for r in _ventas_pragma if r[1] == "numero_ticket"), None)
            if _nt_row and _nt_row[3] == 1:  # notnull == 1
                logger.info("[MIGRATION v6.9.5] Recreando tabla ventas para hacer numero_ticket NULLABLE...")
                conn.execute(text("PRAGMA foreign_keys = OFF"))
                old_cols = [c["name"] for c in inspector.get_columns("ventas")]
                conn.execute(text("ALTER TABLE ventas RENAME TO _ventas_old_v695"))
                conn.execute(text("""
                    CREATE TABLE ventas (
                        id INTEGER NOT NULL PRIMARY KEY,
                        sucursal VARCHAR NOT NULL,
                        fecha DATETIME NOT NULL,
                        modo_pago VARCHAR NOT NULL,
                        cuotas INTEGER,
                        total FLOAT NOT NULL,
                        subtotal_base FLOAT NOT NULL DEFAULT 0.0,
                        interes_pct FLOAT NOT NULL DEFAULT 0.0,
                        interes_monto FLOAT NOT NULL DEFAULT 0.0,
                        descuento_pct FLOAT NOT NULL DEFAULT 0.0,
                        descuento_monto FLOAT NOT NULL DEFAULT 0.0,
                        pagado FLOAT,
                        vuelto FLOAT,
                        numero_ticket INTEGER,
                        numero_ticket_cae INTEGER,
                        afip_cae VARCHAR,
                        afip_cae_vencimiento VARCHAR,
                        afip_numero_comprobante INTEGER,
                        afip_error VARCHAR,
                        tipo_comprobante VARCHAR,
                        cuit_cliente VARCHAR,
                        nombre_cliente VARCHAR,
                        domicilio_cliente VARCHAR,
                        localidad_cliente VARCHAR,
                        codigo_postal_cliente VARCHAR,
                        condicion_cliente VARCHAR,
                        vendedor VARCHAR,
                        nota_credito_cae VARCHAR,
                        nota_credito_numero INTEGER
                    )
                """))
                new_cols_v695 = [
                    "id", "sucursal", "fecha", "modo_pago", "cuotas", "total",
                    "subtotal_base", "interes_pct", "interes_monto",
                    "descuento_pct", "descuento_monto", "pagado", "vuelto",
                    "numero_ticket", "numero_ticket_cae",
                    "afip_cae", "afip_cae_vencimiento", "afip_numero_comprobante",
                    "afip_error", "tipo_comprobante",
                    "cuit_cliente", "nombre_cliente", "domicilio_cliente",
                    "localidad_cliente", "codigo_postal_cliente", "condicion_cliente",
                    "vendedor", "nota_credito_cae", "nota_credito_numero",
                ]
                common = [c for c in new_cols_v695 if c in old_cols]
                cols_csv = ", ".join(common)
                conn.execute(text(f"INSERT INTO ventas ({cols_csv}) SELECT {cols_csv} FROM _ventas_old_v695"))
                conn.execute(text("DROP TABLE _ventas_old_v695"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ventas_numero_ticket ON ventas (numero_ticket)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ventas_numero_ticket_cae ON ventas (numero_ticket_cae)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ventas_sucursal_fecha ON ventas (sucursal, fecha)"))
                conn.execute(text("PRAGMA foreign_keys = ON"))
                logger.info("[MIGRATION v6.9.5] OK: numero_ticket ahora es NULLABLE")

        conn.commit()


def init_db():
    # Si la BD no existe, se crea con las tablas al vuelo
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    _run_migrations()
