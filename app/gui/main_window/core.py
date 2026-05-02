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
from app.gui.main_window.ventas_ticket_mixin import VentasTicketMixin
from app.gui.main_window.ventas_finalizacion_mixin import VentasFinalizacionMixin
from app.gui.main_window.filters  import LimitedFilterProxy
from app.gui.main_window.proveedores_mixin import ProveedoresMixin
from app.gui.main_window.compradores_mixin import CompradoresMixin
from app.gui.main_window.usuarios_mixin import UsuariosMixin
from app.gui.main_window.configuracion_mixin import ConfiguracionMixin
from app.gui.main_window.ticket_templates_mixin import TicketTemplatesMixin
from app.gui.main_window.reportes_mixin import ReportesMixin
from app.gui.main_window.backups_mixin import BackupsMixin
from app.gui.main_window.sync_mixin import SyncNotificationsMixin
from app.gui.main_window.stats_mixin import StatsMixin
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
from app.repository import prod_repo, VentaRepo, UsuarioRepo, PagoProveedorRepo
from app.gui.qt_helpers import freeze_table
from pathlib import Path
from PyQt5.QtMultimedia import QSoundEffect
from app.gui.proveedores import ProveedorService  # NUEVO
from app.gui.compradores import CompradorService
from datetime import date, datetime,timedelta
from app.gui.historialventas import HistorialVentasWidget
# Importar helpers y diálogos desde el paquete nuevo
from app.gui.common import BASE_ICONS_PATH, MIN_BTN_HEIGHT, ICON_SIZE, icon, _safe_viewport, _mouse_release_event_type, _checked_states, FullCellCheckFilter
from app.gui.dialogs import DevolucionDialog, ProductosDialog
from app.firebase_sync import FirebaseSyncManager



#---------------------------------------------------------------------------------------------------------------------
# ╔═══════════════════════════════════════════════════════════════════════════════════════════════════════════════════╗
# ║                          MainWindow — DEPENDENCY MATRIX (mixins ↔ atributos compartidos)                          ║
# ╠═══════════════════════════════════════════════════════════════════════════════════════════════════════════════════╣
# ║ MainWindow hereda de 13 mixins. Cada mixin asume que ciertos atributos en `self` ya existen (creados en           ║
# ║ core.__init__ o por otro mixin antes en MRO). Esta tabla documenta el contrato. Si agregás un mixin o cambiás un  ║
# ║ atributo, actualizá esta tabla — previene roturas silenciosas.                                                    ║
# ║                                                                                                                   ║
# ║   ATRIBUTO                  CREADO EN                CONSUMIDORES                          NOTAS                  ║
# ║   ─────────────────────────────────────────────────────────────────────────────────────────────────────────────   ║
# ║   self.session              core.__init__            TODOS los mixins (BD)                 Crash si None          ║
# ║   self.sucursal             core.__init__            sync, stats, config, ventas           Default obligatorio    ║
# ║   self.username             core.__init__ (param)    audit logs, ventas                    "" si vacío            ║
# ║   self.es_admin             core.__init__ (param)    config, audit, eliminaciones masivas  bool (default False)   ║
# ║   self.prod_repo            core.__init__            productos, stats, ventas              prod_repo(session)     ║
# ║   self.venta_repo           core.__init__            ventas_finalizacion, stats, historial VentaRepo(session)     ║
# ║   self.pago_prov_repo       core.__init__            historial, reportes (IVA compras)     PagoProveedorRepo      ║
# ║   self.comprador_service    core.__init__            ventas_finalizacion, compradores      CompradorService       ║
# ║   self.proveedor_service    core.__init__            proveedores, ventas_finalizacion      ProveedorService       ║
# ║   self.tabs                 core.__init__            config, sync, _goto_tab               QTabWidget central     ║
# ║   self.historial            core.__init__            reportes (_crear_excel)               HistorialVentasWidget  ║
# ║   self._interes_pct         core.__init__            ventas_finalizacion                   default 0.0            ║
# ║   self._descuento_pct       core.__init__            ventas_finalizacion                   default 0.0            ║
# ║   self._total_actual        ventas (actualizar_total)ventas_finalizacion                   actualizado por venta  ║
# ║   self._cesta_updating      ventas (flag temporal)   core._on_cesta_item_changed (handler) v6.5.0: anti-RuntimeErr ║
# ║   self._datos_tarjeta       ventas (al pagar)        ventas_finalizacion, ticket           cuotas+interes payload ║
# ║   self._completer           core.__init__ (None)     ventas (busqueda producto)            QCompleter             ║
# ║   self._comp_proxy          core.__init__            idem, filtra autocomplete             LimitedFilterProxy     ║
# ║   self._rep_sched           reportes (al armar)      reportes._tick_reports_scheduler      v6.5.2: dict 3 freqs   ║
# ║   self._reports_timer       reportes._init           reportes._tick                        QTimer 60s             ║
# ║   self._sync_manager        sync_mixin._setup        sync_mixin                            FirebaseSyncManager    ║
# ║   self._stop_backup_evt     backups_mixin._init      backups_mixin (thread)                threading.Event        ║
# ║   self._product_change_log  productos (en sesion)    productos (mostrar cambios recientes) lista de cambios       ║
# ║                                                                                                                   ║
# ║ MIXINS Y SUS PESTAÑAS PRIMARIAS:                                                                                  ║
# ║   ProductosMixin              tab_productos()                                                                     ║
# ║   VentasMixin                 tab_ventas()  (+ helpers actualizar_total, _descuento_en_fila, etc)                 ║
# ║   VentasTicketMixin           render e impresion de ticket post-venta                                             ║
# ║   VentasFinalizacionMixin     finalizar_venta(), llamadas a AFIP, persistencia                                    ║
# ║   ProveedoresMixin            tab_proveedores()                                                                   ║
# ║   CompradoresMixin            tab_compradores() ("Clientes")                                                      ║
# ║   UsuariosMixin               tab_usuarios()                                                                      ║
# ║   ConfiguracionMixin          tab_configuracion() — split en submixins por archivo (ver configuracion/)           ║
# ║   TicketTemplatesMixin        tab de plantillas de ticket (10 slots)                                              ║
# ║   ReportesMixin               scheduler de envio automatico (DAILY/WEEKLY/MONTHLY paralelos, v6.5.2)              ║
# ║   BackupsMixin                automaticos + manual + restore                                                      ║
# ║   SyncNotificationsMixin      bandeja, sync Firebase, _sync_push, _beep_ok                                        ║
# ║   StatsMixin                  KPIs, graficos en Historial                                                         ║
# ║                                                                                                                   ║
# ║ INVARIANTES DE TABLAS PyQt5:                                                                                      ║
# ║   - NUNCA llamar setItem(r, c, ...) desde un handler de itemChanged. Destruye el QTableWidgetItem original y      ║
# ║     deja referencias Python wrapping objetos C++ muertos -> RuntimeError. Usar .setText() sobre el item existente ║
# ║     o usar QSignalBlocker + flag (_cesta_updating) para updates programaticos. Ver bug v6.5.0 para detalles.      ║
# ║                                                                                                                   ║
# ║ INVARIANTES DE FIREBASE SYNC:                                                                                     ║
# ║   - Cada cambio empujado a Firebase lleva sucursal_origen. Al hacer pull, descartar lo que origen == sucursal     ║
# ║     local (anti-eco). Ver firebase_sync.py.                                                                       ║
# ║                                                                                                                   ║
# ║ Si modificás MainWindow, mantené esta tabla actualizada.                                                          ║
# ╚═══════════════════════════════════════════════════════════════════════════════════════════════════════════════════╝

