# app/gui/error_messages.py
# -*- coding: utf-8 -*-
"""
Clasificador de mensajes de error para mostrar al usuario.

Usa heurísticas sobre el texto de la excepción para clasificarla en
categorías (BD / red / AFIP / Firebase / validación / archivo) y devolver
un mensaje accionable en lugar del genérico "Error inesperado: {e}".

Uso típico:
    from app.gui.error_messages import classify_error, show_error

    try:
        do_something()
    except Exception as e:
        show_error(self, "No se pudo guardar el borrador", e)

    # O con contexto extra:
        show_error(self, "Error al sincronizar", e, context="sync_push")
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


# Categorías → mensaje al usuario (en español, accionable)
ERROR_TEMPLATES = {
    "BD_LOCKED":       "La base de datos está bloqueada por otra ventana o sucursal. Cerrá las otras instancias o esperá unos segundos y reintentá.",
    "BD_DISK_FULL":    "Espacio en disco insuficiente. Liberá espacio antes de continuar.",
    "BD_CONSTRAINT":   "La operación viola una restricción de la base de datos (probablemente un duplicado).",
    "BD_CORRUPT":      "La base de datos parece estar corrupta. Restaurá un backup desde Configuración → Backups.",
    "AFIP_CERT":       "Certificado AFIP inválido o vencido. Renovalo desde Configuración → AFIP.",
    "AFIP_CUIT":       "CUIT inválido o no autorizado para emitir comprobantes.",
    "AFIP_NETWORK":    "No se pudo conectar con AFIP. Verificá tu conexión a internet.",
    "AFIP_VALIDATION": "AFIP rechazó el comprobante por validación. Revisá los datos del cliente y los items.",
    "FIREBASE_AUTH":   "Error de autenticación con Firebase. Revisá el token en Configuración → Sincronización.",
    "FIREBASE_NETWORK":"No se pudo conectar con Firebase. Los cambios se guardarán localmente y se sincronizarán cuando vuelva la conexión.",
    "FILE_NOT_FOUND":  "No se encontró el archivo solicitado.",
    "FILE_PERMISSION": "Sin permisos para acceder al archivo. Cerralo si está abierto en Excel u otra aplicación.",
    "VALIDATION":      "Datos inválidos. Verificá los campos obligatorios.",
    "UNKNOWN":         "Error desconocido. Revisá el log para más detalles.",
}


def classify_error(exc: Exception) -> str:
    """
    Devuelve la categoría que mejor describe la excepción.
    Heurísticas basadas en el tipo y el texto de la excepción.

    Returns:
        Una clave de ERROR_TEMPLATES.
    """
    if exc is None:
        return "UNKNOWN"

    type_name = type(exc).__name__
    msg = str(exc).lower()

    # ── BD / SQLite / SQLAlchemy ──────────────────────────────────────
    if "database is locked" in msg or "lock" in msg and "database" in msg:
        return "BD_LOCKED"
    if "disk" in msg and "full" in msg or "no space" in msg:
        return "BD_DISK_FULL"
    if "unique constraint" in msg or "integrity" in msg or "constraint failed" in msg:
        return "BD_CONSTRAINT"
    if "corrupt" in msg or "malformed" in msg:
        return "BD_CORRUPT"

    # ── AFIP ─────────────────────────────────────────────────────────
    if "cert" in msg and ("expired" in msg or "vencido" in msg or "invalid" in msg):
        return "AFIP_CERT"
    if "cuit" in msg and ("invalid" in msg or "invalido" in msg or "no autorizado" in msg):
        return "AFIP_CUIT"
    if "afip" in msg and ("connection" in msg or "timeout" in msg or "unreachable" in msg):
        return "AFIP_NETWORK"
    if "afip" in msg and ("rechaz" in msg or "10071" in msg or "10016" in msg or "validation" in msg):
        return "AFIP_VALIDATION"

    # ── Firebase ─────────────────────────────────────────────────────
    if "firebase" in msg and ("auth" in msg or "401" in msg or "403" in msg or "permission" in msg):
        return "FIREBASE_AUTH"
    if "firebase" in msg and ("connection" in msg or "timeout" in msg or "unreachable" in msg or "network" in msg):
        return "FIREBASE_NETWORK"

    # ── Archivos ─────────────────────────────────────────────────────
    if type_name == "FileNotFoundError" or "no such file" in msg:
        return "FILE_NOT_FOUND"
    if type_name == "PermissionError" or "permission denied" in msg or "access denied" in msg:
        return "FILE_PERMISSION"

    # ── Validación genérica ──────────────────────────────────────────
    if type_name in ("ValueError", "TypeError", "AssertionError"):
        return "VALIDATION"

    return "UNKNOWN"


def get_user_message(exc: Exception, fallback_action: Optional[str] = None) -> str:
    """
    Devuelve un mensaje formateado para mostrar al usuario.

    Args:
        exc: la excepción capturada.
        fallback_action: descripción de qué se estaba intentando hacer
                         (ej: "guardar el borrador"). Se prepende al mensaje.

    Returns:
        Mensaje en español, accionable.
    """
    category = classify_error(exc)
    template = ERROR_TEMPLATES.get(category, ERROR_TEMPLATES["UNKNOWN"])

    if fallback_action:
        return f"No se pudo {fallback_action}.\n\n{template}\n\n(detalle técnico: {type(exc).__name__})"
    return f"{template}\n\n(detalle técnico: {type(exc).__name__})"


def show_error(parent, action_desc: str, exc: Exception, context: str = "") -> None:
    """
    Muestra un QMessageBox.warning con mensaje clasificado y loguea el error completo.

    Args:
        parent: widget padre (puede ser None).
        action_desc: descripción de la acción que falló (ej: "guardar el borrador").
        exc: la excepción.
        context: identificador opcional para logs (ej: "sync_push", "afip_emit").
    """
    # Loguear con stack trace para debugging
    log_prefix = f"[{context}] " if context else ""
    logger.error("%s%s falló: %s", log_prefix, action_desc, exc, exc_info=True)

    # Mostrar diálogo amigable
    try:
        from PyQt5.QtWidgets import QMessageBox
        msg = get_user_message(exc, fallback_action=action_desc)
        QMessageBox.warning(parent, "Error", msg)
    except Exception as _qt_err:
        # Si Qt no está disponible (test sin app), solo logueamos
        logger.warning("[error_messages] no se pudo mostrar QMessageBox: %s", _qt_err)
