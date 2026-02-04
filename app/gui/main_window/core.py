# Ventana principal extraída de gui.py (sin cambios funcionales)
import tempfile, os
import sys
import time as time_mod
import zipfile
import sqlite3
import shutil
import threading
import logging

logger = logging.getLogger(__name__)

import pandas as pd
from app.gui.main_window.productos import ProductosMixin
from app.gui.main_window.ventas import VentasMixin
from app.gui.main_window.filters  import LimitedFilterProxy
from app.gui.main_window.proveedores_mixin import ProveedoresMixin
from app.gui.main_window.usuarios_mixin import UsuariosMixin
from app.gui.main_window.configuracion_mixin import ConfiguracionMixin
from app.gui.main_window.reportes_mixin import ReportesMixin
from app.gui.main_window.backups_mixin import BackupsMixin
from app.gui.shortcuts import ShortcutManager
from app.gui.autofocus import AutoFocusManager







from PyQt5.QtWidgets import QSizePolicy,QScrollArea,QTabWidget,QMessageBox, QInputDialog
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QComboBox,
    QTableWidget, QTableWidgetItem, QMessageBox, QTabWidget,
    QRadioButton, QButtonGroup, QSpinBox, QInputDialog, QMenu, QFileDialog,
    QCheckBox, QStyle, QHeaderView, QDialog, QDoubleSpinBox,QCompleter,QApplication,QSizePolicy,QScrollArea,QTabWidget,QMessageBox, QInputDialog,QSystemTrayIcon,QAction,QSystemTrayIcon, QAction
)
from PyQt5 import QtCore
from PyQt5.QtCore import Qt, QSize, QEvent, QObject, QRect,QSortFilterProxyModel, QModelIndex,QTimer,QSignalBlocker,QStringListModel,QDate,QTime,QUrl
from PyQt5.QtGui import QPainter, QPixmap, QIcon, QMouseEvent, QFont, QFontMetrics
from PyQt5.QtPrintSupport import QPrinter, QPrintDialog
from app.gui.reportes_config import ReportesCorreoConfig
from app.gui.ventas_helpers import build_product_completer, imprimir_ticket
from app.gui.fastui import make_filterable_combo, update_filterable_combo
from app.email_helper import send_mail_with_attachments
from app.database import SessionLocal
from app.config import (
    load as load_config,
    save as save_config,
    CONFIG_PATH,
    has_pending_backup,
    restore_from_backup,
    restore_from_path,
    get_backup_path,
)
from app.models import Producto, Proveedor, Venta, VentaItem
from app.repository import prod_repo, VentaRepo, UsuarioRepo
from app.gui.qt_helpers import freeze_table
from pathlib import Path
from PyQt5.QtMultimedia import QSoundEffect
from app.gui.proveedores import ProveedorService  # NUEVO
from datetime import date, datetime,timedelta
from app.gui.historialventas import HistorialVentasWidget
# Importar helpers y diálogos desde el paquete nuevo
from app.gui.common import BASE_ICONS_PATH, MIN_BTN_HEIGHT, ICON_SIZE, icon, _safe_viewport, _mouse_release_event_type, _checked_states, FullCellCheckFilter
from app.gui.dialogs import DevolucionDialog, ProductosDialog
from app.sync_manager import SyncManager



#---------------------------------------------------------------------------------------------------------------------

class MainWindow(ProductosMixin, VentasMixin ,ProveedoresMixin, UsuariosMixin, ConfiguracionMixin,ReportesMixin,BackupsMixin,QMainWindow):

    def __init__(self, es_admin=True):
        from app.gui.ventas_helpers import build_product_completer
        from PyQt5.QtMultimedia import QSoundEffect
        from PyQt5.QtCore import QUrl
        super().__init__()
        self.history = []
        self.vuelto = 0.0
        self.setWindowTitle('App Compras y Ventas')
        self.setGeometry(100, 100, 1000, 700)
        # Bandeja del sistema
        self.tray = None
        cfg = load_config()
        gen_cfg = cfg.get("general") or {}
        self._minimize_to_tray_on_close = bool(gen_cfg.get("minimize_to_tray_on_close", False))

        
        # Usar el mismo icono que tiene la aplicación
        try:
            app = QApplication.instance()
            if app is not None and not app.windowIcon().isNull():
                self.setWindowIcon(app.windowIcon())
        except Exception:
            pass
        self.productos_pagina_actual = 0
        self.productos_filtro = ""
        self._comp_inicializado = False
        self._comp_timer = QTimer(self)
        self._comp_timer.setSingleShot(True)
        self._comp_timer.setInterval(200)  # 200 ms
        self._init_sound()
        
    
        
    ## --- Totales/Ajustes globales ---
        self._interes_pct = 0.0
        self._descuento_pct = 0.0
        self._subtotal_base = 0.0
        self._interes_monto = 0.0
        self._descuento_monto = 0.0
        self._total_actual = 0.0

        # Selección de sucursal al iniciar (lee config)
        _pref = ((cfg.get("startup") or {}).get("default_sucursal") or "ask")

        # direcciones desde config (si no, usa fallback actual)
        self.direcciones = ((cfg.get("business") or {}).get("sucursales") or {
            'Sarmiento': 'Pte. Sarmiento 1695, Gerli',
            'Salta':     'Salta 1694, Gerli'
        })

        if _pref in ("Sarmiento", "Salta"):
            self.sucursal = _pref
        else:
            sucursales = ["Sarmiento", "Salta"]
            suc, ok = QInputDialog.getItem(self, 'Sucursal', 'Seleccione sucursal:', sucursales, 0, False)
            if not ok:
                sys.exit(0)
            self.sucursal = suc

        # Sesión y repositorios
        self.session    = SessionLocal()
        self.proveedores = ProveedorService(self.session)  # NUEVO
        self.prod_repo = prod_repo(self.session, Producto)
        
        self.venta_repo = VentaRepo(self.session)
        self.user_repo  = UsuarioRepo(self.session)
        # Admin?
        self.es_admin = es_admin
        # --- COMPLETER: atributos base (evita AttributeError) ---
        self._completer = None
        self._completer_model = None
        
        # Pestañas con iconos + texto
        tabs = QTabWidget()
        tabs.setIconSize(QtCore.QSize(22, 22))   # antes 100x100, hacía la barra altísima
        self.tabs = tabs                      # <— para poder leer su índice actual
        self._admin_ok_until = (datetime.max if getattr(self, "es_admin", False) else None)
        # <— vence el cache de admin
        self._last_tab_index = 0              # <— para volver atrás si cancela login
        tabs.addTab(self.tab_productos(),   icon('productos.svg'), 'Productos')
        tabs.setTabToolTip(0, 'Productos')

        tabs.addTab(self.tab_proveedores(), icon('proveedor.png'), 'Proveedores')
        tabs.setTabToolTip(1, 'Proveedores')

        tabs.addTab(self.tab_ventas(), icon('ventas.svg'), 'Ventas')
        tabs.setTabToolTip(2, 'Ventas')

        self.historial = HistorialVentasWidget(self.session, sucursal_actual=None, parent=self, es_admin=self.es_admin)

        self.idx_historial = tabs.addTab(self.historial, icon('history.svg'), 'Historial')
        tabs.setTabToolTip(self.idx_historial, 'Historial de ventas')
        
        
        
        self._init_reports_scheduler()

        self.idx_config = tabs.addTab(self.tab_configuracion(), icon('config.svg'), 'Configuración')
        tabs.setTabToolTip(self.idx_config, 'Configuración')

        # Las acciones internas quedarán protegidas con login admin.
        self.idx_usuarios = tabs.addTab(self.tab_usuarios(), icon('usuarios.svg'), 'Usuarios')
        tabs.setTabToolTip(self.idx_usuarios, 'Usuarios')
        self.tabs.currentChanged.connect(self._gate_tabs_admin)

        tabs.tabBar().setExpanding(False)
        tabs.setUsesScrollButtons(True)

        self.setCentralWidget(tabs)

        # Barra de estado
        self._setup_status_bar()

        # Sistema de sincronización (inicializar antes de setup)
        self._sync_manager = None
        self._sync_timer = QTimer(self)
        self._sync_timer.timeout.connect(self._ejecutar_sincronizacion)
        self._last_sync_time = None
        self._setup_sync_scheduler()
        self._crear_boton_sync_manual()  # Crear botón para modo manual

        from PyQt5.QtCore import QSize
        self.setMinimumSize(980, 640)  # un mínimo razonable que siempre cabe
        
        from PyQt5.QtWidgets import QApplication
        screen_geo = QApplication.primaryScreen().availableGeometry()

# tamaño objetivo “amable”: hasta el 85% del área disponible
        target_w = min(max(1100, int(screen_geo.width()  * 0.85)),  screen_geo.width()  - 20)
        target_h = min(max(700,  int(screen_geo.height() * 0.85)),  screen_geo.height() - 40)

# aplica respetando el mínimo recién puesto
        self.resize(max(self.minimumWidth(),  target_w),
                    max(self.minimumHeight(), target_h))
        
        QTimer.singleShot(0, self.showMaximized)
# Abrir siempre maximizada
        self.setWindowState(self.windowState() | Qt.WindowMaximized)

        
# --- Construir el completer una sola vez ---
        self._setup_completer()

# Aplicar tema al arrancar
        self._apply_theme_stylesheet()
## Backups programados       
        self._setup_backups()
        QTimer.singleShot(500, self._check_pending_config_restore)
    
 # Icono en bandeja (si está activado en config)
        self._init_tray_icon()

# Menú de ayuda
        self._setup_help_menu()

# Atajos (globales y por sección)
        try:
            from app.gui.shortcuts import ShortcutManager
