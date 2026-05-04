# app/sync_dispatcher.py
# -*- coding: utf-8 -*-
"""
Dispatcher de backends de sync: elige FirebaseSyncManager, SupabaseSyncManager
o DualSyncManager segun config.

DualSyncManager (modo de validacion previo al cutover):
- Push: A AMBOS backends. Si Supabase falla, NO aborta Firebase.
- Pull: solo del primario (Firebase).
- Realtime: arranca Supabase WS (informativo, no aplica datos en este modo).

Riesgo Firebase = 0 (no se modifica su flujo). Supabase queda como espejo.

Uso:
    backend = (load_config().get("sync") or {}).get("backend", "firebase")
    manager = build_sync_manager(session, sucursal, backend)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

logger = logging.getLogger("sync_dispatcher")


def build_sync_manager(session: Session, sucursal_local: str,
                       backend: str = "supabase"):
    """Factory: devuelve la instancia correcta segun backend.

    v6.9.2: default cambiado a 'supabase' (usuario migro). Firebase queda
    disponible si alguien explicita backend='firebase' en config.
    """
    backend = (backend or "supabase").lower()
    if backend == "supabase":
        from app.supabase_sync import SupabaseSyncManager
        return SupabaseSyncManager(session, sucursal_local)
    if backend == "dual":
        from app.firebase_sync import FirebaseSyncManager
        from app.supabase_sync import SupabaseSyncManager
        primary = FirebaseSyncManager(session, sucursal_local)
        secondary = SupabaseSyncManager(session, sucursal_local)
        return DualSyncManager(primary, secondary, sucursal_local)
    if backend == "firebase":
        from app.firebase_sync import FirebaseSyncManager
        return FirebaseSyncManager(session, sucursal_local)

    # default: supabase
    from app.supabase_sync import SupabaseSyncManager
    return SupabaseSyncManager(session, sucursal_local)


class DualSyncManager:
    """Wrapper que envia los push a 2 backends en paralelo.

    Pull, realtime y diagnose vienen del primario. El secundario solo se llena
    via push: si falla, se loggea y se sigue.

    No modifica los managers internos — solo los compone.
    """

    def __init__(self, primary, secondary, sucursal_local: str):
        self.primary = primary           # FirebaseSyncManager (autoritativo)
        self.secondary = secondary       # SupabaseSyncManager (espejo)
        self.sucursal_local = sucursal_local
        # Compat: codigo viejo lee `_log_path` y `session` del manager
        self._log_path = getattr(primary, "_log_path", None)
        self.session = getattr(primary, "session", None)
        self._price_mismatches: List[dict] = []

    def _log(self, msg: str):
        try:
            self.primary._log(f"[DUAL] {msg}")
        except Exception:
            pass

    def _safe_secondary(self, name: str, *args, **kwargs):
        """Llama a secondary.<name>(*args) y captura excepciones para no romper push primario."""
        fn = getattr(self.secondary, name, None)
        if fn is None:
            return None
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            logger.warning("[DUAL] secundario %s fallo: %s", name, e)
            self._log(f"secundario {name} fallo: {e}")
            return None

    # ─── Push ───────────────────────────────────────────────────────

    # Cada push delega primero a primary (resultado autoritativo) y despues
    # a secondary (best-effort). Si secondary lanza una excepcion, la captura
    # _safe_secondary y se loggea sin propagar.

    def push_producto(self, producto, accion: str = "upsert"):
        self.primary.push_producto(producto, accion)
        self._safe_secondary("push_producto", producto, accion)

    def push_producto_eliminado(self, codigo_barra: str):
        self.primary.push_producto_eliminado(codigo_barra)
        self._safe_secondary("push_producto_eliminado", codigo_barra)

    def push_productos_batch(self, productos):
        ok = self.primary.push_productos_batch(productos)
        self._safe_secondary("push_productos_batch", productos)
        return ok

    def push_proveedor(self, proveedor, accion: str = "upsert"):
        self.primary.push_proveedor(proveedor, accion)
        self._safe_secondary("push_proveedor", proveedor, accion)

    def push_proveedor_eliminado(self, nombre: str):
        self.primary.push_proveedor_eliminado(nombre)
        self._safe_secondary("push_proveedor_eliminado", nombre)

    def push_comprador(self, comprador, accion: str = "upsert"):
        self.primary.push_comprador(comprador, accion)
        self._safe_secondary("push_comprador", comprador, accion)

    def push_comprador_eliminado(self, cuit: str):
        self.primary.push_comprador_eliminado(cuit)
        self._safe_secondary("push_comprador_eliminado", cuit)

    def push_venta(self, venta):
        self.primary.push_venta(venta)
        self._safe_secondary("push_venta", venta)

    def push_venta_modificada(self, venta):
        self.primary.push_venta_modificada(venta)
        self._safe_secondary("push_venta_modificada", venta)

    def push_venta_eliminada(self, venta):
        # Firebase puede no tener este metodo en versiones viejas
        if hasattr(self.primary, "push_venta_eliminada"):
            self.primary.push_venta_eliminada(venta)
        self._safe_secondary("push_venta_eliminada", venta)

    def push_pago_proveedor(self, pago):
        self.primary.push_pago_proveedor(pago)
        self._safe_secondary("push_pago_proveedor", pago)

    def push_all_existing(self, callback=None, tipos=None) -> Dict[str, int]:
        """Bulk push: corre primary, despues secondary. Devuelve combinado."""
        result_p = self.primary.push_all_existing(callback=callback, tipos=tipos)
        # Secondary corre en background pero esperamos a que termine para
        # poder reportar el resultado. Si falla, no rompe el bulk de primary.
        result_s = self._safe_secondary("push_all_existing", callback=callback, tipos=tipos) or {}
        out = dict(result_p or {})
        out["secondary"] = result_s
        return out

    # ─── Pull / orquestacion (solo primario) ───────────────────────

    def pull_changes(self, *args, **kwargs):
        return self.primary.pull_changes(*args, **kwargs)

    def force_pull_all(self, *args, **kwargs):
        return self.primary.force_pull_all(*args, **kwargs)

    def reset_pull_cursors(self):
        return self.primary.reset_pull_cursors()

    def ejecutar_sincronizacion_completa(self) -> Dict:
        result = self.primary.ejecutar_sincronizacion_completa()
        # Tambien hacer flush de la cola offline del secundario para que
        # los pushes que fallaron antes se reintenten
        try:
            if hasattr(self.secondary, "_flush_offline_queue"):
                sent = self.secondary._flush_offline_queue(by_type=True) or {}
                if sent:
                    self._log(f"secondary cola offline flush: {sent}")
        except Exception as e:
            self._log(f"secondary flush offline error: {e}")
        return result

    # ─── Diagnose ───────────────────────────────────────────────────

    def diagnose_full(self) -> dict:
        return self.primary.diagnose_full()

    def diagnose_pending(self, max_per_type: int = 200) -> dict:
        return self.primary.diagnose_pending(max_per_type)

    def diagnose_full_dual(self) -> dict:
        """Devuelve ambos diagnosticos lado a lado para auditoria."""
        return {
            "primary": self.primary.diagnose_full(),
            "secondary": self._safe_secondary("diagnose_full") or {},
        }

    # ─── Test de conexion ──────────────────────────────────────────

    def test_connection(self) -> Tuple[bool, str]:
        ok_p, msg_p = self.primary.test_connection()
        ok_s, msg_s = (False, "Supabase no probado")
        try:
            ok_s, msg_s = self.secondary.test_connection()
        except Exception as e:
            ok_s, msg_s = False, f"Excepcion: {e}"
        combined_ok = ok_p and ok_s
        msg = (
            "[Modo Dual]\n\n"
            f"FIREBASE (primario): {'OK' if ok_p else 'FAIL'}\n  {msg_p}\n\n"
            f"SUPABASE (secundario): {'OK' if ok_s else 'FAIL'}\n  {msg_s}"
        )
        return combined_ok, msg

    # ─── Realtime (solo Supabase) ───────────────────────────────────

    def start_realtime(self, on_event=None):
        if hasattr(self.secondary, "start_realtime"):
            return self.secondary.start_realtime(on_event)
        return None

    def stop_realtime(self):
        if hasattr(self.secondary, "stop_realtime"):
            return self.secondary.stop_realtime()
        return None

    # ─── Compat: pending deletes (vienen del primario) ─────────────

    def get_pending_deletes(self) -> list:
        if hasattr(self.primary, "get_pending_deletes"):
            return self.primary.get_pending_deletes()
        return []

    def accept_pending_delete(self, index: int) -> bool:
        if hasattr(self.primary, "accept_pending_delete"):
            return self.primary.accept_pending_delete(index)
        return False

    def reject_pending_delete(self, index: int) -> bool:
        if hasattr(self.primary, "reject_pending_delete"):
            return self.primary.reject_pending_delete(index)
        return False

    def get_skipped_log_lines(self, max_lines: int = 200) -> list:
        if hasattr(self.primary, "get_skipped_log_lines"):
            return self.primary.get_skipped_log_lines(max_lines)
        return []

    def get_price_mismatches(self) -> list:
        try:
            return self.primary.get_price_mismatches()
        except Exception:
            return []

    # Compat con codigo viejo que toca atributos del manager directamente
    def __getattr__(self, item):
        # Fallback al primario para cualquier atributo no definido aqui
        return getattr(self.primary, item)
