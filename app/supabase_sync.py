# app/supabase_sync.py
# -*- coding: utf-8 -*-
"""
Sincronizacion entre sucursales via Supabase Postgres (REST + Realtime WebSocket).

API espejo de FirebaseSyncManager para que el resto de la app no tenga que cambiar:
los mismos metodos `push_*`, `pull_changes`, `force_pull_all`, `diagnose_full`,
`ejecutar_sincronizacion_completa`, etc.

Diferencias clave con Firebase:
- UPSERT real con `Prefer: resolution=merge-duplicates` (no append-only).
- Soft-delete: en lugar de borrar la fila, se setea `deleted_at = now()`.
  Las otras sucursales ven el cambio como una row con deleted_at, lo aplican
  borrando local.
- Cursor de pull es un timestamp ISO en lugar de Firebase push key.
- Realtime via WebSocket (modulo aparte: app/supabase_realtime.py).

Schema: docs/supabase_schema.sql
"""

import json
import os
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import requests
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models import Venta, VentaItem, Producto, Proveedor, VentaLog, PagoProveedor, Comprador
from app.config import load as load_config, save as save_config, _get_app_data_dir

logger = logging.getLogger("supabase_sync")

QUEUE_FILENAME = "supabase_queue.json"
PENDING_DELETES_FILENAME = "supabase_pending_deletes.json"
MAX_QUEUE_SIZE = 10000
REQUEST_TIMEOUT = 30
BATCH_TIMEOUT = 120
PAGE_SIZE = 500

# Tipos espejados Firebase (API parity)
TIPOS_BACKEND = ("productos", "proveedores", "compradores", "ventas", "pagos_proveedores")

# Tabla Supabase (en plural) por cada tipo logico
TABLA_DE_TIPO = {
    "productos": "productos",
    "proveedores": "proveedores",
    "compradores": "compradores",
    "ventas": "ventas",
    "pagos_proveedores": "pagos_proveedores",
}