# Mapa de callbacks: el gestor invoca estas funciones
            cb = {
                # Navegación F1..F6
               "nav.productos":        lambda: self._goto_tab("productos"),
                "nav.proveedores":      lambda: self._goto_tab("proveedores"),
                "nav.ventas":           lambda: self._goto_tab("ventas"),
                "nav.historial":        lambda: self._goto_tab("historial"),
                "nav.configuraciones":  lambda: self._goto_tab("configuraciones"),
                "nav.usuarios":         lambda: self._goto_tab("usuarios"),
                # --- Productos (letras / Delete) ---
                "productos.agregar":          self._productos_agregar_popup,      # NUEVO: popup mini
                "productos.editar":           self._productos_editar_por_codigo,   # NUEVO: pide código y edita
                "productos.eliminar":         self.eliminar_productos,
                "productos.imprimir_codigo":  self.imprimir_codigos,

                # --- Ventas (letras) ---
                "ventas.finalizar":           self._shortcut_finalizar_venta_dialog,
                "ventas.efectivo":            self._shortcut_set_efectivo,
                "ventas.tarjeta":             self._shortcut_set_tarjeta_dialog,  # pide cuotas + interés
                "ventas.devolucion":          self._on_devolucion,
                "ventas.whatsapp":            self.enviar_ticket_whatsapp,     # usa la última venta si existe
                "ventas.imprimir":            self._imprimir_ticket_via_shortcut, # reimprime ticket seleccionado/último
                "ventas.guardar_borrador":    self._guardar_borrador,          # guarda la cesta como borrador
                "ventas.abrir_borradores":    self._abrir_borradores,          # abre diálogo de borradores
            }
            self.shortcut_manager = ShortcutManager(self, callbacks=cb)
            logger.info("[SHORTCUTS] Sistema de atajos inicializado")
        except Exception as e:
            self.shortcut_manager = None
            logger.error(f"[SHORTCUTS] Error inicializando atajos: {e}")
    
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

    def closeEvent(self, event):
        """
        Al cerrar con la X:
        - Si la opción 'minimizar a bandeja' está activa y hay icono de tray → se oculta.
        - Si no, se cierra la aplicación normalmente.
        """
        if not getattr(self, "_minimize_to_tray_on_close", False):
            # Comportamiento normal: cerrar sesión BD antes de salir
            self._cleanup_resources()
            try:
                super().closeEvent(event)
            except Exception:
                event.accept()
            return

        tray = getattr(self, "tray", None)
        if tray is not None and tray.isVisible():
            event.ignore()
            self.hide()
            try:
                if not getattr(self, "_tray_notified", False):
                    tray.showMessage(
                        "TuLocal 2025",
                        "La aplicación sigue ejecutándose en la bandeja del sistema.\n"
                        "Usá clic derecho → 'Salir' para cerrarla por completo.",
                        QSystemTrayIcon.Information,
                        4000,
                    )
                    self._tray_notified = True
            except Exception:
                pass
        else:
            # Fallback: si por alguna razón no hay bandeja, cerrar normal
            self._cleanup_resources()
            try:
                super().closeEvent(event)
            except Exception:
                event.accept()

    def _cleanup_resources(self):
        """Libera recursos antes de cerrar la aplicación."""
        # Cerrar sesión de base de datos para evitar memory leaks
        try:
            if hasattr(self, 'session') and self.session is not None:
                self.session.close()
                self.session = None
        except Exception:
            pass

        # Detener timers si existen
        try:
            if hasattr(self, '_sync_timer') and self._sync_timer is not None:
                self._sync_timer.stop()
        except Exception:
            pass
                
                
                
