# app/fiscal/afip_sdk_client.py
# Cliente simplificado para hablar con la API HTTP de AfipSDK (afipsdk.com).
# Ahora mismo funciona como "esqueleto":
# - Si no hay URL o API key configuradas, NO hace request real y devuelve un resultado SIMULADO.

from typing import Any, Dict, List, Tuple
import json as _json
import urllib.request
import urllib.error
import logging

log = logging.getLogger(__name__)


class AfipSDKClient:
    """
    Cliente muy simple para AfipSDK.
    Recibe la sección de config "fiscal" tal como sale de app.config.load().
    """

    def __init__(self, cfg_fiscal: Dict[str, Any]) -> None:
        self.cfg = cfg_fiscal or {}
        self._af = self.cfg.get("afipsdk") or {}

    # ---- helpers de configuración ----

    def is_enabled(self) -> bool:
        return bool(self.cfg.get("enabled", False))

    def is_test_mode(self) -> bool:
        return (self.cfg.get("mode") or "test") == "test"

    def get_base_url(self) -> str:
        if self.is_test_mode():
            return (self._af.get("base_url_test") or "").strip()
        return (self._af.get("base_url_prod") or "").strip()

    def get_api_key(self) -> str:
        return (self._af.get("api_key") or "").strip()

    # ---- API pública ----

    def emitir_comprobante(self, venta: Any, items: List[Dict[str, Any]]) -> Tuple[bool, Dict[str, Any]]:
        """
        Emite un comprobante vía AfipSDK.

        Devuelve (ok, data):
          - ok  : True/False
          - data: dict con información o error.

        IMPORTANTE:
        Esta función está pensada para ajustarse a la documentación oficial de AfipSDK:
        - La URL (path) y los nombres de campos pueden necesitar cambios.
        """
        base_url = self.get_base_url()
        api_key = self.get_api_key()

        # Sin config -> modo SIMULADO (no llamamos a nada externo)
        if not base_url or not api_key:
            log.warning("AfipSDK sin base_url/api_key -> modo SIMULADO.")
            return True, {
                "simulado": True,
                "cae": "00000000000000",
                "cae_vencimiento": None,
                "punto_venta": self.cfg.get("punto_venta", 1),
                "tipo_cbte": self.cfg.get("tipo_cbte", "FACTURA_B"),
                "nro_comprobante": getattr(venta, "numero_ticket", getattr(venta, "id", None)),
                "raw_request": None,
                "raw_response": None,
            }

        # Payload genérico: AJUSTAR según la API real de AfipSDK
        payload: Dict[str, Any] = {
            "cuit": self.cfg.get("cuit"),
            "punto_venta": self.cfg.get("punto_venta"),
            "tipo_cbte": self.cfg.get("tipo_cbte", "FACTURA_B"),
            "modo": self.cfg.get("mode", "test"),
            "cliente": {
                "tipo_doc": 99,   # 99 = Consumidor Final (dependerá de tu caso)
                "nro_doc": 0,
                "nombre": "Consumidor Final",
            },
            "totales": {
                "importe_total": float(getattr(venta, "total", 0.0) or 0.0),
            },
            "items": [],
        }

        for it in items or []:
            try:
                payload["items"].append({
                    "codigo": it.get("codigo"),
                    "descripcion": it.get("nombre"),
                    "cantidad": float(it.get("cantidad", 1.0) or 1.0),
                    "precio_unitario": float(it.get("precio_unitario", 0.0) or 0.0),
                })
            except Exception:
                # No rompemos por un ítem raro; simplemente lo saltamos
                continue

        # OJO: el path "/comprobantes" es orientativo, cámbialo al que indique AfipSDK
        url = base_url.rstrip("/") + "/comprobantes"

        data_bytes = _json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data_bytes,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = resp.read().decode("utf-8")
                try:
                    data_resp = _json.loads(raw)
                except Exception:
                    data_resp = {"raw": raw}

            # Estos nombres (cae, cae_vencimiento, etc.) hay que ajustarlos a la respuesta real
            result = {
                "simulado": False,
                "cae": data_resp.get("cae"),
                "cae_vencimiento": data_resp.get("cae_vencimiento"),
                "punto_venta": data_resp.get("punto_venta", self.cfg.get("punto_venta")),
                "tipo_cbte": data_resp.get("tipo_cbte", self.cfg.get("tipo_cbte")),
                "nro_comprobante": data_resp.get("nro_comprobante"),
                "raw_request": payload,
                "raw_response": data_resp,
            }
            return True, result

        except urllib.error.HTTPError as e:
            try:
                raw_err = e.read().decode("utf-8")
            except Exception:
                raw_err = str(e)
            log.error("HTTPError AfipSDK: %s", raw_err)
            return False, {"error": raw_err}

        except Exception as e:
            log.exception("Error general hablando con AfipSDK")
            return False, {"error": str(e)}
