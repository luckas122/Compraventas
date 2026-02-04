from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Tuple, List
from datetime import datetime


@dataclass
class AfipSDKClient:
    """
    Pequeño wrapper alrededor de afip.py (Afip SDK) para emitir
    comprobantes electrónicos desde tu app.

    - Si falta API key o CUIT (en prod), trabaja en modo SIMULACIÓN.
    - Si todo está configurado, llama al WS de Factura Electrónica (WSFE).
    """
    cfg: Dict[str, Any]

    def __post_init__(self):
        self._cfg = self.cfg or {}
        self._mode = (self._cfg.get("mode") or "test").lower()
        self._afipsdk_cfg = self._cfg.get("afipsdk") or {}

    # ---------------------------------------------------------
    #   ¿Trabajamos en modo simulación?
    # ---------------------------------------------------------
    def _is_simulated(self) -> bool:
        """
        True si NO tenemos suficiente config para llamar realmente a AFIP.
        En ese caso, devolvemos 'ok' pero marcando simulado=True.
        """
        api_key = (self._afipsdk_cfg.get("api_key") or "").strip()
        cuit = (str(self._cfg.get("cuit") or "")).strip()

        # Sin API key -> simulación
        if not api_key:
            return True

        # En producción exigimos CUIT configurado
        if self._mode == "prod" and not cuit:
            return True

        return False

    # ---------------------------------------------------------
    #   Punto de entrada: emitir comprobante
    # ---------------------------------------------------------
    def emitir_comprobante(self, venta, items: List[Dict[str, Any]]) -> Tuple[bool, Dict[str, Any]]:
        """
        Devuelve (ok, data)

        ok = True  -> éxito (real o simulado)
        ok = False -> hubo error, 'data["error"]' trae el detalle (string)

        Si está en simulación:
            (True, {"simulado": True})
        """
        # 1) Simulación si falta config clave
        if self._is_simulated():
            return True, {"simulado": True}

        # 2) Importar librería afip.py
        try:
            from afip import Afip
        except Exception as e:
            return False, {"error": f"No se pudo importar afip.py: {e}"}

        api_key = (self._afipsdk_cfg.get("api_key") or "").strip()
        cuit_raw = (str(self._cfg.get("cuit") or "")).strip()
        if not cuit_raw:
            # CUIT de prueba recomendado por AfipSDK para modo dev
            cuit_raw = "20409378472"

        cuit_digits = "".join(ch for ch in cuit_raw if ch.isdigit())
        try:
            cuit = int(cuit_digits)
        except ValueError:
            return False, {"error": f"CUIT inválido: {cuit_raw}"}

        afip_params: Dict[str, Any] = {
            "CUIT": cuit,
            "access_token": api_key,
        }
        # Nota: si más adelante querés usar tu propio certificado,
        # aquí se agregan "cert": ..., "key": ...

        try:
            afip = Afip(afip_params)
        except Exception as e:
            return False, {"error": f"No se pudo inicializar AfipSDK: {e}"}

        # 3) Punto de venta y tipo de comprobante
        pto_vta = int(self._cfg.get("punto_venta") or 1)
        tipo_cbte_str = (self._cfg.get("tipo_cbte") or "FACTURA_B").upper()
        tipo_map = {
            "FACTURA_A": 1,
            "FACTURA_B": 6,
            "FACTURA_C": 11,
        }
        cbte_tipo = tipo_map.get(tipo_cbte_str, 6)  # default B

        # 4) Determinar próximo número de comprobante
        try:
            last = afip.ElectronicBilling.getLastVoucher(pto_vta, cbte_tipo) or 0
            nro = int(last) + 1
        except Exception:
            # Si falla, arrancamos en 1 (no es ideal, pero no rompe la app)
            nro = 1

        # 5) Montos: asumimos TODO al 21% IVA (típico para RI consumidor final)
        total = float(getattr(venta, "total", 0.0) or 0.0)
        iva_rate = 0.21
        if total:
            neto = round(total / (1.0 + iva_rate), 2)
            iva = round(total - neto, 2)
        else:
            neto = 0.0
            iva = 0.0

        hoy = datetime.now().strftime("%Y%m%d")

        data = {
            "CantReg": 1,
            "PtoVta": pto_vta,
            "CbteTipo": cbte_tipo,
            "Concepto": 1,         # 1 = productos
            "DocTipo": 99,         # 99 = consumidor final
            "DocNro": 0,
            "CbteDesde": nro,
            "CbteHasta": nro,
            "CbteFch": int(hoy),
            "ImpTotal": round(total, 2),
            "ImpTotConc": 0.0,
            "ImpNeto": neto,
            "ImpOpEx": 0.0,
            "ImpIVA": iva,
            "ImpTrib": 0.0,
            "MonId": "PES",
            "MonCotiz": 1.0,
            "CondicionIVAReceptorId": 5,   # Consumidor final
            "Iva": [
                {
                    "Id": 5,              # 5 = 21% en AFIP
                    "BaseImp": neto,
                    "Importe": iva,
                }
            ],
        }

        # TODO: si más adelante querés bajar al detalle por ítems, se puede
        # mapear la lista 'items' a la estructura que soporte AfipSDK.

        # 6) Llamar al web service
        try:
            res = afip.ElectronicBilling.createVoucher(data)
        except Exception as e:
            return False, {"error": f"Error al crear comprobante en AFIP: {e}"}

        try:
            cae = res.get("CAE")
            cae_vto = res.get("CAEFchVto")
        except Exception:
            cae = None
            cae_vto = None

        return True, {
            "simulado": False,
            "punto_venta": pto_vta,
            "nro_comprobante": nro,
            "cae": cae,
            "cae_vencimiento": cae_vto,
            "raw_response": res,
        }
