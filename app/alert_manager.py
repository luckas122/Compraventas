# app/alert_manager.py
"""
AlertManager — sistema de alertas por email ante errores criticos.
Tipos: afip_error, sync_offline, db_error, critical.
Cooldown por tipo para evitar spam de emails.
"""
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

# Singleton
_instance = None


class AlertManager:
    """Gestor centralizado de alertas por email."""

    VALID_TYPES = {"afip_error", "sync_offline", "db_error", "critical"}

    TYPE_SUBJECTS = {
        "afip_error": "[ALERTA] Error de facturacion AFIP",
        "sync_offline": "[ALERTA] Sincronizacion Firebase offline",
        "db_error": "[ALERTA] Error de base de datos",
        "critical": "[ALERTA CRITICA] Error critico en el sistema",
    }

    TYPE_DESCRIPTIONS = {
        "afip_error": "Error al comunicarse con AFIP para facturacion electronica.",
        "sync_offline": "La sincronizacion con Firebase ha fallado o esta offline.",
        "db_error": "Se detecto un error en la base de datos local.",
        "critical": "Se produjo un error critico inesperado en la aplicacion.",
    }

    def __init__(self):
        self._last_sent = {}  # {tipo: timestamp_epoch}

    @classmethod
    def get_instance(cls) -> "AlertManager":
        """Retorna la instancia singleton."""
        global _instance
        if _instance is None:
            _instance = cls()
        return _instance

    def send_alert(self, error_type: str, message: str,
                   details: str = "", force: bool = False) -> bool:
        """
        Envia una alerta por email si:
        - Las alertas estan habilitadas en la config
        - El tipo de alerta esta habilitado
        - No se envio una alerta del mismo tipo dentro del cooldown

        Args:
            error_type: Tipo de error (afip_error, sync_offline, db_error, critical)
            message: Mensaje principal del error
            details: Detalles adicionales (traceback, etc.)
            force: Si True, ignora el cooldown

        Returns:
            True si el email fue enviado exitosamente
        """
        if error_type not in self.VALID_TYPES:
            logger.warning("[AlertManager] Tipo de alerta desconocido: %s", error_type)
            return False

        try:
            from app.config import load as load_config
            cfg = load_config()
        except Exception:
            logger.warning("[AlertManager] No se pudo cargar la config")
            return False

        alerts_cfg = cfg.get("alerts", {})

        # Verificar si alertas estan habilitadas
        if not alerts_cfg.get("enabled", False):
            logger.debug("[AlertManager] Alertas deshabilitadas")
            return False

        # Verificar si este tipo esta habilitado
        types_cfg = alerts_cfg.get("types", {})
        if not types_cfg.get(error_type, True):
            logger.debug("[AlertManager] Tipo '%s' deshabilitado", error_type)
            return False

        # Verificar cooldown
        email_cfg = alerts_cfg.get("email", {})
        cooldown_min = email_cfg.get("cooldown_minutes", 30)
        cooldown_sec = cooldown_min * 60

        now = time.time()
        last = self._last_sent.get(error_type, 0)
        if not force and (now - last) < cooldown_sec:
            remaining = int(cooldown_sec - (now - last))
            logger.debug(
                "[AlertManager] Cooldown activo para '%s', faltan %d seg",
                error_type, remaining
            )
            return False

        # Obtener destinatarios
        recipients = email_cfg.get("recipients", [])
        if not recipients:
            # Fallback: usar recipients de la config de email general
            general_email = cfg.get("email", {})
            recipients = general_email.get("recipients", [])

        if not recipients:
            logger.warning("[AlertManager] No hay destinatarios configurados")
            return False

        # Construir email
        subject = self.TYPE_SUBJECTS.get(error_type, f"[ALERTA] {error_type}")
        desc = self.TYPE_DESCRIPTIONS.get(error_type, "")

        # Info del sistema
        try:
            from datetime import datetime
            try:
                from zoneinfo import ZoneInfo
                tz = ZoneInfo(
                    cfg.get("general", {}).get("timezone", "America/Argentina/Buenos_Aires")
                )
                now_str = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            sucursal = cfg.get("business", {}).get("sucursal", "N/A")
            negocio = cfg.get("business", {}).get("nombre", "N/A")
        except Exception:
            now_str = "N/A"
            sucursal = "N/A"
            negocio = "N/A"

        body = (
            f"ALERTA: {desc}\n"
            f"{'=' * 50}\n\n"
            f"Tipo: {error_type}\n"
            f"Fecha/Hora: {now_str}\n"
            f"Negocio: {negocio}\n"
            f"Sucursal: {sucursal}\n\n"
            f"Mensaje:\n{message}\n"
        )
        if details:
            body += f"\nDetalles:\n{'-' * 40}\n{details}\n{'-' * 40}\n"

        body += (
            f"\n{'=' * 50}\n"
            f"Este email fue enviado automaticamente por Compraventas.\n"
            f"Podes desactivar estas alertas en Configuracion > Alertas.\n"
        )

        # Enviar
        try:
            from app.email_helper import send_mail_with_attachments
            send_mail_with_attachments(subject, body, recipients)
            self._last_sent[error_type] = time.time()
            logger.info(
                "[AlertManager] Alerta '%s' enviada a %s",
                error_type, recipients
            )
            return True
        except Exception as e:
            logger.error("[AlertManager] Error enviando alerta: %s", e)
            return False

    def send_test_alert(self, recipients: Optional[list] = None) -> tuple:
        """
        Envia un email de prueba para verificar que la configuracion es correcta.

        Returns:
            (ok: bool, error_msg: str|None)
        """
        try:
            from app.config import load as load_config
            cfg = load_config()
        except Exception as e:
            return False, f"No se pudo cargar config: {e}"

        if not recipients:
            alerts_cfg = cfg.get("alerts", {}).get("email", {})
            recipients = alerts_cfg.get("recipients", [])
        if not recipients:
            recipients = cfg.get("email", {}).get("recipients", [])
        if not recipients:
            return False, "No hay destinatarios configurados."

        try:
            from datetime import datetime
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            now_str = "N/A"

        subject = "[PRUEBA] Alerta de Compraventas"
        body = (
            f"Este es un email de prueba del sistema de alertas.\n\n"
            f"Fecha/Hora: {now_str}\n"
            f"Negocio: {cfg.get('business', {}).get('nombre', 'N/A')}\n"
            f"Sucursal: {cfg.get('business', {}).get('sucursal', 'N/A')}\n\n"
            f"Si recibiste este email, las alertas estan configuradas correctamente.\n\n"
            f"Tipos de alerta habilitados:\n"
        )
        types_cfg = cfg.get("alerts", {}).get("types", {})
        for t in self.VALID_TYPES:
            estado = "SI" if types_cfg.get(t, True) else "NO"
            body += f"  - {t}: {estado}\n"

        cooldown = cfg.get("alerts", {}).get("email", {}).get("cooldown_minutes", 30)
        body += f"\nCooldown entre alertas: {cooldown} minutos\n"

        try:
            from app.email_helper import send_mail_with_attachments
            send_mail_with_attachments(subject, body, recipients)
            return True, None
        except Exception as e:
            return False, str(e)

    def reset_cooldown(self, error_type: Optional[str] = None):
        """Resetea el cooldown de un tipo o de todos."""
        if error_type:
            self._last_sent.pop(error_type, None)
        else:
            self._last_sent.clear()