class MainWindow(ProductosMixin, VentasMixin, VentasTicketMixin, VentasFinalizacionMixin, ProveedoresMixin, CompradoresMixin, UsuariosMixin, ConfiguracionMixin, TicketTemplatesMixin, ReportesMixin, BackupsMixin, SyncNotificationsMixin, StatsMixin, QMainWindow):

    def __init__(self, es_admin=True, username=""):
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

        sucursales = list(self.direcciones.keys())
        if _pref in sucursales:
            self.sucursal = _pref
        else:
            suc, ok = QInputDialog.getItem(self, 'Sucursal', 'Seleccione sucursal:', sucursales, 0, False)
            if not ok:
                sys.exit(0)
            self.sucursal = suc

        # Sesión y repositorios
        self.session    = SessionLocal()
        self.proveedores = ProveedorService(self.session)  # NUEVO
        self.compradores_svc = CompradorService(self.session)
        self.prod_repo = prod_repo(self.session, Producto)
        
        self.venta_repo = VentaRepo(self.session)
        self.pago_prov_repo = PagoProveedorRepo(self.session)
        self.user_repo  = UsuarioRepo(self.session)
        # Admin?
        self.es_admin = es_admin
        self.current_username = username

        # v6.6.0: Audit logger - capturar clicks/dialogos/etc en TODA la app.
        # Los context providers son closures que leen los atributos vivos
        # (asi reflejan cambios de sucursal/usuario en runtime sin rewire).
        try:
            from app.audit_logger import install_audit_filter, get_audit_logger
            # v6.6.3: getattr defensivo para que el lambda nunca raise AttributeError
            # si el atributo aun no esta seteado en algun timing inesperado
            install_audit_filter(
                QApplication.instance(),
                username_provider=lambda: getattr(self, "current_username", None) or "anon",
                sucursal_provider=lambda: getattr(self, "sucursal", None) or "?",
            )
            get_audit_logger().log_action("LOGIN", f"user={self.current_username} sucursal={self.sucursal}")
        except Exception as _audit_err:
            logger.warning("[audit] no se pudo instalar audit filter: %s", _audit_err)
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

        tabs.addTab(self.tab_compradores(), icon('clientes.svg'), 'Clientes')
        tabs.setTabToolTip(2, 'Clientes')

        tabs.addTab(self.tab_ventas(), icon('ventas.svg'), 'Ventas')
        tabs.setTabToolTip(3, 'Ventas')

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

        # Botón cambio de usuario en esquina superior derecha
        from PyQt5.QtWidgets import QToolButton
        self._btn_switch_user = QToolButton()
        self._btn_switch_user.setIcon(icon('useradmin.svg'))
        self._btn_switch_user.setIconSize(QSize(24, 24))
        self._btn_switch_user.setToolTip("Cambiar de usuario")
        self._btn_switch_user.setStyleSheet(
            "QToolButton { border: none; padding: 4px; }"
            "QToolButton:hover { background-color: rgba(0,0,0,30); border-radius: 4px; }"
        )
        self._btn_switch_user.clicked.connect(self._switch_user)
        tabs.setCornerWidget(self._btn_switch_user, Qt.TopRightCorner)

        self.setCentralWidget(tabs)

        # v6.6.1: instrumentar QTabWidgets para que el audit log capture cambios de pestaña.
        # Debe llamarse DESPUES de que todas las tabs esten creadas (incluyendo sub-tabs
        # de configuracion que se construyen en tab_configuracion()).
        try:
            from app.audit_logger import wire_tab_widgets as _wire_tabs
            _wire_tabs(self)
        except Exception as _wt_err:
            logger.warning("[audit] wire_tab_widgets fallo: %s", _wt_err)

        # Barra de estado
        self._setup_status_bar()

        # Sistema de sincronizacion via Firebase
        self._firebase_sync = None
        self._sync_running = False
        self._sync_thread = None          # referencia al hilo de sync activo
        self._sync_start_time = None      # timestamp de inicio de la sync actual
        self._sync_timer = QTimer(self)
        self._sync_timer.timeout.connect(lambda: self._ejecutar_sincronizacion(manual=False))
        self._last_sync_time = None
        self._sync_log_entries = []
        # Iniciar sync despues de que la UI cargue (no en __init__ para evitar problemas)
        QTimer.singleShot(2000, self._setup_sync_scheduler)
        self._crear_boton_sync_manual()

        # Auto-refresh de Productos e Historial (intervalo configurable en segundos)
        self._auto_refresh_timer = QTimer(self)
        self._auto_refresh_timer.timeout.connect(self._auto_refresh_tabs)
        cfg_refresh = load_config()
        _refresh_sec = cfg_refresh.get("refresh_seconds", 300)
        self._auto_refresh_timer.start(_refresh_sec * 1000)
        self._crear_boton_refresh()
        self._historial_loaded = False

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
        # Dialogo de actualizacion movido a main.py (pre-login)
    
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
                "productos.consultar_precio": self._consultar_precio_popup,

                # --- Ventas (letras) ---
                "ventas.finalizar":           self._shortcut_finalizar_venta_dialog,
                "ventas.consultar_precio":    self._consultar_precio_popup,
                "ventas.devolucion":          self._on_devolucion,
                "ventas.whatsapp":            self.enviar_ticket_whatsapp,     # usa la última venta si existe
                "ventas.imprimir":            self._imprimir_ticket_via_shortcut, # reimprime ticket seleccionado/último
                "ventas.guardar_borrador":    self._guardar_borrador,          # guarda la cesta como borrador
                "ventas.abrir_borradores":    self._abrir_borradores,          # abre diálogo de borradores

                # --- Ventas: atajos de cesta ---
                "ventas.sumar":               self._shortcut_sumar_cesta,      # + incrementa cantidad
                "ventas.restar":              self._shortcut_restar_cesta,     # - decrementa cantidad
                "ventas.editar_cantidad":     self._shortcut_editar_cantidad_cesta,  # C editar cantidad
                "ventas.descuento_item":      self._shortcut_descuento_item_cesta,   # X descuento ítem
                "ventas.vaciar_cesta":        self._vaciar_cesta,              # Z vaciar cesta

                # --- Productos: atajo Ñ (editar precio del producto seleccionado / buscado) ---
                "productos.editar_precio_buscado": self._productos_editar_precio_buscado,  # Ñ
            }
            self.shortcut_manager = ShortcutManager(self, callbacks=cb)
            logger.info("[SHORTCUTS] Sistema de atajos inicializado")
        except Exception as e:
            self.shortcut_manager = None
            logger.error(f"[SHORTCUTS] Error inicializando atajos: {e}")
    
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
        # v6.8.0: detener Supabase Realtime worker si esta activo
        try:
            sync = getattr(self, "_firebase_sync", None)
            if sync is not None and hasattr(sync, "stop_realtime"):
                sync.stop_realtime()
        except Exception:
            pass

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
        """Edición masiva: precio, nombre o categoría de los productos seleccionados."""
        import datetime as _dt

        # Recoger productos seleccionados (de la tabla visible + set persistente)
        ids_visibles = set()
        for r in range(self.table_productos.rowCount()):
            id_item = self.table_productos.item(r, 1)
            if id_item and self._is_row_checked(r, self.table_productos):
                ids_visibles.add(int(id_item.text()))

        all_ids = ids_visibles | getattr(self, '_selected_product_ids', set())
        if not all_ids:
            QMessageBox.information(self, 'Edición masiva', 'No hay productos seleccionados.')
            return

        # Elegir qué editar
        campo, ok = QInputDialog.getItem(
            self, 'Edición masiva',
            f'{len(all_ids)} producto(s) seleccionados.\n¿Qué desea editar?',
            ['Precio', 'Nombre', 'Categoría'], 0, False)
        if not ok:
            return

        productos = [self.session.query(Producto).get(pid) for pid in all_ids]
        productos = [p for p in productos if p is not None]
        if not productos:
            return

        # Snapshot ANTES de cambios (para el log)
        snapshots = {}
        for prod in productos:
            snapshots[prod.id] = {
                'codigo_barra': prod.codigo_barra,
                'nombre': prod.nombre,
                'precio': prod.precio,
                'categoria': prod.categoria or '',
                'telefono': prod.telefono or '',
                'numero_cuenta': prod.numero_cuenta or '',
                'cbu': prod.cbu or '',
            }

        cambios = 0
        modo_desc = ''  # Descripción legible de la operación

        if campo == 'Precio':
            modos = ['Valor final', 'Porcentaje', 'Monto fijo']
            modo, ok = QInputDialog.getItem(self, 'Modo de edición', 'Seleccione modo:', modos, 0, False)
            if not ok:
                return
            if modo == 'Porcentaje':
                val, ok = QInputDialog.getDouble(self, 'Porcentaje', 'Introduce % (ej: 10 o -5):', decimals=2)
                modo_desc = f'Porcentaje ({"+"+str(val) if val >= 0 else str(val)}%)'
            elif modo == 'Valor final':
                val, ok = QInputDialog.getDouble(self, 'Valor final', 'Nuevo precio para todos:', 0, 0, 999999, 2)
                modo_desc = f'Valor final ({val:.2f})'
            else:
                val, ok = QInputDialog.getDouble(self, 'Monto fijo', 'Introduce importe (+/-):', decimals=2)
                modo_desc = f'Monto fijo ({"+"+str(val) if val >= 0 else str(val)})'
            if not ok:
                return

            for prod in productos:
                if modo == 'Porcentaje':
                    prod.precio *= (1 + val / 100.0)
                elif modo == 'Valor final':
                    prod.precio = val
                else:
                    prod.precio += val
                prod.precio = max(prod.precio, 0.0)
                cambios += 1

        elif campo == 'Nombre':
            modos_nombre = ['Reemplazar texto', 'Agregar prefijo', 'Agregar sufijo', 'Quitar texto']
            modo, ok = QInputDialog.getItem(self, 'Editar nombre', 'Seleccione operación:', modos_nombre, 0, False)
            if not ok:
                return

            if modo == 'Reemplazar texto':
                buscar, ok = QInputDialog.getText(self, 'Buscar', 'Texto a buscar en el nombre:')
                if not ok or not buscar:
                    return
                reemplazo, ok = QInputDialog.getText(self, 'Reemplazar', f'Reemplazar "{buscar}" por:')
                if not ok:
                    return
                modo_desc = f"Reemplazar '{buscar}' → '{reemplazo}'"
                for prod in productos:
                    nuevo = prod.nombre.replace(buscar.upper(), reemplazo.upper())
                    if nuevo != prod.nombre:
                        prod.nombre = nuevo
                        cambios += 1

            elif modo == 'Agregar prefijo':
                prefijo, ok = QInputDialog.getText(self, 'Prefijo', 'Texto a agregar al inicio:')
                if not ok or not prefijo:
                    return
                modo_desc = f"Prefijo '{prefijo.upper()}'"
                for prod in productos:
                    prod.nombre = prefijo.upper() + ' ' + prod.nombre
                    cambios += 1

            elif modo == 'Agregar sufijo':
                sufijo, ok = QInputDialog.getText(self, 'Sufijo', 'Texto a agregar al final:')
                if not ok or not sufijo:
                    return
                modo_desc = f"Sufijo '{sufijo.upper()}'"
                for prod in productos:
                    prod.nombre = prod.nombre + ' ' + sufijo.upper()
                    cambios += 1

            elif modo == 'Quitar texto':
                quitar, ok = QInputDialog.getText(self, 'Quitar', 'Texto a eliminar del nombre:')
                if not ok or not quitar:
                    return
                modo_desc = f"Quitar '{quitar.upper()}'"
                for prod in productos:
                    nuevo = prod.nombre.replace(quitar.upper(), '').strip()
                    if nuevo != prod.nombre:
                        prod.nombre = nuevo
                        cambios += 1

        elif campo == 'Categoría':
            cat, ok = QInputDialog.getText(self, 'Categoría', 'Nueva categoría para todos los seleccionados:')
            if not ok:
                return
            cat = cat.strip().upper() or None
            modo_desc = f"→ {cat or '(vacía)'}"
            for prod in productos:
                prod.categoria = cat
                cambios += 1

        if cambios > 0:
            self.session.commit()

            # Construir log de cambios (comparar snapshot antes vs después)
            log_entry = {
                'fecha': _dt.datetime.now(),
                'operacion': f'{campo} - {modo_desc}',
                'cambios': []
            }
            for prod in productos:
                snap = snapshots.get(prod.id, {})
                for field in ('nombre', 'precio', 'categoria', 'telefono', 'numero_cuenta', 'cbu'):
                    if field == 'precio':
                        old_val = f"{float(snap.get('precio', 0)):.2f}"
                        new_val = f"{prod.precio:.2f}"
                    else:
                        old_val = str(snap.get(field, '') or '')
                        new_val = str(getattr(prod, field, '') or '')
                    if old_val != new_val:
                        log_entry['cambios'].append({
                            'producto_id': prod.id,
                            'codigo_barra': prod.codigo_barra,
                            'nombre': snap.get('nombre', prod.nombre),
                            'campo': field,
                            'anterior': old_val,
                            'nuevo': new_val,
                        })
            if log_entry['cambios']:
                if not hasattr(self, '_product_change_log'):
                    self._product_change_log = []
                self._product_change_log.append(log_entry)

            # Sync: publicar productos editados
            for prod in productos:
                self._sync_push("producto", prod)
            self._selected_product_ids.clear()
            self.refrescar_productos(preserve_selection=False)
            self.refrescar_completer()

            # Confirmación con botón "Ver cambios"
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Information)
            msg.setWindowTitle('Completado')
            msg.setText(f'{cambios} producto(s) actualizados.')
            btn_ver = msg.addButton('Ver cambios', QMessageBox.ActionRole)
            btn_ok = msg.addButton('Aceptar', QMessageBox.AcceptRole)
            msg.setDefaultButton(btn_ok)
            msg.exec_()
            if msg.clickedButton() == btn_ver:
                self._abrir_ultimos_cambios()
        else:
            QMessageBox.information(self, 'Sin cambios', 'No se realizaron cambios.')
    
    
    # ---------------- Ventas ----------------
    
    
    
    def _on_cesta_item_changed(self, item):
        # Ignorar cambios programáticos (descuento, actualizar_total, etc.)
        if getattr(self, "_cesta_updating", False):
            return
        # Solo columnas editables: 2=Cantidad, 3=Precio Unit.
        col = item.column()
        if col not in (2, 3):
            return
        r = item.row()

        # Si el texto del Precio Unit tiene el formato de descuento "base → eff",
        # es un update programático: no tocar.
        pu_item = self.table_cesta.item(r, 3)
        if pu_item is not None and "→" in (pu_item.text() or ""):
            return

        self._cesta_updating = True
        try:
            # Normalizar cantidad (sólo con setText; nunca reemplazar el item)
            cant_item = self.table_cesta.item(r, 2)
            try:
                cant = float((cant_item.text() if cant_item else "1").strip())
            except Exception:
                cant = 1.0
                if cant_item is not None:
                    cant_item.setText("1")

            # Normalizar P. Unit.
            try:
                pu = float(str(pu_item.text() if pu_item else "0").replace("$", "").strip())
            except Exception:
                pu = 0.0
                if pu_item is not None:
                    pu_item.setText("0.00")

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
        finally:
            self._cesta_updating = False

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

        # Sync: publicar venta modificada
        self._sync_push("venta_mod", venta)

    # (Historial/estadísticas methods moved to stats_mixin.py)

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
        # Limite configurable desde app_config.json -> ui.autocomplete_limit_productos
        try:
            from app.config import load as _load_cfg
            _ac_limit = int((_load_cfg().get("ui") or {}).get("autocomplete_limit_productos", 200))
        except Exception:
            _ac_limit = 200
        self._comp_proxy = LimitedFilterProxy(limit=_ac_limit, parent=self)
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

        # Desconectar highlighted para que navegar con flechas NO
        # escriba automáticamente en el QLineEdit
        try:
            self._comp.highlighted[str].disconnect()
        except (TypeError, RuntimeError):
            pass

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
            # --- Interceptar teclas en el POPUP del completer de ventas ---
            # Qt envía las flechas directamente al popup (QListView), no al
            # QLineEdit, por eso hay que filtrar en el popup mismo.
            ventas_input = getattr(self, 'input_venta_buscar', None)
            comp = getattr(self, '_completer', None) or getattr(self, '_comp', None)

            if comp is not None and ventas_input is not None:
                popup = comp.popup()
                if popup is not None and obj is popup:
                    if event.type() == QEvent.KeyPress:
                        key = event.key()

                        # Flechas ↑↓: mover selección SIN que Qt cambie el texto
                        if key in (Qt.Key_Down, Qt.Key_Up):
                            model = popup.model()
                            if model and model.rowCount() > 0:
                                idx = popup.currentIndex()
                                row = idx.row() if idx.isValid() else -1
                                if key == Qt.Key_Down:
                                    row = min(row + 1, model.rowCount() - 1)
                                else:
                                    row = max(row - 1, 0)
                                new_idx = model.index(row, 0)
                                ventas_input.blockSignals(True)
                                popup.setCurrentIndex(new_idx)
                                popup.scrollTo(new_idx)
                                ventas_input.blockSignals(False)
                            return True  # Consumir: NO toca el QLineEdit

                        # Enter: aceptar selección, poner código, cerrar popup
                        if key in (Qt.Key_Return, Qt.Key_Enter):
                            idx = popup.currentIndex()
                            if idx.isValid():
                                text = idx.data()
                                code = str(text).split(" - ")[0].strip()
                                # Bloquear temporalmente el textChanged para no
                                # refiltrar el completer al setear el texto
                                ventas_input.blockSignals(True)
                                ventas_input.setText(code)
                                ventas_input.blockSignals(False)
                            popup.hide()
                            return True

                        # Escape: cerrar popup
                        if key == Qt.Key_Escape:
                            popup.hide()
                            return True

                        # Cualquier otra tecla: redirigir al QLineEdit
                        # (para que el usuario pueda seguir escribiendo)
                        if key not in (Qt.Key_Shift, Qt.Key_Control, Qt.Key_Alt, Qt.Key_Meta):
                            popup.hide()
                            ventas_input.setFocus()
                            QApplication.sendEvent(ventas_input, event)
                            return True

            # --- Checkbox en tabla productos (con Shift+Click) ---
            tbl = getattr(self, "table_productos", None)
            if tbl is not None:
                try:
                    vp = tbl.viewport()
                except RuntimeError:
                    return False
                if obj is vp:
                    # Capturar Shift en Press (más confiable que en Release)
                    if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                        idx_p = tbl.indexAt(event.pos())
                        if idx_p.isValid() and idx_p.column() == 0:
                            self._shift_on_press_prod = bool(QApplication.keyboardModifiers() & Qt.ShiftModifier)
                            return False  # dejar que Qt procese el press normalmente

                    if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
                        index = tbl.indexAt(event.pos())
                        if index.isValid() and index.column() == 0:
                            item = tbl.item(index.row(), 0)
                            if item is not None:
                                new_state = Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked
                                shift = getattr(self, '_shift_on_press_prod', False)
                                last = getattr(self, '_last_checked_row_productos', None)
                                if shift and last is not None:
                                    start = min(last, index.row())
                                    end = max(last, index.row())
                                    for r in range(start, end + 1):
                                        it = tbl.item(r, 0)
                                        if it:
                                            it.setCheckState(new_state)
                                else:
                                    item.setCheckState(new_state)
                                self._last_checked_row_productos = index.row()
                            self._shift_on_press_prod = False
                            return True
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
                "clientes": 2,
                "ventas": 3,
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

    def _consultar_precio_popup(self):
        """Abre un popup rápido para consultar precio de un producto por código o nombre."""
        try:
            from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLineEdit,
                                         QLabel, QPushButton, QFrame, QCompleter)
            from PyQt5.QtCore import Qt, QStringListModel, QSortFilterProxyModel

            dlg = QDialog(self)
            dlg.setWindowTitle("Consultar Precio")
            dlg.setMinimumWidth(420)
            dlg.setWindowFlags(dlg.windowFlags() | Qt.WindowStaysOnTopHint)
            lay = QVBoxLayout(dlg)
            lay.setSpacing(12)

            lbl_title = QLabel("<b>Buscar producto por código o nombre</b>")
            lbl_title.setAlignment(Qt.AlignCenter)
            lay.addWidget(lbl_title)

            input_buscar = QLineEdit()
            input_buscar.setPlaceholderText("Código de barras o nombre del producto...")
            input_buscar.setMinimumHeight(36)
            input_buscar.setStyleSheet("font-size: 14px; padding: 4px 8px;")
            lay.addWidget(input_buscar)
            input_buscar.setFocus()

            # Autocomplete usando los mismos datos del completer de ventas
            try:
                from app.repository import prod_repo
                repo = prod_repo(self.session)
                pares = repo.listar_codigos_nombres()
                items_list = [f"{(c or '').strip()} - {(n or '').strip()}" for (c, n) in pares]
                completer = QCompleter(items_list, dlg)
                completer.setCaseSensitivity(Qt.CaseInsensitive)
                completer.setFilterMode(Qt.MatchContains)
                completer.setMaxVisibleItems(10)
                input_buscar.setCompleter(completer)
            except Exception:
                pass

            # Frame de resultado
            frame_result = QFrame()
            frame_result.setFrameShape(QFrame.StyledPanel)
            frame_result.setStyleSheet("QFrame { background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 6px; padding: 12px; }")
            rl = QVBoxLayout(frame_result)
            lbl_nombre = QLabel("")
            lbl_nombre.setStyleSheet("font-size: 16px; font-weight: bold; color: #333;")
            lbl_nombre.setWordWrap(True)
            lbl_codigo = QLabel("")
            lbl_codigo.setStyleSheet("font-size: 13px; color: #666;")
            lbl_precio = QLabel("")
            lbl_precio.setStyleSheet("font-size: 22px; font-weight: bold; color: #28a745;")
            lbl_stock = QLabel("")
            lbl_stock.setStyleSheet("font-size: 13px; color: #666;")
            rl.addWidget(lbl_nombre)
            rl.addWidget(lbl_codigo)
            rl.addWidget(lbl_precio)
            rl.addWidget(lbl_stock)
            frame_result.setVisible(False)
            lay.addWidget(frame_result)

            lbl_no_result = QLabel("")
            lbl_no_result.setAlignment(Qt.AlignCenter)
            lbl_no_result.setStyleSheet("color: #dc3545; font-size: 13px;")
            lay.addWidget(lbl_no_result)

            def _buscar():
                text = input_buscar.text().strip()
                if not text:
                    frame_result.setVisible(False)
                    lbl_no_result.setText("")
                    return

                from app.models import Producto
                # Buscar por código de barras exacto primero
                prod = self.session.query(Producto).filter_by(codigo_barra=text).first()
                if not prod:
                    # Si el texto es "CODIGO - NOMBRE" (del completer), extraer el código
                    if " - " in text:
                        code_part = text.split(" - ")[0].strip()
                        prod = self.session.query(Producto).filter_by(codigo_barra=code_part).first()
                if not prod:
                    # Buscar por nombre parcial
                    prod = self.session.query(Producto).filter(
                        Producto.nombre.ilike(f"%{text}%")
                    ).first()

                if prod:
                    lbl_nombre.setText(f"{prod.nombre or 'Sin nombre'}")
                    lbl_codigo.setText(f"Código: {prod.codigo_barra or 'N/A'}")
                    precio = float(getattr(prod, 'precio_venta', 0) or getattr(prod, 'precio', 0) or 0)
                    lbl_precio.setText(f"Precio: ${precio:,.2f}")
                    stock = getattr(prod, 'stock', None)
                    if stock is not None:
                        lbl_stock.setText(f"Stock: {stock}")
                    else:
                        lbl_stock.setText("")
                    frame_result.setVisible(True)
                    lbl_no_result.setText("")
                else:
                    frame_result.setVisible(False)
                    lbl_no_result.setText("Producto no encontrado.")

            btn_buscar = QPushButton("Buscar")
            btn_buscar.setMinimumHeight(32)
            btn_buscar.clicked.connect(_buscar)
            input_buscar.returnPressed.connect(_buscar)

            btn_row = QHBoxLayout()
            btn_row.addStretch(1)
            btn_row.addWidget(btn_buscar)
            btn_cerrar = QPushButton("Cerrar")
            btn_cerrar.setMinimumHeight(32)
            btn_cerrar.clicked.connect(dlg.close)
            btn_row.addWidget(btn_cerrar)
            lay.addLayout(btn_row)

            lay.addStretch(1)
            input_buscar.setFocus()
            dlg.exec_()
        except Exception as e:
            try:
                from PyQt5.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Error", f"No se pudo abrir consulta de precio:\n{e}")
            except Exception:
                pass

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
                # Snapshot antes de modificar para log por campo
                viejos = {'nombre': prod.nombre, 'precio': prod.precio, 'categoria': prod.categoria}
                prod.nombre = nombre
                prod.precio = precio
                prod.categoria = categoria
                self.session.commit()
                nuevos = {'nombre': nombre, 'precio': precio, 'categoria': categoria}
                try:
                    for k in ('nombre', 'precio', 'categoria'):
                        if str(viejos[k] or '') != str(nuevos[k] or ''):
                            self._log_product_change(prod, k, viejos[k], nuevos[k], 'Popup rapido (A) - Actualizar')
                except Exception:
                    pass
            else:
                nuevo = Producto(codigo_barra=codigo, nombre=nombre, precio=precio, categoria=categoria)
                self.session.add(nuevo)
                # registrar en history para deshacer
                self.history.append(('add', {
                    'codigo_barra': codigo, 'nombre': nombre, 'precio': precio, 'categoria': categoria
                }))
                self.session.commit()
                try:
                    self._log_product_change(
                        nuevo, 'producto', '',
                        f'{codigo} / {nombre} / ${precio}',
                        'Popup rapido (A) - Nuevo producto'
                    )
                except Exception:
                    pass
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

            # Snapshot ANTES del dialogo (para log por campo)
            viejos = {'nombre': prod.nombre, 'precio': prod.precio, 'categoria': prod.categoria}

            dlg = QuickEditProductoDialog(prod, self)
            if dlg.exec_() != QDialog.Accepted:
                return
            nom, precio, cate = dlg.datos()
            prod.nombre = nom
            prod.precio = precio
            prod.categoria = cate
            self.session.commit()

            # Log de cambios por campo
            nuevos = {'nombre': nom, 'precio': precio, 'categoria': cate}
            try:
                for k in ('nombre', 'precio', 'categoria'):
                    if str(viejos[k] or '') != str(nuevos[k] or ''):
                        self._log_product_change(prod, k, viejos[k], nuevos[k], 'Popup rapido (E) - Actualizar')
            except Exception:
                pass

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
    def _auto_refresh_tabs(self):
        """Refresca Productos e Historial automáticamente. NO toca Ventas."""
        try:
            self.refrescar_productos()
        except Exception:
            pass
        try:
            if hasattr(self, 'historial') and hasattr(self.historial, 'recargar_historial'):
                self.historial.recargar_historial()
                self._historial_loaded = True
        except Exception:
            pass

    def _crear_boton_refresh(self):
        """Crea un botón de refresh manual en la status bar."""
        btn = QPushButton("🔃 Refrescar")
        btn.setFlat(True)
        btn.setToolTip("Refrescar Productos e Historial manualmente")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(
            "QPushButton { font-size: 11px; padding: 2px 8px; }"
            "QPushButton:hover { background: #e0e0e0; border-radius: 3px; }"
        )
        btn.clicked.connect(self._auto_refresh_tabs)
        self.statusBar().addPermanentWidget(btn)

    def _switch_user(self):
        """Cambio de usuario en caliente sin reiniciar la aplicación."""
        try:
            # Parar timers mientras se muestra el login
            try:
                self._sync_timer.stop()
            except Exception:
                pass
            try:
                self._auto_refresh_timer.stop()
            except Exception:
                pass

            from app.login import LoginDialog
            dlg = LoginDialog(self.session, self)
            if dlg.exec_() == QDialog.Accepted and getattr(dlg, "user", None):
                # Actualizar datos del usuario
                self.es_admin = getattr(dlg.user, "es_admin", False)
                self.current_username = getattr(dlg.user, "username", "")

                # Resetear cache de admin
                if self.es_admin:
                    self._admin_ok_until = datetime.max
                else:
                    self._admin_ok_until = None

                # Actualizar status bar
                self._refresh_user_status()

                # Si el tab actual requiere admin y ya no es admin, volver a Ventas
                admin_tabs = {getattr(self, "idx_historial", -1),
                              getattr(self, "idx_config", -1),
                              getattr(self, "idx_usuarios", -1)}
                if not self.es_admin and self.tabs.currentIndex() in admin_tabs:
                    self.tabs.setCurrentIndex(2)  # Tab Ventas

                logger.info("Cambio de usuario: %s (%s)",
                            self.current_username,
                            "admin" if self.es_admin else "vendedor")

            # Reiniciar timers siempre
            try:
                self._setup_sync_scheduler()
            except Exception:
                pass
            try:
                self._auto_refresh_timer.start()
            except Exception:
                pass

        except Exception as e:
            logger.error("Error en cambio de usuario: %s", e)
            # Intentar reiniciar timers de todas formas
            try:
                self._sync_timer.start()
            except Exception:
                pass
            try:
                self._auto_refresh_timer.start()
            except Exception:
                pass

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
                # Blur + overlay para ocultar datos mientras se pide login
                # (Qt renderiza el tab ANTES de que podamos verificar permisos)
                blur_effect = None
                overlay = None
                try:
                    target_widget = self.tabs.widget(idx)
                    if target_widget:
                        # 1) Blur fuerte para que no se lea nada
                        from PyQt5.QtWidgets import QGraphicsBlurEffect
                        blur_effect = QGraphicsBlurEffect()
                        blur_effect.setBlurRadius(30)
                        target_widget.setGraphicsEffect(blur_effect)

                        # 2) Overlay oscuro encima como capa extra
                        overlay = QWidget(target_widget)
                        overlay.setStyleSheet(
                            "background-color: rgba(30, 30, 30, 200);"
                        )
                        overlay.setGeometry(target_widget.rect())
                        overlay.raise_()
                        overlay.show()
                        QApplication.processEvents()
                except Exception:
                    pass

                passed = self._ensure_admin("abrir esta pestaña")

                # Quitar blur y overlay siempre
                try:
                    if blur_effect and target_widget:
                        target_widget.setGraphicsEffect(None)
                except Exception:
                    pass
                if overlay:
                    try:
                        overlay.deleteLater()
                    except Exception:
                        pass

                if not passed:
                    # revertir selección
                    self.tabs.blockSignals(True)
                    self.tabs.setCurrentIndex(self._last_tab_index)
                    self.tabs.blockSignals(False)
                    return
            # Lazy loading: cargar historial solo al acceder por primera vez
            if idx == getattr(self, 'idx_historial', -1) and not getattr(self, '_historial_loaded', True):
                self._historial_loaded = True
                try:
                    self.historial.recargar_historial()
                except Exception:
                    pass
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

        Si ya se usó el diálogo unificado de tarjeta (_datos_tarjeta existe),
        salta directamente a finalizar_venta() sin preguntar nada más.
        """
        # Deshabilitar shortcuts de sección para evitar interferencia
        _sm = getattr(self, 'shortcut_manager', None)
        if _sm:
            try:
                _sm._clear_section_shortcuts()
            except Exception:
                pass
        try:
            # Si ya se configuró con el diálogo unificado, finalizar directamente
            if hasattr(self, '_datos_tarjeta') and self._datos_tarjeta:
                self.finalizar_venta(modo_pago="tarjeta")
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
            # Efectivo como botón default (Enter lo activa)
            btn_ef.setDefault(True)
            btn_ef.setAutoDefault(True)
            btn_tj.setAutoDefault(False)
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

            # 4) Tecla rápida dentro del popup
            def _on_key(ev):
                ch = ev.text().upper()
                if ch == key_ef:
                    elegir_ef()
                elif ch == key_tj:
                    elegir_tj()
                elif ev.key() in (Qt.Key_Return, Qt.Key_Enter):
                    # Enter sin selección previa → default a Efectivo
                    elegir_ef()
                elif ev.key() == Qt.Key_Escape:
                    dlg.reject()
                # No hacer fallthrough a QDialog.keyPressEvent

            dlg.keyPressEvent = _on_key

            if dlg.exec_() != QDialog.Accepted or elegido["modo"] is None:
                return  # cancelado

            # 5) Sincronizar con la UI antes de cerrar la venta
            if elegido["modo"] == "efectivo":
                self._shortcut_set_efectivo()
            else:
                # Verificar si ya se configuró con el diálogo unificado
                if hasattr(self, '_datos_tarjeta') and self._datos_tarjeta:
                    # Ya está configurado, solo marcar el radio button
                    if hasattr(self, 'rb_tarjeta'):
                        self.rb_tarjeta.blockSignals(True)
                        self.rb_tarjeta.setChecked(True)
                        self.rb_tarjeta.blockSignals(False)
                else:
                    # Abrir el diálogo ANTES de marcar el radio button
                    # para evitar que el evento toggled abra el diálogo otra vez
                    if hasattr(self, '_abrir_dialogo_tarjeta'):
                        self._abrir_dialogo_tarjeta()
                        # Si el usuario canceló el diálogo, no continuar
                        if not (hasattr(self, '_datos_tarjeta') and self._datos_tarjeta):
                            return
                        # Ahora sí marcar el radio button (ya está configurado)
                        if hasattr(self, 'rb_tarjeta'):
                            self.rb_tarjeta.blockSignals(True)
                            self.rb_tarjeta.setChecked(True)
                            self.rb_tarjeta.blockSignals(False)
                    else:
                        # Fallback a popups viejos solo si no existe el método nuevo
                        if hasattr(self, 'rb_tarjeta'):
                            self.rb_tarjeta.blockSignals(True)
                            self.rb_tarjeta.setChecked(True)
                            self.rb_tarjeta.blockSignals(False)
                        ok_tarjeta = self._shortcut_set_tarjeta_dialog()
                        if not ok_tarjeta:
                            return  # canceló cuotas/interés

            # 6) Ahora sí, flujo normal de cierre
            self.finalizar_venta(modo_pago=elegido["modo"])

        except Exception as e:
            logger.error("[VENTAS] Error en _shortcut_finalizar_venta_dialog: %s", e, exc_info=True)
            from PyQt5.QtWidgets import QMessageBox as _QMB
            _QMB.warning(self, "Error",
                f"Ocurrio un error al finalizar la venta:\n{e}\n\n"
                "Intenta de nuevo o revisa los datos.")
        finally:
            # Siempre re-habilitar shortcuts de sección
            if _sm:
                try:
                    _sm.set_section_by_tabindex(self.tabs.currentIndex())
                except Exception:
                    pass

