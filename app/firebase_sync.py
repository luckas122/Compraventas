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
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import requests
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models import Venta, VentaItem, Producto, Proveedor, VentaLog
from app.config import load as load_config, save as save_config, _get_app_data_dir

logger = logging.getLogger("firebase_sync")

QUEUE_FILENAME = "sync_queue.json"
MAX_QUEUE_SIZE = 10000
REQUEST_TIMEOUT = 15  # segundos


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
        os.makedirs(os.path.dirname(self._log_path), exist_ok=True)

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

    def _flush_offline_queue(self) -> int:
        """Envia todos los cambios en cola a Firebase. Retorna cantidad enviados."""
        queue = self._load_offline_queue()
        if not queue:
            return 0

        sent = 0
        remaining = []
        for change in queue:
            path = f"cambios/{change['tipo']}"
            key = self._firebase_post(path, change)
            if key:
                sent += 1
            else:
                remaining.append(change)

        self._save_offline_queue(remaining)
        if sent > 0:
            self._log(f"Cola offline: {sent} enviados, {len(remaining)} pendientes")
        return sent

    # ─── Push: local -> Firebase ──────────────────────────────────────

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
                "items": items_data
            }
        }

        key = self._firebase_post("cambios/ventas", data)
        if not key:
            self._enqueue_change("ventas", "create", data["data"])
        else:
            self._log(f"Venta #{venta.numero_ticket} publicada: {key}")

    def push_venta_modificada(self, venta: Venta):
        """Publica una modificacion de venta (devolucion) en Firebase."""
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
                "sucursal": venta.sucursal,
                "total": venta.total,
                "vuelto": venta.vuelto,
                "items": items_data
            }
        }

        key = self._firebase_post("cambios/ventas", data)
        if not key:
            self._enqueue_change("ventas", "update", data["data"])
        else:
            self._log(f"Venta #{venta.numero_ticket} modificada: {key}")

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
                "nombre": proveedor.nombre,
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

    # ─── Pull: Firebase -> local ──────────────────────────────────────

    def _get_last_processed_keys(self) -> Dict[str, Optional[str]]:
        """Retorna dict con el ultimo key procesado por cada tipo de entidad."""
        sync_cfg = self._get_sync_config()
        keys = sync_cfg.get("last_processed_keys", {})
        if not isinstance(keys, dict):
            # Migrar desde el formato viejo (key unico global)
            old_key = sync_cfg.get("last_processed_key")
            keys = {"ventas": old_key, "productos": old_key, "proveedores": old_key}
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

    def pull_changes(self) -> Dict[str, int]:
        """
        Descarga y aplica cambios nuevos desde Firebase.
        Retorna {"ventas": N, "productos": N, "proveedores": N, "errores": N}
        """
        result = {"ventas": 0, "productos": 0, "proveedores": 0, "errores": 0}
        last_keys = self._get_last_processed_keys()

        for tipo in ["ventas", "productos", "proveedores"]:
            entity_last_key = last_keys.get(tipo)
            count, errors, new_last = self._pull_entity(tipo, entity_last_key)
            result[tipo] = count
            result["errores"] += errors
            if new_last:
                self._set_last_processed_key(tipo, new_last)

        return result

    def _pull_entity(self, tipo: str, last_key: Optional[str]) -> Tuple[int, int, Optional[str]]:
        """
        Descarga cambios de un tipo. Retorna (aplicados, errores, ultimo_key).
        """
        params = {"orderBy": '"$key"'}
        if last_key:
            params["startAt"] = f'"{last_key}"'

        self._log(f"Pull {tipo}: last_key={last_key}")
        data = self._firebase_get(f"cambios/{tipo}", params)
        if data is None:
            self._log(f"Pull {tipo}: sin respuesta de Firebase (error de red o auth)")
            return 0, 0, None
        if not isinstance(data, dict) or len(data) == 0:
            self._log(f"Pull {tipo}: sin cambios nuevos")
            return 0, 0, None

        self._log(f"Pull {tipo}: {len(data)} entradas recibidas")

        applied = 0
        errors = 0
        newest_key = None

        for push_key in sorted(data.keys()):
            # Saltar el key anterior (startAt es inclusivo)
            if push_key == last_key:
                continue

            change = data[push_key]
            if not isinstance(change, dict):
                continue

            # Ignorar cambios propios
            if change.get("sucursal_origen") == self.sucursal_local:
                newest_key = push_key
                continue

            try:
                ok = self._apply_change(tipo, change)
                if ok:
                    applied += 1
                    self._log(f"Pull {tipo}/{push_key}: aplicado OK")
                else:
                    self._log(f"Pull {tipo}/{push_key}: ya existia o no aplica")
                newest_key = push_key
            except Exception as e:
                self._log(f"Error aplicando {tipo}/{push_key}: {e}")
                errors += 1
                newest_key = push_key

        return applied, errors, newest_key

    def _apply_change(self, tipo: str, change: dict) -> bool:
        accion = change.get("accion", "create")
        data = change.get("data", {})
        timestamp = change.get("timestamp", 0)

        if tipo == "ventas":
            if accion == "update":
                return self._apply_venta_update(data)
            return self._apply_venta(data)
        elif tipo == "productos":
            if accion == "delete":
                return self._apply_producto_delete(data)
            return self._apply_producto(data, timestamp)
        elif tipo == "proveedores":
            if accion == "delete":
                return self._apply_proveedor_delete(data)
            return self._apply_proveedor(data, timestamp)
        return False

    # ─── Aplicar cambios a SQLite local ───────────────────────────────

    def _apply_venta(self, data: dict) -> bool:
        """Inserta una venta remota en la base local."""
        numero_ticket = data.get("numero_ticket")
        sucursal = data.get("sucursal")
        if not numero_ticket or not sucursal:
            return False

        # Verificar duplicado
        existing = self.session.query(Venta).filter_by(
            numero_ticket=numero_ticket
        ).first()
        if existing:
            return False  # Ya existe

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
            afip_cae=data.get("afip_cae"),
            afip_cae_vencimiento=data.get("afip_cae_vencimiento"),
            afip_numero_comprobante=data.get("afip_numero_comprobante"),
        )

        self.session.add(venta)
        try:
            self.session.flush()
        except IntegrityError:
            self.session.rollback()
            return False

        # Agregar items
        for item_data in (data.get("items") or []):
            codigo = item_data.get("codigo_barra", "")
            prod = self.session.query(Producto).filter_by(codigo_barra=codigo).first() if codigo else None

            vi = VentaItem(
                venta_id=venta.id,
                producto_id=prod.id if prod else None,
                cantidad=int(item_data.get("cantidad", 1)),
                precio_unit=float(item_data.get("precio_unit", 0))
            )
            self.session.add(vi)

        self.session.commit()
        self._log(f"Venta #{numero_ticket} recibida de {sucursal}")
        return True

    def _apply_venta_update(self, data: dict) -> bool:
        """Aplica una modificacion de venta (devolucion)."""
        numero_ticket = data.get("numero_ticket")
        if not numero_ticket:
            return False

        venta = self.session.query(Venta).filter_by(numero_ticket=numero_ticket).first()
        if not venta:
            return False

        if "total" in data:
            venta.total = float(data["total"])
        if "vuelto" in data:
            venta.vuelto = data["vuelto"]

        # Actualizar items si vienen
        items_data = data.get("items")
        if items_data is not None:
            # Eliminar items actuales
            for item in list(venta.items):
                self.session.delete(item)
            self.session.flush()

            # Recrear items
            for item_data in items_data:
                codigo = item_data.get("codigo_barra", "")
                prod = self.session.query(Producto).filter_by(codigo_barra=codigo).first() if codigo else None
                vi = VentaItem(
                    venta_id=venta.id,
                    producto_id=prod.id if prod else None,
                    cantidad=int(item_data.get("cantidad", 1)),
                    precio_unit=float(item_data.get("precio_unit", 0))
                )
                self.session.add(vi)

        self.session.commit()
        self._log(f"Venta #{numero_ticket} actualizada (devolucion)")
        return True

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

            prod.nombre = data.get("nombre", prod.nombre)
            prod.precio = float(data.get("precio", prod.precio))
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
            self._log(f"Producto '{codigo}' sincronizado")
            return True
        except IntegrityError:
            self.session.rollback()
            return False

    def _apply_producto_delete(self, data: dict) -> bool:
        """Elimina un producto local si existe."""
        codigo = data.get("codigo_barra")
        if not codigo:
            return False
        prod = self.session.query(Producto).filter_by(codigo_barra=codigo).first()
        if prod:
            self.session.delete(prod)
            self.session.commit()
            self._log(f"Producto '{codigo}' eliminado por sync")
            return True
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

    # ─── Orquestacion ─────────────────────────────────────────────────

    def ejecutar_sincronizacion_completa(self) -> Dict:
        """
        Ciclo completo de sync:
        1. Flush cola offline
        2. Pull cambios remotos
        Retorna {"enviados": N, "recibidos": N, "errores": []}
        """
        enviados = 0
        errores_list = []

        # 1. Flush cola offline
        try:
            enviados = self._flush_offline_queue()
        except Exception as e:
            errores_list.append(f"Error flush cola: {e}")

        # 2. Pull cambios remotos
        recibidos = 0
        try:
            result = self.pull_changes()
            recibidos = result.get("ventas", 0) + result.get("productos", 0) + result.get("proveedores", 0)
            if result.get("errores", 0) > 0:
                errores_list.append(f"{result['errores']} errores al aplicar cambios")
        except Exception as e:
            errores_list.append(f"Error pull: {e}")

        self._log(f"Sync completa: {enviados} enviados, {recibidos} recibidos, {len(errores_list)} errores")

        return {
            "enviados": enviados,
            "recibidos": recibidos,
            "errores": errores_list
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

    # ─── Logging ──────────────────────────────────────────────────────

    def _log(self, msg: str):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] [{self.sucursal_local}] {msg}"
        logger.info(line)
        try:
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass
