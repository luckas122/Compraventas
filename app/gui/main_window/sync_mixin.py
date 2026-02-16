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
    #  SINCRONIZACION (Firebase)
    # ============================
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
            return

        # Crear FirebaseSyncManager usando la sesion principal de la app
        sucursal_actual = getattr(self, 'sucursal', 'Sarmiento')
        self._firebase_sync = FirebaseSyncManager(self.session, sucursal_actual)
        logger.info(f"[SYNC] Sync activada, modo={mode}, intervalo={interval_min}min")

        if mode == "interval":
            ms = interval_min * 60 * 1000
            self._sync_timer.setInterval(ms)
            self._sync_timer.start()
            logger.info(f"[SYNC] Timer iniciado: cada {ms}ms ({interval_min} min)")

        # Siempre ejecutar primera sync al iniciar (independiente del modo)
        QTimer.singleShot(3000, lambda: self._ejecutar_sincronizacion(manual=False))

        # Forzar actualización del indicador online después de inicializar sync
        QTimer.singleShot(4000, self._check_online_status)

    def _reiniciar_sync_scheduler(self):
        """Reinicia el scheduler cuando se guarda la configuracion"""
        self._setup_sync_scheduler()

        if hasattr(self, 'btn_sync_manual'):
            cfg = load_config()
            enabled = cfg.get("sync", {}).get("enabled", False)
            self.btn_sync_manual.setVisible(True)
            if not enabled:
                self.btn_sync_manual.setToolTip("Sincronizacion desactivada. Activalo en Configuracion.")
            else:
                self.btn_sync_manual.setToolTip("Click para sincronizar manualmente")

    def _ejecutar_sincronizacion(self, manual=False):
        """Ejecuta un ciclo de sincronizacion via Firebase"""
        cfg = load_config()
        sync_cfg = cfg.get("sync", {})
        enabled = sync_cfg.get("enabled", False)
        if not enabled:
            if manual:
                QMessageBox.information(self, "Sincronizacion", "La sincronizacion esta desactivada en Configuracion.")
            return

        if not self._firebase_sync:
            sucursal_actual = getattr(self, 'sucursal', 'Sarmiento')
            self._firebase_sync = FirebaseSyncManager(self.session, sucursal_actual)

        try:
            resultado = self._firebase_sync.ejecutar_sincronizacion_completa()

            self._last_sync_time = datetime.now()
            self._actualizar_indicador_sync(
                enviados=resultado["enviados"],
                recibidos=resultado["recibidos"],
                errores=resultado["errores"]
            )

            cfg = load_config()
            cfg["sync"]["last_sync"] = self._last_sync_time.isoformat()
            save_config(cfg)

            # Refrescar UI si se recibieron cambios
            if resultado["recibidos"] > 0:
                try:
                    self.refrescar_productos()
                    self.refrescar_completer()
                    self.cargar_lista_proveedores()
                except Exception:
                    pass

            # Verificar precios inconsistentes
            try:
                mismatches = self._firebase_sync.get_price_mismatches()
                if mismatches:
                    self._price_mismatches = mismatches
                    self._mostrar_alerta_precios(mismatches)
            except Exception:
                pass

        except Exception as e:
            logger.error(f"[SYNC] Error: {e}")
            self._actualizar_indicador_sync(error=str(e))

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
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        for c in [0, 2, 3, 4]:
            hdr.setSectionResizeMode(c, QHeaderView.ResizeToContents)

        layout.addWidget(table)

        btns = QDialogButtonBox(QDialogButtonBox.Close, dlg)
        btns.rejected.connect(dlg.close)
        layout.addWidget(btns)

        dlg.exec_()

    def _crear_boton_sync_manual(self):
        """Crea un boton en la status bar para sincronizacion manual"""
        self.btn_sync_manual = QPushButton("Sincronizar")
        self.btn_sync_manual.setFlat(True)
        self.btn_sync_manual.setToolTip("Click para sincronizar manualmente")
        self.btn_sync_manual.clicked.connect(lambda: self._ejecutar_sincronizacion(manual=True))
        self.statusBar().addPermanentWidget(self.btn_sync_manual)

        cfg = load_config()
        enabled = cfg.get("sync", {}).get("enabled", False)
        self.btn_sync_manual.setVisible(True)
        if not enabled:
            self.btn_sync_manual.setToolTip("Sincronizacion desactivada. Activalo en Configuracion.")

    def _sync_push(self, tipo, entity, accion="upsert"):
        """Helper para publicar un cambio en Firebase desde cualquier mixin."""
        if not self._firebase_sync:
            return
        try:
            if tipo == "venta":
                self._firebase_sync.push_venta(entity)
            elif tipo == "venta_mod":
                self._firebase_sync.push_venta_modificada(entity)
            elif tipo == "producto":
                self._firebase_sync.push_producto(entity, accion)
            elif tipo == "producto_del":
                self._firebase_sync.push_producto_eliminado(entity)
            elif tipo == "proveedor":
                self._firebase_sync.push_proveedor(entity, accion)
            elif tipo == "proveedor_del":
                self._firebase_sync.push_proveedor_eliminado(entity)
        except Exception as e:
            self._firebase_sync._log(f"Push {tipo} error: {e}")

    def _check_pending_config_restore(self):
        """
        Al iniciar la app, verifica si:
        1. Hay un backup de config pendiente del instalador -> ofrece restaurar
        2. La version cambio y la config existe -> informa que se mantuvo
        3. Config existente sin _last_version (actualizacion desde version vieja)
        """
        from version import __version__

        # Caso 1: backup pendiente del instalador (legacy)
        try:
            if has_pending_backup():
                self._show_restore_dialog()
                return
        except Exception:
            pass

        # Leer config actual
        cfg = load_config()
        last_version = cfg.get("_last_version", "")
        config_exists = os.path.exists(CONFIG_PATH)

        if not config_exists:
            # No hay config — primera instalacion limpia, nada que mostrar
            return

        # Caso 2: version nueva detectada (ya teniamos _last_version guardada)
        if last_version and last_version != __version__:
            QMessageBox.information(
                self, "Actualizacion detectada",
                f"Se actualizo de v{last_version} a v{__version__}.\n\n"
                f"Tu configuracion se ha mantenido correctamente."
            )
            cfg["_last_version"] = __version__
            save_config(cfg)
            return

        # Caso 3: config existe pero sin _last_version
        # = actualizacion desde version anterior que no guardaba este campo
        if not last_version:
            # Verificar si la config tiene datos reales (no es un config vacio)
            has_real_data = bool(
                cfg.get("sync", {}).get("enabled")
                or cfg.get("sucursal")
                or cfg.get("printers")
                or cfg.get("general")
            )
            if has_real_data:
                QMessageBox.information(
                    self, "Actualizacion detectada",
                    f"Bienvenido a v{__version__}.\n\n"
                    f"Tu configuracion previa se ha mantenido correctamente."
                )
            # Guardar la version actual para futuras detecciones
            cfg["_last_version"] = __version__
            save_config(cfg)
            return

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

        # Etiqueta de usuario (obtener del login si está disponible)
        usuario = "Usuario"  # Por defecto
        try:
            from app.login import LoginDialog
            # Aquí podrías obtener el usuario actual si lo tienes almacenado
            usuario = "Admin" if self.es_admin else "Usuario"
        except:
            pass
        self.status_usuario = QLabel(f"👤 {usuario}")
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

        # --- Indicador Online/Offline ---
        sep3 = QLabel(" | ")
        status_bar.addWidget(sep3)

        self.status_online = QLabel("● Verificando...")
        self.status_online.setStyleSheet("color: #95A5A6; font-weight: bold;")
        self.status_online.setCursor(Qt.PointingHandCursor)
        self.status_online.setToolTip("Estado de conexión con Firebase")
        self.status_online.mousePressEvent = lambda ev: self._mostrar_cola_offline()
        status_bar.addWidget(self.status_online)

        # Timer para verificar conectividad cada 60 segundos
        self._online_check_timer = QTimer(self)
        self._online_check_timer.timeout.connect(self._check_online_status)
        self._online_check_timer.start(60000)  # 60 segundos

        # Check inicial después de 5 segundos
        QTimer.singleShot(5000, self._check_online_status)

        # Actualizar inmediatamente
        self._update_status_time()

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
        """Verifica conectividad con Firebase y actualiza indicador."""
        import threading

        def _check():
            try:
                online = False
                if self._firebase_sync:
                    online = self._firebase_sync._is_online()

                # Contar cola offline
                pending = 0
                if self._firebase_sync:
                    try:
                        queue = self._firebase_sync._load_offline_queue()
                        pending = len(queue)
                    except Exception:
                        pass

                # Actualizar UI en el hilo principal
                QTimer.singleShot(0, lambda: self._update_online_indicator(online, pending))
            except Exception:
                QTimer.singleShot(0, lambda: self._update_online_indicator(False, 0))

        # Ejecutar en hilo para no bloquear UI
        t = threading.Thread(target=_check, daemon=True)
        t.start()

    def _update_online_indicator(self, online: bool, pending: int):
        """Actualiza el indicador visual de online/offline."""
        if not hasattr(self, 'status_online'):
            return

        if online:
            if pending > 0:
                self.status_online.setText(f"● {pending} pendientes")
                self.status_online.setStyleSheet("color: #F39C12; font-weight: bold;")
                self.status_online.setToolTip(f"Online - {pending} cambios pendientes en cola")
            else:
                self.status_online.setText("● Online")
                self.status_online.setStyleSheet("color: #27AE60; font-weight: bold;")
                self.status_online.setToolTip("Conectado a Firebase")
        else:
            cfg = load_config()
            sync_enabled = cfg.get("sync", {}).get("enabled", False)
            if not sync_enabled:
                self.status_online.setText("● Sync off")
                self.status_online.setStyleSheet("color: #95A5A6; font-weight: bold;")
                self.status_online.setToolTip("Sincronización desactivada")
            else:
                txt = "● Offline"
                if pending > 0:
                    txt += f" ({pending})"
                self.status_online.setText(txt)
                self.status_online.setStyleSheet("color: #E74C3C; font-weight: bold;")
                self.status_online.setToolTip(f"Sin conexión a Firebase. {pending} cambios pendientes.")

    def _mostrar_cola_offline(self):
        """Muestra ventana con detalle de la cola offline."""
        from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QTableWidget,
                                      QTableWidgetItem, QHeaderView, QDialogButtonBox, QLabel)

        dlg = QDialog(self)
        dlg.setWindowTitle("Cola de sincronización offline")
        dlg.resize(600, 400)
        layout = QVBoxLayout(dlg)

        # Info
        online = False
        queue = []
        if self._firebase_sync:
            try:
                online = self._firebase_sync._is_online()
                queue = self._firebase_sync._load_offline_queue()
            except Exception:
                pass

        status_text = "● Online" if online else "● Offline"
        layout.addWidget(QLabel(f"Estado: {status_text}  |  Cambios en cola: {len(queue)}"))

        if queue:
            table = QTableWidget(len(queue), 4)
            table.setHorizontalHeaderLabels(["Tipo", "Acción", "Sucursal", "Timestamp"])
            table.verticalHeader().setVisible(False)

            for i, item in enumerate(queue):
                table.setItem(i, 0, QTableWidgetItem(item.get("tipo", "")))
                table.setItem(i, 1, QTableWidgetItem(item.get("accion", "")))
                table.setItem(i, 2, QTableWidgetItem(item.get("sucursal_origen", "")))
                ts = item.get("timestamp", 0)
                if ts:
                    from datetime import datetime
                    dt = datetime.fromtimestamp(ts / 1000)
                    table.setItem(i, 3, QTableWidgetItem(dt.strftime("%d/%m %H:%M:%S")))
                else:
                    table.setItem(i, 3, QTableWidgetItem("--"))

            hdr = table.horizontalHeader()
            hdr.setSectionResizeMode(QHeaderView.Stretch)
            layout.addWidget(table)
        else:
            layout.addWidget(QLabel("No hay cambios pendientes en la cola."))

        btns = QDialogButtonBox(QDialogButtonBox.Close, dlg)
        btns.rejected.connect(dlg.close)
        layout.addWidget(btns)

        dlg.exec_()
