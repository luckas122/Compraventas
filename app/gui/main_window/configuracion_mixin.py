# -*- coding: utf-8 -*-
import logging

from datetime import datetime
import os
import json

logger = logging.getLogger(__name__)

import sqlite3
try:
    from app.database import SessionLocal
except Exception:
    SessionLocal = None

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QHBoxLayout, QGridLayout, QGroupBox, QLabel, QPushButton,
    QComboBox, QCheckBox, QTextEdit, QSpinBox, QLineEdit, QScrollArea, QSizePolicy,
    QFrame, QTabWidget
)
from app.gui.backup_config import BackupConfigPanel
from app.gui.common import ICON_SIZE, MIN_BTN_HEIGHT, icon
# Configurador de correo/reportes (si tu pestaña abre un diálogo de config):
from app.gui.reportes_config import ReportesCorreoConfig

class ConfiguracionMixin:
    """
    Mixin de la pestaña Configuración:
      - Construye la UI de Configuración.
      - Aplica tema/estilos y timezone.
      - Gestiona plantillas de ticket (_tpl_*).
    Este mixin NO inicializa repos; usa atributos creados en MainWindow.__init__.
    """
# ---------------- Configuración ----------------
    
    
    def tab_configuracion(self):
        from PyQt5.QtWidgets import (
        QWidget, QVBoxLayout, QFormLayout, QHBoxLayout, QGridLayout, QGroupBox, QLabel, QPushButton,
        QComboBox, QCheckBox, QTextEdit, QSpinBox, QLineEdit, QScrollArea, QSizePolicy,
        QFrame, QTabWidget
    )
        from PyQt5.QtCore import Qt, QTimer
        from PyQt5.QtPrintSupport import QPrinterInfo
        from app.config import load as load_config
        import os

        FIELD_W = 520
        cfg = load_config()
        th  = cfg.get("theme") or {}
        prn = cfg.get("printers") or {}
        tk  = cfg.get("ticket") or {}
        sc  = cfg.get("scanner") or {}
        gen = cfg.get("general") or {}
        fisc = cfg.get("fiscal") or {}

        # Raíz
        w = QWidget()
        root = QVBoxLayout(w)

        titulo = QLabel("Configuración")
        titulo.setProperty("role", "title")
        root.addWidget(titulo)

        # Tab principal (una sola vez)
        tabs_cfg = QTabWidget(w)

        # ===== PÁGINA: GENERAL =====
        page_general = QWidget(tabs_cfg)
        lay_gen = QVBoxLayout(page_general)

        # --- Estilos ---
        gb_estilos = QGroupBox("Estilos", parent=page_general)
        lay_est = QFormLayout(gb_estilos)
        lay_est.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.cfg_chk_dark = QCheckBox("Activar", parent=gb_estilos)
        self.cfg_chk_dark.setChecked(bool(th.get("dark_mode", True)))
        lay_est.addRow("Modo noche (oscuro):", self.cfg_chk_dark)

        self.cfg_cmb_dark_variant = QComboBox(parent=gb_estilos)
        self.cfg_cmb_dark_variant.addItem("Gris suave",  "soft")
        self.cfg_cmb_dark_variant.addItem("Gris medio",  "medium")
        self.cfg_cmb_dark_variant.addItem("Negro (alto contraste)", "black")
        cur_variant = (th.get("dark_variant") or "soft")
        try:
            idx_var = ["soft", "medium", "black"].index(cur_variant)
        except ValueError:
            idx_var = 0
        self.cfg_cmb_dark_variant.setCurrentIndex(idx_var)
        self.cfg_cmb_dark_variant.setEnabled(self.cfg_chk_dark.isChecked())
        self.cfg_chk_dark.toggled.connect(self.cfg_cmb_dark_variant.setEnabled)
        self.cfg_cmb_dark_variant.currentIndexChanged.connect(self._on_dark_variant_changed)
        self.cfg_chk_dark.toggled.connect(self._aplicar_modo_noche)
        lay_est.addRow("Variante:", self.cfg_cmb_dark_variant)

        row_fuente = QWidget(gb_estilos)
        fila_fuente = QHBoxLayout(row_fuente); fila_fuente.setContentsMargins(0,0,0,0); fila_fuente.setSpacing(8)

        self.cfg_cmb_font = QComboBox(row_fuente)
        for fam in ["Roboto", "Segoe UI", "Arial", "Tahoma"]:
            self.cfg_cmb_font.addItem(fam, fam)
        self.cfg_cmb_font.setCurrentText(th.get("font_family", "Roboto"))
        self.cfg_cmb_font.setMaximumWidth(260)

        self.cfg_spn_size = QComboBox(row_fuente)
        self.cfg_spn_size.addItem("Pequeña", 10)
        self.cfg_spn_size.addItem("Mediana", 12)
        self.cfg_spn_size.addItem("Grande", 14)
        _cur_pt = int(th.get("font_size", 12))
        _idx = {10: 0, 12: 1, 14: 2}.get(_cur_pt, 1)
        self.cfg_spn_size.setCurrentIndex(_idx)
        self.cfg_spn_size.setFixedWidth(120)

        fila_fuente.addWidget(self.cfg_cmb_font)
        fila_fuente.addWidget(QLabel("Tamaño:", row_fuente))
        fila_fuente.addWidget(self.cfg_spn_size)
        fila_fuente.addStretch(1)
        lay_est.addRow("Fuente:", row_fuente)

        lay_gen.addWidget(gb_estilos)
        # --- Comportamiento de la ventana ---
        gb_beh = QGroupBox("Comportamiento", parent=page_general)
        lay_beh = QFormLayout(gb_beh)
        lay_beh.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.cfg_chk_tray = QCheckBox("Minimizar a la bandeja al cerrar (X)", parent=gb_beh)
        self.cfg_chk_tray.setChecked(bool(gen.get("minimize_to_tray_on_close", False)))
        lay_beh.addRow("", self.cfg_chk_tray)

        lay_gen.addWidget(gb_beh)

        # --- Sucursal por defecto ---
        gb_suc = QGroupBox("Sucursal predeterminada", parent=page_general)
        lay_suc = QFormLayout(gb_suc)
        lay_suc.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.cfg_cmb_sucursal = QComboBox(gb_suc)
        self.cfg_cmb_sucursal.addItem("Preguntar al iniciar", "ask")
        self.cfg_cmb_sucursal.addItem("Sarmiento", "Sarmiento")
        self.cfg_cmb_sucursal.addItem("Salta", "Salta")
        start_cfg = (cfg.get("startup") or {})
        cur = start_cfg.get("default_sucursal", "ask")
        try:
            ix = ["ask","Sarmiento","Salta"].index(cur)
        except ValueError:
            ix = 0
        self.cfg_cmb_sucursal.setCurrentIndex(ix)
        lay_suc.addRow("Al iniciar:", self.cfg_cmb_sucursal)

        lay_gen.addWidget(gb_suc)

        # --- Regional / Zona horaria + reloj ---
        gb_region = QGroupBox("Regional / Zona horaria", parent=page_general)
        lay_region = QVBoxLayout(gb_region)

        row_clock = QWidget(gb_region)
        h_clock = QHBoxLayout(row_clock); h_clock.setContentsMargins(0,0,0,0)
        h_clock.addWidget(QLabel("Hora actual:", row_clock))
        self.lbl_tz_clock = QLabel("—", row_clock)
        self.lbl_tz_clock.setObjectName("tzClock")
        self.lbl_tz_clock.setStyleSheet("font-size: 12px; color: #666;")
        h_clock.addWidget(self.lbl_tz_clock, 1)
        lay_region.addWidget(row_clock)

        frm_region = QFormLayout()
        self.cmb_tz = QComboBox(gb_region)
        self.cmb_tz.addItem("Buenos Aires (GMT-3)", "America/Argentina/Buenos_Aires")
        self.cmb_tz.addItem("Madrid (GMT+1/+2)",   "Europe/Madrid")
        _cfg = load_config()
        _curr_tz = ((_cfg.get("general") or {}).get("timezone") or "America/Argentina/Buenos_Aires").strip()
        idx = max(0, self.cmb_tz.findData(_curr_tz))
        self.cmb_tz.setCurrentIndex(idx)
        frm_region.addRow(QLabel("Zona horaria:", gb_region), self.cmb_tz)
        lay_region.addLayout(frm_region)

        if not hasattr(self, "_tz_clock_timer"):
            self._tz_clock_timer = QTimer(self)
            self._tz_clock_timer.setInterval(1000)
            self._tz_clock_timer.timeout.connect(self._update_tz_clock)
            self._tz_clock_timer.start()
        self._update_tz_clock()
        self.cmb_tz.currentIndexChanged.connect(self._update_tz_clock)
        lay_gen.addWidget(gb_region)

        # --- Impresoras y escáner ---
        gb_print = QGroupBox("Impresoras y escáner", parent=page_general)
        lay_prn = QFormLayout(gb_print)
        lay_prn.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        names = [p.printerName() for p in QPrinterInfo.availablePrinters()]
        self.cfg_cmb_prn_ticket = QComboBox(gb_print)
        self.cfg_cmb_prn_ticket.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.cfg_cmb_prn_ticket.addItem("Preguntar al imprimir…", "__ASK__")
        for n in names:
            self.cfg_cmb_prn_ticket.addItem(n, n)
        sel_ticket = prn.get("ticket_printer")
        ask = bool(prn.get("ask_each_time", False))
        if ask or not sel_ticket:
            self.cfg_cmb_prn_ticket.setCurrentIndex(0)
        else:
            ix = self.cfg_cmb_prn_ticket.findData(sel_ticket)
            if ix >= 0:
                self.cfg_cmb_prn_ticket.setCurrentIndex(ix)
        lay_prn.addRow("Impresora TICKETS:", self.cfg_cmb_prn_ticket)

        self.cfg_cmb_prn_bar = QComboBox(gb_print)
        self.cfg_cmb_prn_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.cfg_cmb_prn_bar.addItems(names)
        sel_bar = prn.get("barcode_printer")
        if sel_bar in names:
            self.cfg_cmb_prn_bar.setCurrentText(sel_bar)
        lay_prn.addRow("Impresora CÓDIGOS:", self.cfg_cmb_prn_bar)

        self.cfg_cmb_scan_src = QComboBox(gb_print)
        self.cfg_cmb_scan_src.addItems(["Ninguno", "Webcam 0", "Webcam 1", "Webcam 2", "URL (RTSP/MJPEG)"])
        src = (sc.get("source") or "none").lower()
        if src == "webcam":
            idx_src = 1 + int(sc.get("index", 0))
        elif src == "url":
            idx_src = 4
        else:
            idx_src = 0
        self.cfg_cmb_scan_src.setCurrentIndex(idx_src)
        self.cfg_edt_scan_url = QLineEdit(gb_print)
        self.cfg_edt_scan_url.setPlaceholderText("rtsp://...  o  http://.../stream.mjpeg")
        self.cfg_edt_scan_url.setText(sc.get("url") or "")
        self.cfg_edt_scan_url.setEnabled(idx_src == 4)
        self.cfg_cmb_scan_src.currentIndexChanged.connect(
            lambda i: self.cfg_edt_scan_url.setEnabled(i == 4)
        )
        lay_prn.addRow("Fuente escáner:", self.cfg_cmb_scan_src)
        lay_prn.addRow("URL escáner:", self.cfg_edt_scan_url)

        lay_gen.addWidget(gb_print)

        

        # Scroll para GENERAL
        scr_gen = QScrollArea(tabs_cfg)
        scr_gen.setWidget(page_general)
        scr_gen.setWidgetResizable(True)
        scr_gen.setFrameShape(QFrame.NoFrame)
        scr_gen.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scr_gen.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        tabs_cfg.addTab(scr_gen, "General")

        # ===== PÁGINA: TICKET =====
        page_ticket = QWidget(tabs_cfg)
        lay_tk = QVBoxLayout(page_ticket)

        gb_tpl = QGroupBox("Plantilla de ticket", parent=page_ticket)
        lay_tpl = QFormLayout(gb_tpl)
        lay_tpl.setLabelAlignment(Qt.AlignRight | Qt.AlignTop)

        row_widget = QWidget(gb_tpl)
        row = QHBoxLayout(row_widget); row.setContentsMargins(0, 0, 0, 0); row.setSpacing(12)

        self.cfg_txt_tpl = QTextEdit(row_widget)
        self.cfg_txt_tpl.setPlainText(tk.get("template", ""))
        self.cfg_txt_tpl.setMinimumHeight(240)
        self.cfg_txt_tpl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        ph_panel = self._build_tpl_placeholder_panel()
        scroll = QScrollArea(row_widget)
        scroll.setWidget(ph_panel)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        row.addWidget(self.cfg_txt_tpl, 1)
        row.addWidget(scroll, 2)
        row.setStretch(0, 1)
        row.setStretch(1, 2)
        lay_tpl.addRow("Contenido:", row_widget)

        self.cfg_tpl_slot = QComboBox()
        self._tpl_build_slot_combo()
        btn_tpl_load = QPushButton("Cargar"); btn_tpl_save = QPushButton("Guardar en slot")
        btn_tpl_rename = QPushButton("Renombrar"); btn_tpl_rename.setProperty("role", "inline")
        btn_preview_live = QPushButton("Live"); btn_preview_live.setProperty("role", "inline")
        btn_preview_live.clicked.connect(self._tpl_open_live_preview)
        btn_tpl_load.clicked.connect(self._tpl_load_from_slot)
        btn_tpl_save.clicked.connect(self._tpl_save_to_slot)
        btn_tpl_rename.clicked.connect(self._tpl_rename_slot)

        hl_slots = QHBoxLayout()
        hl_slots.setSpacing(8)
        hl_slots.addWidget(self.cfg_tpl_slot)
        hl_slots.addWidget(btn_tpl_load)
        hl_slots.addWidget(btn_tpl_save)
        hl_slots.addWidget(btn_tpl_rename)
        hl_slots.addSpacing(12)
        hl_slots.addWidget(btn_preview_live)
        hl_slots.addStretch(1)
        lay_tpl.addRow("Plantillas guardadas:", hl_slots)

        # Selección automática de plantilla según forma de pago
        self.cfg_tpl_efectivo = QComboBox()
        self.cfg_tpl_tarjeta = QComboBox()
        self._tpl_build_payment_combos()

        # Conectar señales para guardar automáticamente cuando cambia la selección
        self.cfg_tpl_efectivo.currentIndexChanged.connect(self._tpl_save_payment_selection)
        self.cfg_tpl_tarjeta.currentIndexChanged.connect(self._tpl_save_payment_selection)

        lay_tpl.addRow("Plantilla para Efectivo:", self.cfg_tpl_efectivo)
        lay_tpl.addRow("Plantilla para Tarjeta:", self.cfg_tpl_tarjeta)

        help_lbl = QLabel(
            "Texto libre + placeholders. Separadores: {{hr}}. Ítems: {{items}}. "
            "Alineado/estilo por línea: {{center: ...}}, {{right: ...}}, {{b: ...}}, {{i: ...}}, "
            "{{centerb: ...}}, {{rightb: ...}}"
        )
        help_lbl.setWordWrap(True)
        lay_tpl.addRow("", help_lbl)

        lay_tk.addWidget(gb_tpl)

        # ===== SECCIÓN: ETIQUETAS DE CÓDIGO DE BARRAS =====
        barcode_cfg = cfg.get("barcode") or {}
        gb_barcode = QGroupBox("Etiquetas de código de barras", parent=page_ticket)
        lay_barcode = QFormLayout(gb_barcode)
        lay_barcode.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        # Ancho de etiqueta
        from PyQt5.QtWidgets import QDoubleSpinBox
        self.cfg_barcode_width = QDoubleSpinBox(gb_barcode)
        self.cfg_barcode_width.setRange(1.0, 8.0)
        self.cfg_barcode_width.setSingleStep(0.5)
        self.cfg_barcode_width.setDecimals(1)
        self.cfg_barcode_width.setSuffix(" cm")
        self.cfg_barcode_width.setValue(barcode_cfg.get("width_cm", 5.0))
        lay_barcode.addRow("Ancho de etiqueta:", self.cfg_barcode_width)

        # Alto de etiqueta
        self.cfg_barcode_height = QDoubleSpinBox(gb_barcode)
        self.cfg_barcode_height.setRange(1.0, 8.0)
        self.cfg_barcode_height.setSingleStep(0.5)
        self.cfg_barcode_height.setDecimals(1)
        self.cfg_barcode_height.setSuffix(" cm")
        self.cfg_barcode_height.setValue(barcode_cfg.get("height_cm", 3.0))
        lay_barcode.addRow("Alto de etiqueta:", self.cfg_barcode_height)

        # Info sobre distribución
        barcode_info = QLabel(
            "Distribución automática: 75% código de barras / 25% texto.\n"
            "El tamaño del código y texto se ajustan automáticamente al espacio disponible.\n"
            "Máximo recomendado para impresora térmica: 8 × 8 cm."
        )
        barcode_info.setWordWrap(True)
        barcode_info.setStyleSheet("color: #666; font-size: 9pt;")
        lay_barcode.addRow("", barcode_info)

        lay_tk.addWidget(gb_barcode)

        scr_tk = QScrollArea(tabs_cfg)
        scr_tk.setWidget(page_ticket)
        scr_tk.setWidgetResizable(True)
        scr_tk.setFrameShape(QFrame.NoFrame)
        scr_tk.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scr_tk.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        tabs_cfg.addTab(scr_tk, "Ticket")

        # ===== PÁGINA: REPORTES & ENVÍOS =====
        page_rep_cfg = ReportesCorreoConfig(self)
        try:
            page_rep_cfg.setMinimumSize(0, 0)
            page_rep_cfg.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.MinimumExpanding)
        except Exception:
            pass
        scr_rep = QScrollArea(tabs_cfg)
        scr_rep.setWidget(page_rep_cfg)
        scr_rep.setWidgetResizable(True)
        scr_rep.setFrameShape(QFrame.NoFrame)
        scr_rep.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scr_rep.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        tabs_cfg.addTab(scr_rep, "Reportes & Envíos")
        self._wire_reportes_guardar_programacion(page_rep_cfg)
        



