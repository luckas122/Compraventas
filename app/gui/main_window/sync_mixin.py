"""Mixin con métodos de bandeja del sistema, sincronización Firebase,
sonido y barra de estado.  Se separan de core.py para reducir su tamaño."""

import os
import sys
import logging
from pathlib import Path
from datetime import datetime

from PyQt5.QtWidgets import (
    QApplication, QLabel, QMenu, QPushButton,
    QMessageBox, QAction, QSystemTrayIcon, QFileDialog,
)
from PyQt5.QtCore import Qt, QTimer, QUrl
from PyQt5.QtMultimedia import QSoundEffect

from app.config import (
    load as load_config,
    save as save_config,
    has_pending_backup,
    restore_from_backup,
    restore_from_path,
    get_backup_path,
    CONFIG_PATH,
)
from app.firebase_sync import FirebaseSyncManager

logger = logging.getLogger(__name__)


class SyncNotificationsMixin:
    """Agrupa funcionalidad de tray-icon, sync Firebase, sonido y status bar."""

    # ============================
    #  Icono en bandeja del sistema
    # ============================
    def _init_tray_icon(self):
        """Crea el icono en la bandeja si la opción está activada."""
        if not getattr(self, "_minimize_to_tray_on_close", False):
            return  # opción desactivada: nada que hacer

        try:
            app = QApplication.instance()
        except Exception:
            app = None

        icon = None
        try:
            if app is not None and not app.windowIcon().isNull():
                icon = app.windowIcon()
            elif not self.windowIcon().isNull():
                icon = self.windowIcon()
        except Exception:
            icon = None

        self.tray = QSystemTrayIcon(self)
        if icon is not None:
            self.tray.setIcon(icon)
        self.tray.setToolTip("TuLocal 2025 - Compras y Ventas")

        menu = QMenu(self)

        act_show   = QAction("Mostrar ventana", self)
        act_backup = QAction("Hacer backup ahora", self)
        act_exit   = QAction("Salir", self)

        act_show.triggered.connect(self._restore_from_tray)
        act_backup.triggered.connect(self._backup_now_from_tray)
        act_exit.triggered.connect(self._quit_from_tray)

        menu.addAction(act_show)
        menu.addSeparator()
        menu.addAction(act_backup)
        menu.addSeparator()
        menu.addAction(act_exit)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)

        self._tray_notified = False
        self.tray.show()

    def _on_tray_activated(self, reason):
        """Restaurar ventana al hacer clic en el icono de bandeja."""
        try:
            if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
                self._restore_from_tray()
        except Exception:
            pass

    def _restore_from_tray(self):
        """Muestra la ventana si está oculta/minimizada."""
        try:
            self.showNormal()
            self.show()
            self.raise_()
            self.activateWindow()
        except Exception:
            pass

    def _backup_now_from_tray(self):
        """Lanza un backup manual desde el menú de bandeja."""
        try:
            if hasattr(self, "_backup_now_from_ui"):
                self._backup_now_from_ui()
            else:
                self._run_backup(tag="manual")
        except Exception as e:
            try:
                QMessageBox.warning(self, "Backup", f"No se pudo ejecutar el backup:\n{e}")
            except Exception:
                pass

    def _quit_from_tray(self):
        """Sale completamente de la aplicación (cierra hilos de backup y timers)."""
        try:
            if hasattr(self, "_stop_backups"):
                self._stop_backups()
        except Exception:
            pass

        # Limpiar recursos (cerrar sesión BD, etc.)
        self._cleanup_resources()

        try:
            QApplication.quit()
        except Exception:
            import sys
            sys.exit(0)

    # ============================
    #  SINCRONIZACION (Firebase / Supabase)
    # ============================

    def _make_sync_manager(self, session, sucursal):
        """Factory de sync manager.

        v6.8.0: agrego soporte Supabase.
        v6.9.0: delegado a sync_dispatcher.build_sync_manager para soportar
            tambien backend='dual' (Firebase primario + Supabase secundario).
        Mantengo `_firebase_sync` como nombre del slot por compat con los 30+
        callsites — el nombre ya no refleja el backend, es solo el slot.
        """
        cfg = load_config()
        backend = (cfg.get("sync") or {}).get("backend", "supabase")
        try:
            from app.sync_dispatcher import build_sync_manager
            return build_sync_manager(session, sucursal, backend)
        except Exception as e:
            logger.error(f"[SYNC] Falla en build_sync_manager (backend={backend}): {e}, fallback Supabase")
            try:
                from app.supabase_sync import SupabaseSyncManager
                return SupabaseSyncManager(session, sucursal)
            except Exception:
                return FirebaseSyncManager(session, sucursal)

    def _start_supabase_realtime(self):
        """v6.8.0: arranca el QThread de Realtime contra Supabase si es posible."""
        if not self._firebase_sync:
            return
        if not hasattr(self._firebase_sync, "start_realtime"):
            return  # backend no soporta realtime (Firebase)
        try:
            worker = self._firebase_sync.start_realtime(on_event=None)
            if worker is None:
                return
            # Conectar signals al hilo principal — los applies usan la session principal
            worker.event_received.connect(self._on_realtime_event)
            worker.connection_changed.connect(self._on_realtime_connection_changed)
            logger.info("[SYNC] Realtime worker arrancado")
        except Exception as e:
            logger.warning(f"[SYNC] start_realtime fallo: {e}")

    def _on_realtime_event(self, tipo, action, row):
        """v6.8.0: cada evento INSERT/UPDATE/DELETE de Supabase Realtime se
        aplica al SQLite local con el mismo `_apply_*` que usa el polling.

        v6.9.2: si el evento gatilla un pending delete (popup), disparar
        `_procesar_pending_deletes` para que el popup se vea sin esperar al
        proximo ciclo de sync.
        v6.9.5: agregar logging explicito (action + tipo + key) para
        diagnosticar el bug del popup asimetrico (Salta->Sarmiento no
        muestra popup pero al reves si).
        """
        if not self._firebase_sync:
            logger.info(f"[REALTIME] {tipo}/{action} ignorado: _firebase_sync=None")
            return
        if not hasattr(self._firebase_sync, "_apply_row"):
            logger.info(f"[REALTIME] {tipo}/{action} ignorado: backend sin _apply_row")
            return
        try:
            # Marcar deleted_at para mapear a delete en _apply_row
            is_delete_or_softdelete = False
            if action == "DELETE" or (row and row.get("deleted_at")):
                row = dict(row)
                row["deleted_at"] = row.get("deleted_at") or "now"
                is_delete_or_softdelete = True
            # v6.9.5: log explicito del evento recibido
            try:
                _key = (row.get("codigo_barra") or row.get("cuit")
                        or row.get("numero_ticket") or row.get("id") or "?")
                logger.info(
                    f"[REALTIME] {tipo}/{action} recv key={_key} delete={is_delete_or_softdelete} "
                    f"sucursal_origen={row.get('sucursal_origen', '?')}"
                )
            except Exception:
                pass
            self._firebase_sync._apply_row(tipo, row)
            # Refrescos minimos en UI segun tipo
            try:
                if tipo == "productos":
                    self.refrescar_productos()
                elif tipo == "proveedores":
                    self.cargar_lista_proveedores()
                elif tipo == "compradores" and hasattr(self, 'cargar_lista_compradores'):
                    self.cargar_lista_compradores()
            except Exception:
                pass
            # v6.9.2: si fue una baja, abrir el popup pendiente al toque
            if is_delete_or_softdelete:
                try:
                    QTimer.singleShot(0, self._procesar_pending_deletes)
                except Exception as _e:
                    logger.warning(f"[SYNC] No pude triggear popup pending: {_e}")
        except Exception as e:
            logger.warning(f"[SYNC] Realtime apply {tipo}/{action} fallo: {e}")

    def _on_realtime_connection_changed(self, connected: bool):
        """v6.8.0: actualizar status bar con estado de Realtime."""
        if connected:
            self._update_sync_button_text("Realtime ON")
        # Si se cae, dejamos el texto que estaba (polling sigue activo)

    def _setup_sync_scheduler(self):
        """Configura el scheduler de sincronizacion desde app_config.json"""
        cfg = load_config()
        sync_cfg = cfg.get("sync", {})

        enabled = sync_cfg.get("enabled", False)
        mode = sync_cfg.get("mode", "interval")
        interval_min = sync_cfg.get("interval_minutes", 5)

        self._sync_timer.stop()

        if not enabled:
            self._firebase_sync = None
            logger.info("[SYNC] Sincronizacion desactivada")
            self._update_sync_button_text("Sync desactivada")
            return

        # v6.8.0: dispatcher segun sync.backend (firebase/supabase)
        sucursal_actual = getattr(self, 'sucursal', 'Sarmiento')
        self._firebase_sync = self._make_sync_manager(self.session, sucursal_actual)
        backend_name = sync_cfg.get("backend", "firebase")
        logger.info(f"[SYNC] Sync activada (backend={backend_name}), modo={mode}, intervalo={interval_min}min")

        # v6.8.0: si backend es Supabase y realtime esta activo, arrancar WebSocket
        try:
            sb_cfg = sync_cfg.get("supabase") or {}
            if backend_name == "supabase" and sb_cfg.get("realtime_enabled", True):
                self._start_supabase_realtime()
        except Exception as _e:
            logger.warning(f"[SYNC] No se pudo iniciar Realtime: {_e}")

        if mode == "interval":
            ms = max(interval_min * 60 * 1000, 120_000)  # mínimo 2 minutos
            self._sync_timer.setInterval(ms)
            self._sync_timer.start()
            logger.info(f"[SYNC] Timer iniciado: cada {ms}ms ({max(interval_min, 2)} min)")

        # Solo disparar singleShot la PRIMERA vez (no al reconfigurar)
        # Esto evita syncs duplicadas cuando se guarda la configuración
        if not getattr(self, '_sync_initial_fired', False):
            self._sync_initial_fired = True
            QTimer.singleShot(3000, lambda: self._ejecutar_sincronizacion(manual=False))

    def _reiniciar_sync_scheduler(self):
        """Reinicia el scheduler cuando se guarda la configuracion (sin sync inmediata)."""
        self._setup_sync_scheduler()
        self._actualizar_texto_boton_sync()

    def _ejecutar_sincronizacion(self, manual=False):
        """Ejecuta un ciclo de sincronizacion via Firebase (en hilo background)."""
        cfg = load_config()
        sync_cfg = cfg.get("sync", {})
        enabled = sync_cfg.get("enabled", False)
        if not enabled:
            if manual:
                QMessageBox.information(self, "Sincronización",
                    "La sincronización está desactivada en Configuración.")
            return

        if not self._firebase_sync:
            sucursal_actual = getattr(self, 'sucursal', 'Sarmiento')
            self._firebase_sync = self._make_sync_manager(self.session, sucursal_actual)

        # Evitar multiples syncs simultaneas - pero verificar si realmente hay hilo vivo
        if self._sync_running:
            thread_alive = self._sync_thread is not None and self._sync_thread.is_alive()
            if not thread_alive:
                # El hilo murió pero el flag quedó en True → resetear
                logger.warning("[SYNC] _sync_running=True pero hilo muerto, reseteando")
                self._sync_running = False
            else:
                if manual:
                    self._mostrar_sync_en_curso()
                return

        self._sync_running = True
        self._sync_start_time = datetime.now()

        # Liberar cualquier lock pendiente de la sesión principal ANTES de lanzar
        # el thread de sync. Esto evita "database is locked" por contención.
        try:
            self.session.commit()
        except Exception:
            try:
                self.session.rollback()
            except Exception:
                pass

        # Actualizar botón para indicar sync en curso
        self._update_sync_button_text("⟳ Sincronizando... 0s")

        # Iniciar timer de progreso (muestra elapsed time cada segundo)
        if not hasattr(self, '_sync_progress_timer') or self._sync_progress_timer is None:
            self._sync_progress_timer = QTimer(self)
            self._sync_progress_timer.timeout.connect(self._update_sync_progress)
        self._sync_progress_timer.start(1000)

        import threading

        def _sync_worker():
            resultado = None
            err_msg = None
            try:
                from app.database import SessionLocal
                from sqlalchemy import text as _sa_text
                thread_session = SessionLocal()
                # Timeout largo para el thread de sync (30s) — da tiempo a que
                # la sesión principal libere cualquier lock de escritura
                try:
                    thread_session.execute(_sa_text("PRAGMA busy_timeout=30000"))
                except Exception:
                    pass
                try:
                    sucursal = getattr(self, 'sucursal', 'Sarmiento')
                    sync_manager = self._make_sync_manager(thread_session, sucursal)
                    resultado = sync_manager.ejecutar_sincronizacion_completa()
                    mismatches = sync_manager.get_price_mismatches()
                    resultado["_mismatches"] = mismatches
                finally:
                    thread_session.close()
            except Exception as e:
                err_msg = str(e)
                logger.error(f"[SYNC] Worker exception: {err_msg}")
            finally:
                # SIEMPRE notificar al hilo principal, pase lo que pase
                if resultado is not None:
                    QTimer.singleShot(0, lambda r=resultado: self._on_sync_finished(r))
                else:
                    err = err_msg or "Error desconocido en sync"
                    QTimer.singleShot(0, lambda e=err: self._on_sync_error(e))

        t = threading.Thread(target=_sync_worker, daemon=True)
        self._sync_thread = t
        t.start()

        # Watchdog: resetear flag si la sync tarda mas de 5 minutos
        # (los reintentos con back-off exponencial pueden tardar hasta ~93s)
        QTimer.singleShot(300_000, self._sync_watchdog_reset)

    def _mostrar_sync_en_curso(self):
        """Muestra diálogo con info de la sync en curso y opción de cancelar."""
        elapsed = ""
        if self._sync_start_time:
            secs = int((datetime.now() - self._sync_start_time).total_seconds())
            elapsed = f"\nTiempo transcurrido: {secs} segundos"

        thread_info = ""
        if self._sync_thread is not None:
            if self._sync_thread.is_alive():
                thread_info = "\nEstado: hilo ACTIVO"
            else:
                thread_info = "\nEstado: hilo FINALIZADO (flag no se reseteó)"

        msg = QMessageBox(self)
        msg.setWindowTitle("Sincronización en curso")
        msg.setIcon(QMessageBox.Information)
        msg.setText(
            f"Hay una sincronización ejecutándose.{elapsed}{thread_info}\n\n"
            f"Si el proceso quedó trabado, cancelalo para\n"
            f"poder sincronizar nuevamente."
        )
        btn_cancel = msg.addButton("Cancelar y reintentar", QMessageBox.DestructiveRole)
        btn_ok = msg.addButton("Esperar", QMessageBox.AcceptRole)
        msg.setDefaultButton(btn_ok)
        msg.exec_()

        if msg.clickedButton() == btn_cancel:
            self._force_reset_sync()
            # Lanzar nueva sync automáticamente
            QTimer.singleShot(500, lambda: self._ejecutar_sincronizacion(manual=True))

    def _force_reset_sync(self):
        """Fuerza el reset del flag de sync."""
        logger.warning("[SYNC] Reset forzado por el usuario")
        self._sync_running = False
        self._sync_start_time = None
        self._sync_thread = None

    def _sync_watchdog_reset(self):
        """Safety: resetea _sync_running si quedo trabado."""
        if not self._sync_running:
            return
        thread_alive = self._sync_thread is not None and self._sync_thread.is_alive()
        if thread_alive:
            logger.warning("[SYNC] Watchdog: sync >120s, hilo aún activo, esperando 60s más")
            QTimer.singleShot(60_000, self._sync_watchdog_reset)
        else:
            logger.warning("[SYNC] Watchdog: hilo muerto pero flag=True, reseteando")
            self._sync_running = False
            self._sync_start_time = None
            self._sync_thread = None
            self._update_sync_button_text("Sincronizar")

    def _on_sync_finished(self, resultado):
        """Callback en el hilo principal cuando la sync termina exitosamente."""
        self._sync_running = False
        self._sync_thread = None
        self._sync_start_time = None
        # Parar timer de progreso
        if hasattr(self, '_sync_progress_timer') and self._sync_progress_timer:
            self._sync_progress_timer.stop()
        try:
            self._last_sync_time = datetime.now()
            enviados = resultado.get("enviados", 0)
            recibidos = resultado.get("recibidos", 0)
            errores = resultado.get("errores", [])

            # v6.7.0: persistir resultado completo (con desglose por tipo) para el panel de Estado
            self._last_sync_resultado = dict(resultado)
            self._last_sync_resultado["timestamp"] = self._last_sync_time
            if not hasattr(self, '_sync_history'):
                self._sync_history = []
            self._sync_history.append({
                "timestamp": self._last_sync_time,
                "enviados": enviados,
                "recibidos": recibidos,
                "errores": len(errores) if isinstance(errores, list) else int(errores or 0),
                "por_tipo": resultado.get("por_tipo", {}),
            })
            self._sync_history = self._sync_history[-10:]

            self._actualizar_indicador_sync(
                enviados=enviados,
                recibidos=recibidos,
                errores=errores
            )

            cfg = load_config()
            cfg.setdefault("sync", {})["last_sync"] = self._last_sync_time.isoformat()
            save_config(cfg)

            # Actualizar botón con hora de última sync
            hora = self._last_sync_time.strftime("%H:%M")
            info = f"Sync OK {hora}"
            if enviados or recibidos:
                info += f" ({enviados}↑ {recibidos}↓)"
            self._update_sync_button_text(info)

            # SIEMPRE cerrar transacción implícita de lectura y refrescar
            # cache ORM. En WAL mode, la sesión principal solo ve el snapshot
            # del momento en que abrió su transacción. El thread de sync
            # escribe en una sesión separada, así que la sesión principal
            # necesita cerrar su transacción (rollback) para ver los datos
            # nuevos en la siguiente query.
            try:
                self.session.rollback()    # cerrar transacción implícita
                self.session.expire_all()  # invalidar cache ORM
            except Exception:
                pass

            # SIEMPRE refrescar UI (no solo cuando recibidos > 0)
            # para que ventas remotas que ya estaban en la DB se muestren
            try:
                self.refrescar_productos()
                self.refrescar_completer()
                self.cargar_lista_proveedores()
            except Exception:
                pass

            # v6.7.1: si hay borrados pendientes de confirmacion, mostrarlos
            try:
                self._procesar_pending_deletes()
            except Exception as _pd_err:
                logger.warning("[SYNC] Error procesando pending_deletes: %s", _pd_err)
            try:
                if hasattr(self, 'recargar_ventas_dia'):
                    self.recargar_ventas_dia()
            except Exception:
                pass
            try:
                historial = getattr(self, 'historial', None)
                if historial and hasattr(historial, 'recargar_historial'):
                    historial.recargar_historial()
                elif hasattr(self, 'recargar_historial'):
                    self.recargar_historial()
            except Exception:
                pass

            # Verificar precios inconsistentes (solo si recibidos > 0)
            if recibidos > 0:
                try:
                    mismatches = resultado.get("_mismatches", [])
                    if mismatches:
                        self._price_mismatches = mismatches
                        self._mostrar_alerta_precios(mismatches)
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"[SYNC] Error procesando resultado: {e}")

    def _on_sync_error(self, error_msg):
        """Callback en el hilo principal cuando la sync falla."""
        self._sync_running = False
        self._sync_thread = None
        self._sync_start_time = None
        # Parar timer de progreso
        if hasattr(self, '_sync_progress_timer') and self._sync_progress_timer:
            self._sync_progress_timer.stop()
        logger.error(f"[SYNC] Error: {error_msg}")
        self._actualizar_indicador_sync(error=error_msg)
        self._update_sync_button_text("⚠ Sync error - Reintentar")

    def _actualizar_indicador_sync(self, enviados=0, recibidos=0, errores=None, error=None):
        """Actualiza el indicador de sincronizacion en la barra de estado"""
        if not hasattr(self, 'lbl_sync_status'):
            self.lbl_sync_status = QLabel()
            self.lbl_sync_status.setCursor(Qt.PointingHandCursor)
            self.lbl_sync_status.mousePressEvent = lambda ev: self._mostrar_log_sync()
            self.statusBar().addPermanentWidget(self.lbl_sync_status)

        # Guardar log de esta operacion
        if not hasattr(self, '_sync_log_entries'):
            self._sync_log_entries = []

        cfg = load_config()
        sync_enabled = cfg.get("sync", {}).get("enabled", False)

        if not sync_enabled:
            self.lbl_sync_status.setText("")
            return

        now_str = datetime.now().strftime("%H:%M")

        if error:
            self.lbl_sync_status.setText(f"Sync error ({now_str})")
            self.lbl_sync_status.setStyleSheet("color: #E74C3C; text-decoration: underline;")
            self._sync_log_entries.append(f"[{now_str}] ERROR: {error}")
        elif errores:
            self.lbl_sync_status.setText(f"Sync: {len(errores)} errores ({now_str})")
            self.lbl_sync_status.setStyleSheet("color: #F39C12; text-decoration: underline;")
            for e in errores:
                self._sync_log_entries.append(f"[{now_str}] ERROR: {e}")
        else:
            if self._last_sync_time:
                hora_str = self._last_sync_time.strftime("%H:%M")
                msg = f"Sync OK {hora_str}"
                if enviados > 0 or recibidos > 0:
                    msg += f" ({enviados} env, {recibidos} rec)"

                self.lbl_sync_status.setText(msg)
                self.lbl_sync_status.setStyleSheet("color: #27AE60; text-decoration: underline;")
                self._sync_log_entries.append(
                    f"[{hora_str}] OK: {enviados} enviados, {recibidos} recibidos"
                )
            else:
                self.lbl_sync_status.setText("Sync activa")
                self.lbl_sync_status.setStyleSheet("color: #95A5A6; text-decoration: underline;")

        # Limitar log a ultimas 100 entradas
        self._sync_log_entries = self._sync_log_entries[-100:]

    def _mostrar_log_sync(self):
        """Muestra ventana con el log de sincronizacion."""
        from PyQt5.QtWidgets import QDialog, QTextEdit, QVBoxLayout, QDialogButtonBox

        dlg = QDialog(self)
        dlg.setWindowTitle("Log de sincronizacion")
        dlg.resize(600, 400)

        layout = QVBoxLayout(dlg)

        txt = QTextEdit(dlg)
        txt.setReadOnly(True)
        txt.setFontFamily("Consolas")

        # Cargar entradas de sesion
        session_entries = getattr(self, '_sync_log_entries', [])

        # Tambien leer archivo de log si existe
        file_lines = []
        if self._firebase_sync:
            log_path = self._firebase_sync._log_path
            try:
                if os.path.exists(log_path):
                    with open(log_path, "r", encoding="utf-8") as f:
                        file_lines = f.readlines()[-200:]  # ultimas 200 lineas
            except Exception:
                pass

        if file_lines:
            txt.append("=== Log de archivo ===\n")
            for line in file_lines:
                txt.append(line.rstrip())
            txt.append("\n=== Log de sesion actual ===\n")

        if session_entries:
            for entry in session_entries:
                txt.append(entry)
        elif not file_lines:
            txt.append("No hay registros de sincronizacion todavia.")

        layout.addWidget(txt)

        btns = QDialogButtonBox(QDialogButtonBox.Close, dlg)
        btns.rejected.connect(dlg.close)
        layout.addWidget(btns)

        # Scroll al final
        cursor = txt.textCursor()
        cursor.movePosition(cursor.End)
        txt.setTextCursor(cursor)

        dlg.exec_()

    def _mostrar_alerta_precios(self, mismatches):
        """Muestra alerta en status bar sobre precios inconsistentes."""
        if not mismatches:
            return

        if not hasattr(self, 'lbl_price_alert'):
            self.lbl_price_alert = QLabel()
            self.lbl_price_alert.setCursor(Qt.PointingHandCursor)
            self.lbl_price_alert.mousePressEvent = lambda ev: self._mostrar_detalle_precios()
            self.statusBar().addPermanentWidget(self.lbl_price_alert)

        self.lbl_price_alert.setText(f"⚠ {len(mismatches)} precios diferentes")
        self.lbl_price_alert.setStyleSheet("color: #F39C12; font-weight: bold; text-decoration: underline;")
        self.lbl_price_alert.setToolTip("Click para ver detalle de precios inconsistentes entre sucursales")

    def _mostrar_detalle_precios(self):
        """Muestra tabla detallada de precios inconsistentes."""
        from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QTableWidget,
                                      QTableWidgetItem, QHeaderView, QDialogButtonBox, QLabel)

        mismatches = getattr(self, '_price_mismatches', [])
        if not mismatches:
            QMessageBox.information(self, "Precios", "No hay diferencias de precios pendientes.")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Precios inconsistentes entre sucursales")
        dlg.resize(700, 400)
        layout = QVBoxLayout(dlg)

        layout.addWidget(QLabel(f"Se detectaron {len(mismatches)} productos con precios diferentes:"))

        table = QTableWidget(len(mismatches), 5)
        table.setHorizontalHeaderLabels(["Código", "Nombre", "Precio Local", "Precio Remoto", "Diferencia"])
        table.verticalHeader().setVisible(False)

        for i, m in enumerate(mismatches):
            table.setItem(i, 0, QTableWidgetItem(m.get('codigo', '')))
            table.setItem(i, 1, QTableWidgetItem(m.get('nombre', '')))
            table.setItem(i, 2, QTableWidgetItem(f"${m.get('precio_local', 0):.2f}"))
            table.setItem(i, 3, QTableWidgetItem(f"${m.get('precio_remoto', 0):.2f}"))
            diff = m.get('diferencia', 0)
            item = QTableWidgetItem(f"${diff:+.2f}")
            item.setForeground(Qt.red if diff < 0 else Qt.darkGreen)
            table.setItem(i, 4, item)

        hdr = table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.Interactive)
        hdr.setStretchLastSection(True)
        table.setColumnWidth(0, 120)  # Código
        table.setColumnWidth(1, 200)  # Nombre
        table.setColumnWidth(2, 100)  # Precio Local
        table.setColumnWidth(3, 110)  # Precio Remoto

        layout.addWidget(table)

        btns = QDialogButtonBox(QDialogButtonBox.Close, dlg)
        btns.rejected.connect(dlg.close)
        layout.addWidget(btns)

        dlg.exec_()

    def _crear_boton_sync_manual(self):
        """Crea un botón en la status bar para sincronización manual."""
        self.btn_sync_manual = QPushButton("🔄 Sincronizar")
        self.btn_sync_manual.setFlat(True)
        self.btn_sync_manual.setToolTip("Click para sincronizar manualmente")
        self.btn_sync_manual.setCursor(Qt.PointingHandCursor)
        self.btn_sync_manual.setStyleSheet(
            "QPushButton { font-size: 11px; padding: 2px 8px; }"
            "QPushButton:hover { background: #e0e0e0; border-radius: 3px; }"
        )
        self.btn_sync_manual.clicked.connect(lambda: self._ejecutar_sincronizacion(manual=True))
        self.statusBar().addPermanentWidget(self.btn_sync_manual)

        self._actualizar_texto_boton_sync()

    def _actualizar_texto_boton_sync(self):
        """Lee la config y actualiza el texto del botón con la última sync."""
        if not hasattr(self, 'btn_sync_manual'):
            return
        cfg = load_config()
        sync_cfg = cfg.get("sync", {})
        enabled = sync_cfg.get("enabled", False)

        if not enabled:
            self.btn_sync_manual.setText("Sync desactivada")
            self.btn_sync_manual.setToolTip("Sincronización desactivada. Activalo en Configuración.")
            return

        last = sync_cfg.get("last_sync")
        if last:
            try:
                dt = datetime.fromisoformat(last)
                self.btn_sync_manual.setText(f"🔄 Última sync: {dt.strftime('%d/%m %H:%M')}")
                self.btn_sync_manual.setToolTip(
                    f"Última sincronización: {dt.strftime('%d/%m/%Y %H:%M:%S')}\n"
                    f"Click para sincronizar manualmente"
                )
                return
            except Exception:
                pass
        self.btn_sync_manual.setText("🔄 Sincronizar")
        self.btn_sync_manual.setToolTip("Click para sincronizar manualmente")

    def _update_sync_button_text(self, text: str):
        """Actualiza el texto del botón de sync en la barra de estado."""
        if hasattr(self, 'btn_sync_manual'):
            self.btn_sync_manual.setText(text)
            self.btn_sync_manual.setToolTip(f"{text}\nClick para sincronizar manualmente")

    def _update_sync_progress(self):
        """Actualiza el botón con elapsed time durante sync."""
        if not self._sync_running:
            if hasattr(self, '_sync_progress_timer') and self._sync_progress_timer:
                self._sync_progress_timer.stop()
            return
        if self._sync_start_time:
            elapsed = int((datetime.now() - self._sync_start_time).total_seconds())
            mins, secs = divmod(elapsed, 60)
            if mins > 0:
                time_str = f"{mins}:{secs:02d}"
            else:
                time_str = f"{secs}s"
            self._update_sync_button_text(f"⟳ Sincronizando... {time_str}")

    def _sync_push(self, tipo, entity, accion="upsert"):
        """Helper para publicar un cambio en Firebase (no-bloqueante)."""
        if not self._firebase_sync:
            return
        import threading
        def _do():
            try:
                if tipo == "venta":
                    self._firebase_sync.push_venta(entity)
                elif tipo == "venta_mod":
                    self._firebase_sync.push_venta_modificada(entity)
                elif tipo == "venta_del":
                    self._firebase_sync.push_venta_eliminada(entity)
                elif tipo == "producto":
                    self._firebase_sync.push_producto(entity, accion)
                elif tipo == "producto_del":
                    self._firebase_sync.push_producto_eliminado(entity)
                elif tipo == "proveedor":
                    self._firebase_sync.push_proveedor(entity, accion)
                elif tipo == "proveedor_del":
                    self._firebase_sync.push_proveedor_eliminado(entity)
                elif tipo == "pago_proveedor":
                    self._firebase_sync.push_pago_proveedor(entity)
                elif tipo == "comprador":
                    self._firebase_sync.push_comprador(entity, accion)
                elif tipo == "comprador_del":
                    self._firebase_sync.push_comprador_eliminado(entity)
            except Exception as e:
                self._firebase_sync._log(f"Push {tipo} error: {e}")
        threading.Thread(target=_do, daemon=True).start()

    def _sync_push_batch(self, tipo, lista):
        """Helper para publicar un lote de cambios en Firebase en un solo PATCH (no-bloqueante).
        Mucho más rápido que N llamadas seriadas de _sync_push (p.ej. tras importar Excel).
        """
        if not self._firebase_sync or not lista:
            return
        import threading
        def _do():
            try:
                if tipo == "producto":
                    self._firebase_sync.push_productos_batch(lista)
                else:
                    # Fallback: si no hay implementación batch, caer al seriado
                    for ent in lista:
                        self._firebase_sync._log(f"Batch {tipo} no soportado, push individual")
            except Exception as e:
                try:
                    self._firebase_sync._log(f"Push batch {tipo} error: {e}")
                except Exception:
                    pass
        threading.Thread(target=_do, daemon=True).start()

    def _check_pending_config_restore(self):
        """Movido a main.py (pre-login). Este método ya no se usa."""
        return

        # Leer config actual
        cfg = load_config()
        last_version = cfg.get("_last_version", "")
        config_exists = os.path.exists(CONFIG_PATH)

        if not config_exists:
            # No hay config — primera instalación limpia, nada que mostrar
            return

        # Caso 2: version nueva detectada
        if last_version and last_version != __version__:
            self._mostrar_dialogo_actualizacion(last_version, __version__, cfg)
            return

        # Caso 3: config existe pero sin _last_version (primera vez que detectamos)
        if not last_version:
            has_real_data = bool(
                cfg.get("sync", {}).get("enabled")
                or cfg.get("sucursal")
                or cfg.get("printers")
                or cfg.get("general")
            )
            if has_real_data:
                self._mostrar_dialogo_actualizacion("anterior", __version__, cfg)
            else:
                cfg["_last_version"] = __version__
                save_config(cfg)
            return

    def _mostrar_dialogo_actualizacion(self, version_anterior, version_nueva, cfg):
        """Ofrece al usuario mantener configuración o empezar de nuevo."""
        # Mostrar ruta del backup para que el usuario sepa dónde buscar
        try:
            backup_path = get_backup_path()
            backup_dir = str(Path(backup_path).parent)
        except Exception:
            backup_dir = "(no disponible)"

        msg = QMessageBox(self)
        msg.setWindowTitle("Actualización detectada")
        msg.setIcon(QMessageBox.Question)
        msg.setText(
            f"Se actualizó de v{version_anterior} a v{version_nueva}.\n\n"
            f"Tu configuración anterior se ha detectado.\n"
            f"¿Qué querés hacer?\n\n"
            f"📁 Backup de config: {backup_dir}"
        )

        btn_mantener = msg.addButton("Mantener configuración", QMessageBox.AcceptRole)
        btn_restaurar = msg.addButton("Restaurar desde archivo...", QMessageBox.ActionRole)
        btn_nuevo = msg.addButton("Empezar de nuevo", QMessageBox.DestructiveRole)
        msg.setDefaultButton(btn_mantener)
        msg.exec_()

        clicked = msg.clickedButton()

        if clicked == btn_mantener:
            cfg["_last_version"] = version_nueva
            save_config(cfg)
            QMessageBox.information(
                self, "Configuración mantenida",
                f"Tu configuración se ha mantenido correctamente para v{version_nueva}."
            )

        elif clicked == btn_restaurar:
            try:
                default_dir = str(Path(get_backup_path()).parent)
            except Exception:
                default_dir = ""
            path, _ = QFileDialog.getOpenFileName(
                self, "Elegir app_config.json",
                default_dir, "JSON (*.json);;Todos (*.*)"
            )
            if path:
                ok = restore_from_path(path)
                if ok:
                    cfg_new = load_config()
                    cfg_new["_last_version"] = version_nueva
                    save_config(cfg_new)
                    QMessageBox.information(
                        self, "Restauración exitosa",
                        "Configuración restaurada. Reiniciá la aplicación para aplicar todos los cambios."
                    )
                else:
                    QMessageBox.warning(self, "Error", "No se pudo restaurar la configuración.")
            else:
                # Canceló el diálogo de archivo → mantener config actual
                cfg["_last_version"] = version_nueva
                save_config(cfg)

        elif clicked == btn_nuevo:
            # Obtener ruta de la BD para mostrar al usuario qué se borrará
            try:
                from app.database import DB_PATH as _db_path_val
                db_display = str(_db_path_val)
            except Exception:
                db_display = "(no se pudo determinar)"

            resp = QMessageBox.warning(
                self, "Confirmar",
                "Esto borrará TODA tu configuración actual\n"
                "(impresoras, sync, preferencias, etc.)\n"
                "Y TAMBIÉN la base de datos local completa\n"
                "(productos, ventas, historial, etc.)\n\n"
                f"BD: {db_display}\n"
                f"Config: {CONFIG_PATH}\n\n"
                "¿Estás seguro? Esta acción NO se puede deshacer.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if resp == QMessageBox.Yes:
                try:
                    # 1. Cerrar la sesión de BD para poder borrar el archivo
                    try:
                        if hasattr(self, 'session') and self.session is not None:
                            self.session.close()
                            self.session = None
                    except Exception:
                        pass

                    # 2. Borrar la base de datos
                    try:
                        from app.database import DB_PATH as _db_path_val
                        db_path_str = str(_db_path_val)
                        if os.path.exists(db_path_str):
                            os.remove(db_path_str)
                            logger.info(f"[RESET] BD borrada: {db_path_str}")
                    except Exception as e:
                        logger.warning(f"[RESET] No se pudo borrar BD: {e}")

                    # 3. Borrar config y recrear con defaults
                    if os.path.exists(CONFIG_PATH):
                        os.remove(CONFIG_PATH)
                    cfg_new = load_config()  # Crea config con defaults
                    cfg_new["_last_version"] = version_nueva
                    save_config(cfg_new)

                    # 4. Borrar cola de sync offline
                    try:
                        from app.config import _get_app_data_dir
                        queue_path = os.path.join(_get_app_data_dir(), "sync_queue.json")
                        if os.path.exists(queue_path):
                            os.remove(queue_path)
                    except Exception:
                        pass

                    QMessageBox.information(
                        self, "Reset completo",
                        "Se borró la configuración y la base de datos.\n\n"
                        "La aplicación se cerrará ahora.\n"
                        "Al abrirla de nuevo empezará completamente limpia."
                    )
                    # Cerrar la app — no se puede seguir sin BD ni sesión
                    try:
                        QApplication.quit()
                    except Exception:
                        import sys
                        sys.exit(0)
                except Exception as e:
                    QMessageBox.warning(self, "Error", f"No se pudo reiniciar:\n{e}")
            else:
                cfg["_last_version"] = version_nueva
                save_config(cfg)

    def _show_restore_dialog(self):
        """Muestra el dialogo de restauracion de config desde backup."""
        msg = QMessageBox(self)
        msg.setWindowTitle("Restaurar configuracion")
        msg.setText("Se encontro un backup de configuracion.")
        msg.setInformativeText(
            "¿Quieres restaurarlo ahora? Puedes buscar un archivo manualmente."
        )
        btn_restore = msg.addButton("Restaurar", QMessageBox.AcceptRole)
        btn_browse = msg.addButton("Buscar archivo...", QMessageBox.ActionRole)
        btn_skip = msg.addButton("Omitir", QMessageBox.RejectRole)
        msg.setIcon(QMessageBox.Question)
        msg.exec_()

        if msg.clickedButton() == btn_restore:
            ok = restore_from_backup()
            if ok:
                QMessageBox.information(
                    self, "Restaurar configuracion",
                    "Configuracion restaurada. Reinicia la aplicacion para aplicar los cambios."
                )
            else:
                QMessageBox.warning(
                    self, "Restaurar configuracion",
                    "No se pudo restaurar la configuracion."
                )
        elif msg.clickedButton() == btn_browse:
            try:
                default_dir = str(Path(get_backup_path()).parent)
            except Exception:
                default_dir = ""
            path, _ = QFileDialog.getOpenFileName(
                self, "Elegir app_config.json",
                default_dir, "JSON (*.json);;Todos (*.*)"
            )
            if path:
                ok = restore_from_path(path)
                if ok:
                    QMessageBox.information(
                        self, "Restaurar configuracion",
                        "Configuracion restaurada. Reinicia la aplicacion para aplicar los cambios."
                    )
                else:
                    QMessageBox.warning(
                        self, "Restaurar configuracion",
                        "No se pudo restaurar la configuracion."
                    )

    # ============================
    #  Sonido
    # ============================
    def _init_sound(self):
        # Intentamos varias rutas posibles del proyecto y exigimos la extensión .wav
        from pathlib import Path
        from PyQt5.QtCore import QUrl
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtMultimedia import QSoundEffect

        here = Path(__file__).resolve()
        base_app  = here.parents[2]   # .../app
        base_root = here.parents[3]   # .../<raíz del proyecto>

        candidates = [
            base_app  / "assets" / "sounds" / "pip.wav",   # app/assets/sounds/pip.wav
            base_root / "assets" / "sounds" / "pip.wav",   # <root>/assets/sounds/pip.wav
        ]
        here = Path(__file__).resolve()
        base_app  = here.parents[2]   # .../app (desarrollo)
        base_root = here.parents[3]   # .../repo (desarrollo)
        dist_root = Path(sys.executable).parent if getattr(sys, "frozen", False) else base_root

        candidates = [
            base_app  / "assets" / "sounds" / "pip.wav",           # dev
            base_root / "assets" / "sounds" / "pip.wav",           # dev
            dist_root / "_internal" / "assets" / "sounds" / "pip.wav",  # EXE
            dist_root / "assets" / "sounds" / "pip.wav",                # espejo
]


        wav_path = next((p for p in candidates if p.exists()), None)

        if wav_path is not None:
            try:
                self._sound_ok = QSoundEffect(self)
                self._sound_ok.setSource(QUrl.fromLocalFile(str(wav_path)))
                self._sound_ok.setLoopCount(1)
                self._sound_ok.setVolume(0.35)

                def _beep_ok():
                    self._sound_ok.play()
                self._beep_ok = _beep_ok
                logger.debug(f"[SOUND] beep OK: {wav_path}")
                return
            except Exception as e:
                logger.warning(f"[SOUND] QSoundEffect falló: {e}")

        # Fallbacks si no se encuentra o falla: beep del sistema
        logger.debug("[SOUND] pip.wav no encontrado en rutas conocidas. Usando QApplication.beep()")
        self._beep_ok = QApplication.beep

    # ============================
    #  Barra de estado
    # ============================
    def _setup_status_bar(self):
        """Configura la barra de estado con información en tiempo real"""
        from PyQt5.QtWidgets import QLabel
        from PyQt5.QtCore import QTimer
        from datetime import datetime

        # Crear barra de estado
        status_bar = self.statusBar()

        # Etiqueta de sucursal
        self.status_sucursal = QLabel(f"📍 {self.sucursal}")
        status_bar.addWidget(self.status_sucursal)

        # Separador
        sep1 = QLabel(" | ")
        status_bar.addWidget(sep1)

        # Etiqueta de usuario
        self.status_usuario = QLabel()
        self._refresh_user_status()
        status_bar.addWidget(self.status_usuario)

        # Separador
        sep2 = QLabel(" | ")
        status_bar.addWidget(sep2)

        # Etiqueta de hora (se actualiza cada segundo)
        self.status_hora = QLabel()
        status_bar.addWidget(self.status_hora)

        # Timer para actualizar la hora cada segundo
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self._update_status_time)
        self.status_timer.start(1000)  # 1 segundo

        # Actualizar inmediatamente
        self._update_status_time()

    def _refresh_user_status(self):
        """Actualiza la etiqueta de usuario en la barra de estado."""
        try:
            name = getattr(self, "current_username", "") or ""
            is_admin = getattr(self, "es_admin", False)
            if name:
                txt = f"👤 {name} (Admin)" if is_admin else f"👤 {name}"
            else:
                txt = "👤 Admin" if is_admin else "👤 Usuario"
            self.status_usuario.setText(txt)
        except Exception:
            pass

    def _update_status_time(self):
        """Actualiza la hora en la barra de estado según el timezone configurado"""
        from datetime import datetime
        import pytz

        try:
            # Obtener timezone de la configuración
            cfg = load_config()
            timezone_str = ((cfg.get("general") or {}).get("timezone") or "America/Argentina/Buenos_Aires")
            tz = pytz.timezone(timezone_str)
            now = datetime.now(tz)
        except Exception:
            # Fallback a hora local si hay error
            now = datetime.now()

        self.status_hora.setText(f"🕐 {now.strftime('%H:%M:%S')}")

    def _check_online_status(self):
        """Stub para compatibilidad — ya no hay indicador online separado."""
        pass

    def _update_online_indicator(self, online: bool, pending: int):
        """Stub para compatibilidad — ya no hay indicador online separado."""
        pass

    # ─── Pending deletes (v6.7.1) ─────────────────────────────────────

    def _procesar_pending_deletes(self):
        """v6.7.1: tras un sync, si hay productos cuya baja fue recibida desde otra
        sucursal y `confirm_delete_productos` esta activo, mostrar popup por cada uno
        para que el admin acepte (borrar local) o rechace (re-publicar para deshacer).

        Usa una bandera reentrante para no apilar dialogos si el sync corre denso.
        """
        if not self._firebase_sync:
            return
        if getattr(self, "_pending_deletes_dialog_open", False):
            return
        try:
            pending = self._firebase_sync.get_pending_deletes()
        except Exception:
            pending = []
        if not pending:
            return

        # Solo admins pueden decidir borrados — para no admins, dejar pendientes
        if not getattr(self, "es_admin", False):
            return

        self._pending_deletes_dialog_open = True
        try:
            # Procesar de uno en uno (popups secuenciales para no abrumar)
            # Recorremos copia de la lista; la lista real cambia tras cada accept/reject
            i = 0
            while True:
                pendings_now = self._firebase_sync.get_pending_deletes()
                if i >= len(pendings_now):
                    break
                item = pendings_now[i]
                tipo = item.get("tipo")
                if tipo != "productos":
                    i += 1
                    continue
                data = item.get("data", {}) or {}
                origen = item.get("origen") or "otra sucursal"
                codigo = data.get("codigo_barra", "?")
                nombre = data.get("nombre", "")
                precio = data.get("precio")
                msg = (
                    f"La sucursal <b>{origen}</b> elimino este producto:<br><br>"
                    f"<b>{nombre}</b> (codigo: {codigo})<br>"
                )
                if precio is not None:
                    msg += f"Precio actual local: ${precio}<br>"
                msg += "<br>Queres eliminarlo tambien aqui?"

                box = QMessageBox(self)
                box.setIcon(QMessageBox.Question)
                box.setWindowTitle("Confirmar borrado entre sucursales")
                box.setTextFormat(Qt.RichText)
                box.setText(msg)
                btn_yes = box.addButton("Si, eliminar tambien", QMessageBox.YesRole)
                btn_no = box.addButton("No, mantener aqui", QMessageBox.NoRole)
                btn_skip = box.addButton("Decidir despues", QMessageBox.RejectRole)
                box.exec_()
                clicked = box.clickedButton()
                if clicked is btn_yes:
                    self._firebase_sync.accept_pending_delete(i)
                    # No incrementar i: la lista se acorto en 1
                elif clicked is btn_no:
                    self._firebase_sync.reject_pending_delete(i)
                    # No incrementar i
                else:
                    # Decidir despues — saltarlo, queda en la cola para el proximo sync
                    i += 1
            try:
                self.refrescar_productos()
            except Exception:
                pass
        finally:
            self._pending_deletes_dialog_open = False
