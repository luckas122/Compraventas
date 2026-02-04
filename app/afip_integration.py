"""
Módulo de integración con AFIP SDK para facturación electrónica.

Este módulo maneja la emisión de comprobantes fiscales electrónicos
a través de la API de afipsdk.com cuando el pago es con tarjeta.

Documentación: https://docs.afipsdk.com/
API Reference: https://afipsdk.com/blog/crear-factura-electronica-de-afip-via-api/
"""

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


@dataclass
class AfipConfig:
    """Configuración de AFIP SDK."""
    access_token: str
    environment: str  # 'dev' o 'prod'
    cuit: str
    punto_venta: int
    enabled: bool = False
    only_card_payments: bool = True  # Solo emitir para pagos con tarjeta


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
    FACTURA_C = 11
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
        logger.debug(f"AFIP Request to {url}: {payload}")

        response = requests.post(url, json=payload, headers=self.headers, timeout=30)
        response.raise_for_status()

        data = response.json()
        logger.debug(f"AFIP Response: {data}")
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
                logger.info(f"Factura emitida exitosamente - CAE: {cae}, Vto: {cae_vto}")
                return AfipResponse(
                    success=True,
                    cae=cae,
                    cae_vencimiento=cae_vto,
                    numero_comprobante=proximo_nro,
                    raw_response=response
                )
            else:
                # Obtener errores desde Errors.Err[]
                errors = result.get("Errors", {})
                err_list = errors.get("Err", [])

                if err_list:
                    error_msg = "; ".join([f"[{e.get('Code')}] {e.get('Msg', '')}" for e in err_list])
                else:
                    # Intentar observaciones también
                    observaciones = fe_det.get("Observaciones", {}).get("Obs", [])
                    if observaciones:
                        error_msg = "; ".join([f"[{o.get('Code')}] {o.get('Msg', '')}" for o in observaciones])
                    else:
                        error_msg = "Error desconocido"

                logger.error(f"AFIP rechazó la factura: {error_msg}")
                return AfipResponse(
                    success=False,
                    error_message=error_msg,
                    raw_response=response
                )

        except Exception as e:
            logger.error(f"Error al emitir factura en AFIP: {e}", exc_info=True)
            return AfipResponse(
                success=False,
                error_message=str(e)
            )

    def emitir_nota_credito_b(
        self,
        total: float,
        subtotal: float,
        iva: float,
        comprobante_asociado: int,
        fecha: Optional[datetime] = None
    ) -> AfipResponse:
        """
        Emite una Nota de Crédito B (para devoluciones).

        Args:
            total: Total de la nota de crédito
            subtotal: Subtotal sin IVA
            iva: Monto de IVA
            comprobante_asociado: Número de factura original
            fecha: Fecha del comprobante

        Returns:
            AfipResponse con el CAE
        """
        logger.info(f"Emitiendo Nota de Crédito B por ${total:.2f} asociada a factura {comprobante_asociado}")

        # Similar a emitir_factura_b pero con CbteTipo = NOTA_CREDITO_B (8)
        # y agregando CbtesAsoc para referenciar la factura original
        # Implementación pendiente según necesidad

        return AfipResponse(
            success=False,
            error_message="Nota de Crédito no implementada aún"
        )


def crear_cliente_afip(config_dict: dict) -> Optional[AfipSDKClient]:
    """
    Factory para crear un cliente AFIP desde configuración.

    Args:
        config_dict: Diccionario con configuración AFIP desde app_config.json

    Returns:
        Cliente AFIP o None si está deshabilitado
    """
    if not config_dict.get("enabled", False):
        logger.info("AFIP deshabilitado en configuración")
        return None

    config = AfipConfig(
        access_token=config_dict.get("access_token", ""),
        environment=config_dict.get("environment", "dev"),
        cuit=config_dict.get("cuit", ""),
        punto_venta=config_dict.get("punto_venta", 1),
        enabled=config_dict.get("enabled", False),
        only_card_payments=config_dict.get("only_card_payments", True)
    )

    if not config.access_token or not config.cuit:
        logger.warning("AFIP configurado pero faltan access_token o CUIT")
        return None

    return AfipSDKClient(config)
