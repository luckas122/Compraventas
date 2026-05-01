"""
Módulo de integración con AFIP SDK para facturación electrónica.

Este módulo maneja la emisión de comprobantes fiscales electrónicos
a través de la API de afipsdk.com cuando el pago es con tarjeta.

Documentación: https://docs.afipsdk.com/
API Reference: https://afipsdk.com/blog/crear-factura-electronica-de-afip-via-api/
"""

import os
import requests
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

try:
    import pytz
    PYTZ_AVAILABLE = True
except ImportError:
    PYTZ_AVAILABLE = False

# Fallback para timezone si pytz no está disponible (Python 3.9+)
try:
    from zoneinfo import ZoneInfo
    ZONEINFO_AVAILABLE = True
except ImportError:
    ZONEINFO_AVAILABLE = False

logger = logging.getLogger(__name__)


# ── Logging a archivo para operaciones AFIP ──────────────────────────
def _setup_afip_file_logger():
    """
    Configura un FileHandler dedicado para registrar TODAS las operaciones
    AFIP en %APPDATA%/CompraventasV2/logs/afip.log.
    Se llama una sola vez al importar el módulo.
    """
    try:
        from app.config import _get_log_dir
        log_dir = _get_log_dir()
    except Exception:
        # Fallback si no se puede importar config
        import sys
        base = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        log_dir = os.path.join(base, "CompraventasV2", "logs")
        os.makedirs(log_dir, exist_ok=True)

    log_path = os.path.join(log_dir, "afip.log")
    try:
        # Usar RotatingFileHandler para no crecer infinitamente (max 5MB, 3 backups)
        from logging.handlers import RotatingFileHandler
        fh = RotatingFileHandler(
            log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        fh.setLevel(logging.DEBUG)
        fmt = logging.Formatter(
            "[%(asctime)s] %(levelname)-8s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        fh.setFormatter(fmt)
        logger.addHandler(fh)
        # Asegurar que el logger capture DEBUG
        if logger.level == logging.NOTSET or logger.level > logging.DEBUG:
            logger.setLevel(logging.DEBUG)
        logger.info("═══ AFIP File Logger inicializado ═══  Archivo: %s", log_path)
    except Exception as e:
        print(f"[AFIP] No se pudo crear file logger: {e}")

_setup_afip_file_logger()


def _sanitize_payload_for_log(payload: dict) -> dict:
    """Copia el payload ocultando Token y Sign para no loguear credenciales."""
    import copy
    safe = copy.deepcopy(payload)
    try:
        auth = safe.get("params", {}).get("Auth", {})
        if auth.get("Token"):
            auth["Token"] = auth["Token"][:10] + "..."
        if auth.get("Sign"):
            auth["Sign"] = auth["Sign"][:10] + "..."
        # Redactar certificado y clave privada
        if safe.get("cert"):
            safe["cert"] = safe["cert"][:30] + "...(truncated)"
        if safe.get("key"):
            safe["key"] = "[REDACTED]"
    except Exception:
        pass
    return safe


@dataclass
class AfipConfig:
    """Configuración de AFIP SDK."""
    access_token: str
    environment: str  # 'dev' o 'prod'
    cuit: str
    punto_venta: int
    enabled: bool = False
    only_card_payments: bool = True  # Solo emitir para pagos con tarjeta
    cert: str = ""  # Certificado digital PEM (requerido para producción)
    key: str = ""   # Clave privada PEM (requerido para producción)


@dataclass
class AfipResponse:
    """Respuesta de AFIP con CAE."""
    success: bool
    cae: Optional[str] = None
    cae_vencimiento: Optional[str] = None
    numero_comprobante: Optional[int] = None
    error_message: Optional[str] = None
    raw_response: Optional[dict] = None


class AfipSDKClient:
    """Cliente para interactuar con la API de AFIP SDK."""

    BASE_URL = "https://app.afipsdk.com/api/v1/afip"
    WSID = "wsfe"  # Web Service de Facturación Electrónica

    # Tipos de comprobante AFIP
    FACTURA_A = 1
    FACTURA_B = 6
    NOTA_CREDITO_A = 3
    NOTA_CREDITO_B = 8

    # Condiciones IVA
    IVA_CONSUMIDOR_FINAL = 5
    IVA_RESPONSABLE_INSCRIPTO = 1
    IVA_EXENTO = 4

    # Tipos de documento
    DOC_CUIT = 80
    DOC_CUIL = 86
    DOC_CDI = 87
    DOC_SIN_IDENTIFICAR = 99

    def __init__(self, config: AfipConfig):
        """
        Inicializa el cliente de AFIP SDK.

        Args:
            config: Configuración de AFIP
        """
        self.config = config
        self.headers = {
            "Authorization": f"Bearer {config.access_token}",
            "Content-Type": "application/json"
        }
        self._cached_auth = None
        self._auth_expiration = None

    def _make_request(self, endpoint: str, payload: dict) -> dict:
        """
        Realiza una petición a la API de AFIP SDK.

        Args:
            endpoint: Endpoint de la API
            payload: Datos a enviar

        Returns:
            Respuesta JSON de la API

        Raises:
            requests.RequestException: Si hay error en la petición
        """
        url = f"{self.BASE_URL}/{endpoint}"
        # Log detallado del request (sin token/sign por seguridad)
        safe_payload = _sanitize_payload_for_log(payload)
        logger.info("→ REQUEST  %s  payload=%s", url, safe_payload)

        response = requests.post(url, json=payload, headers=self.headers, timeout=30)
        logger.info("← RESPONSE status=%d", response.status_code)

        if response.status_code >= 400:
            try:
                error_body = response.json()
            except Exception:
                error_body = response.text
            logger.error("← ERROR [%d] body=%s", response.status_code, error_body)
            raise requests.exceptions.HTTPError(
                f"AfipSDK error {response.status_code}: {error_body}",
                response=response
            )

        data = response.json()
        logger.info("← RESPONSE body=%s", data)
        return data

    def get_auth_token(self, force: bool = False) -> Tuple[str, str]:
        """
        Obtiene el token de autenticación de AFIP.

        Args:
            force: Forzar nueva autenticación aunque haya token cacheado

        Returns:
            Tupla (token, sign)
        """
        # Verificar si hay token cacheado válido
        if not force and self._cached_auth and self._auth_expiration:
            now = datetime.now(timezone.utc)
            if now < self._auth_expiration:
                logger.debug("Usando token AFIP cacheado")
                return self._cached_auth

        logger.info(f"Obteniendo token AFIP para CUIT {self.config.cuit}")

        payload = {
            "environment": self.config.environment,
            "tax_id": self.config.cuit,
            "wsid": self.WSID
        }

        # Producción requiere certificado digital y clave privada
        if self.config.environment == "prod":
            if self.config.cert and self.config.key:
                payload["cert"] = self.config.cert
                payload["key"] = self.config.key
                # Validación de formato (sin exponer contenido)
                logger.info(
                    "[AFIP] Auth prod - cert: len=%d begins=%s ends=%s | key: len=%d begins=%s ends=%s",
                    len(self.config.cert),
                    self.config.cert.strip()[:27],
                    self.config.cert.strip()[-5:],
                    len(self.config.key),
                    self.config.key.strip()[:27],
                    self.config.key.strip()[-5:],
                )
            else:
                raise ValueError(
                    "Para modo PRODUCCIÓN se requiere certificado digital (.crt) y clave privada (.key). "
                    "Configuralos en Configuración → Facturación Electrónica."
                )

        try:
            response = self._make_request("auth", payload)

            token = response.get("token")
            sign = response.get("sign")
            expiration_str = response.get("expiration")

            if not token or not sign:
                raise ValueError("La respuesta de autenticación no contiene token o sign")

            # Cachear token
            self._cached_auth = (token, sign)
            if expiration_str:
                self._auth_expiration = datetime.fromisoformat(expiration_str.replace('Z', '+00:00'))

            logger.info("Token AFIP obtenido exitosamente")
            return token, sign

        except Exception as e:
            logger.error(f"Error al obtener token AFIP: {e}")
            raise

    def _generar_fechas_resync(self, fecha_str: str, fch_proceso: str) -> list:
        """
        Genera lista de fechas a probar en el resync de error 10016.
        Clave: AFIP error 10016 se dispara tanto por número incorrecto COMO por fecha incorrecta.
        El servidor de test de AFIP (homologación) suele tener el reloj desactualizado (2024/2025),
        por lo que '20260328' se rechaza como "fecha futura".
        Extraemos la fecha real del servidor desde FchProceso del response fallido.
        """
        from datetime import date, timedelta
        fechas = [fecha_str]  # siempre intentar primero con la fecha local

        # Agregar fecha del servidor AFIP si es diferente (viene de FECAESolicitarResult.FchProceso)
        server_date = fch_proceso[:8] if fch_proceso and len(fch_proceso) >= 8 else ""
        if server_date and server_date != fecha_str:
            fechas.insert(1, server_date)  # prioritaria: justo después de la fecha local
            logger.info(
                "[AFIP] Desfase de fecha detectado: servidor=%s vs local=%s → resync probará fecha servidor",
                server_date, fecha_str
            )

        # Agregar hasta 5 días anteriores (AFIP acepta últimos 5 días hábiles)
        try:
            base = date(int(fecha_str[:4]), int(fecha_str[4:6]), int(fecha_str[6:8]))
            for i in range(1, 6):
                d = base - timedelta(days=i)
                d_str = d.strftime("%Y%m%d")
                if d_str not in fechas:
                    fechas.append(d_str)
        except Exception:
            pass

        return fechas

    def _get_ultimo_comprobante_fresh(self, tipo_comprobante: int) -> int:
        """
        Re-consulta FECompUltimoAutorizado forzando un nuevo token de autenticación
        para obtener el número real actual (sin caché de AfipSDK).
        Se usa en el resync cuando ocurre error 10016.
        """
        logger.info("[AFIP] Re-consultando FECompUltimoAutorizado (token fresco) tipo=%d", tipo_comprobante)
        token, sign = self.get_auth_token(force=True)
        payload = {
            "environment": self.config.environment,
            "method": "FECompUltimoAutorizado",
            "wsid": self.WSID,
            "params": {
                "Auth": {
                    "Token": token,
                    "Sign": sign,
                    "Cuit": self.config.cuit
                },
                "PtoVta": self.config.punto_venta,
                "CbteTipo": tipo_comprobante
            }
        }
        response = self._make_request("requests", payload)
        ultimo = response.get("CbteNro", None)
        if ultimo is None:
            result = response.get("FECompUltimoAutorizadoResult", {})
            ultimo = result.get("CbteNro", 0)
        logger.info("[AFIP] Último comprobante real (fresco): %d", ultimo)
        return ultimo

    def get_ultimo_comprobante(self, tipo_comprobante: int = FACTURA_B) -> int:
        """
        Obtiene el último número de comprobante autorizado.

        Args:
            tipo_comprobante: Tipo de comprobante AFIP (default: Factura B)

        Returns:
            Número del último comprobante autorizado
        """
        logger.info(f"Consultando último comprobante tipo {tipo_comprobante}")

        token, sign = self.get_auth_token()

        payload = {
            "environment": self.config.environment,
            "method": "FECompUltimoAutorizado",
            "wsid": self.WSID,
            "params": {
                "Auth": {
                    "Token": token,
                    "Sign": sign,
                    "Cuit": self.config.cuit
                },
                "PtoVta": self.config.punto_venta,
                "CbteTipo": tipo_comprobante
            }
        }

        try:
            response = self._make_request("requests", payload)

            # La respuesta puede venir en diferentes estructuras
            # Intentar primero la estructura estándar
            ultimo = response.get("CbteNro", None)

            # Si no está en el nivel superior, buscar en FECompUltimoAutorizadoResult
            if ultimo is None:
                result = response.get("FECompUltimoAutorizadoResult", {})
                ultimo = result.get("CbteNro", 0)

            logger.info(f"Último comprobante autorizado: {ultimo}")
            logger.debug(f"Respuesta completa de FECompUltimoAutorizado: {response}")
            return ultimo

        except Exception as e:
            logger.error(f"Error al consultar último comprobante: {e}")
            raise

    def emitir_factura_b(
        self,
        items: List[Dict],
        total: float,
        subtotal: float,
        iva: float,
        fecha: Optional[datetime] = None,
        condicion_iva_receptor: int = IVA_CONSUMIDOR_FINAL,
        doc_tipo: int = DOC_SIN_IDENTIFICAR,
        doc_numero: int = 0
    ) -> AfipResponse:
        """
        Emite una Factura B electrónica en AFIP.

        Args:
            items: Lista de ítems de la venta (no se envían a AFIP, solo para log)
            total: Total de la venta con IVA
            subtotal: Subtotal sin IVA
            iva: Monto de IVA (21%)
            fecha: Fecha del comprobante (default: hoy)
            condicion_iva_receptor: Condición IVA del cliente (default: Consumidor Final)
            doc_tipo: Tipo de documento del cliente (default: Sin identificar)
            doc_numero: Número de documento del cliente (default: 0)

        Returns:
            AfipResponse con el CAE y datos del comprobante
        """
        if not self.config.enabled:
            logger.warning("AFIP deshabilitado en configuración, saltando emisión")
            return AfipResponse(success=False, error_message="AFIP deshabilitado")

        logger.info(f"Emitiendo Factura B - Total: ${total:.2f}")

        try:
            # 1. Obtener autenticación
            token, sign = self.get_auth_token()

            # 2. Obtener próximo número de comprobante
            ultimo_nro = self.get_ultimo_comprobante(self.FACTURA_B)
            proximo_nro = ultimo_nro + 1
            logger.info(
                "══ FACTURA B ══ PtoVta=%d | UltimoAutorizado=%d | ProximoNro=%d | Total=$%.2f | Subtotal=$%.2f | IVA=$%.2f",
                self.config.punto_venta, ultimo_nro, proximo_nro, total, subtotal, iva
            )

            # 3. Preparar fecha (usar timezone de Argentina)
            if fecha is None:
                # Usar timezone de Argentina (preferir pytz, luego zoneinfo, luego fallback)
                if PYTZ_AVAILABLE:
                    tz_arg = pytz.timezone('America/Argentina/Buenos_Aires')
                    fecha = datetime.now(tz_arg).date()
                elif ZONEINFO_AVAILABLE:
                    # Python 3.9+ tiene zoneinfo integrado
                    tz_arg = ZoneInfo('America/Argentina/Buenos_Aires')
                    fecha = datetime.now(tz_arg).date()
                else:
                    # Último fallback: UTC-3 (Argentina no usa horario de verano actualmente)
                    # NOTA: Si Argentina vuelve a usar horario de verano, instalar pytz
                    from datetime import timedelta
                    utc_now = datetime.now(timezone.utc)
                    arg_now = utc_now - timedelta(hours=3)
                    fecha = arg_now.date()
                    logger.warning(
                        "Usando fallback UTC-3 para timezone. "
                        "Instalar 'pytz' para manejo correcto de zonas horarias."
                    )
                fecha_str = fecha.strftime("%Y%m%d")
            else:
                if hasattr(fecha, 'strftime'):
                    fecha_str = fecha.strftime("%Y%m%d")
                else:
                    fecha_str = str(fecha)

            # 4. Preparar payload de factura
            payload = {
                "environment": self.config.environment,
                "method": "FECAESolicitar",
                "wsid": self.WSID,
                "params": {
                    "Auth": {
                        "Token": token,
                        "Sign": sign,
                        "Cuit": self.config.cuit
                    },
                    "FeCAEReq": {
                        "FeCabReq": {
                            "CantReg": 1,
                            "PtoVta": self.config.punto_venta,
                            "CbteTipo": self.FACTURA_B
                        },
                        "FeDetReq": {
                            "FECAEDetRequest": {
                                "Concepto": 1,  # 1=Productos, 2=Servicios, 3=Productos y Servicios
                                "DocTipo": doc_tipo,
                                "DocNro": doc_numero,
                                "CbteDesde": proximo_nro,
                                "CbteHasta": proximo_nro,
                                "CbteFch": fecha_str,
                                "ImpTotal": round(total, 2),
                                "ImpTotConc": 0,  # Importe no gravado
                                "ImpNeto": round(subtotal, 2),
                                "ImpOpEx": 0,  # Importe exento
                                "ImpIVA": round(iva, 2),
                                "ImpTrib": 0,  # Otros tributos
                                "MonId": "PES",  # Moneda: Pesos
                                "MonCotiz": 1,
                                "CondicionIVAReceptorId": condicion_iva_receptor,
                                "Iva": {
                                    "AlicIva": [{
                                        "Id": 5,  # 5 = 21%
                                        "BaseImp": round(subtotal, 2),
                                        "Importe": round(iva, 2)
                                    }]
                                }
                            }
                        }
                    }
                }
            }

            # 5. Emitir factura
            logger.info(f"Emitiendo comprobante Nº {proximo_nro} con fecha {fecha_str}")
            logger.debug(f"Payload completo: PtoVta={self.config.punto_venta}, CbteTipo={self.FACTURA_B}, CbteDesde={proximo_nro}, CbteFch={fecha_str}")
            response = self._make_request("requests", payload)

            # 6. Parsear respuesta
            # Estructura: FECAESolicitarResult.FeDetResp.FECAEDetResponse[0]
            result = response.get("FECAESolicitarResult", {})
            fe_det_resp = result.get("FeDetResp", {})
            fe_det_list = fe_det_resp.get("FECAEDetResponse", [])

            # Obtener el primer elemento de la lista
            fe_det = fe_det_list[0] if fe_det_list else {}

            cae = fe_det.get("CAE", "")
            cae_vto = fe_det.get("CAEFchVto", "")
            resultado = fe_det.get("Resultado", "")

            if resultado == "A" and cae:  # A = Aprobado
                logger.info(f"Factura B emitida exitosamente - CAE: {cae}, Vto: {cae_vto}")
                return AfipResponse(
                    success=True,
                    cae=cae,
                    cae_vencimiento=cae_vto,
                    numero_comprobante=proximo_nro,
                    raw_response=response
                )
            else:
                # Obtener errores desde Errors.Err[] (puede ser dict o lista)
                errors = result.get("Errors", {})
                err_list = errors.get("Err", [])
                if isinstance(err_list, dict):
                    err_list = [err_list]
                observaciones = fe_det.get("Observaciones", {}).get("Obs", [])
                if isinstance(observaciones, dict):
                    observaciones = [observaciones]

                # --- AUTO-RESYNC: error 10016 (número desincronizado) ---
                # El server de AfipSDK puede cachear FECompUltimoAutorizado.
                # Probar incrementando el Nº hasta encontrar el correcto.
                try:
                    all_codes = [str(e.get('Code', '')) for e in err_list] + \
                                [str(o.get('Code', '')) for o in observaciones]
                except Exception:
                    all_codes = []

                if '10016' in all_codes:
                    # CAUSA RAÍZ: en modo dev el CUIT es compartido entre todos los usuarios de
                    # AfipSDK → condición de carrera. En prod con CUIT propio esto es raro.
                    # Solución: re-consultar FECompUltimoAutorizado en CADA reintento para obtener
                    # siempre el número real más reciente, sin importar cuánto haya saltado.
                    logger.warning(
                        "[AFIP] Error 10016 en Factura B (Nº %d) - resync dinámico (max 5 intentos)...",
                        proximo_nro
                    )
                    if self.config.environment == "dev":
                        logger.warning(
                            "[AFIP] MODO DEV: CUIT %s compartido entre usuarios AfipSDK. "
                            "Para facturas reales usar modo PROD con CUIT propio.",
                            self.config.cuit
                        )
                    det_key = payload["params"]["FeCAEReq"]["FeDetReq"]["FECAEDetRequest"]
                    try:
                        for resync_attempt in range(5):
                            real_ultimo = self._get_ultimo_comprobante_fresh(self.FACTURA_B)
                            real_proximo = real_ultimo + 1
                            logger.info(
                                "[AFIP] Resync B intento %d/5: último=%d → intentando Nº %d",
                                resync_attempt + 1, real_ultimo, real_proximo
                            )
                            det_key["CbteDesde"] = real_proximo
                            det_key["CbteHasta"] = real_proximo
                            det_key["CbteFch"] = fecha_str
                            response2 = self._make_request("requests", payload)
                            result2 = response2.get("FECAESolicitarResult", {})
                            fe_det2 = (result2.get("FeDetResp", {}).get("FECAEDetResponse", []) or [{}])[0]
                            cae2 = fe_det2.get("CAE", "")
                            cae_vto2 = fe_det2.get("CAEFchVto", "")
                            if fe_det2.get("Resultado") == "A" and cae2:
                                logger.info(
                                    "[AFIP] Resync Factura B exitoso - CAE: %s, Nº: %d (intento %d)",
                                    cae2, real_proximo, resync_attempt + 1
                                )
                                return AfipResponse(
                                    success=True, cae=cae2,
                                    cae_vencimiento=cae_vto2,
                                    numero_comprobante=real_proximo,
                                    raw_response=response2
                                )
                            errs2 = result2.get("Errors", {}).get("Err", [])
                            if isinstance(errs2, dict):
                                errs2 = [errs2]
                            obs2 = fe_det2.get("Observaciones", {}).get("Obs", [])
                            if isinstance(obs2, dict):
                                obs2 = [obs2]
                            codes2 = [str(x.get('Code', '')) for x in errs2] + \
                                     [str(x.get('Code', '')) for x in obs2]
                            if '10016' not in codes2:
                                logger.error("[AFIP] Error diferente a 10016, abortando resync: %s", codes2)
                                break
                            logger.warning(
                                "[AFIP] Nº %d tomado por otro proceso, re-consultando...", real_proximo
                            )
                    except Exception as ex_resync:
                        logger.error("[AFIP] Error en resync Factura B: %s", ex_resync)

                if err_list:
                    error_msg = "; ".join([f"[{e.get('Code')}] {e.get('Msg', '')}" for e in err_list])
                elif observaciones:
                    error_msg = "; ".join([f"[{o.get('Code')}] {o.get('Msg', '')}" for o in observaciones])
                else:
                    error_msg = "Error desconocido"

                logger.error(f"AFIP rechazó la factura B: {error_msg}")
                return AfipResponse(
                    success=False,
                    error_message=error_msg,
                    raw_response=response
                )

        except Exception as e:
            logger.error(f"Error al emitir factura B en AFIP: {e}", exc_info=True)
            try:
                from app.alert_manager import AlertManager
                AlertManager.get_instance().send_alert(
                    "afip_error",
                    f"Error al emitir Factura B: {e}",
                    details=f"Tipo: Factura B\nImporte: {importe}\nError: {e}"
                )
            except Exception as _alert_err:
                logger.warning("[AFIP] no se pudo enviar AlertManager tras error de Factura B: %s", _alert_err)
            return AfipResponse(
                success=False,
                error_message=str(e)
            )

    def emitir_factura_a(
        self,
        items: List[Dict],
        total: float,
        subtotal: float,
        iva: float,
        cuit_cliente: str,
        fecha: Optional[datetime] = None
    ) -> AfipResponse:
        """
        Emite una Factura A electrónica en AFIP.

        Factura A se emite a Responsables Inscriptos (requiere CUIT del cliente).

        Args:
            items: Lista de ítems de la venta (para log)
            total: Total de la venta con IVA
            subtotal: Subtotal sin IVA (base imponible)
            iva: Monto de IVA (21%)
            cuit_cliente: CUIT del cliente (11 dígitos, sin guiones)
            fecha: Fecha del comprobante (default: hoy)

        Returns:
            AfipResponse con el CAE y datos del comprobante
        """
        if not self.config.enabled:
            logger.warning("AFIP deshabilitado en configuración, saltando emisión")
            return AfipResponse(success=False, error_message="AFIP deshabilitado")

        # Validar CUIT
        cuit_clean = (cuit_cliente or "").replace("-", "").strip()
        if not cuit_clean or len(cuit_clean) != 11 or not cuit_clean.isdigit():
            return AfipResponse(
                success=False,
                error_message=f"CUIT inválido: '{cuit_cliente}'. Debe tener 11 dígitos."
            )

        logger.info(f"Emitiendo Factura A - Total: ${total:.2f}, CUIT cliente: {cuit_clean}")

        try:
            token, sign = self.get_auth_token()
            ultimo_nro = self.get_ultimo_comprobante(self.FACTURA_A)
            proximo_nro = ultimo_nro + 1
            logger.info(
                "══ FACTURA A ══ PtoVta=%d | UltimoAutorizado=%d | ProximoNro=%d | Total=$%.2f | CUIT=%s",
                self.config.punto_venta, ultimo_nro, proximo_nro, total, cuit_clean
            )

            if fecha is None:
                if PYTZ_AVAILABLE:
                    tz_arg = pytz.timezone('America/Argentina/Buenos_Aires')
                    fecha = datetime.now(tz_arg).date()
                elif ZONEINFO_AVAILABLE:
                    tz_arg = ZoneInfo('America/Argentina/Buenos_Aires')
                    fecha = datetime.now(tz_arg).date()
                else:
                    from datetime import timedelta
                    utc_now = datetime.now(timezone.utc)
                    arg_now = utc_now - timedelta(hours=3)
                    fecha = arg_now.date()
                fecha_str = fecha.strftime("%Y%m%d")
            else:
                if hasattr(fecha, 'strftime'):
                    fecha_str = fecha.strftime("%Y%m%d")
                else:
                    fecha_str = str(fecha)

            payload = {
                "environment": self.config.environment,
                "method": "FECAESolicitar",
                "wsid": self.WSID,
                "params": {
                    "Auth": {
                        "Token": token,
                        "Sign": sign,
                        "Cuit": self.config.cuit
                    },
                    "FeCAEReq": {
                        "FeCabReq": {
                            "CantReg": 1,
                            "PtoVta": self.config.punto_venta,
                            "CbteTipo": self.FACTURA_A
                        },
                        "FeDetReq": {
                            "FECAEDetRequest": {
                                "Concepto": 1,
                                "DocTipo": self.DOC_CUIT,
                                "DocNro": int(cuit_clean),
                                "CbteDesde": proximo_nro,
                                "CbteHasta": proximo_nro,
                                "CbteFch": fecha_str,
                                "ImpTotal": round(total, 2),
                                "ImpTotConc": 0,
                                "ImpNeto": round(subtotal, 2),
                                "ImpOpEx": 0,
                                "ImpIVA": round(iva, 2),
                                "ImpTrib": 0,
                                "MonId": "PES",
                                "MonCotiz": 1,
                                "CondicionIVAReceptorId": self.IVA_RESPONSABLE_INSCRIPTO,
                                "Iva": {
                                    "AlicIva": [{
                                        "Id": 5,
                                        "BaseImp": round(subtotal, 2),
                                        "Importe": round(iva, 2)
                                    }]
                                }
                            }
                        }
                    }
                }
            }

            logger.info(f"Emitiendo Factura A Nº {proximo_nro} con fecha {fecha_str}")
            response = self._make_request("requests", payload)

            result = response.get("FECAESolicitarResult", {})
            fe_det_resp = result.get("FeDetResp", {})
            fe_det_list = fe_det_resp.get("FECAEDetResponse", [])
            fe_det = fe_det_list[0] if fe_det_list else {}

            cae = fe_det.get("CAE", "")
            cae_vto = fe_det.get("CAEFchVto", "")
            resultado = fe_det.get("Resultado", "")

            if resultado == "A" and cae:
                logger.info(f"Factura A emitida exitosamente - CAE: {cae}, Vto: {cae_vto}")
                return AfipResponse(
                    success=True,
                    cae=cae,
                    cae_vencimiento=cae_vto,
                    numero_comprobante=proximo_nro,
                    raw_response=response
                )
            else:
                errors = result.get("Errors", {})
                err_list = errors.get("Err", [])
                if isinstance(err_list, dict):
                    err_list = [err_list]
                observaciones = fe_det.get("Observaciones", {}).get("Obs", [])
                if isinstance(observaciones, dict):
                    observaciones = [observaciones]

                # --- AUTO-RESYNC: error 10016 (número desincronizado) ---
                try:
                    all_codes = [str(e.get('Code', '')) for e in err_list] + \
                                [str(o.get('Code', '')) for o in observaciones]
                except Exception:
                    all_codes = []

                if '10016' in all_codes:
                    logger.warning(
                        "[AFIP] Error 10016 en Factura A (Nº %d) - resync dinámico (max 5 intentos)...",
                        proximo_nro
                    )
                    if self.config.environment == "dev":
                        logger.warning(
                            "[AFIP] MODO DEV: CUIT %s compartido entre usuarios AfipSDK. "
                            "Para facturas reales usar modo PROD con CUIT propio.",
                            self.config.cuit
                        )
                    det_key = payload["params"]["FeCAEReq"]["FeDetReq"]["FECAEDetRequest"]
                    try:
                        for resync_attempt in range(5):
                            real_ultimo = self._get_ultimo_comprobante_fresh(self.FACTURA_A)
                            real_proximo = real_ultimo + 1
                            logger.info(
                                "[AFIP] Resync A intento %d/5: último=%d → intentando Nº %d",
                                resync_attempt + 1, real_ultimo, real_proximo
                            )
                            det_key["CbteDesde"] = real_proximo
                            det_key["CbteHasta"] = real_proximo
                            det_key["CbteFch"] = fecha_str
                            response2 = self._make_request("requests", payload)
                            result2 = response2.get("FECAESolicitarResult", {})
                            fe_det2 = (result2.get("FeDetResp", {}).get("FECAEDetResponse", []) or [{}])[0]
                            cae2 = fe_det2.get("CAE", "")
                            cae_vto2 = fe_det2.get("CAEFchVto", "")
                            if fe_det2.get("Resultado") == "A" and cae2:
                                logger.info(
                                    "[AFIP] Resync Factura A exitoso - CAE: %s, Nº: %d (intento %d)",
                                    cae2, real_proximo, resync_attempt + 1
                                )
                                return AfipResponse(
                                    success=True, cae=cae2,
                                    cae_vencimiento=cae_vto2,
                                    numero_comprobante=real_proximo,
                                    raw_response=response2
                                )
                            errs2 = result2.get("Errors", {}).get("Err", [])
                            if isinstance(errs2, dict):
                                errs2 = [errs2]
                            obs2 = fe_det2.get("Observaciones", {}).get("Obs", [])
                            if isinstance(obs2, dict):
                                obs2 = [obs2]
                            codes2 = [str(x.get('Code', '')) for x in errs2] + \
                                     [str(x.get('Code', '')) for x in obs2]
                            if '10016' not in codes2:
                                logger.error("[AFIP] Error diferente a 10016, abortando resync: %s", codes2)
                                break
                            logger.warning(
                                "[AFIP] Nº %d tomado por otro proceso, re-consultando...", real_proximo
                            )
                    except Exception as ex_resync:
                        logger.error("[AFIP] Error en resync Factura A: %s", ex_resync)

                if err_list:
                    error_msg = "; ".join([f"[{e.get('Code')}] {e.get('Msg', '')}" for e in err_list])
                elif observaciones:
                    error_msg = "; ".join([f"[{o.get('Code')}] {o.get('Msg', '')}" for o in observaciones])
                else:
                    error_msg = "Error desconocido"

                logger.error(f"AFIP rechazó la Factura A: {error_msg}")
                return AfipResponse(
                    success=False,
                    error_message=error_msg,
                    raw_response=response
                )

        except Exception as e:
            logger.error(f"Error al emitir Factura A en AFIP: {e}", exc_info=True)
            try:
                from app.alert_manager import AlertManager
                AlertManager.get_instance().send_alert(
                    "afip_error",
                    f"Error al emitir Factura A: {e}",
                    details=f"Tipo: Factura A\nImporte: {importe}\nError: {e}"
                )
            except Exception as _alert_err:
                logger.warning("[AFIP] no se pudo enviar AlertManager tras error de Factura A: %s", _alert_err)
            return AfipResponse(
                success=False,
                error_message=str(e)
            )

    def _emitir_nota_credito(
        self,
        cbte_tipo_nc: int,
        cbte_tipo_original: int,
        total: float,
        subtotal: float,
        iva: float,
        comprobante_asociado: int,
        fecha_comprobante_original: str,
        doc_tipo: int = None,
        doc_numero: int = 0,
        condicion_iva_receptor: int = None,
    ) -> AfipResponse:
        """
        Emite una Nota de Crédito (A o B) para anular una factura.

        Args:
            cbte_tipo_nc: Tipo NC (3=NC A, 8=NC B)
            cbte_tipo_original: Tipo factura original (1=Fact A, 6=Fact B)
            total: Total de la nota de crédito
            subtotal: Subtotal sin IVA
            iva: Monto de IVA
            comprobante_asociado: Nº de factura original
            fecha_comprobante_original: Fecha factura original YYYYMMDD
            doc_tipo: Tipo documento (80=CUIT, 86=CUIL, 99=Sin Identificar)
            doc_numero: Número de documento
            condicion_iva_receptor: Condición IVA del receptor
        """
        if doc_tipo is None:
            doc_tipo = self.DOC_SIN_IDENTIFICAR
        if condicion_iva_receptor is None:
            condicion_iva_receptor = self.IVA_CONSUMIDOR_FINAL

        nc_label = "A" if cbte_tipo_nc == self.NOTA_CREDITO_A else "B"
        logger.info(
            "[AFIP] Emitiendo Nota de Crédito %s por $%.2f asociada a comprobante %d",
            nc_label, total, comprobante_asociado
        )

        try:
            # 1. Auth
            token, sign = self.get_auth_token()

            # 2. Fecha
            if PYTZ_AVAILABLE:
                tz_arg = pytz.timezone('America/Argentina/Buenos_Aires')
                fecha_str = datetime.now(tz_arg).date().strftime("%Y%m%d")
            elif ZONEINFO_AVAILABLE:
                tz_arg = ZoneInfo('America/Argentina/Buenos_Aires')
                fecha_str = datetime.now(tz_arg).date().strftime("%Y%m%d")
            else:
                from datetime import timedelta
                fecha_str = (datetime.now(timezone.utc) - timedelta(hours=3)).date().strftime("%Y%m%d")

            # 3. Último comprobante de este tipo de NC
            ultimo = self.get_ultimo_comprobante(cbte_tipo_nc)
            proximo_nro = ultimo + 1

            # 4. Payload
            payload = {
                "environment": self.config.environment,
                "method": "FECAESolicitar",
                "wsid": self.WSID,
                "params": {
                    "Auth": {"Token": token, "Sign": sign, "Cuit": self.config.cuit},
                    "FeCAEReq": {
                        "FeCabReq": {
                            "CantReg": 1,
                            "PtoVta": self.config.punto_venta,
                            "CbteTipo": cbte_tipo_nc
                        },
                        "FeDetReq": {
                            "FECAEDetRequest": {
                                "Concepto": 1,
                                "DocTipo": doc_tipo,
                                "DocNro": doc_numero,
                                "CbteDesde": proximo_nro,
                                "CbteHasta": proximo_nro,
                                "CbteFch": fecha_str,
                                "ImpTotal": round(total, 2),
                                "ImpTotConc": 0,
                                "ImpNeto": round(subtotal, 2),
                                "ImpOpEx": 0,
                                "ImpIVA": round(iva, 2),
                                "ImpTrib": 0,
                                "MonId": "PES",
                                "MonCotiz": 1,
                                "CondicionIVAReceptorId": condicion_iva_receptor,
                                "CbtesAsoc": {
                                    "CbteAsoc": [{
                                        "Tipo": cbte_tipo_original,
                                        "PtoVta": self.config.punto_venta,
                                        "Nro": comprobante_asociado,
                                        "Cuit": self.config.cuit,
                                        "CbteFch": fecha_comprobante_original
                                    }]
                                },
                                "Iva": {
                                    "AlicIva": [{
                                        "Id": 5,
                                        "BaseImp": round(subtotal, 2),
                                        "Importe": round(iva, 2)
                                    }]
                                }
                            }
                        }
                    }
                }
            }

            # 5. Emitir
            logger.info("[AFIP] NC %s Nº %d con fecha %s", nc_label, proximo_nro, fecha_str)
            response = self._make_request("requests", payload)

            # 6. Parsear respuesta
            result = response.get("FECAESolicitarResult", {})
            fe_det_list = result.get("FeDetResp", {}).get("FECAEDetResponse", [])
            fe_det = fe_det_list[0] if fe_det_list else {}

            cae = fe_det.get("CAE", "")
            cae_vto = fe_det.get("CAEFchVto", "")
            resultado = fe_det.get("Resultado", "")

            if resultado == "A" and cae:
                logger.info("[AFIP] NC %s emitida - CAE: %s, Nº: %d", nc_label, cae, proximo_nro)
                return AfipResponse(
                    success=True, cae=cae, cae_vencimiento=cae_vto,
                    numero_comprobante=proximo_nro, raw_response=response
                )

            # Error
            errs = result.get("Errors", {}).get("Err", [])
            if isinstance(errs, dict): errs = [errs]
            obs = fe_det.get("Observaciones", {}).get("Obs", [])
            if isinstance(obs, dict): obs = [obs]
            all_msgs = [f"[{x.get('Code')}] {x.get('Msg', '')}" for x in errs + obs]
            error_msg = "; ".join(all_msgs) if all_msgs else "Error desconocido"
            logger.error("[AFIP] NC %s rechazada: %s", nc_label, error_msg)
            return AfipResponse(success=False, error_message=error_msg, raw_response=response)

        except Exception as e:
            logger.error("[AFIP] Error emitiendo NC %s: %s", nc_label, e)
            return AfipResponse(success=False, error_message=str(e))

    def emitir_nota_credito_a(
        self,
        total: float,
        subtotal: float,
        iva: float,
        comprobante_asociado: int,
        fecha_comprobante_original: str,
        cuit_cliente: str,
    ) -> AfipResponse:
        """Emite Nota de Crédito A (CbteTipo 3) para anular una Factura A."""
        cuit_clean = (cuit_cliente or "").replace("-", "").strip()
        return self._emitir_nota_credito(
            cbte_tipo_nc=self.NOTA_CREDITO_A,
            cbte_tipo_original=self.FACTURA_A,
            total=total, subtotal=subtotal, iva=iva,
            comprobante_asociado=comprobante_asociado,
            fecha_comprobante_original=fecha_comprobante_original,
            doc_tipo=self.DOC_CUIT,
            doc_numero=int(cuit_clean) if cuit_clean else 0,
            condicion_iva_receptor=self.IVA_RESPONSABLE_INSCRIPTO,
        )

    def emitir_nota_credito_b(
        self,
        total: float,
        subtotal: float,
        iva: float,
        comprobante_asociado: int,
        fecha_comprobante_original: str,
        doc_tipo: int = None,
        doc_numero: int = 0,
    ) -> AfipResponse:
        """Emite Nota de Crédito B (CbteTipo 8) para anular una Factura B."""
        return self._emitir_nota_credito(
            cbte_tipo_nc=self.NOTA_CREDITO_B,
            cbte_tipo_original=self.FACTURA_B,
            total=total, subtotal=subtotal, iva=iva,
            comprobante_asociado=comprobante_asociado,
            fecha_comprobante_original=fecha_comprobante_original,
            doc_tipo=doc_tipo or self.DOC_SIN_IDENTIFICAR,
            doc_numero=doc_numero,
            condicion_iva_receptor=self.IVA_CONSUMIDOR_FINAL,
        )


def resolver_punto_venta(fiscal_config: dict, sucursal: str = "") -> int:
    """
    Devuelve el punto de venta correcto según la sucursal.
    Prioridad: puntos_venta_por_sucursal[sucursal] → punto_venta global → 1
    """
    pv_map = fiscal_config.get("puntos_venta_por_sucursal") or {}
    if sucursal and pv_map.get(sucursal):
        pv = int(pv_map[sucursal])
        logger.info("[AFIP] Punto de venta para '%s': %d (por sucursal)", sucursal, pv)
        return pv
    pv = int(fiscal_config.get("punto_venta", 1) or 1)
    logger.info("[AFIP] Punto de venta global: %d (sucursal='%s')", pv, sucursal)
    return pv


def crear_cliente_afip(config_dict: dict, sucursal: str = "") -> Optional[AfipSDKClient]:
    """
    Factory para crear un cliente AFIP desde configuración.

    Args:
        config_dict: Diccionario con configuración AFIP (sección 'fiscal' del config)
        sucursal:    Nombre de la sucursal para resolver el punto de venta

    Returns:
        Cliente AFIP o None si está deshabilitado
    """
    if not config_dict.get("enabled", False):
        logger.info("AFIP deshabilitado en configuración")
        return None

    pv = resolver_punto_venta(config_dict, sucursal)

    # --- Normalizar claves: fiscal config → AfipConfig ---
    # access_token: puede venir directo O dentro de afipsdk.api_key
    access_token = config_dict.get("access_token", "")
    if not access_token:
        af = config_dict.get("afipsdk") or {}
        access_token = af.get("api_key", "")

    # environment: puede venir directo O como 'mode' (test→dev, prod→prod)
    environment = config_dict.get("environment", "")
    if not environment:
        mode = config_dict.get("mode", "test")
        environment = "dev" if mode == "test" else ("prod" if mode == "prod" else "dev")

    # only_card_payments: puede venir directo O como 'only_card'
    only_card = config_dict.get("only_card_payments",
                                config_dict.get("only_card", True))

    # Certificado y clave privada para producción
    af = config_dict.get("afipsdk") or {}
    cert_content = af.get("cert", "")
    key_content = af.get("key", "")

    # Cargar desde archivos si son rutas
    if cert_content and not cert_content.startswith("-----"):
        try:
            with open(cert_content, "r", encoding="utf-8-sig") as f:
                cert_content = f.read().strip()
            logger.info("Certificado leído desde %s (%d bytes)", cert_content[:50], len(cert_content))
        except Exception as e:
            logger.warning("No se pudo leer certificado desde %s: %s", cert_content, e)
            cert_content = ""
    if key_content and not key_content.startswith("-----"):
        try:
            with open(key_content, "r", encoding="utf-8-sig") as f:
                key_content = f.read().strip()
            logger.info("Clave privada leída (%d bytes)", len(key_content))
        except Exception as e:
            logger.warning("No se pudo leer clave privada desde %s: %s", key_content, e)
            key_content = ""

    config = AfipConfig(
        access_token=access_token,
        environment=environment,
        cuit=config_dict.get("cuit", ""),
        punto_venta=pv,
        enabled=config_dict.get("enabled", False),
        only_card_payments=bool(only_card),
        cert=cert_content,
        key=key_content
    )

    if not config.access_token or not config.cuit:
        logger.warning("AFIP configurado pero faltan access_token o CUIT (token=%s, cuit=%s)",
                        bool(config.access_token), bool(config.cuit))
        return None

    return AfipSDKClient(config)
