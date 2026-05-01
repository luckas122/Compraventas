# app/firebase_sync.py
# -*- coding: utf-8 -*-
"""
Sincronizacion entre sucursales via Firebase Realtime Database (REST API).
Reemplaza el sistema anterior basado en Gmail SMTP/IMAP.

Arquitectura:
- SQLite local es la base de datos primaria (funciona sin internet)
- Firebase es el bus de sincronizacion (cambios se publican y consumen)
- Cada sucursal ignora sus propios cambios al consumir
- Conflictos: gana el ultimo cambio (last-write-wins por timestamp)
- Cola offline: cambios se guardan localmente si no hay internet
"""

import json
import os
import time
import random
import string
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import requests
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models import Venta, VentaItem, Producto, Proveedor, VentaLog, PagoProveedor, Comprador
from app.config import load as load_config, save as save_config, _get_app_data_dir

logger = logging.getLogger("firebase_sync")

QUEUE_FILENAME = "sync_queue.json"
PENDING_DELETES_FILENAME = "sync_pending_deletes.json"  # v6.7.1
MAX_QUEUE_SIZE = 10000
REQUEST_TIMEOUT = 30   # segundos (para requests normales)
BATCH_TIMEOUT = 120    # segundos (para batch PATCH con muchos datos)
BATCH_SIZE = 500       # productos por batch en sync inicial
PAGE_SIZE = 500  # entradas por pagina en pull (Firebase REST paginacion)


