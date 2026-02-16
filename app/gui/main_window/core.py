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
from app.firebase_sync import FirebaseSyncManager



#---------------------------------------------------------------------------------------------------------------------

class MainWindow(ProductosMixin, VentasMixin, VentasTicketMixin, VentasFinalizacionMixin, ProveedoresMixin, UsuariosMixin, ConfiguracionMixin, TicketTemplatesMixin, ReportesMixin, BackupsMixin, SyncNotificationsMixin, StatsMixin, QMainWindow):

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

        # Sistema de sincronizacion via Firebase
        self._firebase_sync = None
        self._sync_timer = QTimer(self)
        self._sync_timer.timeout.connect(lambda: self._ejecutar_sincronizacion(manual=False))
        self._last_sync_time = None
        self._sync_log_entries = []
        # Iniciar sync despues de que la UI cargue (no en __init__ para evitar problemas)
        QTimer.singleShot(2000, self._setup_sync_scheduler)
        self._crear_boton_sync_manual()

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

                # --- Ventas: atajos de cesta ---
                "ventas.sumar":               self._shortcut_sumar_cesta,      # + incrementa cantidad
                "ventas.restar":              self._shortcut_restar_cesta,     # - decrementa cantidad
                "ventas.editar_cantidad":     self._shortcut_editar_cantidad_cesta,  # C editar cantidad
                "ventas.descuento_item":      self._shortcut_descuento_item_cesta,   # X descuento ítem
                "ventas.vaciar_cesta":        self._vaciar_cesta,              # Z vaciar cesta
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

