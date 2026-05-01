# app/single_instance.py
# -*- coding: utf-8 -*-
"""
Garantia de instancia unica usando QSharedMemory + QLocalServer.

Patron estandar Qt para impedir que la app se abra dos veces:

- QSharedMemory: detecta si ya hay otra instancia corriendo (lock cross-process).
- QLocalServer/QLocalSocket: la 2da instancia notifica a la 1ra que se "muestre",
  para que el usuario no tenga que ir a buscarla manualmente en la bandeja.

Uso tipico (en main.py):

    guard = SingleInstanceGuard()
    if guard.is_already_running():
        guard.notify_existing_to_show()
        QMessageBox.information(None, "...", "La app ya esta abierta...")
        sys.exit(0)
    # ... continuar con app normal ...
    # Despues de crear la MainWindow:
    guard.setup_listener(on_show_request=mw._restore_from_tray)
"""
from __future__ import annotations

import logging
import os
import sys
from typing import Callable, Optional

from PyQt5.QtCore import QObject, QTimer
from PyQt5.QtNetwork import QLocalServer, QLocalSocket

logger = logging.getLogger(__name__)

# Clave del lock — debe ser unica por aplicacion+usuario para evitar colisiones.
# Incluimos el username para que dos sesiones de Windows distintas puedan
# correr cada una su propia instancia.
_DEFAULT_KEY = f"TuLocal2025_singleton_{os.environ.get('USERNAME', 'default')}"

# Mensaje protocol simple: la 2da instancia manda b"SHOW\n" a la 1ra
_SHOW_CMD = b"SHOW"


class SingleInstanceGuard(QObject):
    """
    Lock + IPC para single-instance.

    Llamar:
      1. is_already_running() — al inicio. True => hay otra instancia.
      2. notify_existing_to_show() — solo si is_already_running() devolvio True.
      3. setup_listener(callback) — solo en la 1ra instancia, para reaccionar a
         futuras tentativas de abrir la app.
    """

    def __init__(self, key: str = _DEFAULT_KEY, parent=None):
        super().__init__(parent)
        self._key = key
        self._server: Optional[QLocalServer] = None
        self._is_first_instance: Optional[bool] = None

    # ── deteccion ────────────────────────────────────────────────────

    def is_already_running(self) -> bool:
        """
        Verifica si ya hay otra instancia. Usa un QLocalServer "probe":
        intentamos conectar a un servidor con la key. Si conecta, ya hay
        instancia. Si no, somos los primeros.

        Mas robusto que QSharedMemory en presencia de crashes (QSharedMemory
        en Linux puede dejar el lock huerfano si la app crashea).
        """
        # Limpieza previa: en Windows, si la app crasheo, el QLocalServer
        # puede quedar registrado pero sin proceso vivo. removeServer()
        # lo limpia silenciosamente.
        socket = QLocalSocket()
        socket.connectToServer(self._key)
        connected = socket.waitForConnected(500)  # 500ms timeout
        socket.disconnectFromServer()
        socket.close()

        if connected:
            self._is_first_instance = False
            logger.info("[single-instance] Otra instancia detectada en key=%s", self._key)
            return True

        self._is_first_instance = True
        return False

    # ── IPC: 2da instancia notifica a la 1ra ─────────────────────────

    def notify_existing_to_show(self, timeout_ms: int = 1000) -> bool:
        """
        Llamado desde la 2da instancia: enviar al server de la 1ra el comando
        "mostrate". Devuelve True si la 1ra instancia recibio el mensaje.
        """
        socket = QLocalSocket()
        socket.connectToServer(self._key)
        if not socket.waitForConnected(timeout_ms):
            logger.warning("[single-instance] No se pudo conectar al server existente: %s",
                           socket.errorString())
            return False
        try:
            socket.write(_SHOW_CMD + b"\n")
            socket.flush()
            socket.waitForBytesWritten(timeout_ms)
            return True
        except Exception as e:
            logger.warning("[single-instance] Error enviando SHOW: %s", e)
            return False
        finally:
            socket.disconnectFromServer()
            socket.close()

    # ── Listener: la 1ra instancia escucha ───────────────────────────

    def setup_listener(self, on_show_request: Callable[[], None]) -> None:
        """
        Llamado desde la 1ra instancia: empieza a escuchar pedidos de "mostrate"
        de futuras instancias. Cuando llega un mensaje SHOW, dispara el callback.
        """
        if self._is_first_instance is False:
            logger.warning("[single-instance] setup_listener llamado en 2da instancia (no-op)")
            return

        # Si quedo un server "fantasma" de un crash anterior, limpiarlo
        QLocalServer.removeServer(self._key)

        self._server = QLocalServer(self)
        if not self._server.listen(self._key):
            logger.warning("[single-instance] No se pudo iniciar QLocalServer: %s",
                           self._server.errorString())
            self._server = None
            return

        def _on_new_connection():
            sock = self._server.nextPendingConnection()
            if not sock:
                return

            def _on_ready_read():
                data = bytes(sock.readAll())
                if _SHOW_CMD in data:
                    logger.info("[single-instance] Pedido SHOW recibido")
                    # Disparar el callback en el event loop principal (no en el handler)
                    QTimer.singleShot(0, on_show_request)
                sock.disconnectFromServer()

            sock.readyRead.connect(_on_ready_read)
            # Si ya hay datos disponibles, procesarlos ahora
            if sock.bytesAvailable() > 0:
                _on_ready_read()

        self._server.newConnection.connect(_on_new_connection)
        logger.info("[single-instance] Listener activo en key=%s", self._key)

    def cleanup(self) -> None:
        """Llamar al cerrar la app para liberar el server."""
        if self._server is not None:
            try:
                self._server.close()
            except Exception:
                pass
            self._server = None