class FirebaseSyncManager:
    """
    Sincronizacion bidireccional entre sucursales via Firebase Realtime Database.
    Usa la REST API de Firebase (no requiere SDKs adicionales).
    """

    def __init__(self, session: Session, sucursal_local: str):
        self.session = session
        self.sucursal_local = sucursal_local
        self._queue_path = os.path.join(_get_app_data_dir(), QUEUE_FILENAME)
        self._log_path = os.path.join(_get_app_data_dir(), "logs", "sync.log")
        self._price_mismatches = []
        os.makedirs(os.path.dirname(self._log_path), exist_ok=True)
        # Adjuntar RotatingFileHandler dedicado al logger del modulo (5MB x 5 backups)
        # para que los _log() escriban con rotacion automatica en lugar del open() manual.
        try:
            from app.logging_setup import get_module_logger
            self._sync_logger = get_module_logger(f"{__name__}.fs", filename="sync.log")
        except Exception:
            self._sync_logger = logger  # fallback al logger del modulo

    # ─── Configuracion ───────────────────────────────────────────────

    def _get_sync_config(self) -> dict:
        cfg = load_config()
        return cfg.get("sync", {})

    def _get_firebase_config(self) -> Tuple[str, str]:
        """Retorna (database_url, auth_token) desde la config."""
        sync_cfg = self._get_sync_config()
        fb = sync_cfg.get("firebase", {})
        return fb.get("database_url", ""), fb.get("auth_token", "")

    # ─── Firebase REST helpers ────────────────────────────────────────

    def _firebase_url(self, path: str) -> str:
        db_url, token = self._get_firebase_config()
        db_url = db_url.rstrip("/")
        path = path.strip("/")
        return f"{db_url}/{path}.json?auth={token}"

    def _firebase_get(self, path: str, params: dict = None) -> Optional[dict]:
        try:
            url = self._firebase_url(path)
            resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
            if resp.status_code != 200:
                self._log(f"GET {path} HTTP {resp.status_code}: {resp.text[:200]}")
                return None
            result = resp.json()
            return result
        except Exception as e:
            self._log(f"GET {path} error: {e}")
            return None

    def _firebase_post(self, path: str, data: dict) -> Optional[str]:
        """POST (push) data. Retorna el push key generado o None."""
        try:
            url = self._firebase_url(path)
            resp = requests.post(url, json=data, timeout=REQUEST_TIMEOUT)
            if resp.status_code != 200:
                self._log(f"POST {path} HTTP {resp.status_code}: {resp.text[:200]}")
                return None
            result = resp.json()
            key = result.get("name")
            self._log(f"POST {path} OK -> {key}")
            return key
        except Exception as e:
            self._log(f"POST {path} error: {e}")
            return None

    def _firebase_put(self, path: str, data) -> bool:
        try:
            url = self._firebase_url(path)
            resp = requests.put(url, json=data, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            return True
        except Exception as e:
            self._log(f"PUT {path} error: {e}")
            return False

    def _firebase_patch(self, path: str, data: dict) -> bool:
        """PATCH (multi-path update) para escribir multiples keys de una vez."""
        try:
            url = self._firebase_url(path)
            resp = requests.patch(url, json=data, timeout=BATCH_TIMEOUT)
            if resp.status_code != 200:
                self._log(f"PATCH {path} HTTP {resp.status_code}: {resp.text[:500]}")
                return False
            return True
        except Exception as e:
            self._log(f"PATCH {path} error: {e}")
            return False

    def _firebase_delete(self, path: str) -> bool:
        """DELETE de un node en Firebase. Usado por el auto-cleanup (v6.6.0)."""
        try:
            url = self._firebase_url(path)
            resp = requests.delete(url, timeout=10)
            if resp.status_code not in (200, 204):
                self._log(f"DELETE {path} HTTP {resp.status_code}: {resp.text[:200]}")
                return False
            return True
        except Exception as e:
            self._log(f"DELETE {path} error: {e}")
            return False

    def _is_old_enough(self, change: dict, safe_window_days: int) -> bool:
        """v6.6.0: True si el cambio tiene timestamp mas viejo que safe_window_days."""
        try:
            ts_ms = int(change.get("timestamp", 0))
            if ts_ms <= 0:
                return False  # sin timestamp: NO borrar (conservador)
            now_ms = int(time.time() * 1000)
            age_ms = now_ms - ts_ms
            return age_ms >= (safe_window_days * 86400 * 1000)
        except Exception:
            return False

    def _is_online(self) -> bool:
        try:
            db_url, token = self._get_firebase_config()
            if not db_url:
                return False
            url = f"{db_url.rstrip('/')}/.json?auth={token}&shallow=true"
            resp = requests.get(url, timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    # ─── Cola offline ─────────────────────────────────────────────────

    def _load_offline_queue(self) -> List[dict]:
        try:
            if os.path.exists(self._queue_path):
                with open(self._queue_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception as e:
            self._log(f"Error cargando cola offline: {e}")
        return []

    def _save_offline_queue(self, queue: List[dict]):
        try:
            with open(self._queue_path, "w", encoding="utf-8") as f:
                json.dump(queue[-MAX_QUEUE_SIZE:], f, ensure_ascii=False)
        except Exception as e:
            self._log(f"Error guardando cola offline: {e}")

    def _enqueue_change(self, tipo: str, accion: str, data: dict):
        queue = self._load_offline_queue()
        queue.append({
            "tipo": tipo,
            "accion": accion,
            "sucursal_origen": self.sucursal_local,
            "timestamp": int(time.time() * 1000),
            "data": data
        })
        self._save_offline_queue(queue)

    def _flush_offline_queue(self, by_type: bool = False):
        """Envia todos los cambios en cola a Firebase.

        v6.7.0: si by_type=True devuelve dict {"productos": N, "ventas": N, ...} con desglose
        por tipo, util para el panel de estado de sync. Si by_type=False (default), mantiene
        el contrato viejo y devuelve solo el int total (compat con callers existentes).
        """
        queue = self._load_offline_queue()
        if not queue:
            return {} if by_type else 0

        sent_by_type: Dict[str, int] = {}
        remaining = []
        for change in queue:
            tipo = change.get("tipo") or "?"
            path = f"cambios/{tipo}"
            key = self._firebase_post(path, change)
            if key:
                sent_by_type[tipo] = sent_by_type.get(tipo, 0) + 1
            else:
                remaining.append(change)

        self._save_offline_queue(remaining)
        total_sent = sum(sent_by_type.values())
        if total_sent > 0:
            self._log(f"Cola offline: {total_sent} enviados ({sent_by_type}), {len(remaining)} pendientes")
        return sent_by_type if by_type else total_sent

    # ─── Push: local -> Firebase ──────────────────────────────────────

    def _resolver_punto_venta(self, sucursal: str) -> int:
        """Devuelve el punto de venta AFIP de la sucursal (con fallback global)."""
        try:
            fiscal = (load_config().get("fiscal") or {})
            por_suc = fiscal.get("puntos_venta_por_sucursal") or {}
            return int(por_suc.get(sucursal) or fiscal.get("punto_venta") or 1)
        except Exception:
            return 1

    def push_venta(self, venta: Venta):
        """Publica una venta nueva en Firebase."""
        items_data = []
        for item in (venta.items or []):
            prod = item.producto
            items_data.append({
                "codigo_barra": prod.codigo_barra if prod else "",
                "nombre": prod.nombre if prod else "",
                "cantidad": item.cantidad,
                "precio_unit": item.precio_unit
            })

        data = {
            "sucursal_origen": self.sucursal_local,
            "timestamp": int(time.time() * 1000),
            "accion": "create",
            "data": {
                "numero_ticket": venta.numero_ticket,
                "numero_ticket_cae": venta.numero_ticket_cae,  # v6.6.0: dashboard ahora muestra este si existe
                "sucursal": venta.sucursal,
                "fecha": venta.fecha.isoformat() if venta.fecha else None,
                "modo_pago": venta.modo_pago,
                "cuotas": venta.cuotas,
                "total": venta.total,
                "subtotal_base": venta.subtotal_base,
                "interes_pct": venta.interes_pct,
                "interes_monto": venta.interes_monto,
                "descuento_pct": venta.descuento_pct,
                "descuento_monto": venta.descuento_monto,
                "pagado": venta.pagado,
                "vuelto": venta.vuelto,
                "afip_cae": venta.afip_cae,
                "afip_cae_vencimiento": venta.afip_cae_vencimiento,
                "afip_numero_comprobante": venta.afip_numero_comprobante,
                "tipo_comprobante": venta.tipo_comprobante,                # v6.6.0
                "punto_venta": self._resolver_punto_venta(venta.sucursal), # v6.6.0: para formatear "0001-XXXX"
                "nota_credito_cae": venta.nota_credito_cae,                # v6.6.0: critico para que el dashboard descuente NCs
                "nota_credito_numero": venta.nota_credito_numero,          # v6.6.0
                "items": items_data
            }
        }

        key = self._firebase_post("cambios/ventas", data)
        if not key:
            self._enqueue_change("ventas", "create", data["data"])
            self._log(f"Venta #{venta.numero_ticket} encolada offline")
        else:
            self._log(f"Venta #{venta.numero_ticket} publicada: {key}")

    def push_venta_modificada(self, venta: Venta):
        """Publica una modificacion de venta (devolucion / nota de credito) en Firebase."""
        items_data = []
        for item in (venta.items or []):
            prod = item.producto
            items_data.append({
                "codigo_barra": prod.codigo_barra if prod else "",
                "nombre": prod.nombre if prod else "",
                "cantidad": item.cantidad,
                "precio_unit": item.precio_unit
            })

        data = {
            "sucursal_origen": self.sucursal_local,
            "timestamp": int(time.time() * 1000),
            "accion": "update",
            "data": {
                "numero_ticket": venta.numero_ticket,
                "numero_ticket_cae": venta.numero_ticket_cae,           # v6.6.0
                "sucursal": venta.sucursal,
                "total": venta.total,
                "vuelto": venta.vuelto,
                # Campos AFIP / NC: criticos para que el dashboard refleje el estado correcto
                # despues de una devolucion o nota de credito (v6.6.0)
                "afip_cae": venta.afip_cae,
                "afip_numero_comprobante": venta.afip_numero_comprobante,
                "tipo_comprobante": venta.tipo_comprobante,
                "nota_credito_cae": venta.nota_credito_cae,             # v6.6.0
                "nota_credito_numero": venta.nota_credito_numero,       # v6.6.0
                "items": items_data
            }
        }

        key = self._firebase_post("cambios/ventas", data)
        if not key:
            self._enqueue_change("ventas", "update", data["data"])
        else:
            self._log(f"Venta #{venta.numero_ticket} modificada: {key}")

    def push_venta_eliminada(self, venta: Venta):
        """v6.7.1: Publica la eliminacion de una venta en Firebase.

        Identificadores enviados: numero_ticket, numero_ticket_cae, afip_numero_comprobante,
        sucursal — la otra sucursal busca la venta local por cualquiera de ellos.
        """
        data = {
            "sucursal_origen": self.sucursal_local,
            "timestamp": int(time.time() * 1000),
            "accion": "delete",
            "data": {
                "numero_ticket": venta.numero_ticket,
                "numero_ticket_cae": venta.numero_ticket_cae,
                "afip_numero_comprobante": venta.afip_numero_comprobante,
                "sucursal": venta.sucursal,
            }
        }

        key = self._firebase_post("cambios/ventas", data)
        if not key:
            self._enqueue_change("ventas", "delete", data["data"])
            self._log(f"Venta #{venta.numero_ticket} (delete) encolada offline")
        else:
            self._log(f"Venta #{venta.numero_ticket} ELIMINADA publicada: {key}")

    def push_producto(self, producto: Producto, accion: str = "upsert"):
        """Publica un producto creado/actualizado/eliminado en Firebase."""
        sync_cfg = self._get_sync_config()
        if not sync_cfg.get("sync_productos", True):
            return

        data = {
            "sucursal_origen": self.sucursal_local,
            "timestamp": int(time.time() * 1000),
            "accion": accion,
            "data": {
                "codigo_barra": producto.codigo_barra,
                "nombre": producto.nombre,
                "precio": producto.precio,
                "categoria": producto.categoria,
                "telefono": getattr(producto, "telefono", None),
                "numero_cuenta": getattr(producto, "numero_cuenta", None),
                "cbu": getattr(producto, "cbu", None),
            }
        }

        key = self._firebase_post("cambios/productos", data)
        if not key:
            self._enqueue_change("productos", accion, data["data"])
        else:
            self._log(f"Producto '{producto.codigo_barra}' ({accion}): {key}")

    def push_productos_batch(self, productos) -> bool:
        """Publica varios productos en un solo PATCH (1 HTTP request).
        Usado tras importar Excel para evitar N requests seriados.
        """
        if not productos:
            return True
        sync_cfg = self._get_sync_config()
        if not sync_cfg.get("sync_productos", True):
            return True
        ts_base = int(time.time() * 1000)
        batch = {}
        data_by_key = {}
        for i, prod in enumerate(productos):
            key = self._generate_push_key()
            data = {
                "codigo_barra": prod.codigo_barra,
                "nombre": prod.nombre,
                "precio": prod.precio,
                "categoria": prod.categoria,
                "telefono": getattr(prod, "telefono", None),
                "numero_cuenta": getattr(prod, "numero_cuenta", None),
                "cbu": getattr(prod, "cbu", None),
            }
            batch[key] = {
                "sucursal_origen": self.sucursal_local,
                "timestamp": ts_base + i,
                "accion": "upsert",
                "data": data,
            }
            data_by_key[key] = data
        ok = self._batch_patch("cambios/productos", batch)
        if not ok:
            # Fallback: encolar offline uno por uno
            for key, data in data_by_key.items():
                self._enqueue_change("productos", "upsert", data)
        self._log(f"Batch push productos: {len(productos)} ({'OK' if ok else 'FAIL->queue'})")
        return ok

    def push_producto_eliminado(self, codigo_barra: str):
        """Publica la eliminacion de un producto en Firebase."""
        sync_cfg = self._get_sync_config()
        if not sync_cfg.get("sync_productos", True):
            return

        data = {
            "sucursal_origen": self.sucursal_local,
            "timestamp": int(time.time() * 1000),
            "accion": "delete",
            "data": {"codigo_barra": codigo_barra}
        }

        key = self._firebase_post("cambios/productos", data)
        if not key:
            self._enqueue_change("productos", "delete", data["data"])

    def push_proveedor(self, proveedor: Proveedor, accion: str = "upsert"):
        """Publica un proveedor creado/actualizado en Firebase."""
        sync_cfg = self._get_sync_config()
        if not sync_cfg.get("sync_proveedores", True):
            return

        data = {
            "sucursal_origen": self.sucursal_local,
            "timestamp": int(time.time() * 1000),
            "accion": accion,
            "data": {
                "nombre": (proveedor.nombre or "").strip(),
                "telefono": proveedor.telefono,
                "numero_cuenta": proveedor.numero_cuenta,
                "cbu": proveedor.cbu,
            }
        }

        key = self._firebase_post("cambios/proveedores", data)
        if not key:
            self._enqueue_change("proveedores", accion, data["data"])
        else:
            self._log(f"Proveedor '{proveedor.nombre}' ({accion}): {key}")

    def push_proveedor_eliminado(self, nombre: str):
        """Publica la eliminacion de un proveedor en Firebase."""
        sync_cfg = self._get_sync_config()
        if not sync_cfg.get("sync_proveedores", True):
            return

        data = {
            "sucursal_origen": self.sucursal_local,
            "timestamp": int(time.time() * 1000),
            "accion": "delete",
            "data": {"nombre": nombre}
        }

        key = self._firebase_post("cambios/proveedores", data)
        if not key:
            self._enqueue_change("proveedores", "delete", data["data"])

    def push_pago_proveedor(self, pago):
        """Publica un pago a proveedor en Firebase."""
        data = {
            "sucursal_origen": self.sucursal_local,
            "timestamp": int(time.time() * 1000),
            "accion": "create",
            "data": {
                "numero_ticket": getattr(pago, 'numero_ticket', None),
                "sucursal": getattr(pago, 'sucursal', ''),
                "fecha": pago.fecha.isoformat() if pago.fecha else None,
                "proveedor_nombre": getattr(pago, 'proveedor_nombre', ''),
                "monto": float(getattr(pago, 'monto', 0) or 0),
                "metodo_pago": getattr(pago, 'metodo_pago', 'Efectivo'),
                "pago_de_caja": bool(getattr(pago, 'pago_de_caja', False)),
                "incluye_iva": bool(getattr(pago, 'incluye_iva', False)),
                "nota": getattr(pago, 'nota', '') or '',
            }
        }

        key = self._firebase_post("cambios/pagos_proveedores", data)
        if not key:
            self._enqueue_change("pagos_proveedores", "create", data["data"])
            self._log(f"Pago prov #{pago.numero_ticket} encolado offline")
        else:
            self._log(f"Pago prov #{pago.numero_ticket} a {pago.proveedor_nombre}: {key}")

    def push_comprador(self, comprador: Comprador, accion: str = "upsert"):
        """v6.7.0: Publica un comprador (cliente) creado/actualizado en Firebase."""
        data = {
            "sucursal_origen": self.sucursal_local,
            "timestamp": int(time.time() * 1000),
            "accion": accion,
            "data": {
                "cuit": (comprador.cuit or "").strip(),
                "nombre": comprador.nombre or "",
                "domicilio": comprador.domicilio or "",
                "localidad": comprador.localidad or "",
                "codigo_postal": comprador.codigo_postal or "",
                "condicion": comprador.condicion or "",
            }
        }

        key = self._firebase_post("cambios/compradores", data)
        if not key:
            self._enqueue_change("compradores", accion, data["data"])
        else:
            self._log(f"Comprador CUIT {comprador.cuit} ({accion}): {key}")

    def push_comprador_eliminado(self, cuit: str):
        """v6.7.0: Publica la eliminacion de un comprador en Firebase."""
        data = {
            "sucursal_origen": self.sucursal_local,
            "timestamp": int(time.time() * 1000),
            "accion": "delete",
            "data": {"cuit": (cuit or "").strip()}
        }

        key = self._firebase_post("cambios/compradores", data)
        if not key:
            self._enqueue_change("compradores", "delete", data["data"])

    # ─── Sync inicial: subir todo lo existente ───────────────────────

    @staticmethod
    def _generate_push_key():
        """Genera un key unico estilo Firebase push key (20 chars)."""
        chars = "-0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_abcdefghijklmnopqrstuvwxyz"
        ts = int(time.time() * 1000)
        key_parts = []
        for _ in range(8):
            key_parts.append(chars[ts % 64])
            ts //= 64
        key_parts.reverse()
        # 12 chars aleatorios
        for _ in range(12):
            key_parts.append(random.choice(chars))
        return "".join(key_parts)

    def _batch_patch(self, path: str, batch: dict) -> bool:
        """Envia un batch de datos via PATCH (multi-path update)."""
        try:
            url = self._firebase_url(path)
            resp = requests.patch(url, json=batch, timeout=BATCH_TIMEOUT)
            if resp.status_code != 200:
                self._log(f"BATCH PATCH {path} HTTP {resp.status_code}: {resp.text[:200]}")
                return False
            return True
        except Exception as e:
            self._log(f"BATCH PATCH {path} error: {e}")
            return False

    # Tipos validos para bulk push selectivo (v6.7.0)
    _BULK_PUSH_TIPOS = ("productos", "proveedores", "ventas", "pagos_proveedores", "compradores")

    def push_all_existing(self, callback=None, tipos=None) -> Dict[str, int]:
        """
        Sube los datos locales existentes a Firebase usando batch PATCH.

        v6.7.0: `tipos` es un iterable con los tipos a subir. Si es None, por compatibilidad
        sube productos+proveedores (comportamiento previo). Tipos validos:
            "productos", "proveedores", "ventas", "pagos_proveedores", "compradores".

        En vez de 1 HTTP request por item (14K requests = horas), agrupa de a BATCH_SIZE (500)
        en un solo PATCH (28 requests = minutos).

        callback(progreso, total, tipo) se llama para informar progreso.
        Retorna {"productos": N, "proveedores": N, "ventas": N, "pagos_proveedores": N,
                 "compradores": N, "errores": N}
        """
        if tipos is None:
            seleccion = {"productos", "proveedores"}
        else:
            seleccion = {t for t in tipos if t in self._BULK_PUSH_TIPOS}

        result = {t: 0 for t in self._BULK_PUSH_TIPOS}
        result["errores"] = 0

        if "productos" in seleccion:
            self._push_all_productos_batch(result, callback)
        if "proveedores" in seleccion:
            self._push_all_proveedores_batch(result, callback)
        if "compradores" in seleccion:
            self._push_all_compradores_batch(result, callback)
        if "ventas" in seleccion:
            self._push_all_ventas_batch(result, callback)
        if "pagos_proveedores" in seleccion:
            self._push_all_pagos_proveedores_batch(result, callback)

        self._log(f"Sync inicial completada (tipos={sorted(seleccion)}): {result}")
        return result

    def _push_all_productos_batch(self, result: dict, callback=None) -> None:
        ts_base = int(time.time() * 1000)
        try:
            productos = self.session.query(Producto).all()
            total = len(productos)
            self._log(f"Sync inicial: subiendo {total} productos en batches de {BATCH_SIZE}...")

            batch = {}
            for i, prod in enumerate(productos):
                key = self._generate_push_key()
                batch[key] = {
                    "sucursal_origen": self.sucursal_local,
                    "timestamp": ts_base + i,
                    "accion": "upsert",
                    "data": {
                        "codigo_barra": prod.codigo_barra,
                        "nombre": prod.nombre,
                        "precio": prod.precio,
                        "categoria": prod.categoria,
                        "telefono": getattr(prod, "telefono", None),
                        "numero_cuenta": getattr(prod, "numero_cuenta", None),
                        "cbu": getattr(prod, "cbu", None),
                    },
                }
                if len(batch) >= BATCH_SIZE or i == total - 1:
                    ok = self._batch_patch("cambios/productos", batch)
                    if ok:
                        result["productos"] += len(batch)
                    else:
                        result["errores"] += len(batch)
                        self._log(f"Batch productos fallo ({len(batch)} items)")
                    batch = {}
                    if callback:
                        callback(i + 1, total, "productos")
        except Exception as e:
            self._log(f"Sync inicial productos error: {e}")

    def _push_all_proveedores_batch(self, result: dict, callback=None) -> None:
        ts_base = int(time.time() * 1000)
        try:
            proveedores = self.session.query(Proveedor).all()
            total = len(proveedores)
            self._log(f"Sync inicial: subiendo {total} proveedores en batches de {BATCH_SIZE}...")

            batch = {}
            for i, prov in enumerate(proveedores):
                key = self._generate_push_key()
                batch[key] = {
                    "sucursal_origen": self.sucursal_local,
                    "timestamp": ts_base + i,
                    "accion": "upsert",
                    "data": {
                        "nombre": prov.nombre,
                        "telefono": prov.telefono,
                        "numero_cuenta": prov.numero_cuenta,
                        "cbu": prov.cbu,
                    },
                }
                if len(batch) >= BATCH_SIZE or i == total - 1:
                    ok = self._batch_patch("cambios/proveedores", batch)
                    if ok:
                        result["proveedores"] += len(batch)
                    else:
                        result["errores"] += len(batch)
                        self._log(f"Batch proveedores fallo ({len(batch)} items)")
                    batch = {}
                    if callback:
                        callback(i + 1, total, "proveedores")
        except Exception as e:
            self._log(f"Sync inicial proveedores error: {e}")

    def _push_all_compradores_batch(self, result: dict, callback=None) -> None:
        """v6.7.0: sube todos los compradores (clientes) locales en batches PATCH."""
        ts_base = int(time.time() * 1000)
        try:
            compradores = self.session.query(Comprador).all()
            total = len(compradores)
            self._log(f"Sync inicial: subiendo {total} compradores en batches de {BATCH_SIZE}...")

            batch = {}
            for i, comp in enumerate(compradores):
                key = self._generate_push_key()
                batch[key] = {
                    "sucursal_origen": self.sucursal_local,
                    "timestamp": ts_base + i,
                    "accion": "upsert",
                    "data": {
                        "cuit": (comp.cuit or "").strip(),
                        "nombre": comp.nombre or "",
                        "domicilio": comp.domicilio or "",
                        "localidad": comp.localidad or "",
                        "codigo_postal": comp.codigo_postal or "",
                        "condicion": comp.condicion or "",
                    },
                }
                if len(batch) >= BATCH_SIZE or i == total - 1:
                    ok = self._batch_patch("cambios/compradores", batch)
                    if ok:
                        result["compradores"] += len(batch)
                    else:
                        result["errores"] += len(batch)
                        self._log(f"Batch compradores fallo ({len(batch)} items)")
                    batch = {}
                    if callback:
                        callback(i + 1, total, "compradores")
        except Exception as e:
            self._log(f"Sync inicial compradores error: {e}")

    def _push_all_ventas_batch(self, result: dict, callback=None) -> None:
        """v6.7.0: sube todas las ventas locales (creates) y luego sus NCs como updates.

        Las NCs van separadas con accion="update" después del create para que el dashboard
        merge la información sobre la venta original (mantiene compatibilidad con el flujo
        normal en linea de push_venta_modificada).
        """
        ts_base = int(time.time() * 1000)
        try:
            ventas = self.session.query(Venta).all()
            total = len(ventas)
            self._log(f"Sync inicial: subiendo {total} ventas en batches de {BATCH_SIZE}...")

            batch = {}
            ncs_updates = []  # acumular NCs para enviar después
            for i, v in enumerate(ventas):
                key = self._generate_push_key()
                items_data = []
                for it in (v.items or []):
                    prod = it.producto
                    items_data.append({
                        "codigo_barra": prod.codigo_barra if prod else "",
                        "nombre": prod.nombre if prod else "",
                        "cantidad": it.cantidad,
                        "precio_unit": it.precio_unit,
                    })

                # CREATE de la venta original (sin nota de credito todavia)
                batch[key] = {
                    "sucursal_origen": self.sucursal_local,
                    "timestamp": ts_base + i,
                    "accion": "create",
                    "data": {
                        "numero_ticket": v.numero_ticket,
                        "numero_ticket_cae": v.numero_ticket_cae,
                        "sucursal": v.sucursal,
                        "fecha": v.fecha.isoformat() if v.fecha else None,
                        "modo_pago": v.modo_pago,
                        "cuotas": v.cuotas,
                        "total": v.total,
                        "subtotal_base": v.subtotal_base,
                        "interes_pct": v.interes_pct,
                        "interes_monto": v.interes_monto,
                        "descuento_pct": v.descuento_pct,
                        "descuento_monto": v.descuento_monto,
                        "pagado": v.pagado,
                        "vuelto": v.vuelto,
                        "afip_cae": v.afip_cae,
                        "afip_cae_vencimiento": v.afip_cae_vencimiento,
                        "afip_numero_comprobante": v.afip_numero_comprobante,
                        "tipo_comprobante": v.tipo_comprobante,
                        "punto_venta": self._resolver_punto_venta(v.sucursal),
                        # No mandamos nota_credito_* en el create — se manda como update separado
                        "items": items_data,
                    },
                }

                # Si la venta tiene NC, encolar el update correspondiente
                if v.nota_credito_cae:
                    ncs_updates.append({
                        "venta": v,
                        "items_data": items_data,
                    })

                if len(batch) >= BATCH_SIZE or i == total - 1:
                    ok = self._batch_patch("cambios/ventas", batch)
                    if ok:
                        result["ventas"] += len(batch)
                    else:
                        result["errores"] += len(batch)
                        self._log(f"Batch ventas fallo ({len(batch)} items)")
                    batch = {}
                    if callback:
                        callback(i + 1, total, "ventas")

            # Segunda pasada: NCs como updates (timestamp posterior al create)
            if ncs_updates:
                self._log(f"Sync inicial: subiendo {len(ncs_updates)} notas de credito como updates...")
                ts_nc = ts_base + total + 1
                nc_batch = {}
                for j, item in enumerate(ncs_updates):
                    v = item["venta"]
                    key = self._generate_push_key()
                    nc_batch[key] = {
                        "sucursal_origen": self.sucursal_local,
                        "timestamp": ts_nc + j,
                        "accion": "update",
                        "data": {
                            "numero_ticket": v.numero_ticket,
                            "numero_ticket_cae": v.numero_ticket_cae,
                            "sucursal": v.sucursal,
                            "total": v.total,
                            "vuelto": v.vuelto,
                            "afip_cae": v.afip_cae,
                            "afip_numero_comprobante": v.afip_numero_comprobante,
                            "tipo_comprobante": v.tipo_comprobante,
                            "nota_credito_cae": v.nota_credito_cae,
                            "nota_credito_numero": v.nota_credito_numero,
                            "items": item["items_data"],
                        },
                    }
                    if len(nc_batch) >= BATCH_SIZE or j == len(ncs_updates) - 1:
                        ok = self._batch_patch("cambios/ventas", nc_batch)
                        if ok:
                            result["ventas"] += len(nc_batch)
                        else:
                            result["errores"] += len(nc_batch)
                            self._log(f"Batch NCs fallo ({len(nc_batch)} items)")
                        nc_batch = {}
                        if callback:
                            callback(total + j + 1, total + len(ncs_updates), "ventas")
        except Exception as e:
            self._log(f"Sync inicial ventas error: {e}")

    def _push_all_pagos_proveedores_batch(self, result: dict, callback=None) -> None:
        """v6.7.0: sube todos los pagos a proveedores locales en batches PATCH."""
        ts_base = int(time.time() * 1000)
        try:
            pagos = self.session.query(PagoProveedor).all()
            total = len(pagos)
            self._log(f"Sync inicial: subiendo {total} pagos a proveedores en batches de {BATCH_SIZE}...")

            batch = {}
            for i, pago in enumerate(pagos):
                key = self._generate_push_key()
                batch[key] = {
                    "sucursal_origen": self.sucursal_local,
                    "timestamp": ts_base + i,
                    "accion": "create",
                    "data": {
                        "numero_ticket": getattr(pago, "numero_ticket", None),
                        "sucursal": getattr(pago, "sucursal", "") or self.sucursal_local,
                        "fecha": pago.fecha.isoformat() if pago.fecha else None,
                        "proveedor_nombre": getattr(pago, "proveedor_nombre", "") or "",
                        "monto": float(getattr(pago, "monto", 0) or 0),
                        "metodo_pago": getattr(pago, "metodo_pago", "Efectivo"),
                        "pago_de_caja": bool(getattr(pago, "pago_de_caja", False)),
                        "incluye_iva": bool(getattr(pago, "incluye_iva", False)),
                        "nota": getattr(pago, "nota", "") or "",
                    },
                }
                if len(batch) >= BATCH_SIZE or i == total - 1:
                    ok = self._batch_patch("cambios/pagos_proveedores", batch)
                    if ok:
                        result["pagos_proveedores"] += len(batch)
                    else:
                        result["errores"] += len(batch)
                        self._log(f"Batch pagos_proveedores fallo ({len(batch)} items)")
                    batch = {}
                    if callback:
                        callback(i + 1, total, "pagos_proveedores")
        except Exception as e:
            self._log(f"Sync inicial pagos_proveedores error: {e}")

    # ─── Pull: Firebase -> local ──────────────────────────────────────

    def _get_last_processed_keys(self) -> Dict[str, Optional[str]]:
        """Retorna dict con el ultimo key procesado por cada tipo de entidad."""
        sync_cfg = self._get_sync_config()
        keys = sync_cfg.get("last_processed_keys", {})
        if not isinstance(keys, dict):
            # Migrar desde el formato viejo (key unico global)
            old_key = sync_cfg.get("last_processed_key")
            keys = {
                "ventas": old_key, "productos": old_key, "proveedores": old_key,
                "pagos_proveedores": old_key, "compradores": old_key,
            }
        # v6.7.0: garantizar todos los tipos presentes (compradores agregado)
        for _t in ("ventas", "productos", "proveedores", "pagos_proveedores", "compradores"):
            keys.setdefault(_t, None)
        return keys

    def _set_last_processed_key(self, tipo: str, key: str):
        """Guarda el ultimo key procesado para un tipo especifico."""
        cfg = load_config()
        sync = cfg.setdefault("sync", {})
        keys = sync.setdefault("last_processed_keys", {})
        keys[tipo] = key
        save_config(cfg)
        # Tambien guardar en Firebase para referencia
        self._firebase_put(f"meta/last_processed/{self.sucursal_local}/{tipo}", key)

    def reset_pull_cursors(self) -> None:
        """v6.6.2: Resetea last_processed_keys para forzar un pull completo desde el principio.

        Util cuando la sincronizacion se atasca o el usuario quiere garantizar que se
        re-procesen todos los cambios disponibles en Firebase. Las ventas/productos
        que ya existen localmente son detectados como duplicados y skipped (no se
        re-importan), pero los faltantes se aplican.

        Tambien limpia el fail counter para que items que fueron skipeados puedan
        reintentarse desde cero.
        """
        cfg = load_config()
        sync = cfg.setdefault("sync", {})
        sync["last_processed_keys"] = {
            "ventas": None, "productos": None, "proveedores": None,
            "pagos_proveedores": None, "compradores": None,
        }
        save_config(cfg)
        # Limpiar fail counter para que items skipeados reintenten
        try:
            self._save_fail_counter({})
        except Exception:
            pass
        self._log("[FORCE-PULL] last_processed_keys reseteado a None y fail_counter limpiado")

    def force_pull_all(self, progress_callback=None, cancel_check=None) -> Dict[str, int]:
        """v6.6.2: Resetea cursores y dispara pull completo. Retorna mismo formato que pull_changes().

        v6.6.3: acepta progress_callback(tipo, page, applied, errors) y cancel_check() opcionales.
        """
        self.reset_pull_cursors()
        return self.pull_changes(progress_callback=progress_callback, cancel_check=cancel_check)

    def pull_changes(self, progress_callback=None, cancel_check=None) -> Dict[str, int]:
        """
        Descarga y aplica cambios nuevos desde Firebase.
        Retorna {"ventas": N, "productos": N, "proveedores": N, "errores": N}

        v6.6.3:
          - progress_callback(tipo: str, page: int, applied: int, errors: int) — llamado tras cada pagina
          - cancel_check() -> bool — si retorna True, se aborta gracefully
        """
        result = {
            "ventas": 0, "productos": 0, "proveedores": 0,
            "pagos_proveedores": 0, "compradores": 0, "errores": 0,
        }
        last_keys = self._get_last_processed_keys()

        for tipo in ["ventas", "productos", "proveedores", "pagos_proveedores", "compradores"]:
            if cancel_check and cancel_check():
                self._log(f"Pull cancelado por el usuario antes de procesar {tipo}")
                break
            entity_last_key = last_keys.get(tipo)
            count, errors, new_last = self._pull_entity(
                tipo, entity_last_key,
                progress_callback=progress_callback,
                cancel_check=cancel_check,
            )
            result[tipo] = count
            result["errores"] += errors
            if new_last:
                self._set_last_processed_key(tipo, new_last)

        return result

    def _pull_entity(self, tipo: str, last_key: Optional[str],
                     progress_callback=None, cancel_check=None) -> Tuple[int, int, Optional[str]]:
        """
        Descarga cambios de un tipo CON PAGINACION.
        Firebase REST limita respuestas grandes; usamos limitToFirst para paginar.
        Retorna (aplicados, errores, ultimo_key).

        v6.6.0: auto-cleanup en Firebase. Tras procesar un cambio (propio o ajeno
        aplicado OK), si paso la safe_window_days (default 30), se borra de la nube.
        Esto reduce la cuota Firebase casi a 0 en estado estable.

        v6.6.3:
          - progress_callback(tipo, page, applied, errors) — llamado al final de cada pagina
          - cancel_check() -> bool — si True, se interrumpe entre paginas
        """
        total_applied = 0
        total_errors = 0
        total_deleted = 0
        cursor = last_key
        page_num = 0

        # v6.6.0: configuracion de auto-cleanup (v6.6.3: default subido a 30 para no perder histórico del dashboard)
        cleanup_cfg = (self._get_sync_config().get("cleanup") or {})
        cleanup_enabled = bool(cleanup_cfg.get("enabled", True))
        safe_window_days = int(cleanup_cfg.get("safe_window_days", 30))

        self._log(f"Pull {tipo}: inicio, last_key={last_key} (cleanup={cleanup_enabled} safe={safe_window_days}d)")

        while True:
            # v6.6.3: chequear cancelacion antes de cada pagina
            if cancel_check and cancel_check():
                self._log(f"Pull {tipo}: cancelado por el usuario en pagina {page_num + 1}")
                break
            page_num += 1
            params = {
                "orderBy": '"$key"',
                "limitToFirst": PAGE_SIZE + 1,  # +1 porque startAt es inclusivo
            }
            if cursor:
                params["startAt"] = f'"{cursor}"'
            else:
                params["limitToFirst"] = PAGE_SIZE

            data = self._firebase_get(f"cambios/{tipo}", params)
            if data is None:
                self._log(f"Pull {tipo} pag{page_num}: error de red o auth")
                break
            if not isinstance(data, dict) or len(data) == 0:
                self._log(f"Pull {tipo} pag{page_num}: sin mas cambios")
                break

            keys = sorted(data.keys())
            self._log(f"Pull {tipo} pag{page_num}: {len(keys)} entradas recibidas")

            page_applied = 0
            skipped_own = 0
            skipped_cursor = 0
            skipped_invalid = 0
            skipped_apply_fail = 0
            canceled_mid_page = False
            for _idx, push_key in enumerate(keys):
                # v6.6.4: progress callback cada 25 items para que el usuario vea avance
                # antes era solo al final de cada pagina (parecia colgado en pages grandes)
                if progress_callback and _idx > 0 and (_idx % 25) == 0:
                    try:
                        progress_callback(tipo, page_num, total_applied + page_applied, total_errors)
                    except Exception:
                        pass
                if cancel_check and cancel_check():
                    canceled_mid_page = True
                    break
                # Saltar el key del cursor (startAt es inclusivo)
                if push_key == cursor:
                    skipped_cursor += 1
                    continue

                change = data[push_key]
                if not isinstance(change, dict):
                    skipped_invalid += 1
                    cursor = push_key
                    continue

                # Ignorar cambios propios (pero borrarlos de Firebase si pasaron safe_window)
                origen = change.get("sucursal_origen", "???")
                if origen == self.sucursal_local:
                    skipped_own += 1
                    cursor = push_key
                    # v6.6.0: cleanup de mis propios cambios viejos
                    if cleanup_enabled and self._is_old_enough(change, safe_window_days):
                        if self._firebase_delete(f"cambios/{tipo}/{push_key}"):
                            total_deleted += 1
                    continue

                try:
                    accion = change.get("accion", "create")
                    inner_data = change.get("data", {})

                    # v6.6.4: reintentar hasta 3 veces con back-off corto (1, 2, 4s = 7s max)
                    # antes era 5 × (3,6,12,24,48s = 93s), demasiado lento si hay contencion
                    ok = False
                    for _attempt in range(3):
                        try:
                            ok = self._apply_change(tipo, change)
                            break
                        except Exception as _retry_err:
                            if "database is locked" in str(_retry_err) and _attempt < 2:
                                import time as _t
                                wait = 1 * (2 ** _attempt)  # 1, 2, 4 seg
                                self._log(f"  DB locked, esperando {wait}s ({_attempt+1}/3)...")
                                try:
                                    self.session.rollback()
                                except Exception as _rb_err:
                                    self._log(f"  WARN: rollback fallo durante retry DB-locked: {_rb_err}")
                                _t.sleep(wait)
                                continue
                            raise

                    if ok:
                        page_applied += 1
                        self._log(f"  -> APLICADO OK")
                        self._reset_fail_count(tipo, push_key)
                    else:
                        skipped_apply_fail += 1
                        self._log(f"  -> NO APLICADO (ya existe o datos invalidos)")
                        self._reset_fail_count(tipo, push_key)
                    cursor = push_key
                    # v6.6.0: cleanup tras aplicar (o saltar duplicado) si paso safe_window
                    if cleanup_enabled and self._is_old_enough(change, safe_window_days):
                        if self._firebase_delete(f"cambios/{tipo}/{push_key}"):
                            total_deleted += 1
                except Exception as e:
                    # v6.6.2: skip-on-fail. Si una misma key falla MAX_RETRIES veces seguidas
                    # avanzamos el cursor de todas formas para no atascar el pull entero.
                    # El item se registra en sync_skipped.log para que el usuario pueda
                    # inspeccionar manualmente.
                    fail_count = self._bump_fail_count(tipo, push_key)
                    MAX_RETRIES = 3
                    if fail_count >= MAX_RETRIES:
                        self._log(f"Error aplicando {tipo}/{push_key}: {e}")
                        self._log(f"  -> SKIPPED PERMANENTE (fallo {fail_count} veces). Cursor avanza.")
                        self._log_skipped(tipo, push_key, change, str(e), fail_count)
                        cursor = push_key
                        skipped_apply_fail += 1
                        # cleanup tambien: si paso safe_window, sacarlo de Firebase para
                        # que no nos siga molestando
                        if cleanup_enabled and self._is_old_enough(change, safe_window_days):
                            if self._firebase_delete(f"cambios/{tipo}/{push_key}"):
                                total_deleted += 1
                    else:
                        self._log(f"Error aplicando {tipo}/{push_key}: {e}")
                        total_errors += 1
                        # NO avanzar cursor: se reintentara en el proximo ciclo
                        self._log(f"  -> CURSOR NO AVANZADO, se reintentara ({fail_count}/{MAX_RETRIES})")

            total_applied += page_applied
            self._log(f"Pull {tipo} pag{page_num} resumen: "
                      f"aplicados={page_applied}, skip_cursor={skipped_cursor}, "
                      f"skip_propios={skipped_own}, skip_invalidos={skipped_invalid}, "
                      f"no_aplicados={skipped_apply_fail}, "
                      f"borrados_firebase={total_deleted}")

            # v6.6.3: notificar progreso a la UI
            if progress_callback:
                try:
                    progress_callback(tipo, page_num, total_applied, total_errors)
                except Exception as _cb_err:
                    self._log(f"WARN: progress_callback fallo: {_cb_err}")

            # v6.6.4: si se cancelo durante esta pagina, salir del while
            if canceled_mid_page:
                self._log(f"Pull {tipo}: cancelado por el usuario mid-pagina")
                break

            # Si hubo errores irrecuperables, parar paginacion y reintentar proximo ciclo
            if total_errors > 0:
                self._log(f"Pull {tipo}: detenido por errores, reintentara en proximo ciclo")
                break

            # Si recibimos menos de PAGE_SIZE+1, ya no hay mas paginas
            expected = PAGE_SIZE + 1 if last_key or (page_num > 1) else PAGE_SIZE
            if len(keys) < expected:
                break

        self._log(f"Pull {tipo}: total {total_applied} aplicados, {total_errors} errores en {page_num} paginas")
        return total_applied, total_errors, cursor

    def _apply_change(self, tipo: str, change: dict) -> bool:
        accion = change.get("accion", "create")
        data = change.get("data", {})
        timestamp = change.get("timestamp", 0)

        if tipo == "ventas":
            if accion == "update":
                return self._apply_venta_update(data)
            if accion == "delete":
                return self._apply_venta_delete(data)
            return self._apply_venta(data)
        elif tipo == "productos":
            if accion == "delete":
                # v6.7.1: pasar sucursal de origen para mostrarla en el popup de confirmacion
                data["_sucursal_origen"] = change.get("sucursal_origen", "")
                return self._apply_producto_delete(data)
            return self._apply_producto(data, timestamp)
        elif tipo == "proveedores":
            if accion == "delete":
                return self._apply_proveedor_delete(data)
            return self._apply_proveedor(data, timestamp)
        elif tipo == "pagos_proveedores":
            return self._apply_pago_proveedor(data)
        elif tipo == "compradores":
            if accion == "delete":
                return self._apply_comprador_delete(data)
            return self._apply_comprador(data, timestamp)
        return False

    # ─── Aplicar cambios a SQLite local ───────────────────────────────

    def _apply_venta(self, data: dict) -> bool:
        """Inserta una venta remota en la base local.

        v6.6.4: acepta ventas con numero_ticket=null (caso v6.5.1 con tarjeta/CAE),
        usando numero_ticket_cae o afip_numero_comprobante como identidad fallback.
        """
        sucursal = data.get("sucursal")
        if not sucursal:
            self._log(f"  _apply_venta SKIP: sin sucursal")
            return False

        numero_ticket = data.get("numero_ticket") or 0
        numero_ticket_cae = data.get("numero_ticket_cae") or 0
        afip_num = data.get("afip_numero_comprobante") or 0

        # Verificar duplicado: priorizar numero_ticket > numero_ticket_cae > afip_numero_comprobante
        existing = None
        if numero_ticket:
            existing = self.session.query(Venta).filter_by(
                numero_ticket=numero_ticket, sucursal=sucursal,
            ).first()
        if not existing and numero_ticket_cae:
            existing = self.session.query(Venta).filter_by(
                numero_ticket_cae=numero_ticket_cae, sucursal=sucursal,
            ).first()
        if not existing and afip_num:
            existing = self.session.query(Venta).filter_by(
                afip_numero_comprobante=afip_num, sucursal=sucursal,
            ).first()
        if existing:
            self._log(f"  _apply_venta SKIP: ya existe (id={existing.id}, ticket={numero_ticket}, cae_ticket={numero_ticket_cae}, afip_num={afip_num})")
            return False  # Ya existe

        # Si no tiene ningun identificador (ni ticket, ni cae, ni afip_num), usar
        # combinacion fecha+total+sucursal como heuristica para evitar duplicados puros.
        if not numero_ticket and not numero_ticket_cae and not afip_num:
            fecha_str = data.get("fecha", "")
            total_val = float(data.get("total", 0))
            try:
                from datetime import datetime as _dt
                fecha_dt = _dt.fromisoformat(fecha_str) if fecha_str else None
            except Exception:
                fecha_dt = None
            if fecha_dt is not None:
                heur_existing = self.session.query(Venta).filter_by(
                    sucursal=sucursal, fecha=fecha_dt, total=total_val,
                ).first()
                if heur_existing:
                    self._log(f"  _apply_venta SKIP heuristic: ya existe ({sucursal}, {fecha_dt}, ${total_val})")
                    return False

        try:
            fecha = datetime.fromisoformat(data["fecha"]) if data.get("fecha") else datetime.now()
        except (ValueError, TypeError):
            fecha = datetime.now()

        venta = Venta(
            sucursal=sucursal,
            fecha=fecha,
            modo_pago=data.get("modo_pago", "Efectivo"),
            cuotas=data.get("cuotas"),
            total=float(data.get("total", 0)),
            subtotal_base=float(data.get("subtotal_base", 0)),
            interes_pct=float(data.get("interes_pct", 0)),
            interes_monto=float(data.get("interes_monto", 0)),
            descuento_pct=float(data.get("descuento_pct", 0)),
            descuento_monto=float(data.get("descuento_monto", 0)),
            pagado=data.get("pagado"),
            vuelto=data.get("vuelto"),
            numero_ticket=numero_ticket,
            numero_ticket_cae=data.get("numero_ticket_cae"),    # v6.6.0
            afip_cae=data.get("afip_cae"),
            afip_cae_vencimiento=data.get("afip_cae_vencimiento"),
            afip_numero_comprobante=data.get("afip_numero_comprobante"),
            tipo_comprobante=data.get("tipo_comprobante"),       # v6.6.0
            nota_credito_cae=data.get("nota_credito_cae"),       # v6.6.0
            nota_credito_numero=data.get("nota_credito_numero"), # v6.6.0
        )

        self.session.add(venta)
        try:
            self.session.flush()
        except IntegrityError:
            self.session.rollback()
            return False
        except Exception:
            self.session.rollback()
            raise

        # Agregar items
        for item_data in (data.get("items") or []):
            codigo = item_data.get("codigo_barra", "")
            prod = self.session.query(Producto).filter_by(codigo_barra=codigo).first() if codigo else None
            if not prod and codigo:
                self._log(f"  WARN: producto '{codigo}' no encontrado, item creado sin vinculo")

            vi = VentaItem(
                venta_id=venta.id,
                producto_id=prod.id if prod else None,
                cantidad=int(item_data.get("cantidad", 1)),
                precio_unit=float(item_data.get("precio_unit", 0))
            )
            self.session.add(vi)

        self.session.commit()
        _items_count = len(data.get("items") or [])
        self._log(f"Venta #{numero_ticket} recibida de {sucursal} ({_items_count} items, total={data.get('total', 0)})")
        return True

    def _apply_venta_update(self, data: dict) -> bool:
        """Aplica una modificacion de venta (devolucion)."""
        numero_ticket = data.get("numero_ticket")
        if not numero_ticket:
            self._log(f"  _apply_venta_update SKIP: sin numero_ticket")
            return False

        venta = self.session.query(Venta).filter_by(numero_ticket=numero_ticket).first()
        if not venta:
            self._log(f"  _apply_venta_update SKIP: ticket #{numero_ticket} no existe localmente")
            return False

        if "total" in data:
            venta.total = float(data["total"])
        if "vuelto" in data:
            venta.vuelto = data["vuelto"]
        # v6.6.0: aplicar nota de credito y datos AFIP que vienen en el update
        for _k in ("nota_credito_cae", "nota_credito_numero",
                   "afip_cae", "afip_numero_comprobante",
                   "tipo_comprobante", "numero_ticket_cae"):
            if _k in data:
                setattr(venta, _k, data[_k])

        # Actualizar items si vienen (con rollback seguro)
        items_data = data.get("items")
        if items_data is not None:
            try:
                # Eliminar items actuales
                for item in list(venta.items):
                    self.session.delete(item)
                self.session.flush()

                # Recrear items
                for item_data in items_data:
                    codigo = item_data.get("codigo_barra", "")
                    prod = self.session.query(Producto).filter_by(codigo_barra=codigo).first() if codigo else None
                    if not prod and codigo:
                        self._log(f"  WARN: producto '{codigo}' no encontrado en update, item sin vinculo")
                    vi = VentaItem(
                        venta_id=venta.id,
                        producto_id=prod.id if prod else None,
                        cantidad=int(item_data.get("cantidad", 1)),
                        precio_unit=float(item_data.get("precio_unit", 0))
                    )
                    self.session.add(vi)

                self.session.commit()
            except Exception as e:
                self.session.rollback()
                self._log(f"Error actualizando items de venta #{numero_ticket}: {e}")
                return False
        else:
            self.session.commit()

        self._log(f"Venta #{numero_ticket} actualizada (devolucion)")
        return True

    def _apply_venta_delete(self, data: dict) -> bool:
        """v6.7.1: Elimina una venta local cuando otra sucursal la borra.

        Busca por (sucursal + numero_ticket) > (sucursal + numero_ticket_cae) >
        (sucursal + afip_numero_comprobante). Si no encuentra, no hace nada.
        Tambien borra los items asociados (cascade no esta configurado).
        """
        sucursal = (data.get("sucursal") or "").strip()
        if not sucursal:
            self._log(f"  _apply_venta_delete SKIP: sin sucursal")
            return False

        numero_ticket = data.get("numero_ticket") or 0
        numero_ticket_cae = data.get("numero_ticket_cae") or 0
        afip_num = data.get("afip_numero_comprobante") or 0

        venta = None
        if numero_ticket:
            venta = self.session.query(Venta).filter_by(
                numero_ticket=numero_ticket, sucursal=sucursal,
            ).first()
        if not venta and numero_ticket_cae:
            venta = self.session.query(Venta).filter_by(
                numero_ticket_cae=numero_ticket_cae, sucursal=sucursal,
            ).first()
        if not venta and afip_num:
            venta = self.session.query(Venta).filter_by(
                afip_numero_comprobante=afip_num, sucursal=sucursal,
            ).first()

        if not venta:
            self._log(f"  _apply_venta_delete: ya no existe (ticket={numero_ticket}, "
                      f"cae_ticket={numero_ticket_cae}, afip_num={afip_num}, suc={sucursal})")
            return False

        try:
            for item in list(venta.items):
                self.session.delete(item)
            self.session.flush()
            self.session.delete(venta)
            self.session.commit()
            self._log(f"Venta #{numero_ticket or numero_ticket_cae or afip_num} "
                      f"({sucursal}) eliminada por sync")
            return True
        except Exception as e:
            self.session.rollback()
            self._log(f"  _apply_venta_delete ERROR: {e}")
            raise

    def _apply_producto(self, data: dict, timestamp: int) -> bool:
        """Crea o actualiza un producto. Last-write-wins."""
        codigo = data.get("codigo_barra")
        if not codigo:
            return False

        prod = self.session.query(Producto).filter_by(codigo_barra=codigo).first()
        if prod:
            # Last-write-wins: comparar timestamps
            local_ts = 0
            if hasattr(prod, "last_modified") and prod.last_modified:
                local_ts = int(prod.last_modified.timestamp() * 1000)
            if timestamp and local_ts > timestamp:
                return False  # Local es mas nuevo, no sobrescribir

            # Detectar diferencia de precio antes de actualizar
            remote_precio = float(data.get("precio", prod.precio))
            if abs(remote_precio - prod.precio) > 0.01:
                if not hasattr(self, '_price_mismatches'):
                    self._price_mismatches = []
                self._price_mismatches.append({
                    'codigo': prod.codigo_barra,
                    'nombre': prod.nombre,
                    'precio_local': prod.precio,
                    'precio_remoto': remote_precio,
                    'diferencia': round(remote_precio - prod.precio, 2)
                })

            prod.nombre = data.get("nombre", prod.nombre)
            prod.precio = remote_precio
            prod.categoria = data.get("categoria", prod.categoria)
            prod.telefono = data.get("telefono", prod.telefono)
            prod.numero_cuenta = data.get("numero_cuenta", prod.numero_cuenta)
            prod.cbu = data.get("cbu", prod.cbu)
            if hasattr(prod, "last_modified"):
                prod.last_modified = datetime.fromtimestamp(timestamp / 1000) if timestamp else datetime.now()
        else:
            prod = Producto(
                codigo_barra=codigo,
                nombre=data.get("nombre", ""),
                precio=float(data.get("precio", 0)),
                categoria=data.get("categoria"),
                telefono=data.get("telefono"),
                numero_cuenta=data.get("numero_cuenta"),
                cbu=data.get("cbu"),
            )
            if hasattr(prod, "last_modified"):
                prod.last_modified = datetime.fromtimestamp(timestamp / 1000) if timestamp else datetime.now()
            self.session.add(prod)

        try:
            self.session.commit()
            self._log(f"Producto '{codigo}' sincronizado (precio={data.get('precio', 0)})")
            return True
        except IntegrityError:
            self.session.rollback()
            return False

    def _apply_producto_delete(self, data: dict) -> bool:
        """Elimina un producto local si existe.

        v6.7.1: si sync.confirm_delete_productos es True, NO borra inmediatamente.
        Encola el delete en pending_deletes.json para que la UI muestre popup de
        confirmacion al usuario en el hilo principal.
        """
        codigo = data.get("codigo_barra")
        if not codigo:
            return False
        prod = self.session.query(Producto).filter_by(codigo_barra=codigo).first()
        if not prod:
            return False  # ya no existe, nada que confirmar

        # v6.7.1: chequear flag — default True (pedir confirmacion)
        sync_cfg = self._get_sync_config()
        confirmar = bool(sync_cfg.get("confirm_delete_productos", True))
        if confirmar:
            origen = data.get("_sucursal_origen", "")  # opcional, llenado por _apply_change
            self._enqueue_pending_delete("productos", {
                "codigo_barra": codigo,
                "nombre": prod.nombre,
                "precio": prod.precio,
                "categoria": prod.categoria,
                "telefono": getattr(prod, "telefono", None),
                "numero_cuenta": getattr(prod, "numero_cuenta", None),
                "cbu": getattr(prod, "cbu", None),
            }, origen)
            self._log(f"Producto '{codigo}' delete recibido — pendiente de confirmacion")
            return True  # tratado, cursor avanza; UI hara el resto

        # Sin confirmacion: borrar directo (comportamiento previo)
        self.session.delete(prod)
        self.session.commit()
        self._log(f"Producto '{codigo}' eliminado por sync")
        return True

    # ─── Pending deletes (v6.7.1) ─────────────────────────────────────

    def _pending_deletes_path(self) -> str:
        return os.path.join(_get_app_data_dir(), PENDING_DELETES_FILENAME)

    def _load_pending_deletes(self) -> list:
        try:
            p = self._pending_deletes_path()
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception as e:
            self._log(f"Error cargando pending_deletes: {e}")
        return []

    def _save_pending_deletes(self, items: list):
        try:
            with open(self._pending_deletes_path(), "w", encoding="utf-8") as f:
                json.dump(items[-500:], f, ensure_ascii=False, indent=2)
        except Exception as e:
            self._log(f"Error guardando pending_deletes: {e}")

    def _enqueue_pending_delete(self, tipo: str, data: dict, origen: str = ""):
        """v6.7.1: agrega un delete recibido a la cola para confirmacion en UI."""
        items = self._load_pending_deletes()
        # Dedup: si ya hay uno con (tipo, codigo) sin resolver, no duplicar
        codigo = data.get("codigo_barra") or data.get("nombre") or data.get("cuit")
        for it in items:
            if it.get("tipo") == tipo and (
                it.get("data", {}).get("codigo_barra") == data.get("codigo_barra") and
                it.get("data", {}).get("nombre") == data.get("nombre")
            ):
                return  # ya esta
        items.append({
            "tipo": tipo,
            "origen": origen,
            "timestamp": int(time.time() * 1000),
            "data": data,
        })
        self._save_pending_deletes(items)

    def get_pending_deletes(self) -> list:
        """v6.7.1: lista de deletes pendientes de confirmacion (para la UI)."""
        return self._load_pending_deletes()

    def accept_pending_delete(self, index: int) -> bool:
        """v6.7.1: confirmar borrado pendiente — borra el item localmente."""
        items = self._load_pending_deletes()
        if not (0 <= index < len(items)):
            return False
        item = items.pop(index)
        tipo = item.get("tipo")
        data = item.get("data", {}) or {}
        try:
            if tipo == "productos":
                codigo = data.get("codigo_barra")
                if codigo:
                    prod = self.session.query(Producto).filter_by(codigo_barra=codigo).first()
                    if prod:
                        self.session.delete(prod)
                        self.session.commit()
                        self._log(f"Producto '{codigo}' eliminado tras confirmacion del usuario")
            self._save_pending_deletes(items)
            return True
        except Exception as e:
            self.session.rollback()
            self._log(f"Error confirmando pending_delete: {e}")
            self._save_pending_deletes(items + [item])  # regresa a la cola
            return False

    def reject_pending_delete(self, index: int) -> bool:
        """v6.7.1: rechazar borrado pendiente — re-publica el item para 'deshacer' la baja en otras sucursales."""
        items = self._load_pending_deletes()
        if not (0 <= index < len(items)):
            return False
        item = items.pop(index)
        tipo = item.get("tipo")
        data = item.get("data", {}) or {}
        try:
            # Re-publicar como upsert con timestamp actual para sobreescribir el delete previo
            if tipo == "productos":
                payload = {
                    "sucursal_origen": self.sucursal_local,
                    "timestamp": int(time.time() * 1000),
                    "accion": "upsert",
                    "data": {
                        "codigo_barra": data.get("codigo_barra"),
                        "nombre": data.get("nombre"),
                        "precio": data.get("precio"),
                        "categoria": data.get("categoria"),
                        "telefono": data.get("telefono"),
                        "numero_cuenta": data.get("numero_cuenta"),
                        "cbu": data.get("cbu"),
                    },
                }
                key = self._firebase_post("cambios/productos", payload)
                if not key:
                    self._enqueue_change("productos", "upsert", payload["data"])
                self._log(f"Producto '{data.get('codigo_barra')}' delete RECHAZADO — re-publicado para deshacer")
            self._save_pending_deletes(items)
            return True
        except Exception as e:
            self._log(f"Error rechazando pending_delete: {e}")
            self._save_pending_deletes(items + [item])
            return False

    def _apply_proveedor(self, data: dict, timestamp: int) -> bool:
        """Crea o actualiza un proveedor. Last-write-wins."""
        nombre = (data.get("nombre") or "").strip()
        if not nombre:
            return False

        prov = self.session.query(Proveedor).filter(Proveedor.nombre == nombre).first()
        if prov:
            local_ts = 0
            if hasattr(prov, "last_modified") and prov.last_modified:
                local_ts = int(prov.last_modified.timestamp() * 1000)
            if timestamp and local_ts > timestamp:
                return False

            prov.telefono = data.get("telefono", prov.telefono)
            prov.numero_cuenta = data.get("numero_cuenta", prov.numero_cuenta)
            prov.cbu = data.get("cbu", prov.cbu)
            if hasattr(prov, "last_modified"):
                prov.last_modified = datetime.fromtimestamp(timestamp / 1000) if timestamp else datetime.now()
        else:
            prov = Proveedor(
                nombre=nombre,
                telefono=data.get("telefono"),
                numero_cuenta=data.get("numero_cuenta"),
                cbu=data.get("cbu"),
            )
            if hasattr(prov, "last_modified"):
                prov.last_modified = datetime.fromtimestamp(timestamp / 1000) if timestamp else datetime.now()
            self.session.add(prov)

        try:
            self.session.commit()
            self._log(f"Proveedor '{nombre}' sincronizado")
            return True
        except IntegrityError:
            self.session.rollback()
            return False

    def _apply_proveedor_delete(self, data: dict) -> bool:
        """Elimina un proveedor local si existe."""
        nombre = (data.get("nombre") or "").strip()
        if not nombre:
            return False
        prov = self.session.query(Proveedor).filter(Proveedor.nombre == nombre).first()
        if prov:
            self.session.delete(prov)
            self.session.commit()
            self._log(f"Proveedor '{nombre}' eliminado por sync")
            return True
        return False

    def _apply_pago_proveedor(self, data: dict) -> bool:
        """Inserta un pago a proveedor recibido desde Firebase (otra sucursal o dashboard)."""
        proveedor_nombre = (data.get("proveedor_nombre") or "").strip()
        monto = data.get("monto")
        if not proveedor_nombre or monto is None:
            self._log(f"  _apply_pago_proveedor SKIP: datos incompletos")
            return False

        sucursal = (data.get("sucursal") or self.sucursal_local or "").strip()
        numero_ticket = data.get("numero_ticket")

        # Deduplicación: mismo ticket + sucursal ya existe
        if numero_ticket:
            existing = self.session.query(PagoProveedor).filter_by(
                numero_ticket=numero_ticket, sucursal=sucursal
            ).first()
            if existing:
                self._log(f"  _apply_pago_proveedor SKIP: ticket #{numero_ticket} suc={sucursal} ya existe")
                return False

        try:
            fecha = datetime.fromisoformat(data["fecha"]) if data.get("fecha") else datetime.now()
        except (ValueError, TypeError):
            fecha = datetime.now()

        # Vincular proveedor por nombre si existe
        prov = self.session.query(Proveedor).filter(Proveedor.nombre == proveedor_nombre).first()

        # Asignar numero_ticket local si no viene
        if not numero_ticket:
            last = (self.session.query(PagoProveedor)
                    .filter(PagoProveedor.sucursal == sucursal,
                            PagoProveedor.numero_ticket.isnot(None))
                    .order_by(PagoProveedor.numero_ticket.desc())
                    .first())
            numero_ticket = (last.numero_ticket + 1) if last else 1

        pago = PagoProveedor(
            sucursal=sucursal,
            proveedor_id=prov.id if prov else None,
            proveedor_nombre=proveedor_nombre,
            fecha=fecha,
            monto=float(monto),
            metodo_pago=data.get("metodo_pago", "Efectivo"),
            pago_de_caja=bool(data.get("pago_de_caja", False)),
            incluye_iva=bool(data.get("incluye_iva", False)),
            numero_ticket=numero_ticket,
            nota=data.get("nota") or None,
        )
        self.session.add(pago)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            return False
        self._log(f"Pago prov #{numero_ticket} a {proveedor_nombre} recibido (${monto}, suc={sucursal})")
        return True

    def _apply_comprador(self, data: dict, timestamp: int) -> bool:
        """v6.7.0: Crea o actualiza un comprador (cliente). Identidad por CUIT (UNIQUE)."""
        cuit = (data.get("cuit") or "").strip()
        if not cuit:
            return False

        comp = self.session.query(Comprador).filter(Comprador.cuit == cuit).first()
        if comp:
            # No tenemos last_modified en Comprador; aceptamos last-write-wins por orden de llegada
            comp.nombre = data.get("nombre", comp.nombre) or comp.nombre
            comp.domicilio = data.get("domicilio", comp.domicilio) or comp.domicilio
            comp.localidad = data.get("localidad", comp.localidad) or comp.localidad
            comp.codigo_postal = data.get("codigo_postal", comp.codigo_postal) or comp.codigo_postal
            comp.condicion = data.get("condicion", comp.condicion) or comp.condicion
        else:
            comp = Comprador(
                cuit=cuit,
                nombre=data.get("nombre") or None,
                domicilio=data.get("domicilio") or None,
                localidad=data.get("localidad") or None,
                codigo_postal=data.get("codigo_postal") or None,
                condicion=data.get("condicion") or None,
            )
            self.session.add(comp)

        try:
            self.session.commit()
            self._log(f"Comprador CUIT {cuit} sincronizado")
            return True
        except IntegrityError:
            self.session.rollback()
            return False

    def _apply_comprador_delete(self, data: dict) -> bool:
        """v6.7.0: Elimina un comprador local si existe."""
        cuit = (data.get("cuit") or "").strip()
        if not cuit:
            return False
        comp = self.session.query(Comprador).filter(Comprador.cuit == cuit).first()
        if comp:
            self.session.delete(comp)
            self.session.commit()
            self._log(f"Comprador CUIT {cuit} eliminado por sync")
            return True
        return False

    # ─── Orquestacion ─────────────────────────────────────────────────

    def ejecutar_sincronizacion_completa(self) -> Dict:
        """
        Ciclo completo de sync:
        1. Flush cola offline
        2. Pull cambios remotos
        Retorna {"enviados": N, "recibidos": N, "errores": [...], "por_tipo": {tipo: {sent,recv,err}}}.

        v6.7.0: incluye `por_tipo` con desglose por entidad (productos/ventas/proveedores/
        pagos_proveedores/compradores) para que el panel UI muestre que se subio/bajo de cada
        cosa, no solo totales.
        """
        TIPOS = ("ventas", "productos", "proveedores", "pagos_proveedores", "compradores")
        por_tipo: Dict[str, Dict[str, int]] = {t: {"sent": 0, "recv": 0, "err": 0} for t in TIPOS}
        errores_list = []

        # 1. Flush cola offline (con desglose por tipo)
        sent_by_type: Dict[str, int] = {}
        try:
            sent_by_type = self._flush_offline_queue(by_type=True) or {}
        except Exception as e:
            errores_list.append(f"Error flush cola: {e}")
        for t, n in sent_by_type.items():
            if t in por_tipo:
                por_tipo[t]["sent"] = n

        # 2. Pull cambios remotos
        try:
            result = self.pull_changes()
            for t in TIPOS:
                por_tipo[t]["recv"] = int(result.get(t, 0) or 0)
            if result.get("errores", 0) > 0:
                errores_list.append(f"{result['errores']} errores al aplicar cambios")
        except Exception as e:
            errores_list.append(f"Error pull: {e}")

        enviados = sum(p["sent"] for p in por_tipo.values())
        recibidos = sum(p["recv"] for p in por_tipo.values())

        self._log(f"Sync completa: {enviados} enviados, {recibidos} recibidos, {len(errores_list)} errores")

        # Enviar alerta si hubo errores de sync
        if errores_list:
            try:
                from app.alert_manager import AlertManager
                AlertManager.get_instance().send_alert(
                    "sync_offline",
                    f"Errores durante sincronizacion Firebase ({len(errores_list)}).",
                    details="\n".join(errores_list)
                )
            except Exception as _alert_err:
                logger.warning("[sync] no se pudo enviar AlertManager: %s", _alert_err)

        return {
            "enviados": enviados,
            "recibidos": recibidos,
            "errores": errores_list,
            "por_tipo": por_tipo,  # v6.7.0
        }

    # ─── Test de conexion ─────────────────────────────────────────────

    def test_connection(self) -> Tuple[bool, str]:
        """Verifica la conexion con Firebase. Retorna (exito, mensaje)."""
        db_url, token = self._get_firebase_config()

        if not db_url:
            return False, "URL de Firebase no configurada."
        if not token:
            return False, "Token de autenticacion no configurado."

        try:
            url = f"{db_url.rstrip('/')}/.json?auth={token}&shallow=true"
            resp = requests.get(url, timeout=10)

            if resp.status_code == 200:
                return True, "Conexion exitosa con Firebase."
            elif resp.status_code == 401:
                return False, "Token de autenticacion invalido."
            elif resp.status_code == 404:
                return False, "URL de base de datos no encontrada."
            else:
                return False, f"Error HTTP {resp.status_code}: {resp.text[:100]}"
        except requests.ConnectionError:
            return False, "No se pudo conectar. Verifica tu conexion a internet."
        except requests.Timeout:
            return False, "Timeout: Firebase no respondio a tiempo."
        except Exception as e:
            return False, f"Error inesperado: {e}"

    def get_price_mismatches(self) -> list:
        """Retorna y limpia la lista de precios con diferencias detectadas."""
        mismatches = getattr(self, '_price_mismatches', [])
        self._price_mismatches = []
        return mismatches

    # ─── Diagnostico (v6.6.0) ─────────────────────────────────────────

    def diagnose_pending(self, max_per_type: int = 200) -> dict:
        """
        Devuelve un diagnostico de sincronizacion pendiente:
          - upload: cantidad de cambios encolados offline (por tipo).
          - download: cantidad de cambios EN Firebase aun no aplicados localmente
                      (excluye los que tienen sucursal_origen == sucursal_local).
          - last_processed_keys: cursor por tipo (para debug).

        Se usa para el boton "Verificar pendientes" en sync_config.py.
        Hace 4 GETs a Firebase (uno por tipo) — cuesta cuota pero el usuario lo activo a demanda.
        """
        result = {
            "upload": {"ventas": 0, "productos": 0, "proveedores": 0, "pagos_proveedores": 0, "compradores": 0},
            "download": {"ventas": 0, "productos": 0, "proveedores": 0, "pagos_proveedores": 0, "compradores": 0},
            "last_processed_keys": dict(getattr(self, "last_processed_keys", {}) or {}),
            "examples_download": {"ventas": [], "productos": [], "proveedores": [], "pagos_proveedores": [], "compradores": []},
            "ok": True,
            "error": None,
        }

        # ---- Upload (cola offline) ----
        try:
            queue = self._load_offline_queue()
            for item in queue:
                tipo = item.get("tipo")
                if tipo in result["upload"]:
                    result["upload"][tipo] += 1
        except Exception as e:
            result["ok"] = False
            result["error"] = f"Error leyendo cola offline: {e}"
            return result

        # ---- Download (diff con Firebase) ----
        # Para cada tipo, GET cambios/{tipo}.json y contar los que NO son propios
        # y aun no fueron procesados (key > last_processed_key).
        try:
            db_url, token = self._get_firebase_config()
            if not db_url:
                result["ok"] = False
                result["error"] = "Firebase no configurado (falta URL)."
                return result
        except Exception as e:
            result["ok"] = False
            result["error"] = f"Error de config: {e}"
            return result

        # v6.6.2: usar el helper real (la clase no tiene un atributo last_processed_keys,
        # los cursores viven en config["sync"]["last_processed_keys"]).
        try:
            last_keys = self._get_last_processed_keys() or {}
        except Exception:
            last_keys = {}
        result["last_processed_keys"] = dict(last_keys)

        for tipo in ("ventas", "productos", "proveedores", "pagos_proveedores", "compradores"):
            try:
                # Reusar el helper interno _firebase_get_path (paginado por orderBy)
                from urllib.parse import urlencode
                path = f"cambios/{tipo}.json"
                params = {"orderBy": '"$key"'}
                last_k = last_keys.get(tipo)
                if last_k:
                    params["startAt"] = f'"{last_k}"'
                params["limitToFirst"] = str(max_per_type + 1)  # +1 para detectar "hay mas"
                if token:
                    params["auth"] = token
                url = f"{db_url.rstrip('/')}/{path}?{urlencode(params)}"

                import requests
                r = requests.get(url, timeout=10)
                if r.status_code != 200:
                    continue
                data = r.json() or {}
                count = 0
                examples = []
                for key, change in data.items():
                    if not isinstance(change, dict):
                        continue
                    # Si tiene last_k, el primer item retornado es el ultimo procesado, lo saltamos
                    if last_k and key == last_k:
                        continue
                    if change.get("sucursal_origen") == self.sucursal_local:
                        continue  # propio (no nos lo bajamos a nosotros mismos)
                    count += 1
                    if len(examples) < 3:
                        d = change.get("data") or {}
                        # Ejemplo descriptivo segun tipo
                        if tipo == "ventas":
                            examples.append(
                                f"#{d.get('numero_ticket_cae') or d.get('numero_ticket') or '?'} "
                                f"de {change.get('sucursal_origen', '?')}"
                            )
                        elif tipo == "productos":
                            examples.append(
                                f"{change.get('accion', 'upsert')} {d.get('codigo_barra', '?')} "
                                f"({change.get('sucursal_origen', '?')})"
                            )
                        elif tipo == "compradores":
                            examples.append(
                                f"CUIT {d.get('cuit', '?')} {d.get('nombre','')[:30]} "
                                f"({change.get('sucursal_origen', '?')})"
                            )
                        else:
                            examples.append(f"{change.get('sucursal_origen', '?')}")

                result["download"][tipo] = count
                result["examples_download"][tipo] = examples
            except Exception as e:
                # No bloquear todo el diagnostico por un tipo que falle
                self._log(f"diagnose_pending: error consultando {tipo}: {e}")
                continue

        return result

    # ─── Diagnose full: local vs Firebase (v6.6.3) ────────────────────

    def diagnose_full(self) -> dict:
        """v6.6.3: cuenta items locales (BD SQLite) y Firebase (cambios/) para detectar diffs.

        Las cantidades de Firebase son de cambios/ (incluye creates+updates de toda la
        historia, no estado actual). Las cantidades locales son del estado actual de
        SQLite.

        Returns dict:
        {
          "local": {
            "ventas": {"total": N, "por_sucursal": {...}},
            "productos": N, "proveedores": N, "pagos_proveedores": N
          },
          "firebase": {
            "ventas": N, "productos": N, "proveedores": N, "pagos_proveedores": N
          },
          "upload_queue": {...},
          "cursors": {...},
          "ok": True/False,
          "error": str or None
        }
        """
        from sqlalchemy import func
        result = {
            "local": {},
            "firebase": {},
            "upload_queue": {"ventas": 0, "productos": 0, "proveedores": 0, "pagos_proveedores": 0, "compradores": 0},
            "cursors": {},
            "ok": True,
            "error": None,
        }

        # ---- Local DB counts ----
        try:
            ventas_total = self.session.query(Venta).count()
            por_sucursal_rows = (self.session.query(Venta.sucursal, func.count(Venta.id))
                                              .group_by(Venta.sucursal).all())
            por_sucursal = {(s or "?"): c for s, c in por_sucursal_rows}
            result["local"]["ventas"] = {"total": ventas_total, "por_sucursal": por_sucursal}
            result["local"]["productos"] = self.session.query(Producto).count()
            result["local"]["proveedores"] = self.session.query(Proveedor).count()
            result["local"]["pagos_proveedores"] = self.session.query(PagoProveedor).count()
            result["local"]["compradores"] = self.session.query(Comprador).count()  # v6.7.0
        except Exception as e:
            result["ok"] = False
            result["error"] = f"Error contando local: {e}"
            return result

        # ---- Firebase counts (shallow=true es gratis en cuota) ----
        try:
            db_url, token = self._get_firebase_config()
            if not db_url:
                result["ok"] = False
                result["error"] = "Firebase no configurado (falta URL)."
                return result
            for tipo in ("ventas", "productos", "proveedores", "pagos_proveedores", "compradores"):
                try:
                    url = f"{db_url.rstrip('/')}/cambios/{tipo}.json?shallow=true&auth={token}"
                    r = requests.get(url, timeout=15)
                    if r.status_code == 200:
                        data = r.json() or {}
                        # shallow=true devuelve dict {key: true, ...}
                        result["firebase"][tipo] = len(data) if isinstance(data, dict) else 0
                    else:
                        result["firebase"][tipo] = -1  # error
                except Exception as _e:
                    self._log(f"diagnose_full: error contando Firebase/{tipo}: {_e}")
                    result["firebase"][tipo] = -1
        except Exception as e:
            self._log(f"diagnose_full: error general Firebase: {e}")

        # ---- Upload queue ----
        try:
            queue = self._load_offline_queue()
            for item in queue:
                tipo = item.get("tipo")
                if tipo in result["upload_queue"]:
                    result["upload_queue"][tipo] += 1
        except Exception:
            pass

        # ---- Cursors ----
        try:
            result["cursors"] = dict(self._get_last_processed_keys() or {})
        except Exception:
            pass

        return result

    # ─── Skip-on-fail helpers (v6.6.2) ────────────────────────────────

    def _fail_counter_path(self) -> str:
        return os.path.join(_get_app_data_dir(), "sync_fail_counter.json")

    def _load_fail_counter(self) -> dict:
        try:
            if os.path.exists(self._fail_counter_path()):
                with open(self._fail_counter_path(), "r", encoding="utf-8") as f:
                    return json.load(f) or {}
        except Exception:
            pass
        return {}

    def _save_fail_counter(self, data: dict) -> None:
        try:
            with open(self._fail_counter_path(), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self._log(f"WARN: no se pudo persistir fail counter: {e}")

    def _bump_fail_count(self, tipo: str, push_key: str) -> int:
        """Incrementa el contador de fallos para (tipo, push_key) y devuelve el nuevo valor."""
        data = self._load_fail_counter()
        bucket = data.setdefault(tipo, {})
        n = int(bucket.get(push_key, 0)) + 1
        bucket[push_key] = n
        self._save_fail_counter(data)
        return n

    def _reset_fail_count(self, tipo: str, push_key: str) -> None:
        """Limpia el contador para (tipo, push_key) cuando se aplica OK o se skipea por duplicado."""
        data = self._load_fail_counter()
        bucket = data.get(tipo) or {}
        if push_key in bucket:
            bucket.pop(push_key, None)
            data[tipo] = bucket
            self._save_fail_counter(data)

    def _skipped_log_path(self) -> str:
        return os.path.join(_get_app_data_dir(), "logs", "sync_skipped.log")

    def _log_skipped(self, tipo: str, push_key: str, change: dict, err: str, fail_count: int) -> None:
        """Registra un cambio que fue skipeado permanentemente para inspeccion del usuario."""
        try:
            os.makedirs(os.path.dirname(self._skipped_log_path()), exist_ok=True)
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            origen = change.get("sucursal_origen", "?")
            data = change.get("data", {}) or {}
            # Resumen breve del item dañado
            if tipo == "ventas":
                ident = f"#{data.get('numero_ticket') or data.get('numero_ticket_cae') or '?'} suc={data.get('sucursal','?')}"
            elif tipo == "productos":
                ident = f"codigo={data.get('codigo_barra','?')} {data.get('nombre','')[:40]}"
            elif tipo == "proveedores":
                ident = f"nombre={data.get('nombre','?')}"
            elif tipo == "pagos_proveedores":
                ident = f"prov={data.get('proveedor_nombre','?')} monto={data.get('monto','?')}"
            elif tipo == "compradores":
                ident = f"cuit={data.get('cuit','?')} {data.get('nombre','')[:30]}"
            else:
                ident = "?"
            line = (
                f"[{ts}] [{self.sucursal_local}] SKIP {tipo}/{push_key} "
                f"(origen={origen}, fallos={fail_count}): {ident} :: {err}\n"
            )
            with open(self._skipped_log_path(), "a", encoding="utf-8") as f:
                f.write(line)
        except Exception as e:
            self._log(f"WARN: no se pudo escribir sync_skipped.log: {e}")

    def get_skipped_log_lines(self, max_lines: int = 200) -> list:
        """Retorna las ultimas N lineas del log de items skipeados, para mostrar en UI."""
        try:
            if not os.path.exists(self._skipped_log_path()):
                return []
            with open(self._skipped_log_path(), "r", encoding="utf-8") as f:
                lines = f.readlines()
            return [ln.rstrip() for ln in lines[-max_lines:]]
        except Exception:
            return []

    # ─── Logging ──────────────────────────────────────────────────────

    def _log(self, msg: str):
        # Logger dedicado con RotatingFileHandler (5MB x 5 backups) si esta disponible.
        # El handler escribe a logs/sync.log con rotacion automatica.
        line = f"[{self.sucursal_local}] {msg}"
        try:
            self._sync_logger.info(line)
        except Exception as _io_err:
            # Fallback al logger del modulo si el dedicado falla
            logger.info(line)
            logger.warning("[sync] logger dedicado fallo: %s", _io_err)
