# app/config.py
# -*- coding: utf-8 -*-
"""
Gestión de configuración de la aplicación.
- Lee y escribe app_config.json junto a este archivo.
- Completa claves faltantes con DEFAULTS sin pisar lo que el usuario ya guardó.
- API estable usada en el resto de la app: load(), save(cfg)
"""

import json
import os
import copy
from typing import Any, Dict

APP_DIRNAME = "CompraventasV2"
CONFIG_FILENAME = "app_config.json"
RESTORE_MARKER_FILENAME = "config_restore.marker"

def _get_app_data_dir() -> str:
    """Retorna la carpeta persistente de datos (AppData)."""
    base = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA")
    if base:
        path = os.path.join(base, APP_DIRNAME)
    else:
        path = os.path.join(os.path.expanduser("~"), f".{APP_DIRNAME.lower()}")
    os.makedirs(path, exist_ok=True)
    return path

def _get_log_dir() -> str:
    """Carpeta persistente para logs."""
    log_dir = os.path.join(_get_app_data_dir(), "logs")
    os.makedirs(log_dir, exist_ok=True)
    return log_dir

def _get_restore_marker_path() -> str:
    return os.path.join(_get_app_data_dir(), RESTORE_MARKER_FILENAME)

def _write_restore_marker(src_path: str) -> None:
    try:
        data = {"path": src_path, "mtime": os.path.getmtime(src_path)}
        marker_path = _get_restore_marker_path()
        with open(marker_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception as e:
        _log_config(f"No se pudo escribir marker de restore: {e}")

def _is_same_backup_restored(src_path: str) -> bool:
    try:
        marker_path = _get_restore_marker_path()
        if not os.path.exists(marker_path):
            return False
        with open(marker_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("path") == src_path and data.get("mtime") == os.path.getmtime(src_path)
    except Exception:
        return False

# Función de logging a archivo (para debug en modo frozen)
def _log_config(msg: str):
    """Escribe logs tanto a consola como a archivo para debugging."""
    import sys
    from datetime import datetime

    # Print a consola (util en desarrollo)
    print(msg)

    # Tambien escribir a archivo (util en modo frozen)
    try:
        log_dir = _get_log_dir()
        log_file = os.path.join(log_dir, "config_restore.log")
        with open(log_file, "a", encoding="utf-8") as f:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{timestamp}] {msg}\n")
    except:
        pass  # Silenciar errores de logging

# Ruta del archivo JSON de configuracion
def _get_legacy_config_path() -> str:
    """Ubicacion legacy del config dentro de la instalacion."""
    import sys
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
        return os.path.join(base, '_internal', 'app', CONFIG_FILENAME)
    return os.path.join(os.path.dirname(__file__), CONFIG_FILENAME)

def _get_config_path() -> str:
    """Obtiene la ruta correcta del config tanto en desarrollo como frozen."""
    import sys
    if getattr(sys, 'frozen', False):
        return os.path.join(_get_app_data_dir(), CONFIG_FILENAME)
    return os.path.join(os.path.dirname(__file__), CONFIG_FILENAME)

CONFIG_PATH = _get_config_path()

def _migrate_legacy_config() -> None:
    """Copia el config legacy a AppData si hace falta."""
    import sys
    import shutil
    if not getattr(sys, 'frozen', False):
        return
    if os.path.exists(CONFIG_PATH):
        return
    legacy_path = _get_legacy_config_path()
    if os.path.exists(legacy_path):
        try:
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
            shutil.copy2(legacy_path, CONFIG_PATH)
            _log_config(f"Migrado config legacy: {legacy_path} -> {CONFIG_PATH}")
        except Exception as e:
            _log_config(f"Error migrando config legacy: {e}")



# -------------------- DEFAULTS --------------------
# Estos valores sirven como base; cualquier clave faltante en el JSON
# será completada con estos valores sin sobrescribir las ya existentes.
DEFAULTS: Dict[str, Any] = {
    "business": {
        "nombre": "Mi Negocio",
        "cuit": "00-00000000-0",
        "iva_responsable": "Consumidor Final",
        "telefono": "+54 11 0000-0000",
        "sucursales": {
            "Sarmiento": "Pte. Sarmiento 1695, Gerli",
            "Salta": "Salta 1694, Gerli"
        }
    },

    "general": {
        "timezone": "America/Argentina/Buenos_Aires",
        "default_send_time": "20:30",# HH:MM
        # Si está en True: al cerrar con la X, la ventana se oculta y la app queda en la bandeja
        "minimize_to_tray_on_close": True
    },
    
    

    "shortcuts": {
        "global": {
            "productos": "F1",
            "proveedores": "F2",
            "ventas": "F3",
            "historial": "F4",
            "configuraciones": "F5",
            "usuarios": "F6"
        },
        "section": {
            "productos": {"agregar": "A", "editar": "E", "eliminar": "Delete", "imprimir_codigo": "I"},
            "ventas": {"finalizar": "V", "efectivo": "E", "tarjeta": "T", "devolucion": "D", "whatsapp": "W", "imprimir": "F"}
        },
        "section_mode_enabled": True
    },

    # TEMA
    "theme": {
        "dark_mode": False,
        "dark_variant": "soft",

        # Paleta oscuro (gris amigable, nada de negro puro)
        "background":  "#2B2D31",   # fondo principal
        "panel_bg":    "#32343A",   # paneles / groupboxes / áreas elevadas
        "tab_bg":      "#3A3D44",   # tabs
        "border":      "#4A4D55",
        "accent_title":"#9CC4FF",   # títulos
        "accent_text": "#ECEFF1",   # texto (alto contraste)
        "muted_text":  "#BFC5CF",   # texto secundario

        # Paleta claro
        "light_background": "#F5F6F8",
        "light_panel_bg":   "#FFFFFF",
        "light_tab_bg":     "#ECEFF1",
        "light_border":     "#D0D4DB",
        "light_title":      "#4F6B95",
        "light_text":       "#222222",

        # Tipografía base
        "font_family": "Roboto",
        "font_size": 10  # puntos
    },

    # IMPRESORAS
    "printers": {
        "ticket_printer": None,   # nombre lógico de la impresora de tickets
        "barcode_printer": None   # impresora para códigos/etiquetas
    },

    # TICKET
    # Parámetros para el render del ticket
    "ticket": {
        "paper": {
            "width_mm": 80,         # ancho térmico típico
            "height_mm": 200,       # alto por defecto (si no es dinámico)
            "dynamic_height": True  # si True, el alto se ajusta al contenido
        },
        "margins_mm": 12,           # margen en mm aplicado en el dibujado
        "fonts": {
            "title_px": 18,         # tamaño título en píxeles
            "head_px": 12,          # cabecera
            "text_px": 11,          # cuerpo
            "total_px": 20          # total grande (verde)
        },
        "color": {
            "total_hex": "#2e7d32"
        },
        "show_interest_line": False,  # si mostrar "Interés: …" en el pie
        "slots": {
            "slot1": """{{centerb: SUSI PERFUMERÍA}}
{{center: ================================}}
{{b: TICKET DE VENTA}}
Nº: {{ticket.numero}}
Fecha: {{ticket.fecha_hora}}
Sucursal: {{sucursal}}
{{hr}}
{{items}}
{{hr}}
Subtotal: {{totales.subtotal}}
Descuento: {{totales.descuento}}
{{b: TOTAL: {{totales.total}}}}
{{hr}}
Forma de pago: {{pago.modo}}
Abonado: {{abonado}}
Vuelto: {{vuelto}}
{{cae}}
{{hr}}
{{center: ¡Gracias por su compra!}}""",
            "slot2": """{{centerb: SUSI PERFUMERÍA}}
{{hr}}
Ticket: {{ticket.numero}} | {{ticket.fecha_hora}}
{{sucursal}}
{{hr}}
{{items}}
{{hr}}
{{rightb: TOTAL: {{totales.total}}}}
{{hr}}
{{pago.modo}} | Abonado: {{abonado}} | Vuelto: {{vuelto}}
{{cae}}
{{center: Gracias por su compra}}""",
            "slot3": """{{centerb: SUSI PERFUMERÍA}}
{{center: ================================}}
{{b: TICKET DE VENTA}}
Nº: {{ticket.numero}}
Fecha: {{ticket.fecha_hora}}
Sucursal: {{sucursal}}
{{hr}}
{{items}}
{{hr}}
Subtotal: {{totales.subtotal}}
Descuento: {{totales.descuento}}
Interés: {{totales.interes}}
{{b: TOTAL: {{totales.total}}}}
{{hr}}
Forma de pago: {{pago.modo}}
Cuotas: {{pago.cuotas}} x {{pago.monto_cuota}}
{{cae}}
{{hr}}
{{center: ¡Gracias por su compra!}}""",
            "slot4": """{{centerb: SUSI PERFUMERÍA}}
{{hr}}
Ticket: {{ticket.numero}} | {{ticket.fecha_hora}}
{{sucursal}}
{{hr}}
{{items}}
{{hr}}
Interés: {{totales.interes}}
{{rightb: TOTAL: {{totales.total}}}}
{{hr}}
{{pago.modo}} - {{pago.cuotas}} cuotas de {{pago.monto_cuota}}
{{cae}}
{{center: Gracias por su compra}}"""
        },
        "slot_names": {
            "slot1": "Efectivo - Clásica",
            "slot2": "Efectivo - Minimalista",
            "slot3": "Tarjeta - Clásica",
            "slot4": "Tarjeta - Minimalista"
        },
        "template_efectivo": "slot1",
        "template_tarjeta": "slot3",
        "placeholders": [
            "{{ticket.numero}}", "{{ticket.fecha_hora}}", "{{sucursal}}",
            "{{cliente.nombre}}", "{{cliente.doc}}",
            "{{pago.modo}}", "{{pago.cuotas}}", "{{pago.monto_cuota}}",
            "{{totales.subtotal}}", "{{totales.descuento}}", "{{totales.interes}}", "{{totales.total}}",
            "{{abonado}}", "{{vuelto}}", "{{business}}", "{{title}}",
            "{{hr}}", "{{items}}", "{{cae}}"
        ]
    },

    # CÓDIGOS DE BARRAS / ETIQUETAS
    "barcode": {
        "width_cm": 5.0,            # ancho de etiqueta en cm
        "height_cm": 3.0,           # alto de etiqueta en cm (máx 8cm)
        "barcode_ratio": 0.75,      # 75% para código de barras
        "text_ratio": 0.25          # 25% para texto (nombre + código)
    },

    # BACKUP
    "backup": {
        "enabled": True,
        # Si es None -> usa ./backups (junto al proyecto)
        "dir": None,

        # Compatibilidad con distintas UIs:
        "times_daily": ["13:00", "20:00"],  # usado por algunas pantallas
        "daily_times": ["13:00", "20:00"],  # alias equivalente

        # 1..7 (Lunes=1 ... Domingo=7) y hora HH:MM
        "weekly": {
            "weekday": 7,        # Domingo
            "time": "23:30"
        },

        # Retención en dos formatos para compatibilidad
        "retention": {
            "daily_days": 30,
            "weekly_weeks": 26
        },
        "retention_days": {
            "daily": 30,
            "weekly": 180
        },

        # Compresión del ZIP
        "compress": {
            "format": "zip",
            "level": 9
        }
    },

    "export": {
        "default_dir": None,      # carpeta sugerida al exportar (si None, usa diálogo)
        "ticket_pdf": {
            "dpi": 203,           # 203 dpi usual térmica
            "abrir_al_finalizar": True
        }
    },

    "whatsapp": {
        "usar_web": True,         # usar WhatsApp Web (True) o app nativa si aplica
        "preguntar_antes": True,  # preguntar antes de abrir/enviar
        "formato_ticket": "pdf"   # "pdf" o "png"
    },

    # Configuración de correo para envíos de reportes
    "email": {
        "enabled": False,
        "sender": "ventas@tudominio.com",
        "recipients": ["dueno@tudominio.com"],
        "bcc": [],
        "subject_prefix": "[Historial]",
        "smtp": {
            "host": "smtp.tudominio.com",
            "port": 587,
            "use_tls": True,
            "username": "",
            "password": ""
        },
        "attach_format": "xlsx"   # por ahora sólo xlsx
    },


 # Facturación electrónica (AFIP / ARCA vía AfipSDK)
    "fiscal": {
        "enabled": False,          # Master switch
        "provider": "afipsdk",     # Por si más adelante usas otro proveedor
        "mode": "test",            # "test" o "prod"
        "only_card": True,         # Solo dispara AFIP cuando el pago es con tarjeta
        "cuit": "",                # CUIT del comercio (solo números o con guiones, como prefieras)
        "punto_venta": 1,          # Punto de venta AFIP
        "tipo_cbte": "FACTURA_B",  # Identificador interno para el tipo de comprobante

        "afipsdk": {
            "api_key": "",         # Token / API key de AfipSDK
            "base_url_test": "",   # URL base del entorno de pruebas (sandbox)
            "base_url_prod": ""    # URL base del entorno de producción
        }
    },


    # Preferencias generales
    "startup": {
        "default_sucursal": "ask"  # "ask" | "Sarmiento" | "Salta"
    },

    # Preferencias de reportes (Historial)
    "reports": {
        "historial": {
            "default_filters": {
                "sucursal": "*",       # "*", "Sarmiento", "Salta", etc.
                "forma_pago": "*",     # "*", "efectivo", "tarjeta"
                "desde": "hoy",
                "hasta": "hoy"
            },
            "auto_send": {
                "enabled": False,
                "freq": "Diario",   # "Diario" | "Semanal" | "Mensual"
                "time": "21:00",
                "last_sent": None
            },
            "export_content": {
                "daily":   ["ventas_diarias", "productos_mas_vendidos"],
                "weekly":  ["ventas_diarias", "resumen_semanal", "productos_mas_vendidos", "comparativa_2_semanas"],
                "monthly": ["ventas_por_dia", "resumen_semanal_del_mes", "productos_mas_vendidos", "comparativa_2_meses"]
            }
        }
    },

    "sync": {
        "enabled": False,
        "mode": "interval",
        "interval_minutes": 5,
        "firebase": {
            "database_url": "",
            "auth_token": ""
        },
        "sync_productos": True,
        "sync_proveedores": True,
        "last_sync": None,
        "last_processed_keys": {
            "ventas": None,
            "productos": None,
            "proveedores": None
        }
    }
}

# -------------------- MERGE --------------------
def _merge(existing: Dict[str, Any], defaults: Dict[str, Any]) -> Dict[str, Any]:
    """
    Completa en 'existing' las claves faltantes de 'defaults' sin pisar lo ya definido.
    Mezcla profunda para dicts anidados.
    """
    if not isinstance(existing, dict):
        # si el existente no es dict, devolvemos una copia de defaults
        return copy.deepcopy(defaults)

    for k, v in (defaults or {}).items():
        if k not in existing:
            existing[k] = copy.deepcopy(v)
        else:
            if isinstance(existing[k], dict) and isinstance(v, dict):
                _merge(existing[k], v)  # recursivo
            # si no son dicts, dejamos el valor existente tal cual
    return existing

# -------------------- API pública --------------------
def load() -> Dict[str, Any]:
    """
    Carga el archivo de configuración y completa con DEFAULTS.
    Si el archivo no existe o está corrupto, retorna sólo DEFAULTS.
    """
    _migrate_legacy_config()
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        else:
            cfg = {}
    except Exception:
        # archivo corrupto o ilegible: arrancar con {}
        cfg = {}

    # ...después de leer el archivo a cfg...
    try:
        # Si alguna vez se guardó 'general' adentro de 'business', moverlo a raíz
        if "general" not in cfg and isinstance(cfg.get("business"), dict) and "general" in cfg["business"]:
            cfg["general"] = cfg["business"].pop("general")
    except Exception:
        pass

    # completar claves faltantes con DEFAULTS (sin pisar valores existentes)
    cfg = _merge(cfg, copy.deepcopy(DEFAULTS))
    return cfg

def save(cfg: Dict[str, Any]) -> bool:
    """
    Guarda el dict de configuración en disco (app_config.json).
    Devuelve True si guardó correctamente.
    """
    try:
        # Asegurarnos de que el directorio existe (por si cambió estructura)
        base_dir = os.path.dirname(CONFIG_PATH) or "."
        os.makedirs(base_dir, exist_ok=True)

        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


# -------------------- RUTAS PUBLICAS --------------------
def get_log_dir() -> str:
    """Carpeta persistente de logs."""
    return _get_log_dir()


# -------------------- BACKUP / RESTORE --------------------
def get_backup_path() -> str:
    """
    Retorna la ruta del backup de configuración creado por el instalador.
    El instalador guarda en: {app}/config_backup/app_config.json
    """
    import sys
    if getattr(sys, 'frozen', False):
        # Modo frozen: el exe está en {app}/Tu local 2025.exe
        app_dir = os.path.dirname(sys.executable)
    else:
        # Modo desarrollo: usar carpeta raíz del proyecto
        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    backup_path = os.path.join(app_dir, "config_backup", "app_config.json")
    _log_config(f"get_backup_path() -> {backup_path}")
    return backup_path


def has_pending_backup() -> bool:
    """Verifica si existe un backup pendiente de restaurar."""
    backup_path = get_backup_path()
    exists = os.path.exists(backup_path)
    if not exists:
        _log_config(f"has_pending_backup() -> False (no existe: {backup_path})")
        return False
    if _is_same_backup_restored(backup_path):
        _log_config(f"has_pending_backup() -> False (ya restaurado: {backup_path})")
        return False
    _log_config(f"has_pending_backup() -> True (path: {backup_path})")
    return True


def restore_from_backup() -> bool:
    """
    Restaura la configuración desde el backup.
    Retorna True si se restauró correctamente.
    """
    import shutil
    backup_path = get_backup_path()

    _log_config("restore_from_backup() iniciando...")
    _log_config(f"Backup path: {backup_path}")
    _log_config(f"Config path destino: {CONFIG_PATH}")

    if not os.path.exists(backup_path):
        _log_config(f"ERROR: Backup no existe en {backup_path}")
        return False

    try:
        # Verificar que el directorio destino existe
        config_dir = os.path.dirname(CONFIG_PATH)
        if not os.path.exists(config_dir):
            _log_config(f"Creando directorio: {config_dir}")
            os.makedirs(config_dir, exist_ok=True)

        # Copiar backup sobre config actual
        _log_config(f"Copiando {backup_path} -> {CONFIG_PATH}")
        shutil.copy2(backup_path, CONFIG_PATH)
        _log_config("Copia exitosa!")

        # Verificar que se copió
        if os.path.exists(CONFIG_PATH):
            _log_config("Verificación: CONFIG_PATH existe después de copiar")
        else:
            _log_config("ERROR: CONFIG_PATH no existe después de copiar!")

        # Eliminar backup después de restaurar
        delete_backup()
        return True
    except Exception as e:
        _log_config(f"ERROR en restore_from_backup: {e}")
        return False

def restore_from_path(src_path: str) -> bool:
    """
    Restaura la configuracion desde un archivo JSON especifico.
    """
    import shutil
    if not src_path or not os.path.exists(src_path):
        _log_config(f"restore_from_path() -> archivo no existe: {src_path}")
        return False
    try:
        config_dir = os.path.dirname(CONFIG_PATH)
        if not os.path.exists(config_dir):
            os.makedirs(config_dir, exist_ok=True)
        shutil.copy2(src_path, CONFIG_PATH)
        _write_restore_marker(src_path)
        _log_config(f"restore_from_path() -> OK: {src_path} -> {CONFIG_PATH}")
        return True
    except Exception as e:
        _log_config(f"ERROR en restore_from_path: {e}")
        return False


def delete_backup() -> bool:
    """
    Elimina el backup y su carpeta.
    """
    import shutil
    backup_path = get_backup_path()
    backup_dir = os.path.dirname(backup_path)

    _log_config(f"delete_backup() - eliminando {backup_dir}")

    try:
        if os.path.exists(backup_path):
            os.remove(backup_path)
            _log_config("Archivo backup eliminado")
        if os.path.exists(backup_dir) and os.path.isdir(backup_dir):
            shutil.rmtree(backup_dir, ignore_errors=True)
            _log_config("Carpeta backup eliminada")
        return True
    except Exception as e:
        _log_config(f"ERROR en delete_backup: {e}")
        return False
