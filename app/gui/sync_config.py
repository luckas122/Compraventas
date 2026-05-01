# app/gui/sync_config.py
"""
Pestana de configuracion de Sincronizacion entre sucursales via Firebase.
"""
from PyQt5.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QHBoxLayout, QGridLayout, QGroupBox, QLabel,
    QCheckBox, QLineEdit, QPushButton, QMessageBox, QSpinBox,
    QFrame, QProgressBar, QProgressDialog, QTableWidget, QTableWidgetItem,
    QHeaderView, QSizePolicy,
)
from app.config import load as load_config, save as save_config
from app.gui.qt_helpers import NoScrollComboBox


class _ForcePullWorker(QThread):
    """v6.6.3: worker thread que ejecuta force_pull_all con progress callbacks."""
    progress = pyqtSignal(str, int, int, int)   # (tipo, page, applied, errors)
    finished_ok = pyqtSignal(dict)              # resultado dict
    failed = pyqtSignal(str)                    # mensaje de error

    def __init__(self, sucursal: str, parent=None):
        super().__init__(parent)
        self.sucursal = sucursal
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            from app.firebase_sync import FirebaseSyncManager
            from app.database import SessionLocal
            from sqlalchemy import text as _sa_text
            session = SessionLocal()
            # v6.6.4: PRAGMA synchronous=NORMAL hace los commits ~10x mas rapidos
            # (1 fsync por checkpoint, no por commit). Seguro en WAL mode.
            # busy_timeout reducido a 5s porque ahora retry interno es rapido.
            try:
                session.execute(_sa_text("PRAGMA busy_timeout=5000"))
                session.execute(_sa_text("PRAGMA synchronous=NORMAL"))
                session.execute(_sa_text("PRAGMA journal_mode=WAL"))
                session.commit()
            except Exception:
                pass
            try:
                mgr = FirebaseSyncManager(session, self.sucursal)
                resultado = mgr.force_pull_all(
                    progress_callback=lambda tipo, page, applied, errors: self.progress.emit(tipo, page, applied, errors),
                    cancel_check=lambda: self._cancel,
                )
                self.finished_ok.emit(resultado)
            finally:
                session.close()
        except Exception as e:
            self.failed.emit(str(e))


