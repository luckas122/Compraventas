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

# Ruta del archivo JSON de configuración
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "app_config.json")

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
        "font_family": "Arial",
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
        "show_interest_line": False,  # si mostrar “Interés: …” en el pie
        "slots": {
            "slot1": "",
            "slot2": "",
            "slot3": ""
        },
        "placeholders": [
            "{{ticket.numero}}", "{{ticket.fecha_hora}}", "{{sucursal}}",
            "{{cliente.nombre}}", "{{cliente.doc}}",
            "{{pago.modo}}", "{{pago.cuotas}}", "{{pago.monto_cuota}}",
            "{{totales.subtotal}}", "{{totales.interes}}", "{{totales.total}}",
            "{{abonado}}", "{{vuelto}}"
        ]
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