# ===== PÁGINA: FACTURACIÓN ELECTRÓNICA =====
        page_fiscal = QWidget(tabs_cfg)
        lay_fisc = QVBoxLayout(page_fiscal)

        gb_fisc = QGroupBox("AFIP / ARCA - Facturación electrónica", parent=page_fiscal)
        lay_fisc_form = QFormLayout(gb_fisc)
        lay_fisc_form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        # ON/OFF integración
        self.cfg_chk_fiscal_enabled = QCheckBox("Habilitar facturación electrónica con AfipSDK",
                                                parent=gb_fisc)
        self.cfg_chk_fiscal_enabled.setChecked(bool(fisc.get("enabled", False)))
        lay_fisc_form.addRow("Integración AFIP:", self.cfg_chk_fiscal_enabled)

        # Modo: test / prod
        self.cfg_cmb_fiscal_mode = QComboBox(gb_fisc)
        self.cfg_cmb_fiscal_mode.addItem("Pruebas", "test")
        self.cfg_cmb_fiscal_mode.addItem("Producción", "prod")
        cur_mode = (fisc.get("mode") or "test")
        idx_mode = 1 if cur_mode == "prod" else 0
        self.cfg_cmb_fiscal_mode.setCurrentIndex(idx_mode)
        lay_fisc_form.addRow("Modo:", self.cfg_cmb_fiscal_mode)

        # Solo tarjeta
        self.cfg_chk_fiscal_only_card = QCheckBox(
            "Solo emitir cuando el pago sea con tarjeta",
            parent=gb_fisc
        )
        self.cfg_chk_fiscal_only_card.setChecked(bool(fisc.get("only_card", True)))
        lay_fisc_form.addRow("Disparador:", self.cfg_chk_fiscal_only_card)

        # CUIT
        self.cfg_edt_fiscal_cuit = QLineEdit(gb_fisc)
        self.cfg_edt_fiscal_cuit.setPlaceholderText("CUIT del comercio (solo números)")
        self.cfg_edt_fiscal_cuit.setText(str(fisc.get("cuit", "")))
        self.cfg_edt_fiscal_cuit.setMaxLength(13)
        lay_fisc_form.addRow("CUIT:", self.cfg_edt_fiscal_cuit)

        # Punto de venta
        self.cfg_spn_fiscal_pv = QSpinBox(gb_fisc)
        self.cfg_spn_fiscal_pv.setRange(1, 9999)
        try:
            self.cfg_spn_fiscal_pv.setValue(int(fisc.get("punto_venta", 1) or 1))
        except Exception:
            self.cfg_spn_fiscal_pv.setValue(1)
        lay_fisc_form.addRow("Punto de venta:", self.cfg_spn_fiscal_pv)

        # Tipo de comprobante
        self.cfg_cmb_fiscal_tipo = QComboBox(gb_fisc)
        self.cfg_cmb_fiscal_tipo.addItem("Factura A - Resp. Inscripto a Resp. Inscripto", "FACTURA_A")
        self.cfg_cmb_fiscal_tipo.addItem("Factura B - Monotributista a Consumidor Final", "FACTURA_B")
        self.cfg_cmb_fiscal_tipo.addItem("Factura C - Consumidor Final", "FACTURA_C")
        self.cfg_cmb_fiscal_tipo.addItem("Ticket Factura B", "TICKET_B")
        cur_tipo = fisc.get("tipo_cbte") or "FACTURA_B"
        idx_tipo = self.cfg_cmb_fiscal_tipo.findData(cur_tipo)
        if idx_tipo < 0:
            idx_tipo = 1  # Default a Factura B
        self.cfg_cmb_fiscal_tipo.setCurrentIndex(idx_tipo)
        lay_fisc_form.addRow("Tipo de comprobante:", self.cfg_cmb_fiscal_tipo)

        # Datos específicos de AfipSDK
        af = fisc.get("afipsdk") or {}

        self.cfg_edt_fiscal_api_key = QLineEdit(gb_fisc)
        self.cfg_edt_fiscal_api_key.setPlaceholderText("API Key / token de AfipSDK")
        self.cfg_edt_fiscal_api_key.setText(af.get("api_key", ""))
        lay_fisc_form.addRow("API key AfipSDK:", self.cfg_edt_fiscal_api_key)

        self.cfg_edt_fiscal_url_test = QLineEdit(gb_fisc)
        self.cfg_edt_fiscal_url_test.setPlaceholderText("URL base sandbox (AfipSDK)")
        self.cfg_edt_fiscal_url_test.setText(af.get("base_url_test", ""))
        lay_fisc_form.addRow("URL sandbox:", self.cfg_edt_fiscal_url_test)

        self.cfg_edt_fiscal_url_prod = QLineEdit(gb_fisc)
        self.cfg_edt_fiscal_url_prod.setPlaceholderText("URL base producción (AfipSDK)")
        self.cfg_edt_fiscal_url_prod.setText(af.get("base_url_prod", ""))
        lay_fisc_form.addRow("URL producción:", self.cfg_edt_fiscal_url_prod)

        lay_fisc.addWidget(gb_fisc)
        lay_fisc.addStretch(1)

        scr_fisc = QScrollArea(tabs_cfg)
        scr_fisc.setWidget(page_fiscal)
        scr_fisc.setWidgetResizable(True)
        scr_fisc.setFrameShape(QFrame.NoFrame)
        scr_fisc.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scr_fisc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        tabs_cfg.addTab(scr_fisc, "Facturación")
        
        
        # Agregar tabs y botón de guardar
        root.addWidget(tabs_cfg, 1)
        btn_apply = QPushButton("Aplicar cambios / Guardar")
        btn_apply.setMinimumHeight(36)
        btn_apply.clicked.connect(self._apply_config_from_ui)
        root.addWidget(btn_apply, alignment=Qt.AlignRight)