#SINCRONIZACION
    def _setup_sync_scheduler(self):
        """Configura el scheduler de sincronización desde app_config.json"""
        cfg = load_config()
        sync_cfg = cfg.get("sync", {})

        enabled = sync_cfg.get("enabled", False)
        mode = sync_cfg.get("mode", "interval")
        interval_min = sync_cfg.get("interval_minutes", 5)

        # Detener timer si ya está corriendo
        self._sync_timer.stop()

        if not enabled:
            return

        # Crear SyncManager
        from app.database import SessionLocal
        session = SessionLocal()

        # Obtener sucursal actual
        sucursal_actual = getattr(self, 'sucursal', 'Sarmiento')
        self._sync_manager = SyncManager(session, sucursal_actual)

        # Configurar según modo
        if mode == "interval":
            # Sincronizar cada X minutos
            self._sync_timer.setInterval(interval_min * 60 * 1000)  # Convertir a ms
            self._sync_timer.start()
        elif mode == "on_change":
            # Revisar cada 30 segundos si hay cambios
            self._sync_timer.setInterval(30 * 1000)
            self._sync_timer.start()
        # Si mode == "manual", no iniciar timer

    def _reiniciar_sync_scheduler(self):
        """Reinicia el scheduler cuando se guarda la configuración"""
        self._setup_sync_scheduler()

        # Actualizar visibilidad del botón manual
        if hasattr(self, 'btn_sync_manual'):
            cfg = load_config()
            enabled = cfg.get("sync", {}).get("enabled", False)
            self.btn_sync_manual.setVisible(True)
            if not enabled:
                self.btn_sync_manual.setToolTip("Sincronizacion desactivada. Activalo en Configuracion.")
            else:
                self.btn_sync_manual.setToolTip("Click para sincronizar manualmente")
        
        #EJECUTAR SINCRO
        
    def _ejecutar_sincronizacion(self):
        """Ejecuta un ciclo de sincronizacion"""
        cfg = load_config()
        sync_cfg = cfg.get("sync", {})
        enabled = sync_cfg.get("enabled", False)
        if not enabled:
            QMessageBox.information(self, "Sincronizacion", "La sincronizacion esta desactivada en Configuracion.")
            return

        if not self._sync_manager:
            from app.database import SessionLocal
            session = SessionLocal()
            sucursal_actual = getattr(self, 'sucursal', 'Sarmiento')
            self._sync_manager = SyncManager(session, sucursal_actual)

        if not self._sync_manager:
            return

        mode = sync_cfg.get("mode", "interval")
        # Si es modo "on_change", verificar si hay cambios
        if mode == "on_change":
            if not self._sync_manager.detectar_cambios_pendientes():
                # No hay cambios, actualizar indicador y salir
                self._actualizar_indicador_sync(pendiente=False)
                return

        # Ejecutar sincronización
        try:
            resultado = self._sync_manager.ejecutar_sincronizacion_completa()

            # Actualizar indicador
            self._last_sync_time = datetime.now()
            self._actualizar_indicador_sync(
                enviados=resultado["enviados"],
                recibidos=resultado["recibidos"],
                errores=resultado["errores"]
            )

            # Guardar timestamp
            cfg = load_config()
            cfg["sync"]["last_sync"] = self._last_sync_time.isoformat()
            from app.config import save as save_config
            save_config(cfg)

        except Exception as e:
            print(f"[SYNC] Error: {e}")
            self._actualizar_indicador_sync(error=str(e))
            
            
            
    #INDICADOR SINC Y  SINC MANUAL
    def _actualizar_indicador_sync(self, enviados=0, recibidos=0, errores=None, pendiente=False, error=None):
        """Actualiza el indicador de sincronización en la barra de estado"""
        if not hasattr(self, 'lbl_sync_status'):
            # Crear label si no existe
            self.lbl_sync_status = QLabel()
            self.statusBar().addPermanentWidget(self.lbl_sync_status)

        cfg = load_config()
        sync_enabled = cfg.get("sync", {}).get("enabled", False)

        if not sync_enabled:
            self.lbl_sync_status.setText("")
            return

        if error:
            self.lbl_sync_status.setText(f"🔴 Sync error: {error[:30]}")
            self.lbl_sync_status.setStyleSheet("color: #E74C3C;")
        elif errores:
            self.lbl_sync_status.setText(f"⚠️ Sync: {len(errores)} errores")
            self.lbl_sync_status.setStyleSheet("color: #F39C12;")
        elif pendiente:
            self.lbl_sync_status.setText("⏳ Cambios pendientes")
            self.lbl_sync_status.setStyleSheet("color: #3498DB;")
        else:
            if self._last_sync_time:
                # Calcular tiempo desde última sync
                delta = datetime.now() - self._last_sync_time
                if delta.seconds < 60:
                    tiempo_str = "hace un momento"
                elif delta.seconds < 3600:
                    tiempo_str = f"hace {delta.seconds // 60} min"
                else:
                    tiempo_str = f"hace {delta.seconds // 3600}h"

                msg = f"✓ Sync: {tiempo_str}"
                if enviados > 0 or recibidos > 0:
                    msg += f" ({enviados}↑ {recibidos}↓)"

                self.lbl_sync_status.setText(msg)
                self.lbl_sync_status.setStyleSheet("color: #27AE60;")
            else:
                self.lbl_sync_status.setText("🔄 Sync activa")
                self.lbl_sync_status.setStyleSheet("color: #95A5A6;")
    
    ### 6. (Opcional) Botón manual en status bar para modo manual

    def _crear_boton_sync_manual(self):
        """Crea un boton en la status bar para sincronizacion manual"""
        self.btn_sync_manual = QPushButton("Sincronizar")
        self.btn_sync_manual.setFlat(True)
        self.btn_sync_manual.setToolTip("Click para sincronizar manualmente")
        self.btn_sync_manual.clicked.connect(self._ejecutar_sincronizacion)
        self.statusBar().addPermanentWidget(self.btn_sync_manual)

        cfg = load_config()
        enabled = cfg.get("sync", {}).get("enabled", False)

        self.btn_sync_manual.setVisible(True)
        if not enabled:
            self.btn_sync_manual.setToolTip("Sincronizacion desactivada. Activalo en Configuracion.")

    def _check_pending_config_restore(self):
        """Pregunta si hay backup de configuracion pendiente."""
        try:
            if not has_pending_backup():
                return
        except Exception:
            return

        msg = QMessageBox(self)
        msg.setWindowTitle("Restaurar configuracion")
        msg.setText("Se encontro un backup de configuracion.")
        msg.setInformativeText("Quieres restaurarlo ahora? Puedes buscar un archivo manualmente.")
        btn_restore = msg.addButton("Restaurar", QMessageBox.AcceptRole)
        btn_browse = msg.addButton("Buscar archivo...", QMessageBox.ActionRole)
        btn_skip = msg.addButton("Omitir", QMessageBox.RejectRole)
        msg.setIcon(QMessageBox.Question)
        msg.exec_()

        if msg.clickedButton() == btn_restore:
            ok = restore_from_backup()
            if ok:
                QMessageBox.information(self, "Restaurar configuracion", "Configuracion restaurada. Reinicia la aplicacion para aplicar los cambios.")
            else:
                QMessageBox.warning(self, "Restaurar configuracion", "No se pudo restaurar la configuracion.")
        elif msg.clickedButton() == btn_browse:
            try:
                default_dir = str(Path(get_backup_path()).parent)
            except Exception:
                default_dir = ""
            path, _ = QFileDialog.getOpenFileName(self, "Elegir app_config.json", default_dir, "JSON (*.json);;Todos (*.*)")
            if path:
                ok = restore_from_path(path)
                if ok:
                    QMessageBox.information(self, "Restaurar configuracion", "Configuracion restaurada. Reinicia la aplicacion para aplicar los cambios.")
                else:
                    QMessageBox.warning(self, "Restaurar configuracion", "No se pudo restaurar la configuracion.")

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

        
    # —————— Helper para comprobar checkboxes ——————
    def _is_row_checked(self, row, table):
        it = table.item(row, 0)
        return bool(it and it.checkState() == Qt.Checked)
    # ---------------- Productos ----------------
    

    def toggle_checkbox(self, row, col):
        itm = self.table_productos.item(row, 0)
        itm.setCheckState(Qt.Unchecked if itm.checkState()==Qt.Checked else Qt.Checked)

    
    def deshacer(self):
        if not self.history: return
        tipo, datos = self.history.pop()
        if tipo=='add':
            p = self.session.query(Producto).filter_by(codigo_barra=datos['codigo_barra']).first()
            if p: self.session.delete(p)
        elif tipo=='del':
            for d in datos:
                if not self.session.query(Producto).filter_by(codigo_barra=d['codigo_barra']).first():
                    self.session.add(Producto(**d))
        self.session.commit(); self.refrescar_productos()
        self.statusBar().showMessage('Acción deshecha',3000)
        self.refrescar_completer()
    

    def editar_precios_masivos(self):
        """Aplica un porcentaje o un monto fijo a todos los productos seleccionados."""
        modos = ['Porcentaje', 'Monto fijo']
        modo, ok = QInputDialog.getItem(self, 'Modo de edición', 'Seleccione modo:', modos, 0, False)
        if not ok:
            return
        if modo == 'Porcentaje':
            val, ok = QInputDialog.getDouble(self, 'Porcentaje', 'Introduce % (10 o -5):', decimals=2)
        else:
            val, ok = QInputDialog.getDouble(self, 'Monto fijo', 'Introduce importe (+/-):', decimals=2)
        if not ok:
            return

        filas = [
            r for r in range(self.table_productos.rowCount())
            if self._is_row_checked(r, self.table_productos)
        ]
        if not filas:
            QMessageBox.information(self, 'Editar precios', 'No hay productos seleccionados.')
            return
        
        for r in filas:
            pid = int(self.table_productos.item(r, 1).text())
            prod = self.session.query(Producto).get(pid)
            if modo == 'Porcentaje':
                prod.precio *= (1 + val/100.0)
            else:
                prod.precio += val
            prod.precio = max(prod.precio, 0.0)
        self.session.commit()
        self.refrescar_productos()
        QMessageBox.information(self, 'Completado', f'Actualizados {len(filas)} producto(s).')
        self.refrescar_completer()
    
    
    # ---------------- Ventas ----------------
    
    
    
    def _on_cesta_item_changed(self, item):
        # Solo columnas editables: 2=Cantidad, 3=Precio Unit.
        col = item.column()
        if col not in (2, 3):
            return
        r = item.row()

        # Normalizar cantidad
        try:
            cant = float(self.table_cesta.item(r, 2).text())
        except Exception:
            cant = 1.0
            self.table_cesta.setItem(r, 2, QTableWidgetItem("1"))

        # Normalizar P. Unit.
        try:
            pu = float(str(self.table_cesta.item(r, 3).text()).replace("$","").strip())
        except Exception:
            pu = 0.0
            self.table_cesta.setItem(r, 3, QTableWidgetItem("0.00"))

        # Recalcular total de la fila
        total = cant * pu
        it_total = self.table_cesta.item(r, 4)
        if it_total is None:
            it_total = QTableWidgetItem()
            self.table_cesta.setItem(r, 4, it_total)
        it_total.setText(f"{total:.2f}")

        # Alinear numéricos
        for c in (2, 3, 4):
            it = self.table_cesta.item(r, c)
            if it:
                it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

        # Recalcular totales generales y cuota si aplica
        self.actualizar_total()
    
    def _on_cesta_clicked(self,row,col):
        if col!=5: 
            return
        widget=self.table_cesta.cellWidget(row,col)
        if not widget:  # aquí evitamos el NoneType
            return
        for btn in widget.findChildren(QPushButton):
            if btn.underMouse():
                if btn.toolTip() == 'Editar':
                    self.editar_cantidad()
                else:
                    self.quitar_producto()
                break

    

        
    

    def _on_devolucion(self):
        if not self._ensure_admin("Devolución"):
            return
        # 1) Pedir número de ticket
        ticket, ok = QInputDialog.getInt(self, 'Devolución', 'Número de ticket:')
        if not ok:
            return
        try:
            ticket = int(ticket)
        except (TypeError, ValueError):
            QMessageBox.warning(self, 'Error', 'Ticket inválido.')
            return

        # 2) Validar par/impar por sucursal (imprescindible)
        if not self._ticket_valido_para_sucursal(ticket):
            QMessageBox.warning(
                self, 'Ticket inválido',
                'El ticket no corresponde a la numeración de esta sucursal.'
            )
            return

        # 3) Cargar venta por número de ticket (si el repo lo soporta), si no, por id
        venta = None
        if hasattr(self.venta_repo, 'obtener_por_numero'):
            venta = self.venta_repo.obtener_por_numero(ticket)
        if not venta:
            venta = self.venta_repo.obtener(ticket)

        if not venta:
            QMessageBox.warning(self, 'No existe', 'Ticket no encontrado.')
            return

        # 4) Abrir diálogo de edición
        try:
            dlg = DevolucionDialog(venta, self)
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'No se pudo abrir la devolución:\n{e}')
            return

        if dlg.exec_() != QDialog.Accepted:
            return

    # Capturar SIEMPRE el total anterior, antes de modificar la venta
        total_antes = float(getattr(venta, "total", 0.0) or 0.0)

        # 5) Aplicar cambios
        mods = dlg.get_modified()  # [(codigo_barra, nueva_cantidad), ...]
        try:
            self.venta_repo.actualizar_items(venta.id, mods)
            self.venta_repo.commit()
        except Exception as e:
            # rollback defensivo
            try:
                self.session.rollback()
            except Exception:
                pass
            QMessageBox.critical(self, 'Error', f'No se pudo actualizar la venta:\n{e}')
            return

        # 5.b) Comentario (preferir motivo del diálogo)
        motivo = None
        for attr in ("get_motivo", "motivo", "getComentario", "comentario"):
            try:
                val = getattr(dlg, attr)
                motivo = val() if callable(val) else val
                motivo = (motivo or "").strip()
                if motivo:
                    break
            except Exception:
                pass

        if not motivo:
            # fallback solo si el diálogo no provee motivo
            try:
                txt, ok = QInputDialog.getText(self, 'Comentario', 'Motivo de la devolución (opcional):')
                motivo = txt.strip() if ok and txt else ""
            except Exception:
                motivo = ""

        if motivo:
            # guardar en la propia venta para que historial y excel lo lean siempre
            try:
                # intenta atributo "comentario" (o "motivo"/"nota" si no existe)
                if hasattr(venta, "comentario"):
                    venta.comentario = motivo
                elif hasattr(venta, "motivo"):
                    venta.motivo = motivo
                elif hasattr(venta, "nota"):
                    venta.nota = motivo
                self.session.commit()
            except Exception:
                pass
            # además, si existe el helper del repo, registrá el log
            try:
                self.venta_repo.agregar_log(venta.id, motivo)
            except Exception:
                pass

        # 5.c) Recalcular total y actualizar pagado/vuelto si es efectivo
        try:
            total_bd = self.venta_repo.actualizar_total(venta.id)
            self.venta_repo.commit()
        except Exception:
            total_bd = getattr(venta, "total", 0.0)

        forma_raw = (getattr(venta, "forma_pago", None) or getattr(venta, "modo_pago", None) or getattr(venta, "modo", "") or "").lower()
        es_efectivo = not ("tarj" in forma_raw)

        mostro_msg_efectivo = False
        if es_efectivo:
            total_actual = float(total_bd or getattr(venta, "total", 0.0) or 0.0)

            # Solo la devolución del producto (sin considerar 'vuelto' previo)
            monto_devolucion = round(max(0.0, total_antes - total_actual), 2)

            # Guardar 'vuelto' para esta operación de devolución (opcional: solo refleja lo que se regresa ahora)
            try:
                venta.vuelto = monto_devolucion
                self.session.commit()
            except Exception:
                try:
                    # Si tenés un método repo, solo pasa el 'vuelto' nuevo; NO modificar 'pagado'
                    self.venta_repo.actualizar_vuelto(venta.id, monto_devolucion)
                    self.venta_repo.commit()
                except Exception:
                    pass

            # Cache usado por "Ventas del día" (si aplica)
            try:
                if not hasattr(self, "_pagos_efectivo"):
                    self._pagos_efectivo = {}
                key = str(getattr(venta, "numero_ticket", venta.id))
                self._pagos_efectivo[key] = (getattr(venta, "pagado", 0.0), monto_devolucion)
            except Exception:
                pass

            # Mensaje esperado
            QMessageBox.information(
                self, "Devolución",
                f"Total anterior: ${total_antes:.2f}\n"
                f"Total actual: ${total_actual:.2f}\n"
                f"Se debe regresar: ${monto_devolucion:.2f}"
            )
            mostro_msg_efectivo = True
        
    # ---------------- Historial de ventas ----------------
    def tab_historial(self):
        from PyQt5.QtWidgets import (
            QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
            QTableWidget, QHeaderView, QDateEdit, QComboBox, QTabWidget
        )
        from PyQt5.QtCore import Qt, QDate

        w = QWidget()
        main_lay = QVBoxLayout(w)

        # Tabs: Listado y Estadísticas
        tabs = QTabWidget()
        main_lay.addWidget(tabs)

        # TAB 1: LISTADO
        tab_listado = QWidget()
        lay = QVBoxLayout(tab_listado)

        # ----------------- Filtros -----------------
        row = QHBoxLayout()
        row.addWidget(QLabel("Desde:"))
        self.hist_desde = QDateEdit()
        self.hist_desde.setCalendarPopup(True)
        self.hist_desde.setDate(QDate.currentDate())
        row.addWidget(self.hist_desde)

        row.addWidget(QLabel("Hasta:"))
        self.hist_hasta = QDateEdit()
        self.hist_hasta.setCalendarPopup(True)
        self.hist_hasta.setDate(QDate.currentDate())
        row.addWidget(self.hist_hasta)

        row.addWidget(QLabel("Sucursal:"))
        self.hist_sucursal = QComboBox()
        self.hist_sucursal.addItem("Todas", None)
        for s in getattr(self, "direcciones", {}).keys():
            self.hist_sucursal.addItem(s, s)
        row.addWidget(self.hist_sucursal)

        row.addWidget(QLabel("Forma:"))
        self.hist_forma = QComboBox()
        self.hist_forma.addItem("Todas", None)
        self.hist_forma.addItem("Efectivo", "efectivo")
        self.hist_forma.addItem("Tarjeta", "tarjeta")
        row.addWidget(self.hist_forma)

        self.hist_buscar = QLineEdit()
        self.hist_buscar.setPlaceholderText("Nº de ticket o texto (producto)")
        row.addWidget(self.hist_buscar, stretch=1)

        btn_hoy = QPushButton("Hoy")
        btn_buscar = QPushButton("Buscar")
        btn_export = QPushButton("Exportar CSV")
        btn_hoy.clicked.connect(self._hist_hoy)
        btn_buscar.clicked.connect(self.recargar_historial)
        btn_export.clicked.connect(self.exportar_historial_csv)
        row.addWidget(btn_hoy)
        row.addWidget(btn_buscar)
        row.addWidget(btn_export)

        lay.addLayout(row)

        # ----------------- Tabla -----------------
        self.table_historial = QTableWidget(0, 11)
        self.table_historial.setHorizontalHeaderLabels([
            "Nº Ticket", "Fecha", "Sucursal", "Forma", "Cuotas",
            "Total", "Interés","Descuento", "Pagado", "Vuelto", "Acciones"
        ])
        self.table_historial.verticalHeader().setVisible(False)

        f = self.table_historial.font(); f.setPointSize(f.pointSize()+1)
        self.table_historial.setFont(f)

        hdr = self.table_historial.horizontalHeader()
        hf = hdr.font(); hf.setBold(True); hdr.setFont(hf)
        hdr.setSectionResizeMode(QHeaderView.Stretch)
        hdr.setSectionResizeMode(10, QHeaderView.ResizeToContents)  # acciones al ancho del contenido
        lay.addWidget(self.table_historial)

        # ----------------- Resumen -----------------
        self.lbl_hist_resumen = QLabel("0 ventas  |  Total: $0.00  |  Interés: $0.00  |  Efectivo: $0.00  |  Tarjeta: $0.00")
        lay.addWidget(self.lbl_hist_resumen)

        # Agregar tab de listado
        tabs.addTab(tab_listado, "Listado")

        # TAB 2: ESTADÍSTICAS
        try:
            tab_stats = self._create_stats_tab()
            tabs.addTab(tab_stats, "Estadísticas")
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error creando tab de estadísticas: {e}", exc_info=True)
            # Crear un tab de error simple
            error_widget = QWidget()
            error_layout = QVBoxLayout(error_widget)
            error_label = QLabel(f"Error al cargar estadísticas: {str(e)}")
            error_label.setStyleSheet("color: red; padding: 20px;")
            error_layout.addWidget(error_label)
            tabs.addTab(error_widget, "Estadísticas (Error)")

        # Cargar al abrir
        self.recargar_historial()
        return w

    def _create_stats_tab(self):
        """Crea el tab de estadísticas con gráficos y KPIs"""
        from PyQt5.QtWidgets import (
            QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox,
            QGridLayout, QPushButton, QScrollArea, QFrame
        )
        from PyQt5.QtCore import Qt

        container = QWidget()
        scroll = QScrollArea()
        scroll.setWidget(container)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        main_layout = QVBoxLayout(container)
        main_layout.setSpacing(16)

        # Banner de filtros activos
        self.stats_filtros_banner = QLabel()
        self.stats_filtros_banner.setStyleSheet("""
            QLabel {
                background-color: #e3f2fd;
                border: 1px solid #90caf9;
                border-radius: 4px;
                padding: 12px;
                font-size: 13px;
                color: #1565c0;
            }
        """)
        self.stats_filtros_banner.setWordWrap(True)
        main_layout.addWidget(self.stats_filtros_banner)

        # Botón para actualizar estadísticas
        btn_actualizar = QPushButton(" Actualizar Estadísticas")
        from app.gui.common import icon, ICON_SIZE
        btn_actualizar.setIcon(icon('refresh.svg'))
        btn_actualizar.setIconSize(ICON_SIZE)
        btn_actualizar.clicked.connect(self._actualizar_estadisticas)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(btn_actualizar)
        main_layout.addLayout(btn_layout)

        # KPIs principales (tarjetas)
        kpi_group = QGroupBox("Resumen del Período")
        kpi_layout = QGridLayout(kpi_group)
        kpi_layout.setSpacing(16)

        # Creamos labels para los KPIs
        self.kpi_total_ventas = self._create_kpi_card("Total Ventas", "$0.00", "#2e7d32")
        self.kpi_cant_ventas = self._create_kpi_card("Cantidad", "0", "#1976d2")
        self.kpi_promedio = self._create_kpi_card("Promedio", "$0.00", "#f57c00")
        self.kpi_interes_total = self._create_kpi_card("Interés Total", "$0.00", "#c62828")

        kpi_layout.addWidget(self.kpi_total_ventas, 0, 0)
        kpi_layout.addWidget(self.kpi_cant_ventas, 0, 1)
        kpi_layout.addWidget(self.kpi_promedio, 0, 2)
        kpi_layout.addWidget(self.kpi_interes_total, 0, 3)

        main_layout.addWidget(kpi_group)

        # Área para gráfico de ventas
        chart_group = QGroupBox("Ventas por Día")
        chart_layout = QVBoxLayout(chart_group)

        # Placeholder para el canvas de matplotlib
        self.stats_chart_container = QWidget()
        self.stats_chart_layout = QVBoxLayout(self.stats_chart_container)
        self.stats_chart_layout.setContentsMargins(0, 0, 0, 0)
        chart_layout.addWidget(self.stats_chart_container)

        main_layout.addWidget(chart_group)

        # Comparativa de sucursales (solo visible cuando se elige "Todas")
        self.stats_comparativa_group = QGroupBox("Comparativa por Sucursal")
        comparativa_layout = QVBoxLayout(self.stats_comparativa_group)

        self.stats_comparativa_container = QWidget()
        self.stats_comparativa_layout = QVBoxLayout(self.stats_comparativa_container)
        self.stats_comparativa_layout.setContentsMargins(0, 0, 0, 0)
        comparativa_layout.addWidget(self.stats_comparativa_container)

        main_layout.addWidget(self.stats_comparativa_group)
        self.stats_comparativa_group.setVisible(False)  # Oculto por defecto

        # Top productos
        top_group = QGroupBox("Productos Más Vendidos (Top 10)")
        top_layout = QVBoxLayout(top_group)

        from PyQt5.QtWidgets import QTableWidget, QHeaderView
        self.table_top_productos = QTableWidget(0, 4)
        self.table_top_productos.setHorizontalHeaderLabels([
            "Producto", "Código", "Cantidad Vendida", "Total Facturado"
        ])
        self.table_top_productos.verticalHeader().setVisible(False)

        hdr = self.table_top_productos.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)  # Nombre
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Código
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Cantidad
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Total

        self.table_top_productos.setMaximumHeight(350)
        top_layout.addWidget(self.table_top_productos)

        main_layout.addWidget(top_group)
        main_layout.addStretch()

        # Retornamos el scroll
        wrapper = QWidget()
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.addWidget(scroll)

        return wrapper

    def _create_kpi_card(self, title, value, color):
        """Crea una tarjeta KPI con estilo"""
        from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel
        from PyQt5.QtCore import Qt

        card = QWidget()
        card.setStyleSheet(f"""
            QWidget {{
                background-color: white;
                border: 2px solid {color};
                border-radius: 8px;
                padding: 16px;
            }}
        """)

        layout = QVBoxLayout(card)
        layout.setSpacing(8)

        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("font-size: 12px; color: #666; font-weight: normal;")
        lbl_title.setAlignment(Qt.AlignCenter)

        lbl_value = QLabel(value)
        lbl_value.setStyleSheet(f"font-size: 24px; color: {color}; font-weight: bold;")
        lbl_value.setAlignment(Qt.AlignCenter)
        lbl_value.setObjectName("kpi_value")  # Para poder actualizarlo después

        layout.addWidget(lbl_title)
        layout.addWidget(lbl_value)

        return card

    def _actualizar_estadisticas(self):
        """Actualiza las estadísticas y gráficos"""
        from datetime import datetime
        from collections import defaultdict

        # Obtener filtros del tab de listado
        try:
            desde_date = self.hist_desde.date().toPyDate()
            hasta_date = self.hist_hasta.date().toPyDate()
            sucursal = self.hist_sucursal.currentData()
            forma = self.hist_forma.currentData()
            sucursal_nombre = self.hist_sucursal.currentText()
            forma_nombre = self.hist_forma.currentText()
        except Exception:
            desde_date = datetime.now().date()
            hasta_date = datetime.now().date()
            sucursal = None
            forma = None
            sucursal_nombre = "Todas"
            forma_nombre = "Todas"

        # Actualizar banner de filtros
        filtros_texto = f"📊 Mostrando estadísticas: {desde_date.strftime('%d/%m/%Y')} - {hasta_date.strftime('%d/%m/%Y')}"
        filtros_texto += f"  |  Sucursal: {sucursal_nombre}"
        filtros_texto += f"  |  Forma de pago: {forma_nombre}"
        self.stats_filtros_banner.setText(filtros_texto)

        # Obtener ventas del repositorio
        desde_dt = datetime.combine(desde_date, datetime.min.time())
        hasta_dt = datetime.combine(hasta_date, datetime.max.time())

        ventas = self.venta_repo.listar_por_rango(desde_dt, hasta_dt, sucursal)

        # Filtrar por forma de pago si es necesario
        if forma:
            ventas = [v for v in ventas if v.modo_pago.lower().startswith(forma[:3])]

        # Calcular KPIs
        total_ventas = sum(v.total for v in ventas)
        cant_ventas = len(ventas)
        promedio = total_ventas / cant_ventas if cant_ventas > 0 else 0
        interes_total = sum(getattr(v, 'interes_monto', 0) or 0 for v in ventas)

        # Actualizar labels de KPIs
        self.kpi_total_ventas.findChild(QLabel, "kpi_value").setText(f"${total_ventas:,.2f}")
        self.kpi_cant_ventas.findChild(QLabel, "kpi_value").setText(f"{cant_ventas}")
        self.kpi_promedio.findChild(QLabel, "kpi_value").setText(f"${promedio:,.2f}")
        self.kpi_interes_total.findChild(QLabel, "kpi_value").setText(f"${interes_total:,.2f}")

        # Preparar datos para gráfico de ventas por día
        ventas_por_dia = defaultdict(float)
        for v in ventas:
            fecha = v.fecha.date() if hasattr(v.fecha, 'date') else v.fecha
            ventas_por_dia[fecha] += v.total

        # Generar gráfico
        self._generar_grafico_ventas(ventas_por_dia, desde_date, hasta_date)

        # Si se eligió "Todas las sucursales", mostrar comparativa
        if sucursal is None and hasattr(self, 'direcciones') and len(self.direcciones) > 1:
            self.stats_comparativa_group.setVisible(True)
            self._generar_comparativa_sucursales(desde_dt, hasta_dt, forma)
        else:
            self.stats_comparativa_group.setVisible(False)

        # Calcular top productos
        self._calcular_top_productos(ventas)

    def _generar_grafico_ventas(self, ventas_por_dia, desde, hasta):
        """Genera el gráfico de ventas por día usando matplotlib"""
        try:
            import matplotlib
            matplotlib.use('Qt5Agg')
            from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
            from matplotlib.figure import Figure
            import matplotlib.dates as mdates
            from datetime import datetime, timedelta

            # Limpiar canvas anterior
            for i in reversed(range(self.stats_chart_layout.count())):
                self.stats_chart_layout.itemAt(i).widget().setParent(None)

            # Crear figura
            fig = Figure(figsize=(10, 4), dpi=100)
            ax = fig.add_subplot(111)

            # Preparar datos
            if not ventas_por_dia:
                ax.text(0.5, 0.5, 'No hay datos para mostrar',
                       ha='center', va='center', fontsize=14, color='gray')
                ax.set_xlim(0, 1)
                ax.set_ylim(0, 1)
                ax.axis('off')
            else:
                # Ordenar por fecha
                fechas = sorted(ventas_por_dia.keys())
                valores = [ventas_por_dia[f] for f in fechas]

                # Crear gráfico de barras
                ax.bar(fechas, valores, color='#2e7d32', alpha=0.7, edgecolor='#1b5e20')

                # Configurar ejes
                ax.set_xlabel('Fecha', fontsize=10)
                ax.set_ylabel('Total Ventas ($)', fontsize=10)
                ax.set_title(f'Ventas desde {desde} hasta {hasta}', fontsize=12, fontweight='bold')

                # Formato de fechas en eje X
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m'))
                if len(fechas) > 10:
                    ax.xaxis.set_major_locator(mdates.DayLocator(interval=max(1, len(fechas)//10)))

                # Rotar labels
                fig.autofmt_xdate()

                # Grid
                ax.grid(True, alpha=0.3, axis='y')
                ax.set_axisbelow(True)

            fig.tight_layout()

            # Crear canvas y agregarlo
            canvas = FigureCanvasQTAgg(fig)
            self.stats_chart_layout.addWidget(canvas)

        except Exception as e:
            from PyQt5.QtWidgets import QLabel
            error_label = QLabel(f"Error al generar gráfico: {str(e)}")
            error_label.setStyleSheet("color: red; padding: 20px;")
            self.stats_chart_layout.addWidget(error_label)

    def _calcular_top_productos(self, ventas):
        """Calcula y muestra los productos más vendidos"""
        from collections import defaultdict
        from PyQt5.QtWidgets import QTableWidgetItem

        # Acumular por producto
        productos_stats = defaultdict(lambda: {'cantidad': 0, 'total': 0, 'nombre': '', 'codigo': ''})

        for venta in ventas:
            items = self.venta_repo.listar_items(venta.id)
            for item in items:
                # Obtener datos del producto
                if hasattr(item, 'producto') and item.producto:
                    prod_id = item.producto.id
                    nombre = item.producto.nombre
                    codigo = item.producto.codigo_barra
                else:
                    # Si no hay producto asociado, usar el ID del item
                    prod_id = f"item_{item.id}"
                    nombre = getattr(item, 'nombre', 'Producto desconocido')
                    codigo = getattr(item, 'codigo', 'N/A')

                cantidad = getattr(item, 'cantidad', 1)
                precio = getattr(item, 'precio_unit', 0)

                productos_stats[prod_id]['cantidad'] += cantidad
                productos_stats[prod_id]['total'] += cantidad * precio
                productos_stats[prod_id]['nombre'] = nombre
                productos_stats[prod_id]['codigo'] = codigo

        # Ordenar por cantidad vendida
        top_productos = sorted(productos_stats.items(),
                              key=lambda x: x[1]['cantidad'],
                              reverse=True)[:10]

        # Actualizar tabla
        self.table_top_productos.setRowCount(0)
        for i, (prod_id, stats) in enumerate(top_productos):
            self.table_top_productos.insertRow(i)
            self.table_top_productos.setItem(i, 0, QTableWidgetItem(stats['nombre']))
            self.table_top_productos.setItem(i, 1, QTableWidgetItem(stats['codigo']))
            self.table_top_productos.setItem(i, 2, QTableWidgetItem(str(int(stats['cantidad']))))
            self.table_top_productos.setItem(i, 3, QTableWidgetItem(f"${stats['total']:,.2f}"))

    def _generar_comparativa_sucursales(self, desde_dt, hasta_dt, forma):
        """Genera un gráfico comparativo entre sucursales"""
        try:
            import matplotlib
            matplotlib.use('Qt5Agg')
            from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
            from matplotlib.figure import Figure
            from collections import defaultdict

            # Limpiar canvas anterior
            for i in reversed(range(self.stats_comparativa_layout.count())):
                self.stats_comparativa_layout.itemAt(i).widget().setParent(None)

            # Obtener ventas de cada sucursal
            sucursales_data = {}
            for sucursal_nombre in self.direcciones.keys():
                ventas = self.venta_repo.listar_por_rango(desde_dt, hasta_dt, sucursal_nombre)

                # Filtrar por forma de pago si es necesario
                if forma:
                    ventas = [v for v in ventas if v.modo_pago.lower().startswith(forma[:3])]

                total = sum(v.total for v in ventas)
                cantidad = len(ventas)
                sucursales_data[sucursal_nombre] = {
                    'total': total,
                    'cantidad': cantidad,
                    'promedio': total / cantidad if cantidad > 0 else 0
                }

            if not sucursales_data:
                return

            # Crear figura con 2 subplots
            fig = Figure(figsize=(12, 4), dpi=100)

            # Subplot 1: Total facturado por sucursal
            ax1 = fig.add_subplot(121)
            sucursales = list(sucursales_data.keys())
            totales = [sucursales_data[s]['total'] for s in sucursales]

            bars1 = ax1.bar(sucursales, totales, color=['#2e7d32', '#1976d2'], alpha=0.7)
            ax1.set_ylabel('Total Facturado ($)', fontsize=10)
            ax1.set_title('Total Facturado por Sucursal', fontsize=12, fontweight='bold')
            ax1.grid(True, alpha=0.3, axis='y')
            ax1.set_axisbelow(True)

            # Agregar valores sobre las barras
            for bar, total in zip(bars1, totales):
                height = bar.get_height()
                ax1.text(bar.get_x() + bar.get_width()/2., height,
                        f'${total:,.0f}',
                        ha='center', va='bottom', fontsize=9, fontweight='bold')

            # Subplot 2: Cantidad de ventas por sucursal
            ax2 = fig.add_subplot(122)
            cantidades = [sucursales_data[s]['cantidad'] for s in sucursales]

            bars2 = ax2.bar(sucursales, cantidades, color=['#f57c00', '#c62828'], alpha=0.7)
            ax2.set_ylabel('Cantidad de Ventas', fontsize=10)
            ax2.set_title('Cantidad de Ventas por Sucursal', fontsize=12, fontweight='bold')
            ax2.grid(True, alpha=0.3, axis='y')
            ax2.set_axisbelow(True)

            # Agregar valores sobre las barras
            for bar, cant in zip(bars2, cantidades):
                height = bar.get_height()
                ax2.text(bar.get_x() + bar.get_width()/2., height,
                        f'{int(cant)}',
                        ha='center', va='bottom', fontsize=9, fontweight='bold')

            fig.tight_layout()

            # Crear canvas y agregarlo
            canvas = FigureCanvasQTAgg(fig)
            self.stats_comparativa_layout.addWidget(canvas)

            # Agregar tabla resumen debajo
            from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
            table = QTableWidget(len(sucursales), 4)
            table.setHorizontalHeaderLabels(['Sucursal', 'Total Facturado', 'Cantidad', 'Promedio'])
            table.verticalHeader().setVisible(False)

            for i, suc in enumerate(sucursales):
                data = sucursales_data[suc]
                table.setItem(i, 0, QTableWidgetItem(suc))
                table.setItem(i, 1, QTableWidgetItem(f"${data['total']:,.2f}"))
                table.setItem(i, 2, QTableWidgetItem(str(data['cantidad'])))
                table.setItem(i, 3, QTableWidgetItem(f"${data['promedio']:,.2f}"))

            hdr = table.horizontalHeader()
            hdr.setSectionResizeMode(0, QHeaderView.Stretch)
            hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
            hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
            hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)

            table.setMaximumHeight(150)
            self.stats_comparativa_layout.addWidget(table)

        except Exception as e:
            from PyQt5.QtWidgets import QLabel
            error_label = QLabel(f"Error al generar comparativa: {str(e)}")
            error_label.setStyleSheet("color: red; padding: 20px;")
            self.stats_comparativa_layout.addWidget(error_label)

 #-------------------------------------------------------------------------------------------------------
        

    # --- Cargar/Guardar slots de plantilla en config ---
  
    def _build_tpl_placeholder_panel(self):
        from PyQt5.QtWidgets import QWidget, QVBoxLayout, QGroupBox, QGridLayout, QPushButton

        def make_section(title, buttons):
            box = QGroupBox(title)
            grid = QGridLayout(box)
            grid.setHorizontalSpacing(10)
            grid.setVerticalSpacing(8)
            grid.setContentsMargins(8, 8, 8, 8)
            for i, (text, ins) in enumerate(buttons):
                b = QPushButton(text)
                b.setProperty("role", "inline")
                b.setMinimumHeight(28)
                b.setMinimumWidth(0)          # no se estiran
                b.clicked.connect(lambda _=None, s=ins: self._tpl_insert(s))
                grid.addWidget(b, i // 2, i % 2, alignment=Qt.AlignLeft)  # 2 columnas, pegado a la izquierda
            return box

        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)

        v.addWidget(make_section("Encabezado / Sucursal", [
            ("Nº ticket", "{{ticket.numero}}"),
            ("Fecha/hora", "{{ticket.fecha_hora}}"),
            ("Sucursal", "{{sucursal}}"),
            ("Dirección", "{{direccion}}"),
            ("Nombre comercio", "{{business}}"),
        ]))

        v.addWidget(make_section("Pago", [
            ("Modo pago", "{{pago.modo}}"),
            ("Cuotas", "{{pago.cuotas}}"),
            ("Monto cuota", "{{pago.monto_cuota}}"),
            ("Abonado", "{{abonado}}"),
            ("Vuelto", "{{vuelto}}"),
        ]))

        v.addWidget(make_section("Totales", [
            ("Subtotal", "{{totales.subtotal}}"),
            ("Interés", "{{totales.interes}}"),
            ("Descuento", "{{totales.descuento}}"),   # <-- nuevo
            ("TOTAL", "{{totales.total}}"),
        ]))

        v.addWidget(make_section("Ítems / Separadores", [
            ("Ítems", "{{items}}"),
            ("Línea ({{hr}})", "{{hr}}"),
        ]))

        v.addWidget(make_section("Formato por línea", [
            ("Centrar", "{{center: TU TEXTO}}"),
            ("Derecha", "{{right: TU TEXTO}}"),
            ("Negrita", "{{b: TU TEXTO}}"),
            ("Centrar+Negrita", "{{centerb: TU TEXTO}}"),
            ("Derecha+Negrita", "{{rightb: TU TEXTO}}"),
        ]))

        v.addStretch(1)
        return w

    def ir_pagina_anterior(self):
        if getattr(self, "productos_pagina_actual", 0) > 0:
            self.productos_pagina_actual -= 1
            self.refrescar_productos()

    def ir_pagina_siguiente(self):
        # El límite real lo corrige refrescar_productos()
        self.productos_pagina_actual = getattr(self, "productos_pagina_actual", 0) + 1
        self.refrescar_productos()
  
    def _ensure_completer(self):
        """Carga ligera del completer una sola vez (sólo columnas necesarias)."""
        if getattr(self, "_comp_inicializado", False):
            return

        from PyQt5.QtCore import QStringListModel, Qt
        from PyQt5.QtWidgets import QCompleter
        # CARGA LIGERA: solo código y nombre (más rápido que traer objetos enteros)
        filas = self.session.query(Producto.codigo_barra, Producto.nombre).all()
        items = [f"{cb} - {nm}" for cb, nm in filas]

        self._comp_src = QStringListModel(items, self)
        self._comp_proxy = LimitedFilterProxy(limit=100, parent=self)
        self._comp_proxy.setSourceModel(self._comp_src)
        self._comp_proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)

        self._comp = QCompleter(self._comp_proxy, self)
        self._comp.setCaseSensitivity(Qt.CaseInsensitive)
        self._comp.setCompletionMode(QCompleter.UnfilteredPopupCompletion)
        self._comp.setMaxVisibleItems(20)
        self.input_venta_buscar.setCompleter(self._comp)

        # Al elegir, dejamos solo el código (antes del " - ")
        self._comp.activated.connect(
            lambda s: self.input_venta_buscar.setText(str(s).split(" - ")[0].strip())
        )

        self._comp_inicializado = True

    def _apply_completer_filter(self, text: str):
        """Filtra el completer (no abrir popup con 0–1 letras para evitar lag)."""
        self._ensure_completer()
        if not text or len(text) < 2:
            return
        self._comp_proxy.setFilterWildcard(f"*{text}*")
        try:
            self._comp.setCompletionPrefix(text)
            self._comp.complete()
        except Exception:
            pass

    def eventFilter(self, obj, event):
        try:
            tbl = getattr(self, "table_productos", None)
            if tbl is not None:
                try:
                    vp = tbl.viewport()
                except RuntimeError:
                    # Si el objeto fue destruido, no hagas nada
                    return False
                if obj is vp:
                    if event.type() == QEvent.MouseButtonRelease:
                        index = tbl.indexAt(event.pos())
                        if index.column() == 0:
                            item = tbl.item(index.row(), 0)
                            if item is not None:
                                new_state = Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked
                                item.setCheckState(new_state)
                            return True  # Consumir el evento
        except Exception:
            pass
        return super().eventFilter(obj, event)

    

    def _ticket_valido_para_sucursal(self, ticket: int) -> bool:
        if self.sucursal == 'Sarmiento':
            return ticket % 2 == 1  # impares
        if self.sucursal == 'Salta':
            return ticket % 2 == 0  # pares
        return True

    def _fake_venta_for_preview(self):
        from types import SimpleNamespace
        from datetime import datetime
        v = SimpleNamespace()
        v.id = 123
        v.numero_ticket = 123
        v.fecha = datetime.now()
        v.sucursal = "Sarmiento"
        v.modo = "efectivo"
        v.forma_pago = "efectivo"
        v.cuotas = 0
        v.pagado = 200.0
        v.vuelto = 17.5
        v.interes_monto = 0.0
        v.total = 182.5
        # 👉 ÍTEMS DE PRUEBA PARA LA PREVIEW
        v._ticket_items = [
            {"codigo": "7791290786691", "nombre": "Suavizante Felicia 900ml", "precio_unitario": 55.0,  "cantidad": 1},
            {"codigo": "7790828104655", "nombre": "Jabón en pan paquete 3u", "precio_unitario": 18.0,  "cantidad": 1},
            {"codigo": "662425026821",  "nombre": "Tampones Tamaño M 10u",  "precio_unitario": 109.5, "cantidad": 1},
        ]
        return v

    # ----------------- Previsualización: usa el editor -----------------
    
    
    
    def nueva_venta(self):
        # Vaciar lista de ítems
        try:
            if hasattr(self, 'table_cesta') and self.table_cesta is not None:
                self.table_cesta.setRowCount(0)
        except Exception:
            pass

        # Resetear porcentajes, montos y labels
        self._reset_ajustes_globales()

        # Recalcular total y dejar foco en buscador
        try:
            self.actualizar_total()
        except Exception:
            pass
        try:
            self.input_venta_buscar.clear()
            self.input_venta_buscar.setFocus()
        except Exception:
            pass
    #########################
    #DESCUESTO EN FILA
    #########################
        
    

#HELPER PARA CACHE ADMIN
    def _ensure_admin(self, reason: str = "esta acción") -> bool:
        """Pide credenciales de admin si no hay caché vigente (5 min)."""
        now = datetime.now()
        # ⬇️ Si ya sos admin, no pedir nada nunca
        if getattr(self, "es_admin", False):
            self._admin_ok_until = datetime.max
            return True
        try:
            now = datetime.now()
            if getattr(self, "_admin_ok_until", None) and now < self._admin_ok_until:
                return True

            from app.login import LoginDialog# ajusta el import real si cambia el path
            dlg = LoginDialog(self.session, self)
            if dlg.exec_() != QDialog.Accepted or not getattr(dlg, "user", None):
                QMessageBox.warning(self, "Permiso denegado", "Acceso cancelado.")
                return False

            if not getattr(dlg.user, "es_admin", False):
                QMessageBox.critical(self, "Permiso denegado",
                                    "Se requiere un usuario administrador para " + reason + ".")
                return False

            # Cachea 5 minutos
            self._admin_ok_until = now + timedelta(seconds=30)
            return True
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo validar permisos:\n{e}")
            return False

    def _setup_help_menu(self):
        """Crea el menú de Ayuda."""
        from PyQt5.QtWidgets import QAction
        from version import __version__, __app_name__

        menubar = self.menuBar()
        help_menu = menubar.addMenu('&Ayuda')

        # Atajos de teclado
        shortcuts_action = QAction('Atajos de teclado (F12)', self)
        shortcuts_action.setShortcut('F12')
        shortcuts_action.triggered.connect(self._show_shortcuts_help)
        help_menu.addAction(shortcuts_action)

        help_menu.addSeparator()

        about_action = QAction(f'Acerca de {__app_name__}', self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _show_shortcuts_help(self):
        """Muestra la ayuda de atajos de teclado."""
        if self.shortcut_manager:
            help_text = self.shortcut_manager.get_shortcuts_help()
            QMessageBox.information(
                self,
                "Atajos de Teclado (F12)",
                help_text
            )
        else:
            QMessageBox.information(
                self,
                "Atajos de Teclado",
                "Sistema de atajos no disponible."
            )

# ==== Helpers invocados por los atajos (fallbacks visibles) ====
    def _informar_no_impl(self, nombre_accion: str):
        try:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.information(self, "Acción", f"{nombre_accion}: aún no conectado en esta versión.")
        except Exception:
            pass

    # --- Productos (invocados por atajos) ---
    def productos_agregar_via_shortcut(self):
        # Debe abrir popup para alta: código de barra, nombre, precio, categoría
        try:
            from app.gui.dialogs import ProductosDialog
            dlg = ProductosDialog(self.session, parent=self)
            dlg.setWindowTitle("Agregar producto")
            if dlg.exec_():
                self.refrescar_productos()
        except Exception:
            self._informar_no_impl("Agregar producto")

    def productos_editar_via_shortcut(self):
        # Pedir código de barras, traer y permitir editar (código, nombre, precio)
        try:
            from PyQt5.QtWidgets import QInputDialog, QMessageBox
            from app.models import Producto
            cb, ok = QInputDialog.getText(self, "Editar producto", "Código de barras:")
            if not ok or not cb: return
            prod = self.session.query(Producto).filter_by(codigo_barra=str(cb).strip()).first()
            if not prod:
                QMessageBox.information(self, "Editar", "Producto no encontrado.")
                return
            from app.gui.dialogs import ProductosDialog
            dlg = ProductosDialog(self.session, producto=prod, parent=self)
            dlg.setWindowTitle("Editar producto")
            if dlg.exec_():
                self.refrescar_productos()
        except Exception:
            self._informar_no_impl("Editar producto")

    def productos_eliminar_via_shortcut(self):
        # Supr (sin Ctrl+Shift): eliminar producto seleccionado o por código
        try:
            from PyQt5.QtWidgets import QMessageBox
            tbl = getattr(self, "table_productos", None)
            if not tbl or tbl.currentRow() < 0:
                self._informar_no_impl("Eliminar producto (seleccioná una fila)")
                return
            row = tbl.currentRow()
            cod = tbl.item(row, 2).text() if tbl.item(row, 2) else None
            if QMessageBox.question(self, "Eliminar", "¿Eliminar producto seleccionado?") != QMessageBox.Yes:
                return
            # Reutilizar flujo existente si tu mixin ya lo implementa; si no, borrado directo:
            try:
                self._eliminar_producto_desde_tabla(row)  # si existe
            except Exception:
                from app.models import Producto
                prod = self.session.query(Producto).filter_by(codigo_barra=cod).first()
                if prod:
                    self.session.delete(prod)
                    self.session.commit()
                    self.refrescar_productos()
        except Exception:
            self._informar_no_impl("Eliminar producto")

    def productos_imprimir_codigo_via_shortcut(self):
        # Popup: ingresar código -> imprime código+nombre+precio
        try:
            from PyQt5.QtWidgets import QInputDialog, QMessageBox
            from app.models import Producto
            cb, ok = QInputDialog.getText(self, "Imprimir código", "Código de barras:")
            if not ok or not cb: return
            prod = self.session.query(Producto).filter_by(codigo_barra=str(cb).strip()).first()
            if not prod:
                QMessageBox.information(self, "Imprimir", "Producto no encontrado.")
                return
            # Reutilizá tu flujo de impresión de códigos si ya existe:
            try:
                self._imprimir_codigo_producto(prod)  # si existe
            except Exception:
                # Fallback: usar el mismo mecanismo de tickets si tu helper lo soporta
                from app.gui.ventas_helpers import imprimir_ticket
                imprimir_ticket({"_fake": True, "producto": prod}, sucursal=self.sucursal, direcciones=self.direcciones, parent=self, preview=True)
        except Exception:
            self._informar_no_impl("Imprimir código de barras")

    # --- Ventas (invocados por atajos) ---
    def venta_modo_efectivo(self):
        # Conectar a tu handler real si existe
        try:
            self._set_modo_pago("efectivo")  # si tu ventas.py lo implementa
        except Exception:
            self._informar_no_impl("Pago en efectivo")

    def venta_modo_tarjeta(self):
        # Debe mostrar popup de cuotas + interés (por defecto 0%)
        try:
            if hasattr(self, "_abrir_popup_tarjeta"):
                self._abrir_popup_tarjeta()   # si existe helper
            else:
                self._informar_no_impl("Pago con tarjeta (popup cuotas+interés)")
        except Exception:
            self._informar_no_impl("Pago con tarjeta")

    def enviar_ticket_whatsapp_via_shortcut(self):
        # Popup: número de ticket, Enter abre WhatsApp Web
        try:
            from PyQt5.QtWidgets import QInputDialog
            num, ok = QInputDialog.getInt(self, "WhatsApp", "Número de ticket:")
            if not ok: return
            if hasattr(self, "_abrir_whatsapp_web_con_ticket"):
                self._abrir_whatsapp_web_con_ticket(num)
            else:
                self._informar_no_impl("Enviar ticket por WhatsApp")
        except Exception:
            self._informar_no_impl("Enviar ticket por WhatsApp")

    def imprimir_ticket_via_shortcut(self):
        # Igual que W pero abre impresora
        try:
            from PyQt5.QtWidgets import QInputDialog
            num, ok = QInputDialog.getInt(self, "Imprimir ticket", "Número de ticket:")
            if not ok: return
            if hasattr(self, "_imprimir_ticket_por_numero"):
                self._imprimir_ticket_por_numero(num)
            else:
                self._informar_no_impl("Imprimir ticket por número")
        except Exception:
            self._informar_no_impl("Imprimir ticket")
            
    def _goto_tab(self, logical_name: str):
        try:
            if getattr(self, "shortcut_manager", None):
                ix = self.shortcut_manager.get_tab_index_for(logical_name)
                if ix is not None:
                    self.tabs.setCurrentIndex(ix)
                    return
            # Fallback por si no hay manager o no se encontró
            mapping_guess = {
                "productos": 0,
                "proveedores": 1,
                "ventas": 2,
            }
            ix = mapping_guess.get(logical_name, None)
            if ix is not None:
                self.tabs.setCurrentIndex(ix)
        except Exception:
            pass      
        
        
    # --- Atajos de Ventas: E (efectivo) / T (tarjeta con diálogo) / F (imprimir) ---

    def _shortcut_set_efectivo(self):
        """Selecciona Efectivo y refresca UI de cuotas/interés."""
        try:
            if hasattr(self, 'rb_efectivo'):
                self.rb_efectivo.setChecked(True)
            if hasattr(self, '_refrescar_interes_btn'):
                self._refrescar_interes_btn()
            if hasattr(self, 'spin_cuotas'):
                self.spin_cuotas.setEnabled(False)
            if hasattr(self, 'cuota_label'):
                self.cuota_label.clear()
        except Exception:
            pass

    def _shortcut_set_tarjeta_dialog(self):
        """Activa Tarjeta y pide (cuotas, interés%) en dos pasos rápidos.

        Devuelve True si el usuario confirmó todo, False si canceló en algún paso.

        NUEVO: Si ya se configuró con el nuevo diálogo unificado, usar esos datos.
        """
        try:
            # NUEVO: Si ya se usó el nuevo diálogo unificado, no pedir nada más
            if hasattr(self, '_datos_tarjeta') and self._datos_tarjeta:
                # Ya está todo configurado desde el diálogo unificado
                if hasattr(self, 'rb_tarjeta'):
                    self.rb_tarjeta.setChecked(True)
                return True

            from PyQt5.QtWidgets import QInputDialog

            # Marcar tarjeta como modo activo
            if hasattr(self, 'rb_tarjeta'):
                self.rb_tarjeta.setChecked(True)

            # 1) Cuotas
            cuotas, ok = QInputDialog.getInt(
                self, "Tarjeta", "Cuotas (1–12):", 1, 1, 12, 1
            )
            if not ok:
                return False

            if hasattr(self, 'spin_cuotas'):
                self.spin_cuotas.setEnabled(True)
                self.spin_cuotas.setValue(int(cuotas))

            # 2) Interés
            interes, ok2 = QInputDialog.getDouble(
                self, "Tarjeta", "Interés (%)", 0.0, -100.0, 1000.0, 2
            )
            if not ok2:
                return False

            if hasattr(self, "_aplicar_interes_a_cesta"):
                self._aplicar_interes_a_cesta(float(interes))

            # Refrescos de UI
            if hasattr(self, '_update_cuota_label'):
                self._update_cuota_label(int(cuotas))
            if hasattr(self, '_refrescar_interes_btn'):
                self._refrescar_interes_btn()

            return True
        except Exception:
            return False


    def _imprimir_ticket_via_shortcut(self):
        """Si hay una fila seleccionada en 'Ventas del día', reimprime esa.
        Si no, intenta la última venta realizada."""
        try:
            # 1) Si hay selección en la tabla de ventas del día, usa esa
            tbl = getattr(self, 'table_ventas_dia', None)
            if tbl:
                itms = tbl.selectedItems()
                if itms:
                    row = itms[0].row()
                    nro_txt = tbl.item(row, 0).text().strip()  # col 0 = Nº Ticket (o id)
                    try:
                        vid = int(nro_txt)
                        self._last_venta_id = vid
                        self.imprimir_ticket(vid)
                        return
                    except Exception:
                        pass
            # 2) Si no, usa la última venta conocida
            vid = getattr(self, "_last_venta_id", None)
            if vid:
                self.imprimir_ticket(vid)
                return
            # 3) Fallback: mensaje
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.information(self, "Imprimir", "Seleccioná una venta en la lista o realizá una nueva.")
        except Exception:
            pass 
        
        
# ===== Productos: popups rápidos para atajos A / E =====
    def _productos_agregar_popup(self):
        """A: abrir popup con Código / Nombre / Precio / Categoría y guardar."""
        try:
            from app.gui.dialogs import QuickAddProductoDialog
            from app.models import Producto
            dlg = QuickAddProductoDialog(self)
            if dlg.exec_() != QDialog.Accepted:
                return
            datos = dlg.datos()
            if not datos:
                return
            codigo, nombre, precio, categoria = datos
            # Upsert por código
            prod = self.session.query(Producto).filter_by(codigo_barra=codigo).first()
            if prod:
                prod.nombre = nombre
                prod.precio = precio
                prod.categoria = categoria
            else:
                self.session.add(Producto(codigo_barra=codigo, nombre=nombre, precio=precio, categoria=categoria))
                # registrar en history para deshacer
                self.history.append(('add', {
                    'codigo_barra': codigo, 'nombre': nombre, 'precio': precio, 'categoria': categoria
                }))
            self.session.commit()
            # refrescar UI y completer
            try: self.refrescar_productos()
            except Exception: pass
            try: self.refrescar_completer()
            except Exception: pass
            self.statusBar().showMessage("Producto guardado.", 2500)
        except Exception as e:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Agregar producto", f"No se pudo guardar:\n{e}")

    def _productos_editar_por_codigo(self):
        """E: pedir código → si existe, abrir popup con Nombre/Precio/Categoría."""
        try:
            from PyQt5.QtWidgets import QInputDialog, QMessageBox
            from app.gui.dialogs import QuickEditProductoDialog
            from app.models import Producto

            cb, ok = QInputDialog.getText(self, "Editar producto", "Código de barras:")
            if not ok or not cb:
                return
            codigo = str(cb).strip()
            prod = self.session.query(Producto).filter_by(codigo_barra=codigo).first()
            if not prod:
                QMessageBox.information(self, "Editar", "Producto no encontrado.")
                return

            dlg = QuickEditProductoDialog(prod, self)
            if dlg.exec_() != QDialog.Accepted:
                return
            nom, precio, cate = dlg.datos()
            prod.nombre = nom
            prod.precio = precio
            prod.categoria = cate
            self.session.commit()
            # refrescar UI y completer
            try: self.refrescar_productos()
            except Exception: pass
            try: self.refrescar_completer()
            except Exception: pass
            self.statusBar().showMessage("Producto actualizado.", 2500)
        except Exception as e:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Editar producto", f"No se pudo actualizar:\n{e}")

            
    def _show_about(self):
        """Muestra información sobre la aplicación."""
        from PyQt5.QtWidgets import QMessageBox
        from version import __version__, __app_name__
        
        QMessageBox.about(
            self,
            f"Acerca de {__app_name__}",
            f"<h2>{__app_name__}</h2>"
            f"<p><b>Versión:</b> {__version__}</p>"
            f"<p>Sistema de gestión de compraventas</p>"
            f"<p>Copyright © 2025</p>"
        )

#GUARDAR PESTAÑA
    def _gate_tabs_admin(self, idx: int):
        """Bloquea el acceso a pestañas admin si no estás validado; vuelve a la pestaña previa."""
        if getattr(self, "es_admin", False):
            self._last_tab_index = idx
            return
        try:
            admin_tabs = {getattr(self, "idx_historial", -1),
                        getattr(self, "idx_config", -1),
                        getattr(self, "idx_usuarios", -1)}
            if idx in admin_tabs:
                if not self._ensure_admin("abrir esta pestaña"):
                    # revertir selección
                    self.tabs.blockSignals(True)
                    self.tabs.setCurrentIndex(self._last_tab_index)
                    self.tabs.blockSignals(False)
                    return
            # si pasó el guard o es pestaña libre, actualiza el último índice
            self._last_tab_index = idx
        except Exception:
            # En caso de error inesperado, no romper la navegación
            self._last_tab_index = idx
            
            
    def _shortcut_finalizar_venta_dialog(self):
        """
        Atajo de 'finalizar venta' con popup previo:
        - Lee las letras configuradas para ventas.efectivo / ventas.tarjeta.
        - Pregunta Efectivo / Tarjeta.
        - Ajusta el modo de pago (y cuotas/interés si es tarjeta).
        - Luego llama a finalizar_venta() como siempre.

        NUEVO: Si ya se usó el diálogo unificado de tarjeta (_datos_tarjeta existe),
        salta directamente a finalizar_venta() sin preguntar nada más.
        """
        try:
            # NUEVO: Si ya se configuró con el diálogo unificado, finalizar directamente
            if hasattr(self, '_datos_tarjeta') and self._datos_tarjeta:
                # Ya está todo configurado, solo llamar finalizar_venta
                self.finalizar_venta()
                return

            from PyQt5.QtWidgets import (
                QDialog, QVBoxLayout, QHBoxLayout,
                QLabel, QPushButton
            )
            from PyQt5.QtCore import Qt
            from app.config import load as load_config

            # 1) Leer teclas desde la configuración
            cfg = load_config()
            sc = (cfg.get("shortcuts") or {})
            section_map = sc.get("section") or {}
            ventas_map = section_map.get("ventas", {}) or {}

            key_ef = (ventas_map.get("efectivo") or "E").strip().upper()
            key_tj = (ventas_map.get("tarjeta") or "T").strip().upper()
            if not key_ef:
                key_ef = "E"
            if not key_tj:
                key_tj = "T"

            # 2) Si no hay productos en la cesta, llamar flujo viejo
            if not hasattr(self, "table_cesta") or self.table_cesta.rowCount() == 0:
                self.finalizar_venta()
                return

            # 3) Construir diálogo
            dlg = QDialog(self)
            dlg.setWindowTitle("Forma de pago")
            layout = QVBoxLayout(dlg)

            lbl = QLabel("Elegí cómo se cobra la venta:")
            layout.addWidget(lbl)

            fila_botones = QHBoxLayout()
            btn_ef = QPushButton(f"({key_ef}) Efectivo")
            btn_tj = QPushButton(f"({key_tj}) Tarjeta")
            for b in (btn_ef, btn_tj):
                b.setMinimumWidth(140)
                fila_botones.addWidget(b)
            layout.addLayout(fila_botones)

            elegido = {"modo": None}

            def elegir_ef():
                elegido["modo"] = "efectivo"
                dlg.accept()

            def elegir_tj():
                elegido["modo"] = "tarjeta"
                dlg.accept()

            btn_ef.clicked.connect(elegir_ef)
            btn_tj.clicked.connect(elegir_tj)

            # 4) Tecla rápida dentro del popup: usa las letras configuradas (p.ej. X / Y)
            def _on_key(ev):
                ch = ev.text().upper()
                if ch == key_ef:
                    elegir_ef()
                elif ch == key_tj:
                    elegir_tj()
                elif ev.key() == Qt.Key_Escape:
                    dlg.reject()
                else:
                    QDialog.keyPressEvent(dlg, ev)

            dlg.keyPressEvent = _on_key

            if dlg.exec_() != QDialog.Accepted or elegido["modo"] is None:
                return  # cancelado

            # 5) Sincronizar con la UI antes de cerrar la venta
            if elegido["modo"] == "efectivo":
                self._shortcut_set_efectivo()
            else:
                # NUEVO: Verificar si ya se configuró con el diálogo unificado
                if hasattr(self, '_datos_tarjeta') and self._datos_tarjeta:
                    # Ya está configurado, solo marcar el radio button
                    if hasattr(self, 'rb_tarjeta'):
                        self.rb_tarjeta.setChecked(True)
                else:
                    # No está configurado, abrir el diálogo unificado
                    # IMPORTANTE: Abrir el diálogo ANTES de marcar el radio button
                    # para evitar que el evento toggled abra el diálogo otra vez
                    if hasattr(self, '_abrir_dialogo_tarjeta'):
                        self._abrir_dialogo_tarjeta()
                        # Si el usuario canceló el diálogo, no continuar
                        if not (hasattr(self, '_datos_tarjeta') and self._datos_tarjeta):
                            return
                        # Ahora sí marcar el radio button (ya está configurado)
                        if hasattr(self, 'rb_tarjeta'):
                            self.rb_tarjeta.setChecked(True)
                    else:
                        # Fallback a popups viejos solo si no existe el método nuevo
                        if hasattr(self, 'rb_tarjeta'):
                            self.rb_tarjeta.setChecked(True)
                        ok_tarjeta = self._shortcut_set_tarjeta_dialog()
                        if not ok_tarjeta:
                            return  # canceló cuotas/interés

            # 6) Ahora sí, flujo normal de cierre
            self.finalizar_venta()

        except Exception:
            # Si algo raro pasa, no bloqueamos la venta: usamos el flujo viejo
            try:
                self.finalizar_venta()
            except Exception:
                pass