class SyncConfigPanel(QWidget):
    """Panel de configuracion de sincronizacion via Firebase."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cfg = load_config()
        self._build_ui()
        self._load_config()

    # ------------------------------------------------------------------
    #  Utilidad: encontrar MainWindow subiendo por la jerarquia de widgets
    # ------------------------------------------------------------------
    def _find_main_window(self):
        """Recorre la jerarquia de parents hasta encontrar MainWindow."""
        w = self.parent()
        while w is not None:
            if hasattr(w, 'session') and hasattr(w, 'sucursal'):
                return w
            w = w.parent()
        return None

    def _build_ui(self):
        root = QVBoxLayout(self)

        # ===== ESTADO DE SINCRONIZACION (v6.7.0, siempre visible) =====
        self._build_estado_panel(root)

        # ===== ACTIVACION =====
        gb_act = QGroupBox("Activacion de sincronizacion")
        lay_act = QFormLayout(gb_act)

        self.chk_enabled = QCheckBox("Activar sincronizacion entre sucursales")
        lay_act.addRow(self.chk_enabled)

        info = QLabel(
            "La sincronizacion permite compartir ventas, productos y proveedores "
            "entre ambas sucursales automaticamente usando Firebase."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #888; font-size: 10px;")
        lay_act.addRow(info)
        root.addWidget(gb_act)

        # ===== MODO =====
        gb_modo = QGroupBox("Modo de sincronizacion")
        lay_modo = QFormLayout(gb_modo)

        self.cmb_modo = NoScrollComboBox()
        self.cmb_modo.addItem("Automatica (intervalo fijo)", "interval")
        self.cmb_modo.addItem("Manual (boton en status bar)", "manual")
        lay_modo.addRow("Modo:", self.cmb_modo)

        self.lbl_intervalo = QLabel("Intervalo:")
        self.spn_intervalo = QSpinBox()
        self.spn_intervalo.setRange(1, 60)
        self.spn_intervalo.setValue(5)
        self.spn_intervalo.setSuffix(" minutos")
        lay_modo.addRow(self.lbl_intervalo, self.spn_intervalo)

        self.lbl_refresh = QLabel("Refresco UI:")
        self.spn_refresh = QSpinBox()
        self.spn_refresh.setRange(10, 3600)
        self.spn_refresh.setValue(300)
        self.spn_refresh.setSuffix(" segundos")
        self.spn_refresh.setToolTip(
            "Intervalo en segundos para refrescar automáticamente\n"
            "las pestañas de Productos e Historial.\n"
            "Valor recomendado: 60-300 segundos."
        )
        lay_modo.addRow(self.lbl_refresh, self.spn_refresh)

        self.cmb_modo.currentIndexChanged.connect(self._on_modo_changed)
        root.addWidget(gb_modo)

        # ===== FIREBASE =====
        gb_fb = QGroupBox("Firebase Realtime Database")
        lay_fb = QFormLayout(gb_fb)

        self.ed_db_url = QLineEdit()
        self.ed_db_url.setPlaceholderText("https://tu-proyecto.firebaseio.com")
        lay_fb.addRow("URL de base de datos:", self.ed_db_url)

        self.ed_auth_token = QLineEdit()
        self.ed_auth_token.setEchoMode(QLineEdit.Password)
        self.ed_auth_token.setPlaceholderText("Database secret (token de autenticacion)")
        lay_fb.addRow("Token de autenticacion:", self.ed_auth_token)

        help_fb = QLabel(
            '<a href="https://console.firebase.google.com/">Abrir Firebase Console</a> '
            '- Ve a Project Settings > Service accounts > Database secrets'
        )
        help_fb.setOpenExternalLinks(True)
        help_fb.setStyleSheet("color: #4A90E2; font-size: 10px;")
        lay_fb.addRow("", help_fb)
        root.addWidget(gb_fb)

        # ===== QUE SINCRONIZAR =====
        gb_que = QGroupBox("Que sincronizar")
        lay_que = QFormLayout(gb_que)

        lbl_ventas = QLabel("Ventas (siempre activo)")
        lbl_ventas.setStyleSheet("color: green; font-weight: bold;")
        lay_que.addRow(lbl_ventas)

        self.chk_sync_productos = QCheckBox("Sincronizar productos")
        self.chk_sync_productos.setToolTip(
            "Sincroniza productos entre sucursales.\n"
            "Se identifican por codigo de barras.\n"
            "Si hay conflicto, gana el ultimo cambio."
        )
        lay_que.addRow(self.chk_sync_productos)

        self.chk_sync_proveedores = QCheckBox("Sincronizar proveedores")
        self.chk_sync_proveedores.setToolTip(
            "Sincroniza proveedores entre sucursales.\n"
            "Se identifican por nombre.\n"
            "Si hay conflicto, gana el ultimo cambio."
        )
        lay_que.addRow(self.chk_sync_proveedores)

        # v6.7.1: confirmar borrado de productos recibido desde otra sucursal
        self.chk_confirm_delete_prod = QCheckBox(
            "Confirmar al recibir borrado de producto desde otra sucursal"
        )
        self.chk_confirm_delete_prod.setToolTip(
            "Cuando otra sucursal elimina un producto, esta sucursal mostrara un popup\n"
            "preguntando si tambien borrarlo aca:\n"
            "  - 'Si': se elimina localmente.\n"
            "  - 'No': se re-publica el producto a Firebase para revertir la baja en\n"
            "    todas las sucursales (quedaria solo borrado en la que lo borro originalmente).\n"
            "  - 'Decidir despues': queda en la cola para el proximo sync.\n\n"
            "Si esta DESACTIVADO, los borrados se aplican automaticamente (comportamiento previo)."
        )
        lay_que.addRow(self.chk_confirm_delete_prod)

        root.addWidget(gb_que)

        # ===== LIMPIEZA AUTOMATICA DE FIREBASE (v6.6.1) =====
        gb_cleanup = QGroupBox("Limpieza automatica de Firebase (cuota)")
        lay_cleanup = QFormLayout(gb_cleanup)

        self.chk_cleanup_enabled = QCheckBox("Borrar cambios viejos de Firebase tras procesarlos")
        self.chk_cleanup_enabled.setToolTip(
            "Para no llenar la cuota gratuita de Firebase, los cambios ya replicados\n"
            "se borran de la nube tras pasar la ventana de seguridad.\n\n"
            "IMPORTANTE: NO afecta los productos/ventas/proveedores en la base local\n"
            "de ninguna sucursal — solo borra el registro de transito en cambios/.\n"
            "Una vez sincronizados, los datos viven permanentemente en cada sucursal."
        )
        lay_cleanup.addRow(self.chk_cleanup_enabled)

        self.spn_safe_window = QSpinBox()
        self.spn_safe_window.setRange(1, 365)
        self.spn_safe_window.setSuffix(" dia(s)")
        self.spn_safe_window.setToolTip(
            "Margen antes de borrar un cambio de Firebase, por si alguna sucursal\n"
            "estuvo offline o el dashboard necesita el historico.\n\n"
            "Recomendado:\n"
            "  • 30 dias (default v6.6.3): si usas el dashboard para histórico.\n"
            "  • 7-15 dias: si solo te interesan sucursales online.\n"
            "  • 90+ dias: si hay sucursales que se desconectan por largos periodos."
        )
        lay_cleanup.addRow("Margen de seguridad:", self.spn_safe_window)

        lbl_cleanup_info = QLabel(
            "Esto solo borra los <b>registros de transito</b> en Firebase, "
            "no los productos/ventas locales."
        )
        lbl_cleanup_info.setWordWrap(True)
        lbl_cleanup_info.setStyleSheet("color: #888; font-size: 10px;")
        lay_cleanup.addRow(lbl_cleanup_info)

        root.addWidget(gb_cleanup)

        # ===== SYNC INICIAL (diseño mejorado) =====
        gb_inicial = QGroupBox("Sincronizacion inicial")
        gb_inicial.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #4A90E2;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 18px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
                color: #4A90E2;
            }
        """)
        lay_inicial = QVBoxLayout(gb_inicial)
        lay_inicial.setContentsMargins(16, 8, 16, 16)
        lay_inicial.setSpacing(10)

        # Icono + descripcion
        row_desc = QHBoxLayout()
        lbl_icon = QLabel("☁️")
        lbl_icon.setStyleSheet("font-size: 28px;")
        lbl_icon.setFixedWidth(40)
        row_desc.addWidget(lbl_icon)

        lbl_inicial = QLabel(
            "<b>¿Ya tenias datos antes de activar la sync?</b><br>"
            "<span style='color:#666; font-size:11px;'>"
            "Marca abajo qué tipos quieres subir a Firebase. La otra sucursal "
            "los recibira automaticamente en la proxima sincronizacion. "
            "Los items que ya existen alli se detectan como duplicados y NO se duplican.</span>"
        )
        lbl_inicial.setWordWrap(True)
        row_desc.addWidget(lbl_inicial, 1)
        lay_inicial.addLayout(row_desc)

        # v6.7.0: 5 checkboxes para elegir qué subir (todos desmarcados por default)
        self.chk_bulk_productos = QCheckBox("Productos")
        self.chk_bulk_proveedores = QCheckBox("Proveedores")
        self.chk_bulk_ventas = QCheckBox("Ventas (incluye items y notas de credito)")
        self.chk_bulk_pagos = QCheckBox("Pagos a proveedores")
        self.chk_bulk_compradores = QCheckBox("Clientes (compradores)")
        for _chk in (self.chk_bulk_productos, self.chk_bulk_proveedores,
                     self.chk_bulk_ventas, self.chk_bulk_pagos, self.chk_bulk_compradores):
            _chk.setChecked(False)
            _chk.setStyleSheet("font-size: 12px; padding: 2px 0;")
            _chk.toggled.connect(self._on_bulk_chk_toggled)
            lay_inicial.addWidget(_chk)

        # Barra de progreso (oculta hasta que se usa)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #ccc;
                border-radius: 4px;
                text-align: center;
                height: 22px;
                background: #f0f0f0;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4A90E2, stop:1 #67B8F7);
                border-radius: 3px;
            }
        """)
        lay_inicial.addWidget(self.progress_bar)

        # Label de estado (oculto hasta que se usa)
        self.lbl_sync_progress = QLabel("")
        self.lbl_sync_progress.setAlignment(Qt.AlignCenter)
        self.lbl_sync_progress.setStyleSheet("color: #555; font-size: 11px;")
        lay_inicial.addWidget(self.lbl_sync_progress)

        # Boton principal (v6.7.0: deshabilitado hasta que se marque al menos 1 checkbox)
        self.btn_inicial = QPushButton("  Subir seleccionados a Firebase  ")
        self.btn_inicial.setEnabled(False)
        self.btn_inicial.setCursor(Qt.PointingHandCursor)
        self.btn_inicial.setMinimumHeight(42)
        self.btn_inicial.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #5BA0F2, stop:1 #4A90E2);
                color: white;
                font-size: 13px;
                font-weight: bold;
                border: none;
                border-radius: 6px;
                padding: 10px 24px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #6BB0FF, stop:1 #5BA0F2);
            }
            QPushButton:pressed {
                background: #3A80D2;
            }
            QPushButton:disabled {
                background: #aaa;
                color: #ddd;
            }
        """)
        self.btn_inicial.clicked.connect(self._push_all_existing)
        lay_inicial.addWidget(self.btn_inicial)

        # v6.6.0: boton Verificar pendientes (diff Local + Firebase)
        self.btn_verificar = QPushButton("  Verificar pendientes (Local + Firebase)  ")
        self.btn_verificar.setCursor(Qt.PointingHandCursor)
        self.btn_verificar.setMinimumHeight(38)
        self.btn_verificar.setStyleSheet("""
            QPushButton {
                background: #f5f5f5;
                color: #333;
                font-size: 12px;
                font-weight: 500;
                border: 1px solid #ccc;
                border-radius: 6px;
                padding: 8px 20px;
            }
            QPushButton:hover { background: #eaeaea; }
            QPushButton:pressed { background: #d8d8d8; }
            QPushButton:disabled { background: #f0f0f0; color: #aaa; }
        """)
        self.btn_verificar.setToolTip(
            "Muestra cuantos cambios hay encolados localmente para subir y\n"
            "cuantos hay en Firebase aun no aplicados aqui."
        )
        self.btn_verificar.clicked.connect(self._verificar_pendientes)
        lay_inicial.addWidget(self.btn_verificar)

        # v6.6.2: boton Forzar descarga completa (resetea cursors + sync)
        self.btn_force_pull = QPushButton("  Forzar descarga completa desde Firebase  ")
        self.btn_force_pull.setCursor(Qt.PointingHandCursor)
        self.btn_force_pull.setMinimumHeight(38)
        self.btn_force_pull.setStyleSheet("""
            QPushButton {
                background: #fff3e0;
                color: #b85c00;
                font-size: 12px;
                font-weight: bold;
                border: 1px solid #ffb74d;
                border-radius: 6px;
                padding: 8px 20px;
            }
            QPushButton:hover { background: #ffe0b2; }
            QPushButton:pressed { background: #ffcc80; }
            QPushButton:disabled { background: #f5f5f5; color: #999; }
        """)
        self.btn_force_pull.setToolTip(
            "Resetea los cursores de sincronizacion y descarga TODO lo que hay en\n"
            "Firebase desde el principio. Util si la sync se quedo trabada o si\n"
            "faltan datos. Las ventas/productos que ya tenes localmente NO se\n"
            "duplican: se detectan como existentes y se saltan."
        )
        self.btn_force_pull.clicked.connect(self._force_pull)
        lay_inicial.addWidget(self.btn_force_pull)

        # v6.6.2: boton Ver items con error (sync_skipped.log)
        self.btn_ver_errores = QPushButton("  Ver items con error (skipeados)  ")
        self.btn_ver_errores.setCursor(Qt.PointingHandCursor)
        self.btn_ver_errores.setMinimumHeight(34)
        self.btn_ver_errores.setStyleSheet("""
            QPushButton {
                background: #ffebee;
                color: #c62828;
                font-size: 11px;
                font-weight: 500;
                border: 1px solid #ef9a9a;
                border-radius: 6px;
                padding: 6px 16px;
            }
            QPushButton:hover { background: #ffcdd2; }
        """)
        self.btn_ver_errores.setToolTip(
            "Muestra los cambios de Firebase que fallaron en aplicarse 3 veces y fueron\n"
            "skipeados. Util para diagnosticar items danados (ventas duplicadas, productos\n"
            "con codigo invalido, etc.)"
        )
        self.btn_ver_errores.clicked.connect(self._ver_items_skipeados)
        lay_inicial.addWidget(self.btn_ver_errores)

        root.addWidget(gb_inicial)

        # ===== LOG =====
        gb_log = QGroupBox("Registro de sincronización")
        lay_log = QVBoxLayout(gb_log)

        lbl_log_info = QLabel(
            "Consulta el historial detallado de todas las sincronizaciones "
            "realizadas (envíos, recepciones, errores)."
        )
        lbl_log_info.setWordWrap(True)
        lbl_log_info.setStyleSheet("color: #888; font-size: 10px;")
        lay_log.addWidget(lbl_log_info)

        btn_log = QPushButton("  Ver log de sincronización  ")
        btn_log.setCursor(Qt.PointingHandCursor)
        btn_log.clicked.connect(self._mostrar_log_sync)
        lay_log.addWidget(btn_log)

        root.addWidget(gb_log)

        # ===== BOTONES =====
        row_btns = QHBoxLayout()
        row_btns.addStretch(1)

        btn_test = QPushButton("Probar conexion")
        btn_test.clicked.connect(self._test_connection)
        row_btns.addWidget(btn_test)

        btn_save = QPushButton("Guardar configuracion")
        btn_save.clicked.connect(self._save_config)
        btn_save.setMinimumWidth(180)
        row_btns.addWidget(btn_save)

        root.addLayout(row_btns)
        root.addStretch(1)

        self._on_modo_changed()

    # ─── Panel Estado de sincronizacion (v6.7.0) ─────────────────────
    _ESTADO_TIPOS = (
        ("productos", "Productos"),
        ("ventas", "Ventas"),
        ("proveedores", "Proveedores"),
        ("pagos_proveedores", "Pagos prov."),
        ("compradores", "Clientes"),
    )

    def _build_estado_panel(self, parent_layout):
        """v6.7.0: Panel siempre visible con resumen de sincronizacion."""
        gb = QGroupBox("Estado de sincronizacion")
        gb.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #b0bec5;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 14px;
                background: #f7fbfd;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 6px;
                color: #37474f;
            }
        """)
        lay = QVBoxLayout(gb)
        lay.setContentsMargins(12, 8, 12, 12)
        lay.setSpacing(6)

        # Linea: ultima sync + estado en vivo
        self.lbl_estado_ultima = QLabel("Sin sincronizaciones aun.")
        self.lbl_estado_ultima.setStyleSheet("color: #455a64; font-size: 12px;")
        lay.addWidget(self.lbl_estado_ultima)

        self.lbl_estado_vivo = QLabel("")
        self.lbl_estado_vivo.setStyleSheet("color: #1976D2; font-size: 11px; font-style: italic;")
        lay.addWidget(self.lbl_estado_vivo)

        # Grid 5x4 con desglose por tipo
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(2)
        # Encabezados
        for col, txt in enumerate(("Tipo", "Subidos", "Bajados", "Errores")):
            h = QLabel(f"<b>{txt}</b>")
            h.setStyleSheet("color: #455a64; font-size: 11px;")
            grid.addWidget(h, 0, col)
        self._estado_grid_labels = {}
        for row, (key, label) in enumerate(self._ESTADO_TIPOS, start=1):
            grid.addWidget(QLabel(label), row, 0)
            l_sent = QLabel("0"); l_recv = QLabel("0"); l_err = QLabel("0")
            for w in (l_sent, l_recv, l_err):
                w.setStyleSheet("font-family: Consolas, monospace; font-size: 11px;")
            grid.addWidget(l_sent, row, 1)
            grid.addWidget(l_recv, row, 2)
            grid.addWidget(l_err, row, 3)
            self._estado_grid_labels[key] = (l_sent, l_recv, l_err)
        lay.addLayout(grid)

        # Tabla pequeña: ultimas 10 sincronizaciones
        self.tbl_historial_sync = QTableWidget(0, 5)
        self.tbl_historial_sync.setHorizontalHeaderLabels(
            ["Hora", "↑ Enviados", "↓ Recibidos", "Errores", "Tipos involucrados"]
        )
        self.tbl_historial_sync.verticalHeader().setVisible(False)
        self.tbl_historial_sync.setSelectionMode(QTableWidget.NoSelection)
        self.tbl_historial_sync.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl_historial_sync.setShowGrid(False)
        self.tbl_historial_sync.setStyleSheet(
            "QTableWidget { background: #fff; font-size: 11px; } "
            "QHeaderView::section { background: #eceff1; padding: 3px; border: 0; font-size: 11px; }"
        )
        hdr = self.tbl_historial_sync.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.Stretch)
        self.tbl_historial_sync.setMaximumHeight(140)
        lay.addWidget(self.tbl_historial_sync)

        parent_layout.addWidget(gb)

        # Timer de refresco (cada 2s) — barato, lee atributos de MainWindow
        self._estado_timer = QTimer(self)
        self._estado_timer.setInterval(2000)
        self._estado_timer.timeout.connect(self._refresh_estado_panel)
        self._estado_timer.start()
        # Refresco inmediato
        QTimer.singleShot(0, self._refresh_estado_panel)

    def _refresh_estado_panel(self):
        """v6.7.0: lee el estado mas reciente desde MainWindow y refresca el panel."""
        mw = self._find_main_window()
        if mw is None:
            return

        # Estado en vivo: si hay sync corriendo, mostrar elapsed
        sync_running = bool(getattr(mw, "_sync_running", False))
        start = getattr(mw, "_sync_start_time", None)
        if sync_running and start is not None:
            try:
                from datetime import datetime as _dt
                elapsed = int((_dt.now() - start).total_seconds())
                m, s = divmod(elapsed, 60)
                hh = f"{m}:{s:02d}" if m else f"{s}s"
                self.lbl_estado_vivo.setText(f"⟳ Sincronizando... {hh}")
            except Exception:
                self.lbl_estado_vivo.setText("⟳ Sincronizando...")
        else:
            self.lbl_estado_vivo.setText("")

        # Ultimo resultado conocido
        ultimo = getattr(mw, "_last_sync_resultado", None)
        last_time = getattr(mw, "_last_sync_time", None)
        if ultimo is None or last_time is None:
            self.lbl_estado_ultima.setText("Sin sincronizaciones aun en esta sesion.")
            for (l_sent, l_recv, l_err) in self._estado_grid_labels.values():
                l_sent.setText("0"); l_recv.setText("0"); l_err.setText("0")
        else:
            try:
                hora = last_time.strftime("%H:%M:%S")
            except Exception:
                hora = "?"
            errs = ultimo.get("errores", [])
            n_errs = len(errs) if isinstance(errs, list) else int(errs or 0)
            partes = [f"<b>Ultima sync:</b> {hora}",
                      f"↑ {ultimo.get('enviados', 0)} enviados",
                      f"↓ {ultimo.get('recibidos', 0)} recibidos"]
            if n_errs:
                partes.append(f"<span style='color:#c62828;'>{n_errs} errores</span>")
            self.lbl_estado_ultima.setText(" · ".join(partes))

            por_tipo = ultimo.get("por_tipo") or {}
            for key, _label in self._ESTADO_TIPOS:
                stats = por_tipo.get(key) or {}
                l_sent, l_recv, l_err = self._estado_grid_labels[key]
                l_sent.setText(str(stats.get("sent", 0)))
                l_recv.setText(str(stats.get("recv", 0)))
                e = stats.get("err", 0)
                l_err.setText(str(e))
                # Pintar errores en rojo
                style_red = "font-family: Consolas, monospace; font-size: 11px; color: #c62828; font-weight: bold;"
                style_norm = "font-family: Consolas, monospace; font-size: 11px;"
                l_err.setStyleSheet(style_red if e else style_norm)

        # Tabla de historial
        history = getattr(mw, "_sync_history", []) or []
        self.tbl_historial_sync.setRowCount(len(history))
        for i, entry in enumerate(reversed(history)):  # mas reciente arriba
            try:
                hora = entry["timestamp"].strftime("%H:%M:%S")
            except Exception:
                hora = "?"
            por_tipo = entry.get("por_tipo") or {}
            tipos_act = []
            for key, lbl in self._ESTADO_TIPOS:
                stats = por_tipo.get(key) or {}
                if (stats.get("sent", 0) or stats.get("recv", 0)):
                    tipos_act.append(lbl)
            tipos_str = ", ".join(tipos_act) if tipos_act else "(ninguno con cambios)"
            cells = [
                hora,
                f"↑ {entry.get('enviados', 0)}",
                f"↓ {entry.get('recibidos', 0)}",
                str(entry.get("errores", 0)),
                tipos_str,
            ]
            for col, txt in enumerate(cells):
                it = QTableWidgetItem(txt)
                if col == 3 and entry.get("errores", 0):
                    it.setForeground(Qt.red)
                self.tbl_historial_sync.setItem(i, col, it)

    def _on_modo_changed(self):
        visible = (self.cmb_modo.currentData() == "interval")
        self.lbl_intervalo.setVisible(visible)
        self.spn_intervalo.setVisible(visible)

    def _load_config(self):
        sync_cfg = self.cfg.get("sync", {})

        self.chk_enabled.setChecked(sync_cfg.get("enabled", False))

        modo = sync_cfg.get("mode", "interval")
        idx = self.cmb_modo.findData(modo)
        if idx >= 0:
            self.cmb_modo.setCurrentIndex(idx)

        self.spn_intervalo.setValue(sync_cfg.get("interval_minutes", 5))

        self.spn_refresh.setValue(self.cfg.get("refresh_seconds", 300))

        fb = sync_cfg.get("firebase", {})
        self.ed_db_url.setText(fb.get("database_url", ""))
        self.ed_auth_token.setText(fb.get("auth_token", ""))

        self.chk_sync_productos.setChecked(sync_cfg.get("sync_productos", True))
        self.chk_sync_proveedores.setChecked(sync_cfg.get("sync_proveedores", True))
        # v6.7.1: default ACTIVADO — pedir confirmacion al recibir un delete de producto
        self.chk_confirm_delete_prod.setChecked(sync_cfg.get("confirm_delete_productos", True))

        # v6.6.1: cleanup (v6.6.3: default 30)
        cleanup = (sync_cfg.get("cleanup") or {})
        self.chk_cleanup_enabled.setChecked(bool(cleanup.get("enabled", True)))
        self.spn_safe_window.setValue(int(cleanup.get("safe_window_days", 30)))

    def _save_config(self):
        cfg = load_config()

        # Preservar keys existentes que no editamos
        old_sync = cfg.get("sync", {})

        cfg["sync"] = {
            "enabled": self.chk_enabled.isChecked(),
            "mode": self.cmb_modo.currentData(),
            "interval_minutes": self.spn_intervalo.value(),
            "firebase": {
                "database_url": self.ed_db_url.text().strip().rstrip("/"),
                "auth_token": self.ed_auth_token.text().strip(),
            },
            "sync_productos": self.chk_sync_productos.isChecked(),
            "sync_proveedores": self.chk_sync_proveedores.isChecked(),
            "confirm_delete_productos": self.chk_confirm_delete_prod.isChecked(),  # v6.7.1
            "last_sync": old_sync.get("last_sync"),
            "last_processed_keys": old_sync.get("last_processed_keys", {}),
            # v6.6.1: cleanup configurable desde UI
            "cleanup": {
                "enabled": self.chk_cleanup_enabled.isChecked(),
                "safe_window_days": int(self.spn_safe_window.value()),
            },
        }

        # Guardar refresh_seconds a nivel raíz (no dentro de sync)
        cfg["refresh_seconds"] = self.spn_refresh.value()

        save_config(cfg)
        QMessageBox.information(self, "Sincronizacion", "Configuracion guardada correctamente.")

        # Reiniciar scheduler en ventana principal
        try:
            mw = self._find_main_window()
            if mw and hasattr(mw, "_reiniciar_sync_scheduler"):
                mw._reiniciar_sync_scheduler()
            # Actualizar timer de auto-refresh
            if mw and hasattr(mw, "_auto_refresh_timer"):
                mw._auto_refresh_timer.setInterval(self.spn_refresh.value() * 1000)
        except Exception:
            pass

    def _verificar_pendientes(self):
        """v6.6.0: Muestra cambios pendientes de subir + bajar (diff Local <-> Firebase)."""
        cfg = load_config()
        sync_cfg = cfg.get("sync", {})
        if not sync_cfg.get("enabled", False):
            QMessageBox.information(
                self, "Verificar pendientes",
                "La sincronizacion esta DESACTIVADA en la configuracion.\n\n"
                "Activala primero para poder consultar pendientes."
            )
            return

        # Conseguir el sync manager vivo de la MainWindow.
        # v6.6.1: el atributo correcto es _firebase_sync (no _sync_manager).
        # Si no existe (sync nunca se inicializo), creamos uno transitorio para diagnostico.
        mw = self._find_main_window()
        sync_mgr = getattr(mw, "_firebase_sync", None) if mw else None
        if sync_mgr is None:
            session = getattr(mw, "session", None) if mw else None
            if session is None:
                QMessageBox.warning(
                    self, "Verificar pendientes",
                    "No se pudo acceder a la sesion de la app. Reabri la ventana."
                )
                return
            try:
                from app.firebase_sync import FirebaseSyncManager
                sucursal = getattr(mw, "sucursal", "Sarmiento") if mw else "Sarmiento"
                sync_mgr = FirebaseSyncManager(session, sucursal)
            except Exception as e:
                QMessageBox.warning(
                    self, "Verificar pendientes",
                    f"No se pudo crear el sync manager:\n{e}"
                )
                return

        # v6.6.3: usar diagnose_full que compara local DB vs Firebase
        try:
            from app.gui.progress_helpers import busy_dialog
            with busy_dialog(self, "Verificando pendientes", "Contando local + Firebase..."):
                diag = sync_mgr.diagnose_full()
        except Exception as e:
            from app.gui.error_messages import show_error
            show_error(self, "verificar pendientes", e, context="diagnose_full")
            return

        if not diag.get("ok"):
            QMessageBox.warning(self, "Verificar pendientes",
                                f"No se pudo completar el diagnostico:\n\n{diag.get('error', '?')}")
            return

        local = diag.get("local", {})
        firebase = diag.get("firebase", {})
        upload = diag.get("upload_queue", {})

        # Construir mensaje legible
        ventas_local = local.get("ventas", {})
        v_total = ventas_local.get("total", 0) if isinstance(ventas_local, dict) else 0
        v_por_suc = ventas_local.get("por_sucursal", {}) if isinstance(ventas_local, dict) else {}

        def _fb_str(key):
            v = firebase.get(key, 0)
            if v == -1:
                return "(error consultando)"
            return str(v)

        lines = [
            f"Estado de sincronizacion ({sync_mgr.sucursal_local}):",
            "",
            "LOCAL (lo que tenes en tu BD):",
            f"  • Ventas: {v_total} total",
        ]
        for suc, cnt in sorted(v_por_suc.items()):
            lines.append(f"     - de {suc}: {cnt}")
        lines += [
            f"  • Productos: {local.get('productos', 0)}",
            f"  • Proveedores: {local.get('proveedores', 0)}",
            f"  • Pagos a proveedores: {local.get('pagos_proveedores', 0)}",
            f"  • Clientes: {local.get('compradores', 0)}",
            "",
            "FIREBASE (entradas en cambios/, incluye creates+updates):",
            f"  • Ventas: {_fb_str('ventas')}",
            f"  • Productos: {_fb_str('productos')}",
            f"  • Proveedores: {_fb_str('proveedores')}",
            f"  • Pagos a proveedores: {_fb_str('pagos_proveedores')}",
            f"  • Clientes: {_fb_str('compradores')}",
            "",
            "PARA SUBIR (cola offline):",
            f"  • Ventas: {upload.get('ventas',0)}  Productos: {upload.get('productos',0)}  "
            f"Proveedores: {upload.get('proveedores',0)}  Pagos: {upload.get('pagos_proveedores',0)}  "
            f"Clientes: {upload.get('compradores',0)}",
            "",
            "Si las cantidades de ventas locales por sucursal NO coinciden con otras",
            "sucursales, faltan datos. Probá 'Forzar descarga completa'.",
        ]
        QMessageBox.information(self, "Verificar pendientes", "\n".join(lines))

    def _force_pull(self):
        """v6.6.2: Resetea cursores y descarga todos los cambios pendientes desde Firebase.
        v6.6.3: usa QThread + QProgressDialog con progress real cancelable."""
        cfg = load_config()
        sync_cfg = cfg.get("sync", {})
        if not sync_cfg.get("enabled", False):
            QMessageBox.warning(
                self, "Forzar descarga",
                "La sincronizacion esta DESACTIVADA. Activala primero."
            )
            return

        reply = QMessageBox.question(
            self, "Forzar descarga completa",
            "Esto resetea los cursores de sincronizacion y descarga TODOS los cambios\n"
            "pendientes en Firebase desde el principio.\n\n"
            "Util cuando la sync se quedo trabada o faltan datos en una sucursal.\n\n"
            "Los items que ya tenes localmente se detectan como duplicados y NO se duplican.\n\n"
            "Puede tardar varios minutos si hay muchos cambios. ¿Continuar?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        mw = self._find_main_window()
        session = getattr(mw, "session", None) if mw else None
        sucursal = getattr(mw, "sucursal", "Sarmiento") if mw else "Sarmiento"
        if session is None:
            QMessageBox.warning(self, "Forzar descarga",
                                "No se pudo acceder a la sesion. Reabri la ventana.")
            return

        # v6.6.4: liberar locks de la sesion principal y pausar el auto-sync timer
        # para que el thread de pull tenga el SQLite para si solo
        try:
            session.commit()
            session.expire_all()
        except Exception:
            try:
                session.rollback()
            except Exception:
                pass

        sync_timer = getattr(mw, "_sync_timer", None) if mw else None
        sync_timer_was_active = False
        if sync_timer is not None:
            sync_timer_was_active = sync_timer.isActive()
            sync_timer.stop()

        # ---- Progress dialog cancelable ----
        progress_dlg = QProgressDialog(
            "Iniciando descarga forzada...\n",
            "Cancelar", 0, 0, self
        )
        progress_dlg.setWindowTitle("Forzar descarga completa")
        progress_dlg.setWindowModality(Qt.WindowModal)
        progress_dlg.setMinimumDuration(0)
        progress_dlg.setMinimumWidth(450)
        progress_dlg.setAutoClose(False)
        progress_dlg.setAutoReset(False)

        # Worker thread
        worker = _ForcePullWorker(sucursal=sucursal, parent=self)

        # Estado acumulado por tipo (para mostrar el progreso ultimo conocido)
        tipo_state = {"ventas": (0, 0, 0), "productos": (0, 0, 0),
                      "proveedores": (0, 0, 0), "pagos_proveedores": (0, 0, 0),
                      "compradores": (0, 0, 0)}

        def _on_progress(tipo, page, applied, errors):
            tipo_state[tipo] = (page, applied, errors)
            lines = [f"<b>Procesando {tipo} - pagina {page}</b>",
                     f"  Aplicados: {applied}, Errores: {errors}",
                     ""]
            for t, (p_, a_, e_) in tipo_state.items():
                if p_ > 0:
                    lines.append(f"  • {t}: {a_} aplicados, {e_} errores ({p_} pag.)")
            progress_dlg.setLabelText("\n".join(lines))

        # Resultado / error / cancelacion
        result_holder = {"ok": False, "data": None, "error": None, "canceled": False}

        def _on_finished(resultado):
            result_holder["ok"] = True
            result_holder["data"] = resultado
            progress_dlg.reset()
            progress_dlg.close()

        def _on_failed(msg):
            result_holder["error"] = msg
            progress_dlg.reset()
            progress_dlg.close()

        def _on_canceled():
            if not result_holder["ok"] and result_holder["error"] is None:
                result_holder["canceled"] = True
                worker.cancel()
                progress_dlg.setLabelText("Cancelando... esperando que termine la pagina actual...")

        worker.progress.connect(_on_progress)
        worker.finished_ok.connect(_on_finished)
        worker.failed.connect(_on_failed)
        progress_dlg.canceled.connect(_on_canceled)

        # Run
        worker.start()
        progress_dlg.exec_()  # bloquea hasta que se cierre el dialog
        worker.wait(60_000)   # esperar el thread (max 60s tras cancel)

        # v6.6.4: restaurar el auto-sync timer si estaba activo
        if sync_timer is not None and sync_timer_was_active:
            try:
                sync_timer.start()
            except Exception:
                pass

        # Refrescar la sesion principal y la UI
        try:
            session.rollback()
            session.expire_all()
        except Exception:
            pass
        try:
            if mw and hasattr(mw, "refrescar_productos"):
                mw.refrescar_productos()
            if mw and hasattr(mw, "cargar_lista_proveedores"):
                mw.cargar_lista_proveedores()
            historial = getattr(mw, "historial", None)
            if historial and hasattr(historial, "recargar_historial"):
                historial.recargar_historial()
        except Exception:
            pass

        # Reportar resultado al usuario
        if result_holder["error"]:
            QMessageBox.critical(self, "Forzar descarga",
                                 f"La descarga fallo:\n\n{result_holder['error']}")
            return

        if result_holder["canceled"] and not result_holder["ok"]:
            # Mostrar lo que se alcanzo a aplicar
            lines = ["Cancelado por el usuario.\n", "Aplicado hasta el corte:"]
            for t, (p_, a_, e_) in tipo_state.items():
                if p_ > 0:
                    lines.append(f"  • {t}: {a_} aplicados, {e_} errores")
            QMessageBox.information(self, "Forzar descarga", "\n".join(lines))
            return

        if not result_holder["ok"]:
            QMessageBox.warning(self, "Forzar descarga", "Descarga termino sin resultado.")
            return

        resultado = result_holder["data"]
        v = resultado.get("ventas", 0)
        p = resultado.get("productos", 0)
        pr = resultado.get("proveedores", 0)
        pp = resultado.get("pagos_proveedores", 0)
        cc = resultado.get("compradores", 0)  # v6.7.0
        errs = resultado.get("errores", 0)
        msg = (
            "Descarga completa terminada:\n\n"
            f"  - Ventas aplicadas: {v}\n"
            f"  - Productos aplicados: {p}\n"
            f"  - Proveedores aplicados: {pr}\n"
            f"  - Pagos a proveedores aplicados: {pp}\n"
            f"  - Clientes aplicados: {cc}\n"
        )
        if errs:
            msg += (
                f"\nERRORES en {errs} items.\n"
                "Si algun item falla 3 veces seguidas, se skipea automaticamente y\n"
                "queda registrado en 'Ver items con error'."
            )
        else:
            msg += "\nSin errores."
        QMessageBox.information(self, "Forzar descarga", msg)

    def _ver_items_skipeados(self):
        """v6.6.2: Muestra el log de items skipeados por fallar 3+ veces."""
        from PyQt5.QtWidgets import QDialog, QTextEdit, QVBoxLayout, QDialogButtonBox

        # Crear sync manager transitorio solo para leer el log
        mw = self._find_main_window()
        sync_mgr = getattr(mw, "_firebase_sync", None) if mw else None
        if sync_mgr is None:
            session = getattr(mw, "session", None) if mw else None
            if session is None:
                QMessageBox.information(self, "Items skipeados",
                                        "No se pudo acceder a la sesion. Reabri la ventana.")
                return
            try:
                from app.firebase_sync import FirebaseSyncManager
                sucursal = getattr(mw, "sucursal", "Sarmiento") if mw else "Sarmiento"
                sync_mgr = FirebaseSyncManager(session, sucursal)
            except Exception as e:
                QMessageBox.warning(self, "Items skipeados", f"Error: {e}")
                return

        try:
            lines = sync_mgr.get_skipped_log_lines(max_lines=200)
        except Exception as e:
            QMessageBox.warning(self, "Items skipeados", f"Error leyendo log: {e}")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Items skipeados (fallaron 3 veces)")
        dlg.resize(750, 450)
        layout = QVBoxLayout(dlg)

        info = QLabel(
            "<b>Items que fallaron en aplicarse 3 veces seguidas y fueron saltados.</b><br>"
            "<span style='color:#666;'>Si vacias este log y aun aparecen items, "
            "es probable que tengan datos invalidos en Firebase. "
            "Podes intentar 'Forzar descarga completa' para reintentar.</span>"
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        txt = QTextEdit(dlg)
        txt.setReadOnly(True)
        txt.setFontFamily("Consolas")
        txt.setFontPointSize(9)
        if lines:
            for ln in lines:
                txt.append(ln)
        else:
            txt.append("(sin items skipeados)")
        layout.addWidget(txt)

        btns = QDialogButtonBox(QDialogButtonBox.Close, dlg)
        btns.rejected.connect(dlg.close)
        layout.addWidget(btns)
        dlg.exec_()

    def _seleccion_bulk_push(self) -> set:
        """v6.7.0: devuelve el set de tipos marcados en los checkboxes de sync inicial."""
        seleccion = set()
        if self.chk_bulk_productos.isChecked():
            seleccion.add("productos")
        if self.chk_bulk_proveedores.isChecked():
            seleccion.add("proveedores")
        if self.chk_bulk_ventas.isChecked():
            seleccion.add("ventas")
        if self.chk_bulk_pagos.isChecked():
            seleccion.add("pagos_proveedores")
        if self.chk_bulk_compradores.isChecked():
            seleccion.add("compradores")
        return seleccion

    def _on_bulk_chk_toggled(self, _checked):
        """v6.7.0: habilita/deshabilita el boton 'Subir seleccionados' segun la seleccion."""
        self.btn_inicial.setEnabled(bool(self._seleccion_bulk_push()))

    def _push_all_existing(self):
        """v6.7.0: Sube los tipos seleccionados con checkboxes a Firebase (bulk push selectivo)."""
        cfg = load_config()
        sync_cfg = cfg.get("sync", {})
        if not sync_cfg.get("enabled", False):
            QMessageBox.warning(self, "Error", "Primero activa y guarda la configuracion de sync.")
            return

        seleccion = self._seleccion_bulk_push()
        if not seleccion:
            QMessageBox.warning(
                self, "Sync inicial",
                "Marca al menos un tipo para subir."
            )
            return

        # Obtener sesion y sucursal desde MainWindow (subiendo por la jerarquia)
        mw = self._find_main_window()
        session = getattr(mw, 'session', None) if mw else None
        sucursal = getattr(mw, 'sucursal', 'Sarmiento') if mw else 'Sarmiento'

        if not session:
            QMessageBox.warning(
                self, "Error",
                "No se pudo acceder a la sesion de la app.\n"
                "Intenta cerrar y volver a abrir la ventana de configuracion."
            )
            return

        # Conteo previo para confirmacion
        from app.models import Producto, Proveedor, Venta, PagoProveedor, Comprador
        ETIQUETAS = {
            "productos": ("Productos", Producto),
            "proveedores": ("Proveedores", Proveedor),
            "ventas": ("Ventas", Venta),
            "pagos_proveedores": ("Pagos a proveedores", PagoProveedor),
            "compradores": ("Clientes", Comprador),
        }
        try:
            counts = {t: session.query(ETIQUETAS[t][1]).count() for t in seleccion}
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudieron contar items locales:\n{e}")
            return

        lineas_conf = ["Subiras a Firebase:", ""]
        for tipo in ("productos", "proveedores", "ventas", "pagos_proveedores", "compradores"):
            if tipo in seleccion:
                lineas_conf.append(f"  • {ETIQUETAS[tipo][0]}: {counts.get(tipo, 0)}")
        lineas_conf += [
            "",
            "Los items que ya existen en Firebase se detectan como duplicados.",
            "Puede tardar varios minutos si hay muchos datos.",
            "",
            "¿Continuar?",
        ]
        if QMessageBox.question(
            self, "Sync inicial selectiva", "\n".join(lineas_conf),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        ) != QMessageBox.Yes:
            return

        from app.firebase_sync import FirebaseSyncManager
        from PyQt5.QtWidgets import QApplication

        sync = FirebaseSyncManager(session, sucursal)

        # Mostrar barra de progreso y deshabilitar boton
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.btn_inicial.setEnabled(False)
        original_text = self.btn_inicial.text()
        self.btn_inicial.setText("  Subiendo datos...  ")

        def progress_callback(current, total, tipo):
            pct = int((current / max(total, 1)) * 100)
            self.progress_bar.setMaximum(max(total, 1))
            self.progress_bar.setValue(current)
            etiqueta = ETIQUETAS.get(tipo, (tipo, None))[0]
            self.progress_bar.setFormat(f"{etiqueta}: {current}/{total} ({pct}%)")
            self.lbl_sync_progress.setText(f"Subiendo {etiqueta.lower()}...")
            QApplication.processEvents()

        self.lbl_sync_progress.setText("Iniciando sync inicial selectiva...")
        QApplication.processEvents()

        try:
            result = sync.push_all_existing(callback=progress_callback, tipos=seleccion)
            errores = result.get("errores", 0)

            self.progress_bar.setValue(self.progress_bar.maximum())
            self.progress_bar.setFormat("¡Completado!")

            # Resumen breve en label
            partes = []
            for tipo in ("productos", "proveedores", "ventas", "pagos_proveedores", "compradores"):
                if tipo in seleccion:
                    partes.append(f"{result.get(tipo, 0)} {ETIQUETAS[tipo][0].lower()}")
            self.lbl_sync_progress.setText("✓ " + ", ".join(partes) + " subidos")
            self.lbl_sync_progress.setStyleSheet(
                "color: #2E7D32; font-size: 12px; font-weight: bold;"
            )

            # Mensaje detallado
            lineas_msg = ["Sync inicial completada:", ""]
            for tipo in ("productos", "proveedores", "ventas", "pagos_proveedores", "compradores"):
                if tipo in seleccion:
                    lineas_msg.append(f"  • {ETIQUETAS[tipo][0]} subidos: {result.get(tipo, 0)}")
            lineas_msg += ["", f"Errores: {errores}"]
            QMessageBox.information(self, "Sync inicial", "\n".join(lineas_msg))
        except Exception as e:
            self.lbl_sync_progress.setText(f"✗ Error: {e}")
            self.lbl_sync_progress.setStyleSheet(
                "color: #C62828; font-size: 11px; font-weight: bold;"
            )
            self.progress_bar.setFormat("Error")
            QMessageBox.critical(self, "Error", f"Error en sync inicial:\n{e}")
        finally:
            # Volver al estado normal: si hay seleccion, el boton vuelve a estar habilitado
            self.btn_inicial.setEnabled(bool(self._seleccion_bulk_push()))
            self.btn_inicial.setText(original_text)

    def _mostrar_log_sync(self):
        """Muestra el log de sincronización desde el archivo."""
        from PyQt5.QtWidgets import QDialog, QTextEdit, QVBoxLayout, QDialogButtonBox
        import os

        dlg = QDialog(self)
        dlg.setWindowTitle("Log de sincronización")
        dlg.resize(700, 500)
        layout = QVBoxLayout(dlg)

        txt = QTextEdit(dlg)
        txt.setReadOnly(True)
        txt.setFontFamily("Consolas")
        txt.setFontPointSize(9)

        # Leer log del archivo
        from app.config import _get_app_data_dir
        log_path = os.path.join(_get_app_data_dir(), "logs", "sync.log")

        file_lines = []
        try:
            if os.path.exists(log_path):
                with open(log_path, "r", encoding="utf-8") as f:
                    file_lines = f.readlines()[-500:]  # últimas 500 líneas
        except Exception as e:
            txt.append(f"Error leyendo log: {e}")

        if file_lines:
            for line in file_lines:
                txt.append(line.rstrip())
        else:
            txt.append("No hay registros de sincronización todavía.")
            txt.append(f"\nRuta del log: {log_path}")

        # También incluir entradas de sesión actual si existen
        mw = self._find_main_window()
        if mw:
            session_entries = getattr(mw, '_sync_log_entries', [])
            if session_entries:
                txt.append("\n=== Sesión actual ===\n")
                for entry in session_entries:
                    txt.append(entry)

        layout.addWidget(txt)

        btns = QDialogButtonBox(QDialogButtonBox.Close, dlg)
        btns.rejected.connect(dlg.close)
        layout.addWidget(btns)

        # Scroll al final
        cursor = txt.textCursor()
        cursor.movePosition(cursor.End)
        txt.setTextCursor(cursor)

        dlg.exec_()

    def _test_connection(self):
        """Prueba la conexion con Firebase via REST API."""
        db_url = self.ed_db_url.text().strip().rstrip("/")
        token = self.ed_auth_token.text().strip()

        if not db_url:
            QMessageBox.warning(self, "Error", "Ingresa la URL de la base de datos Firebase.")
            return
        if not token:
            QMessageBox.warning(self, "Error", "Ingresa el token de autenticacion.")
            return

        try:
            import requests
            url = f"{db_url}/.json?auth={token}&shallow=true"
            resp = requests.get(url, timeout=10)

            if resp.status_code == 200:
                QMessageBox.information(
                    self, "Conexion exitosa",
                    "Se conecto correctamente a Firebase Realtime Database."
                )
            elif resp.status_code == 401:
                QMessageBox.warning(
                    self, "Error de autenticacion",
                    "El token es invalido. Verifica el Database Secret en Firebase Console."
                )
            elif resp.status_code == 404:
                QMessageBox.warning(
                    self, "No encontrado",
                    "La URL de la base de datos no es valida. Verificala en Firebase Console."
                )
            else:
                QMessageBox.warning(
                    self, "Error",
                    f"Error HTTP {resp.status_code}:\n{resp.text[:200]}"
                )
        except requests.ConnectionError:
            QMessageBox.warning(
                self, "Sin conexion",
                "No se pudo conectar. Verifica tu conexion a internet."
            )
        except requests.Timeout:
            QMessageBox.warning(
                self, "Timeout",
                "Firebase no respondio a tiempo. Intenta nuevamente."
            )
        except Exception as e:
            from app.gui.error_messages import show_error
            show_error(self, "probar la conexion con Firebase", e, context="firebase_test")