class SupabaseSyncManager:
    """
    Sincronizacion bidireccional entre sucursales via Supabase Postgres.
    Usa la REST API auto-generada por PostgREST.

    Metodos publicos (paridad con FirebaseSyncManager):
      push_producto, push_producto_eliminado, push_productos_batch,
      push_proveedor, push_proveedor_eliminado,
      push_comprador, push_comprador_eliminado,
      push_venta, push_venta_modificada, push_venta_eliminada,
      push_pago_proveedor,
      push_all_existing(tipos),
      pull_changes(), force_pull_all(),
      ejecutar_sincronizacion_completa(),
      test_connection(), diagnose_full(), diagnose_pending(),
      get_skipped_log_lines(),
      get_pending_deletes / accept / reject,
      reset_pull_cursors,
      start_realtime / stop_realtime  (delegado al modulo realtime).
    """

    def __init__(self, session: Session, sucursal_local: str):
        self.session = session
        self.sucursal_local = sucursal_local
        self._queue_path = os.path.join(_get_app_data_dir(), QUEUE_FILENAME)
        self._log_path = os.path.join(_get_app_data_dir(), "logs", "sync_supabase.log")
        self._price_mismatches = []
        os.makedirs(os.path.dirname(self._log_path), exist_ok=True)
        try:
            from app.logging_setup import get_module_logger
            self._sync_logger = get_module_logger(f"{__name__}.sb", filename="sync_supabase.log")
        except Exception:
            self._sync_logger = logger
        self._realtime = None  # placeholder, se inicia con start_realtime()

    # ─── Configuracion ───────────────────────────────────────────────

    def _get_sync_config(self) -> dict:
        cfg = load_config()
        return cfg.get("sync", {}) or {}

    def _get_supabase_config(self) -> Tuple[str, str, str]:
        """Retorna (url, publishable_key, secret_key) desde la config."""
        sync_cfg = self._get_sync_config()
        sb = sync_cfg.get("supabase", {}) or {}
        return (
            (sb.get("url") or "").rstrip("/"),
            sb.get("publishable_key") or "",
            sb.get("secret_key") or "",
        )

    def _log(self, msg: str):
        """Loguea con timestamp en sync_supabase.log."""
        try:
            self._sync_logger.info(msg)
        except Exception:
            pass

    # ─── REST helpers ────────────────────────────────────────────────

    def _headers(self, *, prefer: Optional[str] = None) -> dict:
        """Headers para requests con la secret_key (escritura permitida).

        v6.8.1: las keys nuevas de Supabase (sb_publishable_*, sb_secret_*) NO son JWTs,
        son tokens opacos. Mandar el header `Authorization: Bearer <key>` hace que
        PostgREST intente decodificarlo como JWT y devuelva 401. Solo `apikey` basta.
        Para JWTs viejas (eyJ...) tambien funciona porque el server acepta `apikey` como
        identidad valida. Asi cubrimos ambos formatos sin hardcodear deteccion.
        """
        _, _, secret = self._get_supabase_config()
        h = {
            "apikey": secret,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if prefer:
            h["Prefer"] = prefer
        return h

    def _rest_url(self, table: str, path: str = "") -> str:
        url, _, _ = self._get_supabase_config()
        if not url:
            return ""
        return f"{url}/rest/v1/{table}{path}"

    def _rest_get(self, table: str, params: dict) -> Optional[List[dict]]:
        url = self._rest_url(table)
        if not url:
            return None
        try:
            resp = requests.get(url, params=params, headers=self._headers(),
                                timeout=REQUEST_TIMEOUT)
            if resp.status_code != 200:
                self._log(f"GET {table} HTTP {resp.status_code}: {resp.text[:200]}")
                return None
            return resp.json()
        except Exception as e:
            self._log(f"GET {table} error: {e}")
            return None

    def _rest_count(self, table: str, params: Optional[dict] = None) -> int:
        """Cuenta filas con Prefer: count=exact (gratis en Supabase)."""
        url = self._rest_url(table)
        if not url:
            return -1
        params = dict(params or {})
        params["select"] = "id"
        params["limit"] = "0"
        try:
            resp = requests.get(url, params=params,
                                headers=self._headers(prefer="count=exact"),
                                timeout=REQUEST_TIMEOUT)
            if resp.status_code != 200:
                return -1
            cr = resp.headers.get("Content-Range") or ""
            # Formato: "0-N/TOTAL" o "*/TOTAL"
            if "/" in cr:
                return int(cr.split("/")[-1])
            return -1
        except Exception as e:
            self._log(f"COUNT {table} error: {e}")
            return -1

    def _rest_upsert(self, table: str, rows, *, on_conflict: Optional[str] = None,
                     return_minimal: bool = True) -> Tuple[bool, Optional[list]]:
        """POST con Prefer: resolution=merge-duplicates. Soporta dict o lista.

        v6.9.3: forzar `return=representation` para verificar que la operacion
        afecto al menos 1 fila. Si 0 filas, devolver False con warning explicito
        (caso tipico: anon-key intentando escribir contra una tabla con RLS-only-
        SELECT, PostgREST devuelve 204 silenciosamente).
        """
        if isinstance(rows, dict):
            rows = [rows]
        if not rows:
            return True, []
        url = self._rest_url(table)
        if not url:
            return False, None
        params = {}
        if on_conflict:
            params["on_conflict"] = on_conflict
        # v6.9.3: SIEMPRE pedir return=representation para detectar silent fail.
        prefer = "resolution=merge-duplicates,return=representation"
        try:
            resp = requests.post(url, params=params, json=rows,
                                 headers=self._headers(prefer=prefer),
                                 timeout=BATCH_TIMEOUT)
            if resp.status_code not in (200, 201, 204):
                self._log(f"UPSERT {table} HTTP {resp.status_code}: {resp.text[:300]}")
                return False, None
            try:
                data = resp.json()
            except Exception:
                data = None
            # v6.9.3: detectar silent fail (PATCH 204 sin filas)
            if isinstance(data, list) and len(data) == 0 and len(rows) > 0:
                self._log(
                    f"UPSERT {table} SILENT FAIL: HTTP {resp.status_code} pero "
                    f"0 filas afectadas. Probablemente la secret_key es en realidad "
                    f"sb_publishable_* (anon role) y RLS bloquea writes. "
                    f"Revisa Configuracion > Sincronizacion."
                )
                return False, data
            if return_minimal:
                return True, None
            return True, data
        except Exception as e:
            self._log(f"UPSERT {table} error: {e}")
            return False, None

    def _rest_patch(self, table: str, params: dict, body: dict) -> bool:
        """PATCH a /rest/v1/{table}?{params} con body json.

        v6.9.3: usar `return=representation` para detectar 0 filas afectadas.
        El caso tipico es: secret_key incorrecta (anon role), RLS sin policy
        UPDATE, PostgREST devuelve 204 silenciosamente sin modificar nada.
        """
        url = self._rest_url(table)
        if not url:
            return False
        try:
            resp = requests.patch(url, params=params, json=body,
                                  headers=self._headers(prefer="return=representation"),
                                  timeout=REQUEST_TIMEOUT)
            if resp.status_code not in (200, 204):
                self._log(f"PATCH {table} HTTP {resp.status_code}: {resp.text[:200]}")
                return False
            try:
                data = resp.json()
            except Exception:
                data = None
            if isinstance(data, list) and len(data) == 0:
                self._log(
                    f"PATCH {table} SILENT FAIL: HTTP {resp.status_code} con 0 filas "
                    f"afectadas (params={params}). Probable: secret_key invalida "
                    f"(anon role) bloqueada por RLS. Revisa Configuracion."
                )
                return False
            return True
        except Exception as e:
            self._log(f"PATCH {table} error: {e}")
            return False

    def _is_online(self) -> bool:
        url, _, secret = self._get_supabase_config()
        if not url or not secret:
            return False
        try:
            # v6.8.1: solo apikey, sin Authorization (las keys nuevas no son JWT)
            r = requests.get(f"{url}/rest/v1/",
                             headers={"apikey": secret},
                             timeout=5)
            return r.status_code in (200, 404)
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

    def _enqueue_change(self, tipo: str, op: str, body: dict, params: Optional[dict] = None):
        """Encola un push fallido para reintentar. op: 'upsert' | 'patch'."""
        queue = self._load_offline_queue()
        queue.append({
            "tipo": tipo,
            "op": op,
            "params": params or {},
            "body": body,
            "ts": int(time.time() * 1000),
        })
        self._save_offline_queue(queue)

    def _flush_offline_queue(self, by_type: bool = False):
        queue = self._load_offline_queue()
        if not queue:
            return {} if by_type else 0
        sent_by_type: Dict[str, int] = {}
        remaining = []
        for change in queue:
            tipo = change.get("tipo") or "?"
            op = change.get("op")
            ok = False
            if op == "upsert":
                ok, _ = self._rest_upsert(
                    TABLA_DE_TIPO.get(tipo, tipo),
                    change.get("body"),
                    on_conflict=change.get("params", {}).get("on_conflict"),
                )
            elif op == "patch":
                ok = self._rest_patch(
                    TABLA_DE_TIPO.get(tipo, tipo),
                    change.get("params", {}),
                    change.get("body", {}),
                )
            if ok:
                sent_by_type[tipo] = sent_by_type.get(tipo, 0) + 1
            else:
                remaining.append(change)
        self._save_offline_queue(remaining)
        total = sum(sent_by_type.values())
        if total > 0:
            self._log(f"Cola offline Supabase: {total} enviados ({sent_by_type}), {len(remaining)} pendientes")
        return sent_by_type if by_type else total

    # ─── Push: local -> Supabase ──────────────────────────────────────

    def _resolver_punto_venta(self, sucursal: str) -> int:
        try:
            fiscal = (load_config().get("fiscal") or {})
            por_suc = fiscal.get("puntos_venta_por_sucursal") or {}
            return int(por_suc.get(sucursal) or fiscal.get("punto_venta") or 1)
        except Exception:
            return 1

    def _push_with_queue(self, tipo: str, body: dict, on_conflict: str):
        ok, _ = self._rest_upsert(TABLA_DE_TIPO[tipo], body, on_conflict=on_conflict)
        if not ok:
            self._enqueue_change(tipo, "upsert", body, params={"on_conflict": on_conflict})
        else:
            self._log(f"{tipo} upsert OK")
        return ok

    # ─ Productos ─

    def push_producto(self, producto: Producto, accion: str = "upsert"):
        sync_cfg = self._get_sync_config()
        if not sync_cfg.get("sync_productos", True):
            return
        body = {
            "codigo_barra": producto.codigo_barra,
            "nombre": producto.nombre,
            "precio": float(producto.precio),
            "categoria": producto.categoria,
            "telefono": getattr(producto, "telefono", None),
            "numero_cuenta": getattr(producto, "numero_cuenta", None),
            "cbu": getattr(producto, "cbu", None),
            "sucursal_origen": self.sucursal_local,
            "deleted_at": None,
        }
        self._push_with_queue("productos", body, on_conflict="codigo_barra")

    def push_productos_batch(self, productos) -> bool:
        if not productos:
            return True
        sync_cfg = self._get_sync_config()
        if not sync_cfg.get("sync_productos", True):
            return True
        rows = []
        for prod in productos:
            rows.append({
                "codigo_barra": prod.codigo_barra,
                "nombre": prod.nombre,
                "precio": float(prod.precio),
                "categoria": prod.categoria,
                "telefono": getattr(prod, "telefono", None),
                "numero_cuenta": getattr(prod, "numero_cuenta", None),
                "cbu": getattr(prod, "cbu", None),
                "sucursal_origen": self.sucursal_local,
                "deleted_at": None,
            })
        ok, _ = self._rest_upsert("productos", rows, on_conflict="codigo_barra")
        if not ok:
            for row in rows:
                self._enqueue_change("productos", "upsert", row,
                                     params={"on_conflict": "codigo_barra"})
        self._log(f"Batch push productos: {len(rows)} ({'OK' if ok else 'FAIL->queue'})")
        return ok

    def push_producto_eliminado(self, codigo_barra: str):
        """Soft-delete: setea deleted_at = now()."""
        sync_cfg = self._get_sync_config()
        if not sync_cfg.get("sync_productos", True):
            return
        body = {"deleted_at": datetime.utcnow().isoformat() + "Z",
                "sucursal_origen": self.sucursal_local}
        params = {"codigo_barra": f"eq.{codigo_barra}"}
        ok = self._rest_patch("productos", params, body)
        if not ok:
            self._enqueue_change("productos", "patch", body, params=params)
        else:
            self._log(f"Producto '{codigo_barra}' soft-delete OK")

    # ─ Proveedores ─

    def push_proveedor(self, proveedor: Proveedor, accion: str = "upsert"):
        sync_cfg = self._get_sync_config()
        if not sync_cfg.get("sync_proveedores", True):
            return
        body = {
            "nombre": (proveedor.nombre or "").strip(),
            "telefono": proveedor.telefono,
            "numero_cuenta": proveedor.numero_cuenta,
            "cbu": proveedor.cbu,
            "sucursal_origen": self.sucursal_local,
            "deleted_at": None,
        }
        self._push_with_queue("proveedores", body, on_conflict="nombre")

    def push_proveedor_eliminado(self, nombre: str):
        sync_cfg = self._get_sync_config()
        if not sync_cfg.get("sync_proveedores", True):
            return
        body = {"deleted_at": datetime.utcnow().isoformat() + "Z",
                "sucursal_origen": self.sucursal_local}
        params = {"nombre": f"eq.{nombre}"}
        ok = self._rest_patch("proveedores", params, body)
        if not ok:
            self._enqueue_change("proveedores", "patch", body, params=params)

    # ─ Compradores ─

    def push_comprador(self, comprador: Comprador, accion: str = "upsert"):
        sync_cfg = self._get_sync_config()
        if not sync_cfg.get("sync_compradores", True):
            return
        body = {
            "cuit": (comprador.cuit or "").strip(),
            "nombre": comprador.nombre or "",
            "domicilio": comprador.domicilio or "",
            "localidad": comprador.localidad or "",
            "codigo_postal": comprador.codigo_postal or "",
            "condicion": comprador.condicion or "",
            "sucursal_origen": self.sucursal_local,
            "deleted_at": None,
        }
        self._push_with_queue("compradores", body, on_conflict="cuit")

    def push_comprador_eliminado(self, cuit: str):
        sync_cfg = self._get_sync_config()
        if not sync_cfg.get("sync_compradores", True):
            return
        body = {"deleted_at": datetime.utcnow().isoformat() + "Z",
                "sucursal_origen": self.sucursal_local}
        params = {"cuit": f"eq.{(cuit or '').strip()}"}
        ok = self._rest_patch("compradores", params, body)
        if not ok:
            self._enqueue_change("compradores", "patch", body, params=params)

    # ─ Ventas ─

    def _serialize_venta(self, venta: Venta) -> dict:
        return {
            "sucursal": venta.sucursal,
            "numero_ticket": venta.numero_ticket or None,
            "numero_ticket_cae": venta.numero_ticket_cae or None,
            "fecha": venta.fecha.isoformat() if venta.fecha else None,
            "modo_pago": venta.modo_pago,
            "cuotas": venta.cuotas,
            "total": float(venta.total or 0),
            "subtotal_base": float(getattr(venta, "subtotal_base", 0) or 0),
            "interes_pct": float(getattr(venta, "interes_pct", 0) or 0),
            "interes_monto": float(getattr(venta, "interes_monto", 0) or 0),
            "descuento_pct": float(getattr(venta, "descuento_pct", 0) or 0),
            "descuento_monto": float(getattr(venta, "descuento_monto", 0) or 0),
            "pagado": float(venta.pagado) if venta.pagado is not None else None,
            "vuelto": float(venta.vuelto) if venta.vuelto is not None else None,
            "afip_cae": venta.afip_cae,
            "afip_cae_vencimiento": venta.afip_cae_vencimiento,
            "afip_numero_comprobante": venta.afip_numero_comprobante,
            "tipo_comprobante": venta.tipo_comprobante,
            "punto_venta": self._resolver_punto_venta(venta.sucursal),
            "nota_credito_cae": venta.nota_credito_cae,
            "nota_credito_numero": venta.nota_credito_numero,
            "cuit_cliente": getattr(venta, "cuit_cliente", None),
            "nombre_cliente": getattr(venta, "nombre_cliente", None),
            "domicilio_cliente": getattr(venta, "domicilio_cliente", None),
            "localidad_cliente": getattr(venta, "localidad_cliente", None),
            "codigo_postal_cliente": getattr(venta, "codigo_postal_cliente", None),
            "condicion_cliente": getattr(venta, "condicion_cliente", None),
            "sucursal_origen": self.sucursal_local,
            "deleted_at": None,
        }

    def push_venta(self, venta: Venta):
        sync_cfg = self._get_sync_config()
        if not sync_cfg.get("sync_ventas", True):
            return
        return self._push_venta_impl(venta)

    def _push_venta_impl(self, venta: Venta):
        """v6.9.2: SELECT-then-PATCH-or-INSERT.

        El UPSERT con `on_conflict=sucursal,numero_ticket` falla con error 42P10
        ("there is no unique or exclusion constraint matching the ON CONFLICT
        specification") porque nuestros unique son PARCIALES (where numero_ticket
        IS NOT NULL). PostgREST no soporta on_conflict con partial indices.

        Solucion: buscar primero la venta por cualquier identificador conocido;
        si existe, PATCH su id; si no, INSERT plano.
        """
        body = self._serialize_venta(venta)
        sucursal = body.get("sucursal")
        nt = body.get("numero_ticket")
        ntc = body.get("numero_ticket_cae")
        afip_num = body.get("afip_numero_comprobante")

        # Buscar existente por cualquier identidad
        existing = self._find_venta_remota(sucursal, nt, ntc, afip_num)

        venta_id = None
        if existing:
            # Update via PATCH usando el id remoto
            venta_id = existing.get("id")
            ok = self._rest_patch("ventas", {"id": f"eq.{venta_id}"}, body)
            if not ok:
                self._enqueue_change("ventas", "patch", body,
                                     params={"id": f"eq.{venta_id}"})
                self._log(f"Venta #{nt or ntc} encolada offline (PATCH fallo)")
                return
            self._log(f"Venta #{nt or ntc} actualizada (id={venta_id})")
        else:
            # Insert plano (sin on_conflict porque rompe con partial indices)
            url = self._rest_url("ventas")
            try:
                resp = requests.post(
                    url, json=[body],
                    headers={**self._headers(prefer="return=representation")},
                    timeout=REQUEST_TIMEOUT,
                )
                if resp.status_code in (200, 201):
                    data = resp.json() or []
                    if isinstance(data, list) and data:
                        venta_id = data[0].get("id")
                    self._log(f"Venta #{nt or ntc} insertada (id={venta_id})")
                elif resp.status_code == 409:
                    # Conflict: alguna race condition; reintentar como PATCH
                    self._log(f"Venta #{nt or ntc} 409 conflict, reintento via SELECT+PATCH")
                    existing = self._find_venta_remota(sucursal, nt, ntc, afip_num)
                    if existing:
                        venta_id = existing.get("id")
                        self._rest_patch("ventas", {"id": f"eq.{venta_id}"}, body)
                else:
                    self._log(f"Venta INSERT HTTP {resp.status_code}: {resp.text[:200]}")
                    self._enqueue_change("ventas", "upsert", body, params={})
                    return
            except Exception as e:
                self._log(f"Venta INSERT error: {e}")
                self._enqueue_change("ventas", "upsert", body, params={})
                return

        if not venta_id:
            self._log(f"Venta sin id remoto, no inserto items")
            return

        # Items: re-crear (delete + insert) para evitar deduplicar manualmente
        try:
            requests.delete(
                self._rest_url("venta_items"),
                params={"venta_id": f"eq.{venta_id}"},
                headers={**self._headers(prefer="return=minimal")},
                timeout=REQUEST_TIMEOUT,
            )
        except Exception as e:
            self._log(f"DELETE venta_items prev failed: {e}")

        items_rows = []
        for it in (venta.items or []):
            prod = it.producto
            items_rows.append({
                "venta_id": venta_id,
                "codigo_barra": prod.codigo_barra if prod else "",
                "nombre": prod.nombre if prod else "",
                "cantidad": int(it.cantidad or 0),
                "precio_unit": float(it.precio_unit or 0),
            })
        if items_rows:
            try:
                resp = requests.post(
                    self._rest_url("venta_items"), json=items_rows,
                    headers={**self._headers(prefer="return=minimal")},
                    timeout=REQUEST_TIMEOUT,
                )
                if resp.status_code not in (200, 201, 204):
                    self._log(f"INSERT venta_items HTTP {resp.status_code}: {resp.text[:150]}")
            except Exception as e:
                self._log(f"INSERT venta_items error: {e}")

    def _find_venta_remota(self, sucursal, nt, ntc, afip_num):
        """Busca una venta en Supabase por cualquiera de sus identificadores.
        Devuelve el dict de la fila (con id) o None."""
        candidates = []
        if nt is not None:
            candidates.append(("numero_ticket", nt))
        if ntc is not None:
            candidates.append(("numero_ticket_cae", ntc))
        if afip_num is not None:
            candidates.append(("afip_numero_comprobante", afip_num))
        for col, val in candidates:
            try:
                rows = self._rest_get("ventas",
                                      {"select": "id," + col,
                                       "sucursal": f"eq.{sucursal}",
                                       col: f"eq.{val}",
                                       "limit": "1"})
                if rows:
                    return rows[0]
            except Exception as e:
                self._log(f"_find_venta_remota error con {col}={val}: {e}")
        return None

    def push_venta_modificada(self, venta: Venta):
        sync_cfg = self._get_sync_config()
        if not sync_cfg.get("sync_ventas", True):
            return
        return self._push_venta_impl(venta)

    def push_venta_eliminada(self, venta: Venta):
        sync_cfg = self._get_sync_config()
        if not sync_cfg.get("sync_ventas", True):
            return
        """Soft-delete con identificadores (sucursal + numero_ticket o cae o afip_num)."""
        body = {"deleted_at": datetime.utcnow().isoformat() + "Z",
                "sucursal_origen": self.sucursal_local}
        params = {"sucursal": f"eq.{venta.sucursal}"}
        if venta.numero_ticket:
            params["numero_ticket"] = f"eq.{venta.numero_ticket}"
        elif venta.numero_ticket_cae:
            params["numero_ticket_cae"] = f"eq.{venta.numero_ticket_cae}"
        elif venta.afip_numero_comprobante:
            params["afip_numero_comprobante"] = f"eq.{venta.afip_numero_comprobante}"
        else:
            self._log(f"push_venta_eliminada SKIP: sin identidad")
            return
        ok = self._rest_patch("ventas", params, body)
        if not ok:
            self._enqueue_change("ventas", "patch", body, params=params)
        else:
            self._log(f"Venta {params} ELIMINADA (soft) en Supabase")

    # ─ Pagos a proveedores ─

    def push_pago_proveedor(self, pago):
        sync_cfg = self._get_sync_config()
        if not sync_cfg.get("sync_pagos_proveedores", True):
            return
        body = {
            "sucursal": getattr(pago, "sucursal", "") or self.sucursal_local,
            "numero_ticket": getattr(pago, "numero_ticket", None),
            "fecha": pago.fecha.isoformat() if pago.fecha else None,
            "proveedor_nombre": getattr(pago, "proveedor_nombre", "") or "",
            "monto": float(getattr(pago, "monto", 0) or 0),
            "metodo_pago": getattr(pago, "metodo_pago", "Efectivo"),
            "pago_de_caja": bool(getattr(pago, "pago_de_caja", False)),
            "incluye_iva": bool(getattr(pago, "incluye_iva", False)),
            "nota": getattr(pago, "nota", "") or "",
            "sucursal_origen": self.sucursal_local,
            "deleted_at": None,
        }
        on_conflict = "sucursal,numero_ticket" if body.get("numero_ticket") else None
        self._push_with_queue("pagos_proveedores", body, on_conflict=on_conflict or "")

    # ─── Sync inicial ───────────────────────────────────────────────

    _BULK_PUSH_TIPOS = ("productos", "proveedores", "ventas", "pagos_proveedores", "compradores")

    def push_all_existing(self, callback=None, tipos=None) -> Dict[str, int]:
        if tipos is None:
            seleccion = {"productos", "proveedores"}
        else:
            seleccion = {t for t in tipos if t in self._BULK_PUSH_TIPOS}
        result = {t: 0 for t in self._BULK_PUSH_TIPOS}
        result["errores"] = 0
        if "productos" in seleccion:
            self._push_all_table_batch("productos", Producto,
                                       self._row_from_producto, "codigo_barra",
                                       result, callback)
        if "proveedores" in seleccion:
            self._push_all_table_batch("proveedores", Proveedor,
                                       self._row_from_proveedor, "nombre",
                                       result, callback)
        if "compradores" in seleccion:
            self._push_all_table_batch("compradores", Comprador,
                                       self._row_from_comprador, "cuit",
                                       result, callback)
        if "pagos_proveedores" in seleccion:
            self._push_all_table_batch("pagos_proveedores", PagoProveedor,
                                       self._row_from_pago, "sucursal,numero_ticket",
                                       result, callback)
        if "ventas" in seleccion:
            self._push_all_ventas(result, callback)
        self._log(f"Sync inicial Supabase OK (tipos={sorted(seleccion)}): {result}")
        return result

    def _push_all_table_batch(self, tabla: str, modelo, serializer, on_conflict: str,
                              result: dict, callback=None) -> None:
        try:
            items = self.session.query(modelo).all()
            total = len(items)
            self._log(f"Sync inicial: {total} {tabla} a Supabase...")
            CHUNK = 500
            for i in range(0, total, CHUNK):
                batch = [serializer(x) for x in items[i:i + CHUNK]]
                ok, _ = self._rest_upsert(tabla, batch,
                                          on_conflict=on_conflict if on_conflict else None)
                if ok:
                    result[tabla] += len(batch)
                else:
                    result["errores"] += len(batch)
                if callback:
                    callback(min(i + CHUNK, total), total, tabla)
        except Exception as e:
            self._log(f"Sync inicial {tabla} error: {e}")

    def _push_all_ventas(self, result: dict, callback=None) -> None:
        try:
            ventas = self.session.query(Venta).all()
            total = len(ventas)
            self._log(f"Sync inicial: {total} ventas a Supabase...")
            for i, v in enumerate(ventas):
                # No usamos batch para ventas porque necesitamos el id de cada una
                # para insertar sus items.
                self.push_venta(v)
                result["ventas"] += 1
                if callback and (i + 1) % 50 == 0:
                    callback(i + 1, total, "ventas")
            if callback:
                callback(total, total, "ventas")
        except Exception as e:
            self._log(f"Sync inicial ventas error: {e}")

    @staticmethod
    def _row_from_producto(p: Producto) -> dict:
        return {
            "codigo_barra": p.codigo_barra,
            "nombre": p.nombre,
            "precio": float(p.precio or 0),
            "categoria": p.categoria,
            "telefono": getattr(p, "telefono", None),
            "numero_cuenta": getattr(p, "numero_cuenta", None),
            "cbu": getattr(p, "cbu", None),
            "sucursal_origen": "Sarmiento",  # se sobreescribe en init
            "deleted_at": None,
        }

    def _row_from_proveedor(self, p: Proveedor) -> dict:
        return {
            "nombre": (p.nombre or "").strip(),
            "telefono": p.telefono,
            "numero_cuenta": p.numero_cuenta,
            "cbu": p.cbu,
            "sucursal_origen": self.sucursal_local,
            "deleted_at": None,
        }

    def _row_from_comprador(self, c: Comprador) -> dict:
        return {
            "cuit": (c.cuit or "").strip(),
            "nombre": c.nombre or "",
            "domicilio": c.domicilio or "",
            "localidad": c.localidad or "",
            "codigo_postal": c.codigo_postal or "",
            "condicion": c.condicion or "",
            "sucursal_origen": self.sucursal_local,
            "deleted_at": None,
        }

    def _row_from_pago(self, pago: PagoProveedor) -> dict:
        return {
            "sucursal": getattr(pago, "sucursal", "") or self.sucursal_local,
            "numero_ticket": getattr(pago, "numero_ticket", None),
            "fecha": pago.fecha.isoformat() if pago.fecha else None,
            "proveedor_nombre": getattr(pago, "proveedor_nombre", "") or "",
            "monto": float(getattr(pago, "monto", 0) or 0),
            "metodo_pago": getattr(pago, "metodo_pago", "Efectivo"),
            "pago_de_caja": bool(getattr(pago, "pago_de_caja", False)),
            "incluye_iva": bool(getattr(pago, "incluye_iva", False)),
            "nota": getattr(pago, "nota", "") or "",
            "sucursal_origen": self.sucursal_local,
            "deleted_at": None,
        }

    # Patch para que _row_from_producto use sucursal_local correcta
    def _push_all_productos_batch_correct(self, result, callback=None):
        # _row_from_producto es @staticmethod por simetria pero necesita la sucursal
        # local — fix con closure:
        def _row(p):
            r = self._row_from_producto(p)
            r["sucursal_origen"] = self.sucursal_local
            return r
        items = self.session.query(Producto).all()
        total = len(items)
        for i in range(0, total, 500):
            batch = [_row(x) for x in items[i:i+500]]
            ok, _ = self._rest_upsert("productos", batch, on_conflict="codigo_barra")
            if ok:
                result["productos"] += len(batch)
            else:
                result["errores"] += len(batch)
            if callback:
                callback(min(i + 500, total), total, "productos")

    # ─── Pull: Supabase -> local ──────────────────────────────────────

    def _get_last_pull_cursors(self) -> Dict[str, Optional[str]]:
        """Cursor por tipo: timestamp ISO del ultimo updated_at procesado."""
        sync_cfg = self._get_sync_config()
        cursors = sync_cfg.get("last_pull_supabase", {}) or {}
        if not isinstance(cursors, dict):
            cursors = {}
        for t in TIPOS_BACKEND:
            cursors.setdefault(t, None)
        return cursors

    def _set_last_pull_cursor(self, tipo: str, ts_iso: str):
        cfg = load_config()
        sync = cfg.setdefault("sync", {})
        cursors = sync.setdefault("last_pull_supabase", {})
        cursors[tipo] = ts_iso
        save_config(cfg)

    def reset_pull_cursors(self) -> None:
        """Reset de cursores Supabase para forzar pull completo."""
        cfg = load_config()
        sync = cfg.setdefault("sync", {})
        sync["last_pull_supabase"] = {t: None for t in TIPOS_BACKEND}
        save_config(cfg)
        self._log("[FORCE-PULL Supabase] cursores reseteados")

    def force_pull_all(self, progress_callback=None, cancel_check=None) -> Dict[str, int]:
        self.reset_pull_cursors()
        return self.pull_changes(progress_callback=progress_callback,
                                 cancel_check=cancel_check)

    def pull_changes(self, progress_callback=None, cancel_check=None) -> Dict[str, int]:
        result = {t: 0 for t in TIPOS_BACKEND}
        result["errores"] = 0
        cursors = self._get_last_pull_cursors()
        for tipo in TIPOS_BACKEND:
            if cancel_check and cancel_check():
                self._log(f"Pull Supabase cancelado antes de {tipo}")
                break
            count, errors, new_cursor = self._pull_tabla(
                tipo, cursors.get(tipo),
                progress_callback=progress_callback,
                cancel_check=cancel_check,
            )
            result[tipo] = count
            result["errores"] += errors
            if new_cursor:
                self._set_last_pull_cursor(tipo, new_cursor)
        return result

    def _pull_tabla(self, tipo: str, last_cursor: Optional[str],
                    progress_callback=None, cancel_check=None) -> Tuple[int, int, Optional[str]]:
        """Pull de una tabla con KEYSET PAGINATION compuesta (updated_at, id).

        v6.9.1: arreglo el bug que dejaba a la sucursal trabada en 500 filas cuando
        un batch insert daba el mismo `updated_at` a muchos productos. La pagina
        siguiente filtraba `updated_at>cursor` y descartaba TODAS las filas que
        compartian el cursor, asi se perdian las restantes.

        Solucion: cursor compuesto (updated_at, id) usando el filtro `or` de
        PostgREST:
          WHERE  updated_at > cursor_ts
            OR  (updated_at = cursor_ts AND id > cursor_id)
        Sort: ORDER BY updated_at ASC, id ASC.

        El cursor persistente es solo `updated_at` (string ISO). El cursor_id es
        transitorio dentro de la sesion. Al iniciar una nueva sesion arrancamos
        con cursor_id=0 y reprocesamos algunas filas con updated_at=cursor_ts —
        idempotente porque `_apply_*` compara timestamps y descarta lo igual.
        """
        tabla = TABLA_DE_TIPO[tipo]
        total_applied = 0
        total_errors = 0
        cursor_ts = last_cursor   # iso string persistente entre sesiones
        cursor_id = 0             # id transitorio para break ties dentro de la sesion
        max_seen_ts = last_cursor
        page_num = 0

        while True:
            if cancel_check and cancel_check():
                break
            page_num += 1

            # v6.8.3: SIN filtro anti-eco por sucursal_origen (la tabla guarda el
            # estado actual, no eventos; ediciones del panel web tienen sucursal_origen
            # del creador y deben llegar a la sucursal originaria igual).
            params = {
                "select": "*",
                "order": "updated_at.asc,id.asc",
                "limit": str(PAGE_SIZE),
            }
            if cursor_ts:
                # Keyset compound: (updated_at>X) OR (updated_at=X AND id>Y)
                params["or"] = (
                    f"(updated_at.gt.{cursor_ts},"
                    f"and(updated_at.eq.{cursor_ts},id.gt.{cursor_id}))"
                )

            rows = self._rest_get(tabla, params)
            if rows is None:
                self._log(f"Pull {tipo} pag{page_num}: error de red")
                break
            if not rows:
                self._log(f"Pull {tipo} pag{page_num}: sin mas cambios")
                break

            for row in rows:
                try:
                    ok = self._apply_row(tipo, row)
                    if ok:
                        total_applied += 1
                    upd = row.get("updated_at")
                    rid = row.get("id") or 0
                    if upd:
                        if not max_seen_ts or upd > max_seen_ts:
                            max_seen_ts = upd
                        cursor_ts = upd
                        cursor_id = rid
                except Exception as e:
                    total_errors += 1
                    self._log(f"Pull {tipo} apply error: {e}")

            self._log(f"Pull {tipo} pag{page_num}: {len(rows)} filas, total aplicado={total_applied}")
            if progress_callback:
                try:
                    progress_callback(tipo, page_num, total_applied, total_errors)
                except Exception:
                    pass

            if len(rows) < PAGE_SIZE:
                break  # ultima pagina

        return total_applied, total_errors, max_seen_ts

    # ─── Aplicar cambios a SQLite local ────────────────────────────────

    def _apply_row(self, tipo: str, row: dict) -> bool:
        """Despacha la fila al _apply_* correspondiente (igual nombres que Firebase)."""
        deleted = row.get("deleted_at")
        if tipo == "productos":
            if deleted:
                return self._apply_producto_delete({"codigo_barra": row.get("codigo_barra"),
                                                    "_sucursal_origen": row.get("sucursal_origen")})
            return self._apply_producto(row, _ts_to_ms(row.get("updated_at")))
        elif tipo == "proveedores":
            if deleted:
                return self._apply_proveedor_delete({"nombre": row.get("nombre")})
            return self._apply_proveedor(row, _ts_to_ms(row.get("updated_at")))
        elif tipo == "compradores":
            if deleted:
                return self._apply_comprador_delete({"cuit": row.get("cuit")})
            return self._apply_comprador(row, _ts_to_ms(row.get("updated_at")))
        elif tipo == "ventas":
            if deleted:
                return self._apply_venta_delete(row)
            return self._apply_venta(row)
        elif tipo == "pagos_proveedores":
            if deleted:
                return self._apply_pago_proveedor_delete(row)
            return self._apply_pago_proveedor(row)
        return False

    # _apply_* — copiados/adaptados de FirebaseSyncManager (misma logica SQLite)

    def _apply_producto(self, data: dict, timestamp: int) -> bool:
        codigo = data.get("codigo_barra")
        if not codigo:
            return False
        prod = self.session.query(Producto).filter_by(codigo_barra=codigo).first()
        if prod:
            local_ts = 0
            if hasattr(prod, "last_modified") and prod.last_modified:
                local_ts = int(prod.last_modified.timestamp() * 1000)
            if timestamp and local_ts > timestamp:
                return False
            remote_precio = float(data.get("precio", prod.precio))
            if abs(remote_precio - prod.precio) > 0.01:
                self._price_mismatches.append({
                    "codigo": prod.codigo_barra, "nombre": prod.nombre,
                    "precio_local": prod.precio, "precio_remoto": remote_precio,
                    "diferencia": round(remote_precio - prod.precio, 2),
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
            return True
        except IntegrityError:
            self.session.rollback()
            return False

    def _apply_producto_delete(self, data: dict) -> bool:
        codigo = data.get("codigo_barra")
        if not codigo:
            return False
        prod = self.session.query(Producto).filter_by(codigo_barra=codigo).first()
        if not prod:
            return False
        sync_cfg = self._get_sync_config()
        if bool(sync_cfg.get("confirm_delete_productos", True)):
            origen = data.get("_sucursal_origen", "")
            self._enqueue_pending_delete("productos", {
                "codigo_barra": codigo, "nombre": prod.nombre, "precio": prod.precio,
                "categoria": prod.categoria, "telefono": getattr(prod, "telefono", None),
                "numero_cuenta": getattr(prod, "numero_cuenta", None),
                "cbu": getattr(prod, "cbu", None),
            }, origen)
            self._log(f"Producto '{codigo}' delete recibido — pendiente confirmacion")
            return True
        self.session.delete(prod)
        self.session.commit()
        self._log(f"Producto '{codigo}' eliminado por sync")
        return True

    def _apply_proveedor(self, data: dict, timestamp: int) -> bool:
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
            prov = Proveedor(nombre=nombre, telefono=data.get("telefono"),
                             numero_cuenta=data.get("numero_cuenta"), cbu=data.get("cbu"))
            if hasattr(prov, "last_modified"):
                prov.last_modified = datetime.fromtimestamp(timestamp / 1000) if timestamp else datetime.now()
            self.session.add(prov)
        try:
            self.session.commit()
            return True
        except IntegrityError:
            self.session.rollback()
            return False

    def _apply_proveedor_delete(self, data: dict) -> bool:
        nombre = (data.get("nombre") or "").strip()
        if not nombre:
            return False
        prov = self.session.query(Proveedor).filter(Proveedor.nombre == nombre).first()
        if prov:
            self.session.delete(prov)
            self.session.commit()
            return True
        return False

    def _apply_comprador(self, data: dict, timestamp: int) -> bool:
        cuit = (data.get("cuit") or "").strip()
        if not cuit:
            return False
        comp = self.session.query(Comprador).filter(Comprador.cuit == cuit).first()
        if comp:
            comp.nombre = data.get("nombre") or comp.nombre
            comp.domicilio = data.get("domicilio") or comp.domicilio
            comp.localidad = data.get("localidad") or comp.localidad
            comp.codigo_postal = data.get("codigo_postal") or comp.codigo_postal
            comp.condicion = data.get("condicion") or comp.condicion
        else:
            comp = Comprador(
                cuit=cuit, nombre=data.get("nombre") or None,
                domicilio=data.get("domicilio") or None,
                localidad=data.get("localidad") or None,
                codigo_postal=data.get("codigo_postal") or None,
                condicion=data.get("condicion") or None,
            )
            self.session.add(comp)
        try:
            self.session.commit()
            return True
        except IntegrityError:
            self.session.rollback()
            return False

    def _apply_comprador_delete(self, data: dict) -> bool:
        cuit = (data.get("cuit") or "").strip()
        if not cuit:
            return False
        comp = self.session.query(Comprador).filter(Comprador.cuit == cuit).first()
        if comp:
            self.session.delete(comp)
            self.session.commit()
            return True
        return False

    def _apply_venta(self, row: dict) -> bool:
        sucursal = (row.get("sucursal") or "").strip()
        if not sucursal:
            return False
        numero_ticket = row.get("numero_ticket") or 0
        numero_ticket_cae = row.get("numero_ticket_cae") or 0
        afip_num = row.get("afip_numero_comprobante") or 0

        existing = None
        if numero_ticket:
            existing = self.session.query(Venta).filter_by(
                numero_ticket=numero_ticket, sucursal=sucursal).first()
        if not existing and numero_ticket_cae:
            existing = self.session.query(Venta).filter_by(
                numero_ticket_cae=numero_ticket_cae, sucursal=sucursal).first()
        if not existing and afip_num:
            existing = self.session.query(Venta).filter_by(
                afip_numero_comprobante=afip_num, sucursal=sucursal).first()
        if existing:
            # Update — copiar campos del row
            for campo in ("total", "vuelto", "afip_cae", "afip_numero_comprobante",
                          "tipo_comprobante", "nota_credito_cae", "nota_credito_numero",
                          "numero_ticket_cae"):
                if campo in row and row[campo] is not None:
                    setattr(existing, campo, row[campo])
            try:
                self.session.commit()
                return True
            except Exception:
                self.session.rollback()
                return False

        try:
            fecha = datetime.fromisoformat(row["fecha"].replace("Z", "+00:00")) if row.get("fecha") else datetime.now()
        except Exception:
            fecha = datetime.now()
        venta = Venta(
            sucursal=sucursal, fecha=fecha,
            modo_pago=row.get("modo_pago", "Efectivo"),
            cuotas=row.get("cuotas"),
            total=float(row.get("total", 0)),
            subtotal_base=float(row.get("subtotal_base", 0) or 0),
            interes_pct=float(row.get("interes_pct", 0) or 0),
            interes_monto=float(row.get("interes_monto", 0) or 0),
            descuento_pct=float(row.get("descuento_pct", 0) or 0),
            descuento_monto=float(row.get("descuento_monto", 0) or 0),
            pagado=row.get("pagado"), vuelto=row.get("vuelto"),
            numero_ticket=numero_ticket or None,
            numero_ticket_cae=row.get("numero_ticket_cae"),
            afip_cae=row.get("afip_cae"),
            afip_cae_vencimiento=row.get("afip_cae_vencimiento"),
            afip_numero_comprobante=row.get("afip_numero_comprobante"),
            tipo_comprobante=row.get("tipo_comprobante"),
            nota_credito_cae=row.get("nota_credito_cae"),
            nota_credito_numero=row.get("nota_credito_numero"),
        )
        self.session.add(venta)
        try:
            self.session.flush()
        except IntegrityError:
            self.session.rollback()
            return False

        # Items: hay que pullarlos aparte por venta_id.
        venta_id_remoto = row.get("id")
        if venta_id_remoto:
            items_rows = self._rest_get("venta_items",
                                        {"select": "*", "venta_id": f"eq.{venta_id_remoto}"})
            for it in (items_rows or []):
                codigo = it.get("codigo_barra", "")
                prod = self.session.query(Producto).filter_by(codigo_barra=codigo).first() if codigo else None
                vi = VentaItem(
                    venta_id=venta.id,
                    producto_id=prod.id if prod else None,
                    cantidad=int(it.get("cantidad", 1)),
                    precio_unit=float(it.get("precio_unit", 0)),
                )
                self.session.add(vi)
        self.session.commit()
        return True

    def _apply_venta_delete(self, row: dict) -> bool:
        sucursal = (row.get("sucursal") or "").strip()
        if not sucursal:
            return False
        numero_ticket = row.get("numero_ticket") or 0
        numero_ticket_cae = row.get("numero_ticket_cae") or 0
        afip_num = row.get("afip_numero_comprobante") or 0
        venta = None
        if numero_ticket:
            venta = self.session.query(Venta).filter_by(
                numero_ticket=numero_ticket, sucursal=sucursal).first()
        if not venta and numero_ticket_cae:
            venta = self.session.query(Venta).filter_by(
                numero_ticket_cae=numero_ticket_cae, sucursal=sucursal).first()
        if not venta and afip_num:
            venta = self.session.query(Venta).filter_by(
                afip_numero_comprobante=afip_num, sucursal=sucursal).first()
        if not venta:
            return False
        try:
            for it in list(venta.items):
                self.session.delete(it)
            self.session.flush()
            self.session.delete(venta)
            self.session.commit()
            return True
        except Exception:
            self.session.rollback()
            return False

    def _apply_pago_proveedor(self, row: dict) -> bool:
        proveedor_nombre = (row.get("proveedor_nombre") or "").strip()
        monto = row.get("monto")
        if not proveedor_nombre or monto is None:
            return False
        sucursal = (row.get("sucursal") or self.sucursal_local or "").strip()
        numero_ticket = row.get("numero_ticket")
        if numero_ticket:
            existing = self.session.query(PagoProveedor).filter_by(
                numero_ticket=numero_ticket, sucursal=sucursal).first()
            if existing:
                return False
        try:
            fecha = datetime.fromisoformat(row["fecha"].replace("Z", "+00:00")) if row.get("fecha") else datetime.now()
        except Exception:
            fecha = datetime.now()
        prov = self.session.query(Proveedor).filter(Proveedor.nombre == proveedor_nombre).first()
        if not numero_ticket:
            last = (self.session.query(PagoProveedor)
                    .filter(PagoProveedor.sucursal == sucursal,
                            PagoProveedor.numero_ticket.isnot(None))
                    .order_by(PagoProveedor.numero_ticket.desc()).first())
            numero_ticket = (last.numero_ticket + 1) if last else 1
        pago = PagoProveedor(
            sucursal=sucursal, proveedor_id=prov.id if prov else None,
            proveedor_nombre=proveedor_nombre, fecha=fecha,
            monto=float(monto), metodo_pago=row.get("metodo_pago", "Efectivo"),
            pago_de_caja=bool(row.get("pago_de_caja", False)),
            incluye_iva=bool(row.get("incluye_iva", False)),
            numero_ticket=numero_ticket, nota=row.get("nota") or None,
        )
        self.session.add(pago)
        try:
            self.session.commit()
            return True
        except IntegrityError:
            self.session.rollback()
            return False

    def _apply_pago_proveedor_delete(self, row: dict) -> bool:
        sucursal = (row.get("sucursal") or "").strip()
        numero_ticket = row.get("numero_ticket")
        if not (sucursal and numero_ticket):
            return False
        pago = self.session.query(PagoProveedor).filter_by(
            sucursal=sucursal, numero_ticket=numero_ticket).first()
        if pago:
            self.session.delete(pago)
            self.session.commit()
            return True
        return False

    # ─── Orquestacion ─────────────────────────────────────────────────

    def ejecutar_sincronizacion_completa(self) -> Dict:
        TIPOS = TIPOS_BACKEND
        por_tipo: Dict[str, Dict[str, int]] = {t: {"sent": 0, "recv": 0, "err": 0} for t in TIPOS}
        errores_list = []

        sent_by_type: Dict[str, int] = {}
        try:
            sent_by_type = self._flush_offline_queue(by_type=True) or {}
        except Exception as e:
            errores_list.append(f"Error flush cola: {e}")
        for t, n in sent_by_type.items():
            if t in por_tipo:
                por_tipo[t]["sent"] = n

        try:
            result = self.pull_changes()
            for t in TIPOS:
                por_tipo[t]["recv"] = int(result.get(t, 0) or 0)
            if result.get("errores", 0) > 0:
                errores_list.append(f"{result['errores']} errores al aplicar cambios")
        except Exception as e:
            errores_list.append(f"Error pull Supabase: {e}")

        enviados = sum(p["sent"] for p in por_tipo.values())
        recibidos = sum(p["recv"] for p in por_tipo.values())
        self._log(f"Sync Supabase: {enviados} env, {recibidos} rec, {len(errores_list)} err")
        return {
            "enviados": enviados, "recibidos": recibidos,
            "errores": errores_list, "por_tipo": por_tipo,
        }

    # ─── Test de conexion ─────────────────────────────────────────────

    def test_connection(self) -> Tuple[bool, str]:
        url, pub, secret = self._get_supabase_config()
        if not url:
            return False, "URL de Supabase no configurada."
        if not pub or not secret:
            return False, "Faltan claves (publishable o secret)."

        # v6.8.1: las nuevas keys (sb_publishable_*, sb_secret_*) van solo en apikey,
        # NO en Authorization Bearer (no son JWT).
        # v6.8.2: el endpoint root /rest/v1/ no admite anon (devuelve 401 aunque la key
        # sea valida). Tenemos que testear contra una tabla concreta. /rest/v1/productos
        # con la publishable debe responder 200 si RLS tiene policy "Allow read all".

        # 1) Test publishable contra /rest/v1/productos (lectura anon)
        try:
            r = requests.get(f"{url}/rest/v1/productos",
                             params={"select": "id", "limit": 0},
                             headers={"apikey": pub},
                             timeout=10)
            if r.status_code == 401:
                return False, ("HTTP 401 con la publishable key. "
                               "Verifica que copiaste bien la 'sb_publishable_*'. "
                               "Tambien revisa que las policies RLS permitan SELECT "
                               "anon (las del schema oficial las crean — re-ejecuta "
                               "docs/supabase_schema.sql si dudas).")
            if r.status_code == 404:
                return False, ("Tabla 'productos' no existe — corre el schema SQL "
                               "primero (docs/supabase_schema.sql).")
            if r.status_code not in (200, 206):
                return False, f"Error con publishable (HTTP {r.status_code}): {r.text[:120]}"
        except requests.ConnectionError:
            return False, "No se pudo conectar. Revisa internet o la URL."
        except requests.Timeout:
            return False, "Timeout: Supabase no respondio."

        # 2) Test secret + schema con count en productos
        try:
            r = requests.get(f"{url}/rest/v1/productos",
                             params={"select": "id", "limit": 0},
                             headers={"apikey": secret, "Prefer": "count=exact"},
                             timeout=10)
            if r.status_code in (200, 206):
                cr = r.headers.get("Content-Range", "?")
                count = cr.split("/")[-1] if "/" in cr else "?"
            elif r.status_code == 401:
                return False, ("HTTP 401 con la secret key. "
                               "Verifica que copiaste bien la 'sb_secret_*'.")
            else:
                return False, f"Error con secret (HTTP {r.status_code}): {r.text[:120]}"
        except Exception as e:
            return False, f"Error: {e}"

        # 3) v6.9.3: TEST DE ESCRITURA. Si la secret_key es en realidad
        # sb_publishable_* (anon), RLS bloquea writes y el INSERT silenciosamente
        # devuelve 0 filas. Usamos un INSERT a una fila tipo "ping" + DELETE.
        # Asi detectamos el error temprano y evitamos el sintoma confuso de
        # "todo parece OK pero nada se sincroniza".
        try:
            ping_cuit = f"__ping_{int(time.time() * 1000)}"
            r = requests.post(
                f"{url}/rest/v1/compradores",
                json=[{"cuit": ping_cuit, "nombre": "__test_write__",
                       "sucursal_origen": "__test__", "deleted_at": None}],
                headers={"apikey": secret, "Content-Type": "application/json",
                         "Prefer": "return=representation"},
                timeout=10,
            )
            if r.status_code == 401:
                # Sin permisos. Detectar si es publishable.
                hint = ""
                if secret.startswith("sb_publishable_"):
                    hint = ("\n\n⚠ Tu 'secret_key' empieza con 'sb_publishable_'. "
                            "Eso NO es la secret — es la publishable (anon).\n"
                            "Buscala en Supabase Dashboard > Project Settings > API "
                            "y copia la que empieza con 'sb_secret_*'.")
                return False, (
                    f"La secret_key NO tiene permisos de escritura (HTTP 401)."
                    + hint
                )
            data = []
            try: data = r.json()
            except Exception: data = []
            if r.status_code in (200, 201) and isinstance(data, list) and data:
                # Cleanup: borrar la row de ping
                try:
                    requests.delete(
                        f"{url}/rest/v1/compradores",
                        params={"cuit": f"eq.{ping_cuit}"},
                        headers={"apikey": secret, "Prefer": "return=minimal"},
                        timeout=10,
                    )
                except Exception:
                    pass
                return True, (
                    f"Conexion OK con Supabase.\n"
                    f"  Publishable: OK (lectura)\n"
                    f"  Secret: OK (escritura verificada)\n"
                    f"  Productos en Supabase: {count}"
                )
            else:
                hint = ""
                if secret.startswith("sb_publishable_"):
                    hint = ("\n\n⚠ Detectamos que tu 'secret_key' empieza con "
                            "'sb_publishable_'. Eso es la publishable (anon), no "
                            "la secret. Buscala en Supabase > Project Settings > API.")
                return False, (
                    f"La secret_key parece NO tener permisos de escritura "
                    f"(HTTP {r.status_code}, devolvio {len(data)} filas)."
                    + hint
                )
        except Exception as e:
            return False, f"Error en test de escritura: {e}"

    def get_price_mismatches(self) -> list:
        m = self._price_mismatches
        self._price_mismatches = []
        return m

    # ─── Diagnose ────────────────────────────────────────────────────

    def diagnose_full(self) -> dict:
        from sqlalchemy import func
        result = {"local": {}, "firebase": {}, "upload_queue": {t: 0 for t in TIPOS_BACKEND},
                  "cursors": {}, "ok": True, "error": None}
        # Renombramos el key "firebase" a "supabase" pero mantenemos el shape
        # para compat con la UI actual. La UI lo lee como "fuente remota".
        result["supabase"] = result.pop("firebase")

        try:
            ventas_total = self.session.query(Venta).count()
            por_sucursal_rows = (self.session.query(Venta.sucursal, func.count(Venta.id))
                                 .group_by(Venta.sucursal).all())
            por_sucursal = {(s or "?"): c for s, c in por_sucursal_rows}
            result["local"]["ventas"] = {"total": ventas_total, "por_sucursal": por_sucursal}
            result["local"]["productos"] = self.session.query(Producto).count()
            result["local"]["proveedores"] = self.session.query(Proveedor).count()
            result["local"]["pagos_proveedores"] = self.session.query(PagoProveedor).count()
            result["local"]["compradores"] = self.session.query(Comprador).count()
        except Exception as e:
            result["ok"] = False
            result["error"] = f"Error contando local: {e}"
            return result

        for tipo in TIPOS_BACKEND:
            try:
                count = self._rest_count(TABLA_DE_TIPO[tipo],
                                         params={"deleted_at": "is.null"})
                result["supabase"][tipo] = count
            except Exception as e:
                self._log(f"diagnose count {tipo}: {e}")
                result["supabase"][tipo] = -1

        try:
            queue = self._load_offline_queue()
            for item in queue:
                t = item.get("tipo")
                if t in result["upload_queue"]:
                    result["upload_queue"][t] += 1
        except Exception:
            pass

        result["cursors"] = dict(self._get_last_pull_cursors())
        return result

    def diagnose_pending(self, max_per_type: int = 200) -> dict:
        # Igual shape que Firebase pero leyendo Supabase
        result = {
            "upload": {t: 0 for t in TIPOS_BACKEND},
            "download": {t: 0 for t in TIPOS_BACKEND},
            "last_processed_keys": dict(self._get_last_pull_cursors()),
            "examples_download": {t: [] for t in TIPOS_BACKEND},
            "ok": True, "error": None,
        }
        try:
            queue = self._load_offline_queue()
            for item in queue:
                t = item.get("tipo")
                if t in result["upload"]:
                    result["upload"][t] += 1
        except Exception as e:
            result["ok"] = False
            result["error"] = str(e)
            return result

        cursors = self._get_last_pull_cursors()
        for tipo in TIPOS_BACKEND:
            # v6.9.1: keyset pagination compound (updated_at, id) — ver _pull_tabla
            params = {"select": "*", "limit": str(max_per_type),
                      "order": "updated_at.asc,id.asc"}
            cur = cursors.get(tipo)
            if cur:
                # Aproximacion para diagnose: solo updated_at>cursor (no tracker id
                # entre llamadas a diagnose_pending; si subestima por ties no afecta
                # el conteo en el rango utilizable).
                params["updated_at"] = f"gt.{cur}"
            rows = self._rest_get(TABLA_DE_TIPO[tipo], params) or []
            result["download"][tipo] = len(rows)
            ex = []
            for r in rows[:3]:
                if tipo == "ventas":
                    ex.append(f"#{r.get('numero_ticket') or r.get('numero_ticket_cae') or '?'} de {r.get('sucursal_origen', '?')}")
                elif tipo == "productos":
                    ex.append(f"{r.get('codigo_barra', '?')} ({r.get('sucursal_origen', '?')})")
                elif tipo == "compradores":
                    ex.append(f"CUIT {r.get('cuit', '?')} ({r.get('sucursal_origen', '?')})")
                else:
                    ex.append(f"{r.get('sucursal_origen', '?')}")
            result["examples_download"][tipo] = ex
        return result

    # ─── Pending deletes (paridad con Firebase) ──────────────────────

    def _pending_deletes_path(self) -> str:
        return os.path.join(_get_app_data_dir(), PENDING_DELETES_FILENAME)

    def _load_pending_deletes(self) -> list:
        try:
            p = self._pending_deletes_path()
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception:
            pass
        return []

    def _save_pending_deletes(self, items: list):
        try:
            with open(self._pending_deletes_path(), "w", encoding="utf-8") as f:
                json.dump(items[-500:], f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _enqueue_pending_delete(self, tipo: str, data: dict, origen: str = ""):
        items = self._load_pending_deletes()
        for it in items:
            if it.get("tipo") == tipo and it.get("data", {}).get("codigo_barra") == data.get("codigo_barra"):
                return
        items.append({"tipo": tipo, "origen": origen, "timestamp": int(time.time() * 1000), "data": data})
        self._save_pending_deletes(items)

    def get_pending_deletes(self) -> list:
        return self._load_pending_deletes()

    def accept_pending_delete(self, index: int) -> bool:
        items = self._load_pending_deletes()
        if not (0 <= index < len(items)):
            return False
        item = items.pop(index)
        try:
            tipo = item.get("tipo")
            if tipo == "productos":
                codigo = item.get("data", {}).get("codigo_barra")
                if codigo:
                    prod = self.session.query(Producto).filter_by(codigo_barra=codigo).first()
                    if prod:
                        self.session.delete(prod)
                        self.session.commit()
                        self._log(f"Producto '{codigo}' eliminado tras confirmacion")
            self._save_pending_deletes(items)
            return True
        except Exception:
            self.session.rollback()
            self._save_pending_deletes(items + [item])
            return False

    def reject_pending_delete(self, index: int) -> bool:
        items = self._load_pending_deletes()
        if not (0 <= index < len(items)):
            return False
        item = items.pop(index)
        try:
            tipo = item.get("tipo")
            data = item.get("data", {})
            if tipo == "productos":
                # Re-publicar como upsert con deleted_at=null para deshacer la baja
                body = {
                    "codigo_barra": data.get("codigo_barra"),
                    "nombre": data.get("nombre"), "precio": data.get("precio"),
                    "categoria": data.get("categoria"), "telefono": data.get("telefono"),
                    "numero_cuenta": data.get("numero_cuenta"), "cbu": data.get("cbu"),
                    "sucursal_origen": self.sucursal_local, "deleted_at": None,
                }
                self._rest_upsert("productos", body, on_conflict="codigo_barra")
                self._log(f"Producto '{data.get('codigo_barra')}' delete RECHAZADO — re-upsert")
            self._save_pending_deletes(items)
            return True
        except Exception:
            self._save_pending_deletes(items + [item])
            return False

    # ─── Skipped log (compat con UI Firebase) ────────────────────────

    def get_skipped_log_lines(self, max_lines: int = 200) -> list:
        path = os.path.join(_get_app_data_dir(), "logs", "sync_supabase_skipped.log")
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return f.readlines()[-max_lines:]
        except Exception:
            pass
        return []

    # ─── Realtime (delegado al modulo aparte) ────────────────────────

    def start_realtime(self, on_event=None):
        """Inicia WebSocket Realtime. on_event(tipo, action, row) se llama por evento."""
        try:
            from app.supabase_realtime import SupabaseRealtimeWorker
        except ImportError:
            self._log("Realtime no disponible (websocket-client no instalado)")
            return None
        if self._realtime is not None:
            return self._realtime
        url, pub, _ = self._get_supabase_config()
        worker = SupabaseRealtimeWorker(
            url=url, apikey=pub, sucursal_local=self.sucursal_local,
            tables=tuple(TABLA_DE_TIPO.values()),
            on_event=on_event,
        )
        self._realtime = worker
        worker.start()
        return worker

    def stop_realtime(self):
        if self._realtime is not None:
            try:
                self._realtime.stop()
            except Exception:
                pass
            self._realtime = None


# ─── Helpers ───────────────────────────────────────────────────────

def _ts_to_ms(iso: Optional[str]) -> int:
    if not iso:
        return 0
    try:
        return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() * 1000)
    except Exception:
        return 0