# ===== PÁGINA: BACKUPS =====
        self.page_backup = BackupConfigPanel(self)
        try:
            self.page_backup.setMinimumSize(0, 0)
            self.page_backup.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.MinimumExpanding)
        except Exception:
            pass

        scr_bkp = QScrollArea(tabs_cfg)
        scr_bkp.setWidget(self.page_backup)
        scr_bkp.setWidgetResizable(True)
        scr_bkp.setFrameShape(QFrame.NoFrame)
        scr_bkp.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scr_bkp.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        tabs_cfg.addTab(scr_bkp, "Backups")

        # Wiring: aplicar programación al guardar y permitir backup manual
        self.page_backup.backupProgramacionGuardada.connect(lambda payload: self._setup_backups())
        self.page_backup.backupManualSolicitado.connect(self._backup_now_from_ui)
        self.page_backup.backupRestaurarSolicitado.connect(self._restore_from_zip)



# ===== PÁGINA: ACCESOS RÁPIDOS =====
        page_sc = QWidget(tabs_cfg)
        lay_acc = QVBoxLayout()
        page_sc.setLayout(lay_acc)

        # Encabezado
        header = QLabel("<h3>Accesos rápidos</h3>")
        sub = QLabel(
            "Configurá <b>letras</b> (A–Z), <b>F-keys</b> (F1–F12) o <b>Delete</b> para cada sección. "
            "La combinación primaria <b>Ctrl+Shift</b> se aplica solo a letras cuando el modo está inactivo. "
            "Podés activar/desactivar el modo por sección con <b>Ctrl+Shift+S</b> o clicando el indicador de la barra inferior."
        )

        sub.setWordWrap(True)
        lay_acc.addWidget(header)
        lay_acc.addWidget(sub)

        # Estado (informativo)
        info_state = QLabel("Estado actual: ver esquina inferior derecha (Ctrl+Shift ON/OFF).")
        lay_acc.addWidget(info_state)
        
        

        from app.config import load as _load_cfg
        _sc = (_load_cfg().get("shortcuts") or {})
        _sec = dict((_sc.get("section") or {}))
        
        
        from app.gui.shortcuts import DEFAULT_GLOBAL_MAP  # para resetear si hiciera falta
        _glob = dict((_sc.get("global") or {}))

        # Grupo: Globales (F-keys)
        gb_glob = QGroupBox("Globales (F-keys: cambian de pestaña)")
        lg = QGridLayout(gb_glob)
        lg.setHorizontalSpacing(12)
        lg.setVerticalSpacing(8)

        self.ed_glob_prod = QLineEdit(_glob.get("productos", "F1"))
        self.ed_glob_prov = QLineEdit(_glob.get("proveedores", "F2"))
        self.ed_glob_vent = QLineEdit(_glob.get("ventas", "F3"))
        self.ed_glob_hist = QLineEdit(_glob.get("historial", "F4"))
        self.ed_glob_conf = QLineEdit(_glob.get("configuraciones", "F5"))
        self.ed_glob_user = QLineEdit(_glob.get("usuarios", "F6"))

        for w_ in (self.ed_glob_prod, self.ed_glob_prov, self.ed_glob_vent, self.ed_glob_hist, self.ed_glob_conf, self.ed_glob_user):
            w_.setMaxLength(10)
            w_.setPlaceholderText("F1–F12")

        lg.addWidget(QLabel("Productos"),       0, 0); lg.addWidget(self.ed_glob_prod, 0, 1)
        lg.addWidget(QLabel("Proveedores"),     1, 0); lg.addWidget(self.ed_glob_prov, 1, 1)
        lg.addWidget(QLabel("Ventas"),          2, 0); lg.addWidget(self.ed_glob_vent, 2, 1)
        lg.addWidget(QLabel("Historial"),       3, 0); lg.addWidget(self.ed_glob_hist, 3, 1)
        lg.addWidget(QLabel("Configuraciones"), 4, 0); lg.addWidget(self.ed_glob_conf, 4, 1)
        lg.addWidget(QLabel("Usuarios"),        5, 0); lg.addWidget(self.ed_glob_user, 5, 1)

        lay_acc.addWidget(gb_glob)


        # Grupo: Productos
        gb_prod = QGroupBox("Productos")
        lp = QGridLayout(gb_prod)
        lp.setHorizontalSpacing(12)
        lp.setVerticalSpacing(8)
        self.ed_sc_prod_A = QLineEdit((_sec.get("productos", {}) or {}).get("agregar", "A"))
        self.ed_sc_prod_E = QLineEdit((_sec.get("productos", {}) or {}).get("editar", "E"))
        self.ed_sc_prod_D = QLineEdit((_sec.get("productos", {}) or {}).get("eliminar", "Delete"))
        self.ed_sc_prod_I = QLineEdit((_sec.get("productos", {}) or {}).get("imprimir_codigo", "I"))
        for w_ in (self.ed_sc_prod_A, self.ed_sc_prod_E, self.ed_sc_prod_D, self.ed_sc_prod_I):
            w_.setMaxLength(10)
            w_.setPlaceholderText("A–Z, F1–F12 o Delete")
        lp.addWidget(QLabel("A = Agregar"), 0, 0); lp.addWidget(self.ed_sc_prod_A, 0, 1)
        lp.addWidget(QLabel("E = Editar"), 1, 0);  lp.addWidget(self.ed_sc_prod_E, 1, 1)
        lp.addWidget(QLabel("Supr = Eliminar"), 2, 0); lp.addWidget(self.ed_sc_prod_D, 2, 1)
        lp.addWidget(QLabel("I = Imprimir código"), 3, 0); lp.addWidget(self.ed_sc_prod_I, 3, 1)
        lay_acc.addWidget(gb_prod)

        # Grupo: Ventas
        gb_ven = QGroupBox("Ventas")
        lv = QGridLayout(gb_ven)
        lv.setHorizontalSpacing(12)
        lv.setVerticalSpacing(8)
        self.ed_sc_ven_V = QLineEdit((_sec.get("ventas", {}) or {}).get("finalizar", "V"))
        self.ed_sc_ven_E = QLineEdit((_sec.get("ventas", {}) or {}).get("efectivo", "E"))
        self.ed_sc_ven_T = QLineEdit((_sec.get("ventas", {}) or {}).get("tarjeta", "T"))
        self.ed_sc_ven_D = QLineEdit((_sec.get("ventas", {}) or {}).get("devolucion", "D"))
        self.ed_sc_ven_W = QLineEdit((_sec.get("ventas", {}) or {}).get("whatsapp", "W"))
        self.ed_sc_ven_F = QLineEdit((_sec.get("ventas", {}) or {}).get("imprimir", "F"))
        self.ed_sc_ven_G = QLineEdit((_sec.get("ventas", {}) or {}).get("guardar_borrador", "G"))
        self.ed_sc_ven_B = QLineEdit((_sec.get("ventas", {}) or {}).get("abrir_borradores", "B"))
        for w_ in (self.ed_sc_ven_V, self.ed_sc_ven_E, self.ed_sc_ven_T, self.ed_sc_ven_D, self.ed_sc_ven_W, self.ed_sc_ven_F, self.ed_sc_ven_G, self.ed_sc_ven_B):
            w_.setMaxLength(10)
            w_.setPlaceholderText("A–Z, F1–F12 o Delete")
        lv.addWidget(QLabel("V = Finalizar"), 0, 0); lv.addWidget(self.ed_sc_ven_V, 0, 1)
        lv.addWidget(QLabel("E = Efectivo"), 1, 0);  lv.addWidget(self.ed_sc_ven_E, 1, 1)
        lv.addWidget(QLabel("T = Tarjeta"), 2, 0);   lv.addWidget(self.ed_sc_ven_T, 2, 1)
        lv.addWidget(QLabel("D = Devolución"), 3, 0);lv.addWidget(self.ed_sc_ven_D, 3, 1)
        lv.addWidget(QLabel("W = WhatsApp"), 4, 0);  lv.addWidget(self.ed_sc_ven_W, 4, 1)
        lv.addWidget(QLabel("F = Imprimir"), 5, 0);  lv.addWidget(self.ed_sc_ven_F, 5, 1)
        lv.addWidget(QLabel("G = Guardar Borrador"), 6, 0); lv.addWidget(self.ed_sc_ven_G, 6, 1)
        lv.addWidget(QLabel("B = Abrir Borradores"), 7, 0); lv.addWidget(self.ed_sc_ven_B, 7, 1)
        lay_acc.addWidget(gb_ven)
        
        
        # --- Captura de F-keys/Delete en los campos para que se escriban en el QLineEdit ---
        from PyQt5.QtCore import QObject, QEvent, Qt
        from PyQt5.QtGui import QKeyEvent

        class _SCKeyCapture(QObject):
            def __init__(self, owner):
                super().__init__(owner)
                self._owner = owner

            def eventFilter(self, obj, ev):
                # Suspender/rehabilitar globales según foco
                if ev.type() == QEvent.FocusIn:
                    try:
                        if getattr(self._owner, "shortcut_manager", None):
                            self._owner.shortcut_manager._disable_all_globals()
                    except Exception:
                        pass
                elif ev.type() == QEvent.FocusOut:
                    try:
                        if getattr(self._owner, "shortcut_manager", None):
                            self._owner.shortcut_manager._enable_all_globals()
                    except Exception:
                        pass

                # Escribir F1..F12 / Delete en el QLineEdit y consumir el evento
                if ev.type() == QEvent.KeyPress and isinstance(ev, QKeyEvent):
                    k = ev.key()
                    # Delete
                    if k == Qt.Key_Delete:
                        try:
                            obj.setText("Delete")
                            return True
                        except Exception:
                            return False
                    # F1..F12
                    if Qt.Key_F1 <= k <= Qt.Key_F12:
                        try:
                            n = k - Qt.Key_F1 + 1
                            obj.setText(f"F{n}")
                            return True
                        except Exception:
                            return False

                return super().eventFilter(obj, ev)

        # Instalar el filtro en TODOS los QLineEdit de accesos rápidos
        self._sc_keycap = _SCKeyCapture(self)
        for w_ in (
            # Globales:
            self.ed_glob_prod, self.ed_glob_prov, self.ed_glob_vent,
            self.ed_glob_hist, self.ed_glob_conf, self.ed_glob_user,
            # Sección: Productos
            self.ed_sc_prod_A, self.ed_sc_prod_E, self.ed_sc_prod_D, self.ed_sc_prod_I,
            # Sección: Ventas
            self.ed_sc_ven_V, self.ed_sc_ven_E, self.ed_sc_ven_T, self.ed_sc_ven_D, self.ed_sc_ven_W, self.ed_sc_ven_F,
            self.ed_sc_ven_G, self.ed_sc_ven_B
        ):
            try:
                w_.installEventFilter(self._sc_keycap)
            except Exception:
                pass


        # Botones
        btns = QWidget(page_sc); hb = QHBoxLayout(btns); hb.setContentsMargins(0,0,0,0)
        btn_save_sc = QPushButton("Guardar")
        btn_reset_sc = QPushButton("Restaurar valores por defecto")
        hb.addStretch(1); hb.addWidget(btn_reset_sc); hb.addWidget(btn_save_sc)
        lay_acc.addWidget(btns)

        def _normalize(v: str, default: str) -> str:
            v = (v or "").strip()
            return v if v else default

        def _save_shortcuts_from_ui():
            from app.config import load as load_config, save as save_config
            cfg = load_config()
            sc = cfg.get("shortcuts") or {}
            section = sc.get("section") or {}
            section["productos"] = {
                "agregar": _normalize(self.ed_sc_prod_A.text(), "A"),
                "editar": _normalize(self.ed_sc_prod_E.text(), "E"),
                "eliminar": _normalize(self.ed_sc_prod_D.text(), "Delete"),
                "imprimir_codigo": _normalize(self.ed_sc_prod_I.text(), "I"),
            }
            section["ventas"] = {
                "finalizar": _normalize(self.ed_sc_ven_V.text(), "V"),
                "efectivo": _normalize(self.ed_sc_ven_E.text(), "E"),
                "tarjeta": _normalize(self.ed_sc_ven_T.text(), "T"),
                "devolucion": _normalize(self.ed_sc_ven_D.text(), "D"),
                "whatsapp": _normalize(self.ed_sc_ven_W.text(), "W"),
                "imprimir": _normalize(self.ed_sc_ven_F.text(), "F"),
                "guardar_borrador": _normalize(self.ed_sc_ven_G.text(), "G"),
                "abrir_borradores": _normalize(self.ed_sc_ven_B.text(), "B"),
            }
            # — Globales —
            global_map = {
                "productos": _normalize(self.ed_glob_prod.text(), "F1"),
                "proveedores": _normalize(self.ed_glob_prov.text(), "F2"),
                "ventas": _normalize(self.ed_glob_vent.text(), "F3"),
                "historial": _normalize(self.ed_glob_hist.text(), "F4"),
                "configuraciones": _normalize(self.ed_glob_conf.text(), "F5"),
                "usuarios": _normalize(self.ed_glob_user.text(), "F6"),
            }
            sc["global"] = global_map

            # Persistir + hot reload
            sc["section"] = section
            cfg["shortcuts"] = sc
            save_config(cfg)
            try:
                if getattr(self, "shortcut_manager", None):
                    self.shortcut_manager.reload_from_config(reapply_current=True)
                self.statusBar().showMessage("Accesos rápidos guardados y aplicados.", 3000)
            except Exception:
                pass

        def _reset_shortcuts_to_defaults():
            from app.gui.shortcuts import DEFAULT_SECTION_MAP, DEFAULT_GLOBAL_MAP
            # Globales
            self.ed_glob_prod.setText(DEFAULT_GLOBAL_MAP["productos"])
            self.ed_glob_prov.setText(DEFAULT_GLOBAL_MAP["proveedores"])
            self.ed_glob_vent.setText(DEFAULT_GLOBAL_MAP["ventas"])
            self.ed_glob_hist.setText(DEFAULT_GLOBAL_MAP["historial"])
            self.ed_glob_conf.setText(DEFAULT_GLOBAL_MAP["configuraciones"])
            self.ed_glob_user.setText(DEFAULT_GLOBAL_MAP["usuarios"])
            # Sección: Productos
            self.ed_sc_prod_A.setText(DEFAULT_SECTION_MAP["productos"]["agregar"])
            self.ed_sc_prod_E.setText(DEFAULT_SECTION_MAP["productos"]["editar"])
            self.ed_sc_prod_D.setText(DEFAULT_SECTION_MAP["productos"]["eliminar"])
            self.ed_sc_prod_I.setText(DEFAULT_SECTION_MAP["productos"]["imprimir_codigo"])
            # Sección: Ventas
            self.ed_sc_ven_V.setText(DEFAULT_SECTION_MAP["ventas"]["finalizar"])
            self.ed_sc_ven_E.setText(DEFAULT_SECTION_MAP["ventas"]["efectivo"])
            self.ed_sc_ven_T.setText(DEFAULT_SECTION_MAP["ventas"]["tarjeta"])
            self.ed_sc_ven_D.setText(DEFAULT_SECTION_MAP["ventas"]["devolucion"])
            self.ed_sc_ven_W.setText(DEFAULT_SECTION_MAP["ventas"]["whatsapp"])
            self.ed_sc_ven_F.setText(DEFAULT_SECTION_MAP["ventas"]["imprimir"])
            self.ed_sc_ven_G.setText(DEFAULT_SECTION_MAP["ventas"]["guardar_borrador"])
            self.ed_sc_ven_B.setText(DEFAULT_SECTION_MAP["ventas"]["abrir_borradores"])

        btn_save_sc.clicked.connect(_save_shortcuts_from_ui)
        btn_reset_sc.clicked.connect(_reset_shortcuts_to_defaults)

        scr_sc = QScrollArea(tabs_cfg)
        scr_sc.setWidget(page_sc)
        scr_sc.setWidgetResizable(True)
        scr_sc.setFrameShape(QFrame.NoFrame)
        scr_sc.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scr_sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        tabs_cfg.addTab(scr_sc, "Accesos rápidos")

        # ===== PÁGINA: SINCRONIZACIÓN =====
        from app.gui.sync_config import SyncConfigPanel
        page_sync = SyncConfigPanel(self)
        try:
            page_sync.setMinimumSize(0, 0)
            page_sync.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.MinimumExpanding)
        except Exception:
            pass

        scr_sync = QScrollArea(tabs_cfg)
        scr_sync.setWidget(page_sync)
        scr_sync.setWidgetResizable(True)
        scr_sync.setFrameShape(QFrame.NoFrame)
        scr_sync.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scr_sync.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        tabs_cfg.addTab(scr_sync, "Sincronización")

        return w
    def _apply_config_from_ui(self):
        """Guarda TODO y aplica cambios (tema, fuentes, impresoras, plantilla, TZ, etc.)."""
        from app.config import load as load_config, save as save_config
        from PyQt5.QtWidgets import QMessageBox, QLineEdit

        cfg = load_config()

        # ---------- GENERAL: zona horaria ----------
        
        gen = cfg.get("general") or {}
        try:
            if hasattr(self, "cmb_tz") and self.cmb_tz is not None:
                gen["timezone"] = self.cmb_tz.currentData() or "America/Argentina/Buenos_Aires"
        except Exception:
            pass
        try:
            if hasattr(self, "cfg_chk_tray"):
                gen["minimize_to_tray_on_close"] = bool(self.cfg_chk_tray.isChecked())
        except Exception:
            pass
        cfg["general"] = gen

        # ---------- startup: sucursal por defecto ----------
        startup = cfg.get("startup") or {}
        try:
            startup["default_sucursal"] = self.cfg_cmb_sucursal.currentData()
        except Exception:
            startup["default_sucursal"] = "ask"
        cfg["startup"] = startup

        # ---------- theme ----------
        th = cfg.get("theme") or {}
        th["dark_mode"]   = bool(self.cfg_chk_dark.isChecked())
        th["dark_variant"] = (self.cfg_cmb_dark_variant.currentData() or "soft") if th["dark_mode"] else "soft"
        th["font_family"] = (self.cfg_cmb_font.currentData() or self.cfg_cmb_font.currentText() or "Roboto").strip()
        try:
            th["font_size"] = int(self.cfg_spn_size.currentData() or 12)
        except Exception:
            th["font_size"] = 12
        cfg["theme"] = th

        # ---------- email (tolerante: no revienta si los widgets no están) ----------
        em = cfg.get("email") or {}
        def _safe_text(widget, default=""):
            try:
                return (widget.text() or "").strip()
            except Exception:
                return default

        # remitente
        em["sender"] = _safe_text(getattr(self, "cfg_email_sender", None), em.get("sender", ""))

        # destinatarios (máx. 6) — mantiene lógica actual si existen las filas
        recips = []
        try:
            for row in getattr(self, "_recip_rows", []):
                edt = row.findChild(QLineEdit)
                if edt:
                    t = (edt.text() or "").strip()
                    if t:
                        recips.append(t)
        except Exception:
            pass
        if recips:
            em["recipients"] = recips[:6]

        # SMTP (anidado)
        smtp = em.get("smtp") or {}
        smtp["host"]     = _safe_text(getattr(self, "cfg_smtp_host", None), smtp.get("host", ""))
        try:
            # puede ser QSpinBox o QLineEdit; probamos ambos
            if hasattr(self, "cfg_smtp_port") and hasattr(self.cfg_smtp_port, "value"):
                smtp["port"] = int(self.cfg_smtp_port.value())
            else:
                smtp["port"] = int(_safe_text(getattr(self, "cfg_smtp_port", None), str(smtp.get("port", 587))) or 587)
        except Exception:
            smtp["port"] = int(smtp.get("port", 587) or 587)
        try:
            smtp["use_tls"] = bool(self.cfg_smtp_tls.isChecked())
        except Exception:
            smtp["use_tls"] = bool(smtp.get("use_tls", True))
        smtp["username"] = _safe_text(getattr(self, "cfg_smtp_user", None), smtp.get("username", ""))
        smtp["password"] = _safe_text(getattr(self, "cfg_smtp_pwd", None), smtp.get("password", ""))
        em["smtp"] = smtp
        cfg["email"] = em

        # ---------- impresoras ----------
        pr = cfg.get("printers") or {}
        data_ticket = getattr(self, "cfg_cmb_prn_ticket", None).currentData() if hasattr(self, "cfg_cmb_prn_ticket") else "__ASK__"
        if data_ticket == "__ASK__":
            pr["ask_each_time"] = True
        else:
            pr["ask_each_time"] = False
            pr["ticket_printer"] = data_ticket

        if hasattr(self, "cfg_cmb_prn_bar"):
            pr["barcode_printer"] = self.cfg_cmb_prn_bar.currentText() or None
        cfg["printers"] = pr

        # ---------- scanner ----------
        sc = cfg.get("scanner") or {}
        try:
            sc["source"] = self.cfg_cmb_scan_src.currentData()  # 'webcam0','webcam1','webcam2','ip'
        except Exception:
            sc["source"] = (sc.get("source") or "webcam0")
        try:
            sc["url"] = (self.cfg_edt_scan_url.text() or "").strip()
        except Exception:
            pass
        cfg["scanner"] = sc

        # ---------- plantilla ----------
        tk = cfg.get("ticket") or {}
        if hasattr(self, "cfg_txt_tpl"):
            tk["template"] = self.cfg_txt_tpl.toPlainText()
        cfg["ticket"] = tk

        # ---------- barcode / etiquetas ----------
        barcode = cfg.get("barcode") or {}
        try:
            if hasattr(self, "cfg_barcode_width"):
                barcode["width_cm"] = self.cfg_barcode_width.value()
            if hasattr(self, "cfg_barcode_height"):
                barcode["height_cm"] = self.cfg_barcode_height.value()
        except Exception:
            pass
        cfg["barcode"] = barcode

        # ---------- fiscal / AFIP ----------
        fisc = cfg.get("fiscal") or {}

        try:
            fisc["enabled"] = bool(self.cfg_chk_fiscal_enabled.isChecked())
        except Exception:
            pass
        try:
            fisc["mode"] = self.cfg_cmb_fiscal_mode.currentData() or "test"
        except Exception:
            pass
        try:
            fisc["only_card"] = bool(self.cfg_chk_fiscal_only_card.isChecked())
        except Exception:
            pass
        try:
            fisc["cuit"] = (self.cfg_edt_fiscal_cuit.text() or "").strip()
        except Exception:
            pass
        try:
            fisc["punto_venta"] = int(self.cfg_spn_fiscal_pv.value())
        except Exception:
            pass
        try:
            fisc["tipo_cbte"] = self.cfg_cmb_fiscal_tipo.currentData() or "FACTURA_B"
        except Exception:
            pass

        af = fisc.get("afipsdk") or {}
        try:
            af["api_key"] = (self.cfg_edt_fiscal_api_key.text() or "").strip()
            af["base_url_test"] = (self.cfg_edt_fiscal_url_test.text() or "").strip()
            af["base_url_prod"] = (self.cfg_edt_fiscal_url_prod.text() or "").strip()
        except Exception:
            pass
        fisc["afipsdk"] = af
        cfg["fiscal"] = fisc

        

        # ---------- Guardar una sola vez ----------
        save_config(cfg)
        self._apply_theme_stylesheet()
        QMessageBox.information(self, "Configuración", "Cambios guardados y aplicados.")

        # ---------- Re-armar el scheduler con la nueva TZ ----------
        try:
            self._armar_reports_scheduler_desde_config()
            if getattr(self, "_rep_sched", {}).get("enabled"):
                self._reports_timer.start()
            else:
                self._reports_timer.stop()
        except Exception as e:
            logger.error("[config] no pude rearmar scheduler: %s", e)

        # Actualizar reloj TZ en cabecera (si existe)
        try:
            self._update_tz_clock()
        except Exception:
            pass

        # ---------- (re)programar backups ----------
        try:
            if getattr(self, "_stop_backup_evt", None):
                self._stop_backup_evt.set()
        except Exception:
            pass

        try:
            from app.config import load as load_config
            bk = (load_config().get("backup") or {})
            if bk.get("enabled", False):
                self._stop_backups()
                self._setup_backups()
            else:
                self._stop_backups()
        except Exception as e:
            logger.error("[config] error al reprogramar backups: %s", e)


    def _wire_reportes_guardar_programacion(self, page):
        """
        Conecta el botón 'Guardar programación' de la pestaña Reportes & Envíos
        para rearmar el scheduler al instante (sin depender del botón global).
        """

        btn = None
        try:
            # Busca un QPushButton cuyo texto contenga 'guardar' y 'program'
            for b in page.findChildren(QPushButton):
                t = (b.text() or "").lower()
                if ("guardar" in t) and ("program" in t):
                    btn = b
                    break
        except Exception:
            btn = None

        def _reschedule():
            # Traza visible en consola
            try:
                logger.info("[Config] Guardar programación: rearmando scheduler de reportes…")
            except Exception:
                pass

            # Si la página expone un método propio de guardado, ejecútalo primero
            for name in ("guardar_programacion", "save_schedule", "on_save_programacion", "on_save_schedule"):
                if hasattr(page, name):
                    try:
                        getattr(page, name)()
                    except Exception:
                        pass
                    break

            # Rearmar el scheduler global de reportes
            try:
                if hasattr(self, "_armar_reports_scheduler_desde_config"):
                    self._armar_reports_scheduler_desde_config()
            except Exception:
                pass

        # Conexión directa al botón (si existe)
        try:
            if btn:
                btn.clicked.connect(_reschedule)
        except Exception:
            pass

        # Conectar señales opcionales si la página las expone
        for sig in ("scheduleSaved", "programacionGuardada"):
            try:
                if hasattr(page, sig):
                    getattr(page, sig).connect(_reschedule)
            except Exception:
                pass       
                #--------Tema / estilo / tz / preview:------------
                
    def _apply_theme_stylesheet(self):
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtGui import QFont
        from app.config import load as load_config
        cfg = load_config()
        th = cfg.get('theme') or {}
        app = QApplication.instance()
        if not app:
            return

        # Aplicar fuente base a toda la app
        base_family = th.get("font_family", "Segoe UI")
        base_pt = int(th.get("font_size", 12))
        app.setFont(QFont(base_family, base_pt))

        # Alturas dependientes del tamaño (en px)
        control_h = max(28, int(round(base_pt * 2.2)))
        inline_h  = max(24, int(round(base_pt * 1.8)))
        # --- NUEVO: modo (on/off) + variante del oscuro ---
        dark    = bool(th.get('dark_mode', True))
        variant = (th.get('dark_variant') or 'soft')  # 'soft' | 'medium' | 'black'

        if dark:
            # ===== 3 variantes del modo oscuro =====
            if variant == 'soft':
                bg, tabbg = '#2B2D31', '#3A3D44'
                title, text = '#C6D7FF', '#ECEFF1'
                border = '#4A4D55'
                btn, btnhv = '#3A3D44', '#454952'
            elif variant == 'medium':
                bg, tabbg = '#232427', '#32343A'
                title, text = '#BBD0FF', '#E6E9ED'
                border = '#3E4046'
                btn, btnhv = '#2F3136', '#3A3D44'
            else:  # 'black' alto contraste
                bg, tabbg = '#141414', '#202020'
                title, text = '#E0E0E0', '#F2F2F2'
                border = '#303030'
                btn, btnhv = '#1E1E1E', '#262626'
        else:
            # ===== Tema claro (usa la paleta "light_*") =====
            bg      = th.get("light_background", "#F5F6F8")
            tabbg   = th.get("light_tab_bg",   "#ECEFF1")
            title   = th.get("light_title",    "#4F6B95")
            text    = th.get("light_text",     "#222222")
            border  = th.get("light_border",   "#D0D4DB")
            btn, btnhv = "#F0F2F5", "#E6E8EC"

        app = QApplication.instance()
        if not app: return
        # Limpieza previa para evitar restos del tema anterior
        app.setStyleSheet(f"""
            QWidget {{ background-color: {bg}; color: {text}; }}
            QLabel[role='title'] {{ color: {title}; font-weight: bold; }}
            QLabel {{ color: {text}; }}
            QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
                background-color: {bg}; color: {text}; border: 1px solid {border};
                min-height: {control_h}px;
            }}
            QPushButton {{
                background-color: {btn};
                color: {text};
                border: 1px solid {border};
                border-radius: 10px;
                padding: 6px 12px;
                min-width: 160px;
                min-height: {control_h}px;
            }}
            QPushButton:hover {{
                background-color: {btnhv};
            }}

            /* —— Pestañas —— */
            QTabWidget::pane {{
                background: {tabbg};
                border: 1px solid {border};
                border-radius: 8px;
                padding: 6px;
            }}
            QTabBar::tab,
            QTabWidget QTabBar::tab {{
                background: {tabbg};
                padding: 10px;
                margin: 2px;
                border-radius: 6px;
            }}
            QTabBar::tab:hover,
            QTabWidget QTabBar::tab:hover {{
                background: #e7f8eb;           /* verde muy claro al hover */
            }}
            QTabBar::tab:selected,
            QTabWidget QTabBar::tab:selected {{
                background: #d6f1da;           /* queda seleccionado en verde suave */
                border: 1px solid #666;
            }}

            QHeaderView::section {{ background-color: {"#252525" if dark else "#f5f5f5"}; color: {text}; }}
            
            QPushButton[role="inline"] {{
                min-width: 0;          /* no se estiran */
                padding: 4px 8px;      /* más angosto */
                border-radius: 6px;
                min-height: {inline_h}px;
            }}
            QPushButton[role="inline"]:hover {{
                background-color: #FFE3C2;
                border: 1px solid #FFB86C;
            }}

            /* —— Spinboxes (flechas SIEMPRE visibles) —— */
            QSpinBox, QDoubleSpinBox {{
                border: 1px solid {border};
                border-radius: 10px;
                padding: 4px 32px 4px 8px;   /* deja sitio a las flechas */
                min-height: {control_h}px;
            }}
            QSpinBox::up-button, QDoubleSpinBox::up-button,
            QSpinBox::down-button, QDoubleSpinBox::down-button {{
                subcontrol-origin: border;
                width: 24px;
                border-left: 1px solid {border};
                background: {btn};
            }}
            QSpinBox::up-button, QDoubleSpinBox::up-button {{
                subcontrol-position: right top;
                border-top-right-radius: 10px;
            }}
            QSpinBox::down-button, QDoubleSpinBox::down-button {{
                subcontrol-position: right bottom;
                border-bottom-right-radius: 10px;
            }}
            QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
            QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
                background: {btnhv};
            }}
            QSpinBox::up-arrow, QDoubleSpinBox::up-arrow,
            QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
                width: 10px; height: 10px;
            }}
        """)
        from app.gui.common import CELL_BUTTONS_CSS, BUTTON_STYLES, BASE_ICONS_PATH
        app.setStyleSheet(app.styleSheet() + CELL_BUTTONS_CSS + BUTTON_STYLES)

        # --- FIX: evitar backslashes dentro de f-strings ---
        from pathlib import Path
        up_png   = os.path.join(BASE_ICONS_PATH, "up.svg")
        down_png = os.path.join(BASE_ICONS_PATH, "down.svg")
        if os.path.exists(up_png) and os.path.exists(down_png):
            up_url = Path(up_png).as_posix()
            down_url = Path(down_png).as_posix()
            arrows_css = f"""
            QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
                image: url("{up_url}");
            }}
            QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
                image: url("{down_url}");
            }}
            """
            app.setStyleSheet(app.styleSheet() + arrows_css)


    def _aplicar_modo_noche(self, activo: bool):
        from app.config import load as load_config, save as save_config
        cfg = load_config()
        th = cfg.get('theme') or {}
        th['dark_mode'] = bool(activo)
        cfg['theme'] = th
        save_config(cfg)
        self._apply_theme_stylesheet()
        
    def _on_dark_variant_changed(self, ix: int):
        """Guarda la variante seleccionada y re-aplica el tema al instante."""
        from app.config import load as load_config, save as save_config
        variant = self.cfg_cmb_dark_variant.itemData(ix) or "soft"
        cfg = load_config()
        th = cfg.get("theme") or {}
        th["dark_variant"] = variant if th.get("dark_mode", True) else "soft"
        cfg["theme"] = th
        save_config(cfg)
        self._apply_theme_stylesheet()
        
        
    #FUNCION RELOJ PEQUEÑO

    def _update_tz_clock(self):
        """Actualiza el reloj pequeño de la pestaña General según el TZ elegido."""
        try:
            from datetime import datetime
            tz_key = None
            if hasattr(self, "cmb_tz") and self.cmb_tz is not None:
                tz_key = self.cmb_tz.currentData()
            if not tz_key:
                tz_key = (getattr(self, "_rep_sched", {}) or {}).get("tz", "America/Argentina/Buenos_Aires")

            try:
                from zoneinfo import ZoneInfo
                tz = ZoneInfo(tz_key)
                now = datetime.now(tz)
            except Exception:
                now = datetime.now()
                tz_key = "Local"

            ciudad = "Madrid" if tz_key == "Europe/Madrid" else ("Buenos Aires" if tz_key == "America/Argentina/Buenos_Aires" else tz_key)
            if hasattr(self, "lbl_tz_clock") and self.lbl_tz_clock is not None:
                self.lbl_tz_clock.setText(f"{ciudad}: {now.strftime('%d %b %Y, %H:%M:%S')}  ({tz_key})")
        except Exception:
            pass


