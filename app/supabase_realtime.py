# app/supabase_realtime.py
# -*- coding: utf-8 -*-
"""
Worker QThread que mantiene una conexión WebSocket con Supabase Realtime y
emite signals Qt cuando llegan eventos INSERT/UPDATE/DELETE.

Protocolo: https://supabase.com/docs/guides/realtime/protocol

Mensajes JSON:
  - join channel: {"topic": "realtime:public:{tabla}", "event": "phx_join", "payload": {...}, "ref": "1"}
  - heartbeat:    {"topic": "phoenix",                 "event": "heartbeat", "payload": {},     "ref": "N"}  cada 30s
  - postgres_changes: arriva como {"topic": "...", "event": "postgres_changes", "payload": {"data": {...}}, "ref": null}

El worker se reconecta automáticamente si la WS se cae. Si websocket-client no
está instalado (ej. al correr la app sin la dependencia), el worker queda como
no-op silenciosamente — el polling sigue funcionando.
"""

import json
import time
import threading
import logging
from typing import Callable, Optional, Tuple

from PyQt5.QtCore import QThread, pyqtSignal

logger = logging.getLogger("supabase_realtime")

try:
    import websocket  # websocket-client
    _WS_AVAILABLE = True
except ImportError:
    _WS_AVAILABLE = False
    logger.warning("websocket-client no esta instalado: Realtime deshabilitado, polling fallback OK")


class SupabaseRealtimeWorker(QThread):
    """
    Mantiene WebSocket a Supabase Realtime escuchando cambios en las tablas
    indicadas. Emite signal `event_received(tipo, action, row_dict)` por cada
    INSERT/UPDATE/DELETE de una sucursal distinta a `sucursal_local`.

    Uso desde MainWindow:
        worker = self._firebase_sync.start_realtime(on_event=self._on_realtime_event)
        # ... vida util de la app
        self._firebase_sync.stop_realtime()  # al cerrar
    """

    # signal: (tipo str, action str: INSERT/UPDATE/DELETE, row dict)
    event_received = pyqtSignal(str, str, dict)
    # signal: True/False — estado de la conexion (verde/rojo en status bar)
    connection_changed = pyqtSignal(bool)

    HEARTBEAT_INTERVAL = 30  # segundos
    RECONNECT_BACKOFF = (2, 5, 15, 30, 60)  # segundos antes de reintentar

    def __init__(self,
                 url: str,
                 apikey: str,
                 sucursal_local: str,
                 tables: Tuple[str, ...],
                 on_event: Optional[Callable] = None,
                 parent=None):
        super().__init__(parent)
        self.url = (url or "").rstrip("/")
        self.apikey = apikey
        self.sucursal_local = sucursal_local
        self.tables = tables
        self._on_event = on_event
        self._stop_flag = False
        self._ws = None
        self._heartbeat_thread = None
        self._ref_counter = 0

    def stop(self):
        self._stop_flag = True
        try:
            if self._ws is not None:
                self._ws.close()
        except Exception:
            pass

    def _ws_url(self) -> str:
        # wss://xxxxx.supabase.co/realtime/v1/websocket?apikey=...&vsn=1.0.0
        host = self.url.replace("https://", "wss://").replace("http://", "ws://")
        return f"{host}/realtime/v1/websocket?apikey={self.apikey}&vsn=1.0.0"

    def _next_ref(self) -> str:
        self._ref_counter += 1
        return str(self._ref_counter)

    def _send(self, msg: dict):
        if self._ws is None:
            return
        try:
            self._ws.send(json.dumps(msg))
        except Exception as e:
            logger.warning(f"WS send error: {e}")

    def _join_channels(self):
        """Subscribe a postgres_changes para cada tabla."""
        for tabla in self.tables:
            topic = f"realtime:public:{tabla}"
            self._send({
                "topic": topic,
                "event": "phx_join",
                "payload": {
                    "config": {
                        "postgres_changes": [
                            {"event": "*", "schema": "public", "table": tabla}
                        ]
                    }
                },
                "ref": self._next_ref(),
            })
            logger.info(f"Realtime: joined {topic}")

    def _heartbeat_loop(self):
        while not self._stop_flag and self._ws is not None:
            time.sleep(self.HEARTBEAT_INTERVAL)
            if self._stop_flag:
                break
            try:
                self._send({
                    "topic": "phoenix",
                    "event": "heartbeat",
                    "payload": {},
                    "ref": self._next_ref(),
                })
            except Exception:
                break

    def _on_message(self, _ws, message):
        try:
            msg = json.loads(message)
        except Exception:
            return
        event = msg.get("event")
        if event != "postgres_changes":
            return

        payload = msg.get("payload") or {}
        data = payload.get("data") or payload  # tolerar shape

        # data trae: {"type": "INSERT|UPDATE|DELETE", "schema": "public",
        #             "table": "productos", "record": {...}, "old_record": {...}}
        action = data.get("type") or data.get("eventType")
        table = data.get("table")
        record = data.get("record") or data.get("new") or {}
        old = data.get("old_record") or data.get("old") or {}

        # v6.8.3: sin filtro anti-eco. La logica de aplicacion local compara
        # timestamps y skipea redundantes. Asi capturamos tambien las ediciones
        # hechas desde el panel web de Supabase, que mantienen sucursal_origen
        # con el valor original (mi propia sucursal cuando yo cree la fila).

        # Mapear table -> tipo logico (en este caso son iguales)
        tipo = table

        # Emitir signal Qt
        try:
            self.event_received.emit(tipo, action or "", record or old or {})
        except Exception as e:
            logger.warning(f"emit signal failed: {e}")

        # Tambien invocar on_event callback si esta seteado (compat fuera de Qt)
        if self._on_event is not None:
            try:
                self._on_event(tipo, action, record or old or {})
            except Exception as e:
                logger.warning(f"on_event callback failed: {e}")

    def _on_open(self, _ws):
        logger.info("Realtime WS conectado")
        self.connection_changed.emit(True)
        self._join_channels()
        # Arrancar heartbeat en thread separado
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()

    def _on_close(self, _ws, code, reason):
        logger.info(f"Realtime WS cerrado (code={code}, reason={reason})")
        self.connection_changed.emit(False)

    def _on_error(self, _ws, err):
        logger.warning(f"Realtime WS error: {err}")

    def run(self):
        if not _WS_AVAILABLE:
            logger.warning("Realtime: websocket-client no instalado, no-op")
            return

        if not self.url or not self.apikey:
            logger.warning("Realtime: URL/apikey faltante")
            return

        backoff_idx = 0
        while not self._stop_flag:
            try:
                self._ws = websocket.WebSocketApp(
                    self._ws_url(),
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_close=self._on_close,
                    on_error=self._on_error,
                )
                # run_forever bloquea hasta que se cierra la WS
                self._ws.run_forever(ping_interval=25, ping_timeout=10)
            except Exception as e:
                logger.warning(f"Realtime run error: {e}")

            if self._stop_flag:
                break

            wait = self.RECONNECT_BACKOFF[min(backoff_idx, len(self.RECONNECT_BACKOFF) - 1)]
            backoff_idx += 1
            logger.info(f"Realtime: reintentando en {wait}s")
            for _ in range(wait):
                if self._stop_flag:
                    return
                time.sleep(1)

        logger.info("Realtime worker terminado")
        self.connection_changed.emit(False)
