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
    QCheckBox, QTextEdit, QSpinBox, QLineEdit, QScrollArea, QSizePolicy,
    QFrame, QTabWidget, QFileDialog
)
from app.gui.backup_config import BackupConfigPanel
from app.gui.common import ICON_SIZE, MIN_BTN_HEIGHT, icon
from app.gui.qt_helpers import NoScrollComboBox
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
        QCheckBox, QTextEdit, QSpinBox, QLineEdit, QScrollArea, QSizePolicy,
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

        self.cfg_cmb_dark_variant = NoScrollComboBox(parent=gb_estilos)
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

        self.cfg_cmb_font = NoScrollComboBox(row_fuente)
        for fam in ["Roboto", "Segoe UI", "Arial", "Tahoma"]:
            self.cfg_cmb_font.addItem(fam, fam)
        self.cfg_cmb_font.setCurrentText(th.get("font_family", "Roboto"))
        self.cfg_cmb_font.setMaximumWidth(260)

        self.cfg_spn_size = NoScrollComboBox(row_fuente)
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

        # --- Colores de botones (hover) ---
        gb_btn_colors = QGroupBox("Colores de botones (hover)", parent=page_general)
        lay_btn_col = QFormLayout(gb_btn_colors)
        lay_btn_col.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.cfg_btn_hover_bg = QPushButton("", gb_btn_colors)
        self.cfg_btn_hover_bg.setFixedSize(60, 30)
        _bhbg = th.get("btn_hover_bg", "#4CAF50")
        self.cfg_btn_hover_bg.setStyleSheet(f"background-color: {_bhbg}; border: 1px solid #888; border-radius: 4px;")
        self.cfg_btn_hover_bg.setProperty("color_val", _bhbg)
        self.cfg_btn_hover_bg.clicked.connect(lambda: self._pick_color(self.cfg_btn_hover_bg))
        lay_btn_col.addRow("Color fondo hover:", self.cfg_btn_hover_bg)

        self.cfg_btn_hover_border = QPushButton("", gb_btn_colors)
        self.cfg_btn_hover_border.setFixedSize(60, 30)
        _bhbd = th.get("btn_hover_border", "#388E3C")
        self.cfg_btn_hover_border.setStyleSheet(f"background-color: {_bhbd}; border: 1px solid #888; border-radius: 4px;")
        self.cfg_btn_hover_border.setProperty("color_val", _bhbd)
        self.cfg_btn_hover_border.clicked.connect(lambda: self._pick_color(self.cfg_btn_hover_border))
        lay_btn_col.addRow("Color borde hover:", self.cfg_btn_hover_border)

        lbl_btn_help = QLabel(
            "Haz clic en el cuadrado de color para cambiar.\n"
            "Se aplica al pasar el mouse sobre los botones (Aceptar, Cancelar, etc.)")
        lbl_btn_help.setWordWrap(True)
        lbl_btn_help.setStyleSheet("color: #888; font-size: 9pt;")
        lay_btn_col.addRow("", lbl_btn_help)

        lay_gen.addWidget(gb_btn_colors)

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

        self.cfg_cmb_sucursal = NoScrollComboBox(gb_suc)
        self.cfg_cmb_sucursal.addItem("Preguntar al iniciar", "ask")
        _sucursales_cfg = (cfg.get("business") or {}).get("sucursales") or {}
        for _suc_name in sorted(_sucursales_cfg.keys()):
            self.cfg_cmb_sucursal.addItem(_suc_name, _suc_name)
        start_cfg = (cfg.get("startup") or {})
        cur = start_cfg.get("default_sucursal", "ask")
        ix = self.cfg_cmb_sucursal.findData(cur)
        if ix < 0:
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
        self.cmb_tz = NoScrollComboBox(gb_region)
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
        self.cfg_cmb_prn_ticket = NoScrollComboBox(gb_print)
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

        self.cfg_cmb_prn_bar = NoScrollComboBox(gb_print)
        self.cfg_cmb_prn_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.cfg_cmb_prn_bar.addItems(names)
        sel_bar = prn.get("barcode_printer")
        if sel_bar in names:
            self.cfg_cmb_prn_bar.setCurrentText(sel_bar)
        lay_prn.addRow("Impresora CÓDIGOS:", self.cfg_cmb_prn_bar)

        self.cfg_cmb_scan_src = NoScrollComboBox(gb_print)
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

        # ===== PÁGINA: TICKET (organizada en sub-tabs) =====
        page_ticket = QWidget(tabs_cfg)
        lay_tk_root = QVBoxLayout(page_ticket)
        lay_tk_root.setContentsMargins(0, 0, 0, 0)
        tabs_ticket = QTabWidget(page_ticket)
        lay_tk_root.addWidget(tabs_ticket)

        # ────────── Sub-tab 1: EDITOR ──────────
        _sub_editor = QWidget()
        _lay_editor = QVBoxLayout(_sub_editor)

        gb_tpl = QGroupBox("Plantilla de ticket")
        lay_tpl = QFormLayout(gb_tpl)
        lay_tpl.setLabelAlignment(Qt.AlignRight | Qt.AlignTop)

        from app.gui.smart_template_editor import SmartTemplateEditor

        self._smart_editor = SmartTemplateEditor(gb_tpl)
        self._smart_editor.setPlainText(tk.get("template", ""))
        self._smart_editor.setMinimumHeight(350)

        # Mantener referencia al editor interno para compatibilidad
        self.cfg_txt_tpl = self._smart_editor

        lay_tpl.addRow(self._smart_editor)

        self.cfg_tpl_slot = NoScrollComboBox()
        self._tpl_build_slot_combo()
        btn_tpl_load = QPushButton("Cargar"); btn_tpl_save = QPushButton("Guardar en slot")
        btn_tpl_rename = QPushButton("Renombrar"); btn_tpl_rename.setProperty("role", "inline")
        btn_preview_live = QPushButton("Live"); btn_preview_live.setProperty("role", "inline")
        btn_tpl_restore = QPushButton("Restaurar Predeterminados"); btn_tpl_restore.setProperty("role", "inline")
        btn_tpl_restore.setToolTip("Restaura el slot seleccionado a su plantilla por defecto")
        btn_preview_live.clicked.connect(self._tpl_open_live_preview)
        btn_tpl_load.clicked.connect(self._tpl_load_from_slot)
        btn_tpl_save.clicked.connect(self._tpl_save_to_slot)
        btn_tpl_rename.clicked.connect(self._tpl_rename_slot)
        btn_tpl_restore.clicked.connect(self._tpl_restore_defaults)

        hl_slots = QHBoxLayout()
        hl_slots.setSpacing(8)
        hl_slots.addWidget(self.cfg_tpl_slot)
        hl_slots.addWidget(btn_tpl_load)
        hl_slots.addWidget(btn_tpl_save)
        hl_slots.addWidget(btn_tpl_rename)
        hl_slots.addWidget(btn_tpl_restore)
        hl_slots.addSpacing(12)
        hl_slots.addWidget(btn_preview_live)
        hl_slots.addStretch(1)
        lay_tpl.addRow("Plantillas guardadas:", hl_slots)

        help_lbl = QLabel(
            "Escribe {{ para ver el autocompletado de placeholders. "
            "Usa la barra superior o el panel derecho para insertar tags. "
            "Los colores indican si el placeholder es valido (verde), formato (azul) o desconocido (rojo)."
        )
        help_lbl.setWordWrap(True)
        help_lbl.setStyleSheet("color: #888; font-size: 9pt;")
        lay_tpl.addRow("", help_lbl)

        _lay_editor.addWidget(gb_tpl)
        tabs_ticket.addTab(_sub_editor, "Editor")

        # ────────── Sub-tab 2: ASIGNACIÓN ──────────
        _sub_asign = QWidget()
        _lay_asign = QVBoxLayout(_sub_asign)

        gb_payment = QGroupBox("Selección automática de plantilla según tipo de venta")
        lay_payment = QFormLayout(gb_payment)
        lay_payment.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.cfg_tpl_efectivo = NoScrollComboBox()
        self.cfg_tpl_tarjeta = NoScrollComboBox()
        self.cfg_tpl_efectivo_factura_a = NoScrollComboBox()
        self.cfg_tpl_efectivo_factura_b = NoScrollComboBox()
        self.cfg_tpl_efectivo_factura_b_mono = NoScrollComboBox()
        self.cfg_tpl_tarjeta_factura_a = NoScrollComboBox()
        self.cfg_tpl_tarjeta_factura_b = NoScrollComboBox()
        self.cfg_tpl_tarjeta_factura_b_mono = NoScrollComboBox()
        self.cfg_tpl_nota_credito_a = NoScrollComboBox()
        self.cfg_tpl_nota_credito_b = NoScrollComboBox()

        lay_payment.addRow("Efectivo (sin CAE):", self.cfg_tpl_efectivo)
        lay_payment.addRow("Tarjeta (sin comprobante):", self.cfg_tpl_tarjeta)
        _sep1 = QLabel("── Efectivo + Comprobante ──")
        _sep1.setStyleSheet("color: #888; font-weight: bold;")
        lay_payment.addRow(_sep1)
        lay_payment.addRow("Efectivo + Factura A:", self.cfg_tpl_efectivo_factura_a)
        lay_payment.addRow("Efectivo + Factura B CF:", self.cfg_tpl_efectivo_factura_b)
        lay_payment.addRow("Efectivo + Factura B Mono:", self.cfg_tpl_efectivo_factura_b_mono)
        _sep2 = QLabel("── Tarjeta + Comprobante ──")
        _sep2.setStyleSheet("color: #888; font-weight: bold;")
        lay_payment.addRow(_sep2)
        lay_payment.addRow("Tarjeta + Factura A:", self.cfg_tpl_tarjeta_factura_a)
        lay_payment.addRow("Tarjeta + Factura B CF:", self.cfg_tpl_tarjeta_factura_b)
        lay_payment.addRow("Tarjeta + Factura B Mono:", self.cfg_tpl_tarjeta_factura_b_mono)
        _sep3 = QLabel("── Notas de Crédito ──")
        _sep3.setStyleSheet("color: #888; font-weight: bold;")
        lay_payment.addRow(_sep3)
        lay_payment.addRow("Nota de Crédito A:", self.cfg_tpl_nota_credito_a)
        lay_payment.addRow("Nota de Crédito B:", self.cfg_tpl_nota_credito_b)

        _lay_asign.addWidget(gb_payment)

        # Sección de categorías personalizadas
        from PyQt5.QtWidgets import QGroupBox as _GB
        gb_custom = _GB("Categorías personalizadas")
        _lay_custom = QVBoxLayout(gb_custom)
        self._custom_assignments_layout = QVBoxLayout()
        _lay_custom.addLayout(self._custom_assignments_layout)

        btn_add_cat = QPushButton("+ Agregar categoría...")
        btn_add_cat.clicked.connect(self._tpl_add_custom_assignment)
        _lay_custom.addWidget(btn_add_cat)

        _lay_asign.addWidget(gb_custom)

        # Inicializar combos (fijos + custom)
        self._tpl_build_payment_combos()

        for _combo in (self.cfg_tpl_efectivo, self.cfg_tpl_tarjeta,
                       self.cfg_tpl_efectivo_factura_a, self.cfg_tpl_efectivo_factura_b,
                       self.cfg_tpl_efectivo_factura_b_mono,
                       self.cfg_tpl_tarjeta_factura_a, self.cfg_tpl_tarjeta_factura_b,
                       self.cfg_tpl_tarjeta_factura_b_mono,
                       self.cfg_tpl_nota_credito_a, self.cfg_tpl_nota_credito_b):
            _combo.currentIndexChanged.connect(self._tpl_save_payment_selection)

        asign_help = QLabel(
            "Asigná una plantilla diferente para cada tipo de venta. "
            "Cuando se imprime un ticket, la app selecciona automáticamente "
            "la plantilla según el tipo de comprobante. "
            "Podés agregar categorías personalizadas para otros tipos."
        )
        asign_help.setWordWrap(True)
        asign_help.setStyleSheet("color: #888; font-size: 9pt;")
        _lay_asign.addWidget(asign_help)

        _lay_asign.addStretch(1)
        tabs_ticket.addTab(_sub_asign, "Asignación")

        # ────────── Sub-tab 3: FORMATO ──────────
        _sub_formato = QWidget()
        _lay_formato = QVBoxLayout(_sub_formato)

        # IVA Discriminado
        _iva_disc = tk.get("iva_discriminado") or {}
        gb_iva = QGroupBox("Bloque {{iva.discriminado}} — líneas visibles")
        lay_iva = QHBoxLayout(gb_iva)
        lay_iva.setSpacing(16)

        self.cfg_iva_neto = QCheckBox("Subtotal Neto")
        self.cfg_iva_neto.setChecked(_iva_disc.get("mostrar_neto", True))
        self.cfg_iva_iva = QCheckBox("IVA 21%")
        self.cfg_iva_iva.setChecked(_iva_disc.get("mostrar_iva", True))
        self.cfg_iva_total = QCheckBox("TOTAL")
        self.cfg_iva_total.setChecked(_iva_disc.get("mostrar_total", True))

        lay_iva.addWidget(self.cfg_iva_neto)
        lay_iva.addWidget(self.cfg_iva_iva)
        lay_iva.addWidget(self.cfg_iva_total)
        lay_iva.addStretch(1)

        help_iva = QLabel("Seleccioná qué líneas muestra el bloque {{iva.discriminado}}. "
                          "También podés usar {{iva.base}}, {{iva.cuota}} de forma individual.")
        help_iva.setWordWrap(True)
        help_iva.setStyleSheet("color: #888; font-size: 9pt;")
        lay_iva.addWidget(help_iva)

        _lay_formato.addWidget(gb_iva)

        # Fuentes
        _tk_fonts = tk.get("fonts") or {}
        gb_fonts = QGroupBox("Tamaño de fuente del ticket")
        lay_fonts = QFormLayout(gb_fonts)
        lay_fonts.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.cfg_tk_font_h1 = QSpinBox()
        self.cfg_tk_font_h1.setRange(6, 30)
        self.cfg_tk_font_h1.setValue(int(_tk_fonts.get("h1_pt") or _tk_fonts.get("title_pt", 14)))
        self.cfg_tk_font_h1.setSuffix(" pt")
        lay_fonts.addRow("H1 - Titulo/Negocio:", self.cfg_tk_font_h1)

        self.cfg_tk_font_h2 = QSpinBox()
        self.cfg_tk_font_h2.setRange(6, 24)
        self.cfg_tk_font_h2.setValue(int(_tk_fonts.get("h2_pt", 12)))
        self.cfg_tk_font_h2.setSuffix(" pt")
        lay_fonts.addRow("H2 - Total/Secciones:", self.cfg_tk_font_h2)

        self.cfg_tk_font_h3 = QSpinBox()
        self.cfg_tk_font_h3.setRange(6, 20)
        self.cfg_tk_font_h3.setValue(int(_tk_fonts.get("h3_pt") or _tk_fonts.get("head_pt", 10)))
        self.cfg_tk_font_h3.setSuffix(" pt")
        lay_fonts.addRow("H3 - Cabeceras:", self.cfg_tk_font_h3)

        self.cfg_tk_font_h4 = QSpinBox()
        self.cfg_tk_font_h4.setRange(6, 20)
        self.cfg_tk_font_h4.setValue(int(_tk_fonts.get("h4_pt") or _tk_fonts.get("text_pt", 9)))
        self.cfg_tk_font_h4.setSuffix(" pt")
        lay_fonts.addRow("H4 - Texto/Items:", self.cfg_tk_font_h4)

        self.cfg_tk_font_h5 = QSpinBox()
        self.cfg_tk_font_h5.setRange(6, 16)
        self.cfg_tk_font_h5.setValue(int(_tk_fonts.get("h5_pt", 7)))
        self.cfg_tk_font_h5.setSuffix(" pt")
        lay_fonts.addRow("H5 - Pie/Legal/CAE:", self.cfg_tk_font_h5)

        _lay_formato.addWidget(gb_fonts)

        # Márgenes
        from PyQt5.QtWidgets import QDoubleSpinBox as _QDblSpin
        gb_margins = QGroupBox("Márgenes del ticket (mm)")
        lay_margins = QFormLayout(gb_margins)
        lay_margins.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.cfg_margin_left = _QDblSpin()
        self.cfg_margin_left.setRange(0.0, 10.0)
        self.cfg_margin_left.setSingleStep(0.5)
        self.cfg_margin_left.setDecimals(1)
        self.cfg_margin_left.setSuffix(" mm")
        self.cfg_margin_left.setValue(float(tk.get("margin_left_mm", 2.0)))
        self.cfg_margin_left.setToolTip("Margen izquierdo del contenido del ticket.\n0 = sin margen, 4 = valor anterior.")
        lay_margins.addRow("Margen izquierdo:", self.cfg_margin_left)

        self.cfg_margin_right = _QDblSpin()
        self.cfg_margin_right.setRange(0.0, 10.0)
        self.cfg_margin_right.setSingleStep(0.5)
        self.cfg_margin_right.setDecimals(1)
        self.cfg_margin_right.setSuffix(" mm")
        self.cfg_margin_right.setValue(float(tk.get("margin_right_mm", 2.0)))
        self.cfg_margin_right.setToolTip("Margen derecho del contenido del ticket.\n0 = sin margen, 4 = valor anterior.")
        lay_margins.addRow("Margen derecho:", self.cfg_margin_right)

        lbl_margins_help = QLabel(
            "Ajusta los márgenes del contenido impreso. "
            "Si el ticket se imprime muy a la derecha, reducí el margen izquierdo."
        )
        lbl_margins_help.setWordWrap(True)
        lbl_margins_help.setStyleSheet("color: #888; font-size: 9pt;")
        lay_margins.addRow("", lbl_margins_help)

        _lay_formato.addWidget(gb_margins)
        _lay_formato.addStretch(1)

        _scr_formato = QScrollArea()
        _scr_formato.setWidget(_sub_formato)
        _scr_formato.setWidgetResizable(True)
        _scr_formato.setFrameShape(QFrame.NoFrame)
        tabs_ticket.addTab(_scr_formato, "Formato")

        # ────────── Sub-tab 4: IMÁGENES ──────────
        _sub_images = QWidget()
        _lay_images_root = QVBoxLayout(_sub_images)

        gb_images = QGroupBox("Imágenes para Ticket")
        lay_images = QFormLayout(gb_images)
        lay_images.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self._ticket_img_labels = {}
        images_cfg = tk.get("images") or {}
        for img_key, img_label in [("logo", "Logo"), ("instagram", "Instagram"), ("whatsapp", "WhatsApp"), ("qr", "Código QR")]:
            row_h = QHBoxLayout()
            btn_sel = QPushButton("Seleccionar...")
            btn_sel.setToolTip(f"Seleccionar imagen para {img_label}")
            btn_clear = QPushButton("Quitar")
            btn_clear.setToolTip(f"Quitar imagen de {img_label}")
            lbl_prev = QLabel(images_cfg.get(img_key) or "(sin imagen)")
            lbl_prev.setStyleSheet("color: #666; font-size: 9pt;")
            self._ticket_img_labels[img_key] = lbl_prev

            btn_sel.clicked.connect(lambda _, k=img_key: self._select_ticket_image(k))
            btn_clear.clicked.connect(lambda _, k=img_key: self._clear_ticket_image(k))

            row_h.addWidget(btn_sel)
            row_h.addWidget(btn_clear)
            row_h.addWidget(lbl_prev)
            row_h.addStretch()
            lay_images.addRow(f"{img_label}:", row_h)

        self.ed_qr_url = QLineEdit()
        self.ed_qr_url.setPlaceholderText("URL para generar QR automáticamente...")
        self.ed_qr_url.setText(images_cfg.get("qr_url") or "")
        btn_gen_qr = QPushButton("Generar QR")
        btn_gen_qr.clicked.connect(self._generate_qr_from_url)
        qr_row = QHBoxLayout()
        qr_row.addWidget(self.ed_qr_url)
        qr_row.addWidget(btn_gen_qr)
        lay_images.addRow("URL QR:", qr_row)

        self.cmb_img_size = NoScrollComboBox()
        self.cmb_img_size.addItem("2 × 2 cm", 20)
        self.cmb_img_size.addItem("1.5 × 1.5 cm", 15)
        self.cmb_img_size.addItem("1 × 1 cm", 10)
        current_size = int(images_cfg.get("size_mm", 20))
        for i in range(self.cmb_img_size.count()):
            if self.cmb_img_size.itemData(i) == current_size:
                self.cmb_img_size.setCurrentIndex(i)
                break
        lay_images.addRow("Tamaño:", self.cmb_img_size)

        img_help = QLabel(
            "Usá {{img:logo}}, {{img:instagram}}, {{img:whatsapp}} o {{img:qr}} "
            "en la plantilla del ticket. Formato PNG recomendado."
        )
        img_help.setWordWrap(True)
        img_help.setStyleSheet("color: #888; font-size: 9pt;")
        lay_images.addRow("", img_help)

        _lay_images_root.addWidget(gb_images)
        _lay_images_root.addStretch(1)
        tabs_ticket.addTab(_sub_images, "Imágenes")

        # ────────── Sub-tab 5: ETIQUETAS ──────────
        _sub_barcode = QWidget()
        _lay_barcode_root = QVBoxLayout(_sub_barcode)

        barcode_cfg = cfg.get("barcode") or {}
        gb_barcode = QGroupBox("Etiquetas de código de barras")
        lay_barcode = QFormLayout(gb_barcode)
        lay_barcode.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        from PyQt5.QtWidgets import QDoubleSpinBox
        self.cfg_barcode_width = QDoubleSpinBox()
        self.cfg_barcode_width.setRange(1.0, 8.0)
        self.cfg_barcode_width.setSingleStep(0.5)
        self.cfg_barcode_width.setDecimals(1)
        self.cfg_barcode_width.setSuffix(" cm")
        self.cfg_barcode_width.setValue(barcode_cfg.get("width_cm", 5.0))
        lay_barcode.addRow("Ancho de etiqueta:", self.cfg_barcode_width)

        self.cfg_barcode_height = QDoubleSpinBox()
        self.cfg_barcode_height.setRange(1.0, 8.0)
        self.cfg_barcode_height.setSingleStep(0.5)
        self.cfg_barcode_height.setDecimals(1)
        self.cfg_barcode_height.setSuffix(" cm")
        self.cfg_barcode_height.setValue(barcode_cfg.get("height_cm", 3.0))
        lay_barcode.addRow("Alto de etiqueta:", self.cfg_barcode_height)

        barcode_info = QLabel(
            "Distribución automática: 75% código de barras / 25% texto.\n"
            "El tamaño del código y texto se ajustan automáticamente al espacio disponible.\n"
            "Máximo recomendado para impresora térmica: 8 × 8 cm."
        )
        barcode_info.setWordWrap(True)
        barcode_info.setStyleSheet("color: #666; font-size: 9pt;")
        lay_barcode.addRow("", barcode_info)

        _lay_barcode_root.addWidget(gb_barcode)
        _lay_barcode_root.addStretch(1)
        tabs_ticket.addTab(_sub_barcode, "Etiquetas")

        tabs_cfg.addTab(page_ticket, "Ticket")

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
        self.cfg_cmb_fiscal_mode = NoScrollComboBox(gb_fisc)
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

        # Punto de venta — global (fallback) + por sucursal
        self.cfg_spn_fiscal_pv = QSpinBox(gb_fisc)
        self.cfg_spn_fiscal_pv.setRange(1, 9999)
        try:
            self.cfg_spn_fiscal_pv.setValue(int(fisc.get("punto_venta", 1) or 1))
        except Exception:
            self.cfg_spn_fiscal_pv.setValue(1)
        lay_fisc_form.addRow("Punto de venta (global):", self.cfg_spn_fiscal_pv)

        # --- Puntos de venta por sucursal ---
        pv_por_suc = fisc.get("puntos_venta_por_sucursal") or {}
        sucursales_cfg = (cfg.get("business") or {}).get("sucursales") or {"Sarmiento": "", "Salta": ""}
        self._fiscal_pv_spinners = {}  # {nombre_sucursal: QSpinBox}
        for suc_name in sorted(sucursales_cfg.keys()):
            spn = QSpinBox(gb_fisc)
            spn.setRange(0, 9999)       # 0 = usar global
            spn.setSpecialValueText("(usar global)")
            try:
                spn.setValue(int(pv_por_suc.get(suc_name, 0) or 0))
            except Exception:
                spn.setValue(0)
            spn.setToolTip(f"Punto de venta para {suc_name}. Dejá 0 para usar el global.")
            lay_fisc_form.addRow(f"  PV {suc_name}:", spn)
            self._fiscal_pv_spinners[suc_name] = spn

        # Tipo de comprobante
        self.cfg_cmb_fiscal_tipo = NoScrollComboBox(gb_fisc)
        self.cfg_cmb_fiscal_tipo.addItem("Factura A - Resp. Inscripto", "FACTURA_A")
        self.cfg_cmb_fiscal_tipo.addItem("Factura B - Consumidor Final", "FACTURA_B")
        self.cfg_cmb_fiscal_tipo.addItem("Factura B - Monotributo", "FACTURA_B_MONO")
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

        # Certificado digital (requerido para producción)
        cert_row = QHBoxLayout()
        self.cfg_edt_fiscal_cert = QLineEdit(gb_fisc)
        self.cfg_edt_fiscal_cert.setPlaceholderText("Ruta al archivo .crt (requerido para producción)")
        self.cfg_edt_fiscal_cert.setText(af.get("cert", ""))
        cert_row.addWidget(self.cfg_edt_fiscal_cert)
        btn_cert = QPushButton("Examinar...")
        btn_cert.setMaximumWidth(100)
        btn_cert.clicked.connect(lambda: self._seleccionar_archivo_afip(self.cfg_edt_fiscal_cert, "Certificado (*.crt *.pem)"))
        cert_row.addWidget(btn_cert)
        lay_fisc_form.addRow("Certificado (.crt):", cert_row)

        # Clave privada (requerido para producción)
        key_row = QHBoxLayout()
        self.cfg_edt_fiscal_key = QLineEdit(gb_fisc)
        self.cfg_edt_fiscal_key.setPlaceholderText("Ruta al archivo .key (requerido para producción)")
        self.cfg_edt_fiscal_key.setText(af.get("key", ""))
        key_row.addWidget(self.cfg_edt_fiscal_key)
        btn_key = QPushButton("Examinar...")
        btn_key.setMaximumWidth(100)
        btn_key.clicked.connect(lambda: self._seleccionar_archivo_afip(self.cfg_edt_fiscal_key, "Clave privada (*.key *.pem)"))
        key_row.addWidget(btn_key)
        lay_fisc_form.addRow("Clave privada (.key):", key_row)

        self.cfg_edt_fiscal_url_test = QLineEdit(gb_fisc)
        self.cfg_edt_fiscal_url_test.setPlaceholderText("URL base sandbox (AfipSDK)")
        self.cfg_edt_fiscal_url_test.setText(af.get("base_url_test", ""))
        lay_fisc_form.addRow("URL sandbox:", self.cfg_edt_fiscal_url_test)

        self.cfg_edt_fiscal_url_prod = QLineEdit(gb_fisc)
        self.cfg_edt_fiscal_url_prod.setPlaceholderText("URL base producción (AfipSDK)")
        self.cfg_edt_fiscal_url_prod.setText(af.get("base_url_prod", ""))
        lay_fisc_form.addRow("URL producción:", self.cfg_edt_fiscal_url_prod)

        # CUIT/CUIL predefinido del cliente (se usa en diálogos de pago)
        self.cfg_edt_fiscal_cuit_cliente = QLineEdit(gb_fisc)
        self.cfg_edt_fiscal_cuit_cliente.setPlaceholderText("CUIT/CUIL predefinido del cliente (ej: 20000000001)")
        self.cfg_edt_fiscal_cuit_cliente.setText(str(fisc.get("cuit_predefinido", "20000000001") or "20000000001"))
        self.cfg_edt_fiscal_cuit_cliente.setMaxLength(13)
        lay_fisc_form.addRow("CUIT/CUIL cliente predefinido:", self.cfg_edt_fiscal_cuit_cliente)

        lay_fisc.addWidget(gb_fisc)

        # Botón consultar último comprobante
        btn_consultar_ultimo = QPushButton(" Consultar último Nº comprobante en AFIP")
        btn_consultar_ultimo.setStyleSheet(
            "padding: 8px 16px; font-weight: bold; background: #3498DB; color: white; border-radius: 4px;"
        )
        btn_consultar_ultimo.clicked.connect(self._consultar_ultimo_comprobante_afip)
        lay_fisc.addWidget(btn_consultar_ultimo)

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
        self.ed_sc_prod_P = QLineEdit((_sec.get("productos", {}) or {}).get("consultar_precio", "P"))
        for w_ in (self.ed_sc_prod_A, self.ed_sc_prod_E, self.ed_sc_prod_D, self.ed_sc_prod_I, self.ed_sc_prod_P):
            w_.setMaxLength(10)
            w_.setPlaceholderText("A–Z, F1–F12 o Delete")
        lp.addWidget(QLabel("A = Agregar"), 0, 0); lp.addWidget(self.ed_sc_prod_A, 0, 1)
        lp.addWidget(QLabel("E = Editar"), 1, 0);  lp.addWidget(self.ed_sc_prod_E, 1, 1)
        lp.addWidget(QLabel("Supr = Eliminar"), 2, 0); lp.addWidget(self.ed_sc_prod_D, 2, 1)
        lp.addWidget(QLabel("I = Imprimir código"), 3, 0); lp.addWidget(self.ed_sc_prod_I, 3, 1)
        lp.addWidget(QLabel("P = Consultar precio"), 4, 0); lp.addWidget(self.ed_sc_prod_P, 4, 1)
        lay_acc.addWidget(gb_prod)

        # Grupo: Ventas
        gb_ven = QGroupBox("Ventas")
        lv = QGridLayout(gb_ven)
        lv.setHorizontalSpacing(12)
        lv.setVerticalSpacing(8)
        self.ed_sc_ven_V = QLineEdit((_sec.get("ventas", {}) or {}).get("finalizar", "V"))
        self.ed_sc_ven_P = QLineEdit((_sec.get("ventas", {}) or {}).get("consultar_precio", "P"))
        self.ed_sc_ven_D = QLineEdit((_sec.get("ventas", {}) or {}).get("devolucion", "D"))
        self.ed_sc_ven_W = QLineEdit((_sec.get("ventas", {}) or {}).get("whatsapp", "W"))
        self.ed_sc_ven_F = QLineEdit((_sec.get("ventas", {}) or {}).get("imprimir", "F"))
        self.ed_sc_ven_G = QLineEdit((_sec.get("ventas", {}) or {}).get("guardar_borrador", "G"))
        self.ed_sc_ven_B = QLineEdit((_sec.get("ventas", {}) or {}).get("abrir_borradores", "B"))
        self.ed_sc_ven_plus = QLineEdit((_sec.get("ventas", {}) or {}).get("sumar", "+"))
        self.ed_sc_ven_minus = QLineEdit((_sec.get("ventas", {}) or {}).get("restar", "-"))
        self.ed_sc_ven_C = QLineEdit((_sec.get("ventas", {}) or {}).get("editar_cantidad", "C"))
        self.ed_sc_ven_X = QLineEdit((_sec.get("ventas", {}) or {}).get("descuento_item", "X"))
        self.ed_sc_ven_Z = QLineEdit((_sec.get("ventas", {}) or {}).get("vaciar_cesta", "Z"))
        for w_ in (self.ed_sc_ven_V, self.ed_sc_ven_P, self.ed_sc_ven_D, self.ed_sc_ven_W, self.ed_sc_ven_F, self.ed_sc_ven_G, self.ed_sc_ven_B, self.ed_sc_ven_plus, self.ed_sc_ven_minus, self.ed_sc_ven_C, self.ed_sc_ven_X, self.ed_sc_ven_Z):
            w_.setMaxLength(10)
            w_.setPlaceholderText("Cualquier tecla")

        # Autofocus checkboxes (funciona incluso con foco en buscador)
        _af = (_sc.get("autofocus") or {})
        self._af_checks = {}
        _af_keys = [
            ("ventas.finalizar", "V", 0), ("ventas.consultar_precio", "P", 1),
            ("ventas.devolucion", "D", 2), ("ventas.whatsapp", "W", 3),
            ("ventas.imprimir", "F", 4), ("ventas.guardar_borrador", "G", 5),
            ("ventas.abrir_borradores", "B", 6),
        ]
        _af_keys_cesta = [
            ("ventas.sumar", "+", 8), ("ventas.restar", "-", 9),
            ("ventas.editar_cantidad", "C", 10), ("ventas.descuento_item", "X", 11),
            ("ventas.vaciar_cesta", "Z", 12),
        ]

        lv.addWidget(QLabel("<b>Tecla</b>"), -1, 1) if False else None
        lv.addWidget(QLabel("Finalizar"), 0, 0); lv.addWidget(self.ed_sc_ven_V, 0, 1)
        lv.addWidget(QLabel("Consultar Precio"), 1, 0); lv.addWidget(self.ed_sc_ven_P, 1, 1)
        lv.addWidget(QLabel("Devolucion"), 2, 0);lv.addWidget(self.ed_sc_ven_D, 2, 1)
        lv.addWidget(QLabel("WhatsApp"), 3, 0);  lv.addWidget(self.ed_sc_ven_W, 3, 1)
        lv.addWidget(QLabel("Imprimir"), 4, 0);  lv.addWidget(self.ed_sc_ven_F, 4, 1)
        lv.addWidget(QLabel("Guardar Borrador"), 5, 0); lv.addWidget(self.ed_sc_ven_G, 5, 1)
        lv.addWidget(QLabel("Abrir Borradores"), 6, 0); lv.addWidget(self.ed_sc_ven_B, 6, 1)

        for af_key, _lbl, row in _af_keys:
            chk = QCheckBox("Autofoco")
            chk.setToolTip("Si activo, funciona incluso con el foco en el buscador")
            chk.setChecked(bool(_af.get(af_key, True)))
            self._af_checks[af_key] = chk
            lv.addWidget(chk, row, 2)

        # Separador visual para atajos de cesta
        lv.addWidget(QLabel("<b>— Cesta —</b>"), 7, 0, 1, 3)
        lv.addWidget(QLabel("Sumar cantidad"), 8, 0); lv.addWidget(self.ed_sc_ven_plus, 8, 1)
        lv.addWidget(QLabel("Restar cantidad"), 9, 0); lv.addWidget(self.ed_sc_ven_minus, 9, 1)
        lv.addWidget(QLabel("Editar cantidad"), 10, 0); lv.addWidget(self.ed_sc_ven_C, 10, 1)
        lv.addWidget(QLabel("Descuento item"), 11, 0); lv.addWidget(self.ed_sc_ven_X, 11, 1)
        lv.addWidget(QLabel("Vaciar cesta"), 12, 0); lv.addWidget(self.ed_sc_ven_Z, 12, 1)

        for af_key, _lbl, row in _af_keys_cesta:
            chk = QCheckBox("Autofoco")
            chk.setToolTip("Si activo, funciona incluso con el foco en el buscador")
            chk.setChecked(bool(_af.get(af_key, True)))
            self._af_checks[af_key] = chk
            lv.addWidget(chk, row, 2)

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

                # Capturar teclas y escribirlas en el QLineEdit
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
                    # Cualquier caracter imprimible (letras, numeros, simbolos)
                    text = ev.text()
                    if text and text.isprintable() and len(text) == 1:
                        try:
                            obj.setText(text.upper() if text.isalpha() else text)
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
            self.ed_sc_prod_A, self.ed_sc_prod_E, self.ed_sc_prod_D, self.ed_sc_prod_I, self.ed_sc_prod_P,
            # Sección: Ventas
            self.ed_sc_ven_V, self.ed_sc_ven_P, self.ed_sc_ven_D, self.ed_sc_ven_W, self.ed_sc_ven_F,
            self.ed_sc_ven_G, self.ed_sc_ven_B,
            # Sección: Ventas - Cesta
            self.ed_sc_ven_plus, self.ed_sc_ven_minus, self.ed_sc_ven_C, self.ed_sc_ven_X, self.ed_sc_ven_Z
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
                "consultar_precio": _normalize(self.ed_sc_prod_P.text(), "P"),
            }
            section["ventas"] = {
                "finalizar": _normalize(self.ed_sc_ven_V.text(), "V"),
                "consultar_precio": _normalize(self.ed_sc_ven_P.text(), "P"),
                "devolucion": _normalize(self.ed_sc_ven_D.text(), "D"),
                "whatsapp": _normalize(self.ed_sc_ven_W.text(), "W"),
                "imprimir": _normalize(self.ed_sc_ven_F.text(), "F"),
                "guardar_borrador": _normalize(self.ed_sc_ven_G.text(), "G"),
                "abrir_borradores": _normalize(self.ed_sc_ven_B.text(), "B"),
                "sumar": _normalize(self.ed_sc_ven_plus.text(), "+"),
                "restar": _normalize(self.ed_sc_ven_minus.text(), "-"),
                "editar_cantidad": _normalize(self.ed_sc_ven_C.text(), "C"),
                "descuento_item": _normalize(self.ed_sc_ven_X.text(), "X"),
                "vaciar_cesta": _normalize(self.ed_sc_ven_Z.text(), "Z"),
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

            # Autofocus checkboxes
            af_map = {}
            for af_key, chk in self._af_checks.items():
                af_map[af_key] = chk.isChecked()
            sc["autofocus"] = af_map

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
            self.ed_sc_prod_P.setText(DEFAULT_SECTION_MAP["productos"]["consultar_precio"])
            # Sección: Ventas
            self.ed_sc_ven_V.setText(DEFAULT_SECTION_MAP["ventas"]["finalizar"])
            self.ed_sc_ven_P.setText(DEFAULT_SECTION_MAP["ventas"]["consultar_precio"])
            self.ed_sc_ven_D.setText(DEFAULT_SECTION_MAP["ventas"]["devolucion"])
            self.ed_sc_ven_W.setText(DEFAULT_SECTION_MAP["ventas"]["whatsapp"])
            self.ed_sc_ven_F.setText(DEFAULT_SECTION_MAP["ventas"]["imprimir"])
            self.ed_sc_ven_G.setText(DEFAULT_SECTION_MAP["ventas"]["guardar_borrador"])
            self.ed_sc_ven_B.setText(DEFAULT_SECTION_MAP["ventas"]["abrir_borradores"])
            # Sección: Ventas - Cesta
            self.ed_sc_ven_plus.setText(DEFAULT_SECTION_MAP["ventas"]["sumar"])
            self.ed_sc_ven_minus.setText(DEFAULT_SECTION_MAP["ventas"]["restar"])
            self.ed_sc_ven_C.setText(DEFAULT_SECTION_MAP["ventas"]["editar_cantidad"])
            self.ed_sc_ven_X.setText(DEFAULT_SECTION_MAP["ventas"]["descuento_item"])
            self.ed_sc_ven_Z.setText(DEFAULT_SECTION_MAP["ventas"]["vaciar_cesta"])

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

        # ===== PÁGINA: DASHBOARD =====
        from app.gui.dashboard_config import DashboardConfigPanel
        page_dashboard = DashboardConfigPanel(self)
        try:
            page_dashboard.setMinimumSize(0, 0)
            page_dashboard.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.MinimumExpanding)
        except Exception:
            pass

        scr_dash = QScrollArea(tabs_cfg)
        scr_dash.setWidget(page_dashboard)
        scr_dash.setWidgetResizable(True)
        scr_dash.setFrameShape(QFrame.NoFrame)
        scr_dash.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scr_dash.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        tabs_cfg.addTab(scr_dash, "Dashboard")

        # ===== PÁGINA: ALERTAS =====
        page_alertas = QWidget()
        lay_alertas = QVBoxLayout(page_alertas)

        gb_alert_main = QGroupBox("Alertas por Email")
        lay_alert_main = QVBoxLayout(gb_alert_main)

        alert_info = QLabel(
            "Cuando ocurre un error critico (CAE, sincronizacion, base de datos), "
            "el sistema puede enviar un email automatico para que puedas actuar rapido.\n"
            "Usa la misma configuracion SMTP de Reportes & Envios."
        )
        alert_info.setWordWrap(True)
        alert_info.setStyleSheet("color: #888; font-size: 10px;")
        lay_alert_main.addWidget(alert_info)

        self.chk_alerts_enabled = QCheckBox("Habilitar alertas por email")
        lay_alert_main.addWidget(self.chk_alerts_enabled)

        form_alert = QFormLayout()

        self.ed_alert_recipients = QLineEdit()
        self.ed_alert_recipients.setPlaceholderText("email1@ejemplo.com, email2@ejemplo.com")
        self.ed_alert_recipients.setMinimumWidth(350)
        form_alert.addRow("Destinatarios:", self.ed_alert_recipients)

        alert_recip_info = QLabel(
            "Separar multiples emails con coma. Si esta vacio, usa los destinatarios de Reportes."
        )
        alert_recip_info.setWordWrap(True)
        alert_recip_info.setStyleSheet("color: #888; font-size: 10px;")
        form_alert.addRow("", alert_recip_info)

        self.spn_alert_cooldown = QSpinBox()
        self.spn_alert_cooldown.setRange(5, 1440)
        self.spn_alert_cooldown.setSuffix(" min")
        self.spn_alert_cooldown.setToolTip("Tiempo minimo entre alertas del mismo tipo")
        form_alert.addRow("Cooldown entre alertas:", self.spn_alert_cooldown)

        lay_alert_main.addLayout(form_alert)
        lay_alertas.addWidget(gb_alert_main)

        # Tipos de alerta
        gb_alert_types = QGroupBox("Tipos de alerta habilitados")
        lay_alert_types = QVBoxLayout(gb_alert_types)

        self.chk_alert_afip = QCheckBox("Error de facturacion AFIP / CAE")
        self.chk_alert_sync = QCheckBox("Sincronizacion Firebase offline / errores")
        self.chk_alert_db = QCheckBox("Error de base de datos")
        self.chk_alert_critical = QCheckBox("Errores criticos del sistema")

        lay_alert_types.addWidget(self.chk_alert_afip)
        lay_alert_types.addWidget(self.chk_alert_sync)
        lay_alert_types.addWidget(self.chk_alert_db)
        lay_alert_types.addWidget(self.chk_alert_critical)

        lay_alertas.addWidget(gb_alert_types)

        # Boton test
        row_alert_btns = QHBoxLayout()
        row_alert_btns.addStretch(1)

        btn_alert_test = QPushButton("  Enviar prueba  ")
        btn_alert_test.setMinimumWidth(180)
        btn_alert_test.setMinimumHeight(36)
        btn_alert_test.setStyleSheet("""
            QPushButton {
                background: #2e7d32; color: white;
                font-weight: bold; border-radius: 6px;
                padding: 6px 16px; font-size: 12px;
            }
            QPushButton:hover { background: #388e3c; }
        """)
        btn_alert_test.clicked.connect(self._test_alert_email)
        row_alert_btns.addWidget(btn_alert_test)

        btn_alert_save = QPushButton("  Guardar alertas  ")
        btn_alert_save.setMinimumWidth(180)
        btn_alert_save.setMinimumHeight(36)
        btn_alert_save.setStyleSheet("""
            QPushButton {
                background: #1a237e; color: white;
                font-weight: bold; border-radius: 6px;
                padding: 6px 16px; font-size: 12px;
            }
            QPushButton:hover { background: #283593; }
        """)
        btn_alert_save.clicked.connect(self._save_alert_config)
        row_alert_btns.addWidget(btn_alert_save)

        lay_alertas.addLayout(row_alert_btns)
        lay_alertas.addStretch(1)

        # Cargar config actual de alertas
        _alerts_raw = load_config()
        alerts_cfg = _alerts_raw.get("alerts", {})
        self.chk_alerts_enabled.setChecked(alerts_cfg.get("enabled", False))
        email_alert = alerts_cfg.get("email", {})
        self.ed_alert_recipients.setText(", ".join(email_alert.get("recipients", [])))
        self.spn_alert_cooldown.setValue(email_alert.get("cooldown_minutes", 30))
        types_alert = alerts_cfg.get("types", {})
        self.chk_alert_afip.setChecked(types_alert.get("afip_error", True))
        self.chk_alert_sync.setChecked(types_alert.get("sync_offline", True))
        self.chk_alert_db.setChecked(types_alert.get("db_error", True))
        self.chk_alert_critical.setChecked(types_alert.get("critical", True))

        scr_alertas = QScrollArea(tabs_cfg)
        scr_alertas.setWidget(page_alertas)
        scr_alertas.setWidgetResizable(True)
        scr_alertas.setFrameShape(QFrame.NoFrame)
        scr_alertas.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scr_alertas.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        tabs_cfg.addTab(scr_alertas, "Alertas")

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
        # Colores hover de botones
        try:
            th["btn_hover_bg"] = self.cfg_btn_hover_bg.property("color_val") or "#4CAF50"
            th["btn_hover_border"] = self.cfg_btn_hover_border.property("color_val") or "#388E3C"
        except Exception:
            pass
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
        # ---------- iva_discriminado ----------
        try:
            tk["iva_discriminado"] = {
                "mostrar_neto":  self.cfg_iva_neto.isChecked(),
                "mostrar_iva":   self.cfg_iva_iva.isChecked(),
                "mostrar_total": self.cfg_iva_total.isChecked(),
            }
        except Exception:
            pass
        # ---------- fuentes ticket ----------
        try:
            fonts = tk.get("fonts") or {}
            fonts["h1_pt"] = self.cfg_tk_font_h1.value()
            fonts["h2_pt"] = self.cfg_tk_font_h2.value()
            fonts["h3_pt"] = self.cfg_tk_font_h3.value()
            fonts["h4_pt"] = self.cfg_tk_font_h4.value()
            fonts["h5_pt"] = self.cfg_tk_font_h5.value()
            tk["fonts"] = fonts
        except Exception:
            pass
        # ---------- márgenes ticket ----------
        try:
            tk["margin_left_mm"] = self.cfg_margin_left.value()
            tk["margin_right_mm"] = self.cfg_margin_right.value()
        except Exception:
            pass
        # ---------- tamaño imágenes ticket ----------
        try:
            if hasattr(self, "cmb_img_size"):
                images = tk.get("images") or {}
                images["size_mm"] = self.cmb_img_size.currentData()
                tk["images"] = images
        except Exception:
            pass
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
        # Puntos de venta por sucursal
        try:
            pv_map = {}
            for suc_name, spn in getattr(self, "_fiscal_pv_spinners", {}).items():
                val = int(spn.value())
                if val > 0:
                    pv_map[suc_name] = val
            fisc["puntos_venta_por_sucursal"] = pv_map
        except Exception:
            pass
        try:
            fisc["tipo_cbte"] = self.cfg_cmb_fiscal_tipo.currentData() or "FACTURA_B"
        except Exception:
            pass
        try:
            fisc["cuit_predefinido"] = (self.cfg_edt_fiscal_cuit_cliente.text() or "").strip()
        except Exception:
            pass

        af = fisc.get("afipsdk") or {}
        try:
            af["api_key"] = (self.cfg_edt_fiscal_api_key.text() or "").strip()
            af["cert"] = (self.cfg_edt_fiscal_cert.text() or "").strip()
            af["key"] = (self.cfg_edt_fiscal_key.text() or "").strip()
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

    def _pick_color(self, btn):
        """Abre selector de color y actualiza el botón con el color elegido."""
        from PyQt5.QtWidgets import QColorDialog
        from PyQt5.QtGui import QColor
        current = btn.property("color_val") or "#4CAF50"
        color = QColorDialog.getColor(QColor(current), self, "Elegir color")
        if color.isValid():
            hex_color = color.name()
            btn.setStyleSheet(f"background-color: {hex_color}; border: 1px solid #888; border-radius: 4px;")
            btn.setProperty("color_val", hex_color)

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

        # Hover personalizado desde config (sobreescribe el default del tema)
        btn_hover_bg = th.get("btn_hover_bg") or btnhv
        btn_hover_border = th.get("btn_hover_border") or border

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
                border-radius: 6px;
                padding: 4px 8px;
                min-height: {control_h}px;
            }}
            QPushButton:hover {{
                background-color: {btn_hover_bg};
                border: 2px solid {btn_hover_border};
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
                background: {btn_hover_bg};
                border: 1px solid {btn_hover_border};
            }}
            QTabBar::tab:selected,
            QTabWidget QTabBar::tab:selected {{
                background: {btn_hover_bg};
                border: 2px solid {btn_hover_border};
            }}

            QHeaderView::section {{ background-color: {"#252525" if dark else "#f5f5f5"}; color: {text}; }}
            
            QPushButton[role="inline"] {{
                min-width: 0;          /* no se estiran */
                padding: 4px 8px;      /* más angosto */
                border-radius: 6px;
                min-height: {inline_h}px;
            }}
            QPushButton[role="inline"]:hover {{
                background-color: {btn_hover_bg};
                border: 1px solid {btn_hover_border};
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


    # --- Métodos para imágenes de ticket ---
    def _select_ticket_image(self, key):
        from PyQt5.QtWidgets import QFileDialog, QMessageBox
        from app.config import load as load_config, save as save_config, get_images_dir
        import shutil

        path, _ = QFileDialog.getOpenFileName(
            self, f"Seleccionar imagen PNG para {key}",
            "", "Imágenes PNG (*.png)"
        )
        if not path:
            return
        try:
            dest_dir = get_images_dir()
            filename = f"ticket_{key}.png"
            dest = os.path.join(dest_dir, filename)
            # Convertir a PNG si no lo es, y normalizar tamaño
            from PyQt5.QtGui import QPixmap
            pm = QPixmap(path)
            if pm.isNull():
                QMessageBox.warning(self, "Imagen", "No se pudo cargar la imagen.")
                return
            # Guardar como PNG
            pm.save(dest, "PNG")


            cfg = load_config()
            tk = cfg.get("ticket") or {}
            images = tk.get("images") or {}
            images[key] = filename
            tk["images"] = images
            cfg["ticket"] = tk
            save_config(cfg)

            if key in self._ticket_img_labels:
                self._ticket_img_labels[key].setText(os.path.basename(path))
            QMessageBox.information(self, "Imagen", f"Imagen '{key}' configurada.")
        except Exception as ex:
            QMessageBox.warning(self, "Imagen", f"Error al guardar imagen: {ex}")

    def _clear_ticket_image(self, key):
        from PyQt5.QtWidgets import QMessageBox
        from app.config import load as load_config, save as save_config

        cfg = load_config()
        tk = cfg.get("ticket") or {}
        images = tk.get("images") or {}
        images[key] = None
        tk["images"] = images
        cfg["ticket"] = tk
        save_config(cfg)

        if key in self._ticket_img_labels:
            self._ticket_img_labels[key].setText("(sin imagen)")
        QMessageBox.information(self, "Imagen", f"Imagen '{key}' eliminada.")

    def _generate_qr_from_url(self):
        from PyQt5.QtWidgets import QMessageBox
        from app.config import load as load_config, save as save_config, get_images_dir

        url = self.ed_qr_url.text().strip()
        if not url:
            QMessageBox.warning(self, "QR", "Ingresá una URL para generar el QR.")
            return
        try:
            import qrcode
            img = qrcode.make(url)
            dest = os.path.join(get_images_dir(), "ticket_qr.png")
            img.save(dest)

            cfg = load_config()
            tk = cfg.get("ticket") or {}
            images = tk.get("images") or {}
            images["qr"] = "ticket_qr.png"
            images["qr_url"] = url
            tk["images"] = images
            cfg["ticket"] = tk
            save_config(cfg)

            if "qr" in self._ticket_img_labels:
                self._ticket_img_labels["qr"].setText("ticket_qr.png")
            QMessageBox.information(self, "QR", "QR generado correctamente.")
        except ImportError:
            QMessageBox.warning(self, "QR", "Instale la librería 'qrcode':\npip install qrcode[pil]")
        except Exception as ex:
            QMessageBox.warning(self, "QR", f"Error generando QR: {ex}")

    def _seleccionar_archivo_afip(self, line_edit, filtro):
        """Abre diálogo para seleccionar archivo de certificado/clave."""
        path, _ = QFileDialog.getOpenFileName(self, "Seleccionar archivo", "", filtro)
        if path:
            line_edit.setText(path)

    def _consultar_ultimo_comprobante_afip(self):
        """Consulta el último número de comprobante autorizado en AFIP (por sucursal si corresponde)."""
        from PyQt5.QtWidgets import QMessageBox
        from app.config import load as load_config

        cfg = load_config()
        fiscal = cfg.get("fiscal", {})
        if not fiscal.get("enabled"):
            QMessageBox.warning(self, "AFIP", "La facturación electrónica no está habilitada.")
            return

        try:
            from app.afip_integration import crear_cliente_afip, resolver_punto_venta

            pv_map = fiscal.get("puntos_venta_por_sucursal") or {}
            sucursales_cfg = (cfg.get("business") or {}).get("sucursales") or {"Sarmiento": "", "Salta": ""}

            # Recopilar puntos de venta únicos a consultar
            pvs_a_consultar = {}  # {label: punto_venta}
            pv_global = int(fiscal.get("punto_venta", 1) or 1)

            has_per_suc = any(pv_map.get(s) for s in sucursales_cfg)
            if has_per_suc:
                for suc_name in sorted(sucursales_cfg.keys()):
                    pv = resolver_punto_venta(fiscal, suc_name)
                    pvs_a_consultar[suc_name] = pv
            else:
                pvs_a_consultar["Global"] = pv_global

            msg = "Último comprobante autorizado en AFIP:\n"

            for label, pv in pvs_a_consultar.items():
                msg += f"\n{'─'*30}\n"
                msg += f"  {label} (PV {pv}):\n"
                client = crear_cliente_afip(fiscal, sucursal=label if label != "Global" else "")
                if not client:
                    msg += "    No se pudo crear cliente\n"
                    continue
                try:
                    ultimo_b = client.get_ultimo_comprobante(client.FACTURA_B)
                    msg += f"    Factura B:  Nº {ultimo_b}  →  próximo: {ultimo_b + 1}\n"
                except Exception as e:
                    msg += f"    Factura B:  error: {e}\n"
                try:
                    ultimo_a = client.get_ultimo_comprobante(client.FACTURA_A)
                    msg += f"    Factura A:  Nº {ultimo_a}  →  próximo: {ultimo_a + 1}\n"
                except Exception:
                    pass

            QMessageBox.information(self, "AFIP - Último Comprobante", msg)
        except Exception as e:
            QMessageBox.warning(self, "AFIP", f"Error al consultar AFIP:\n{e}")

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

    # ------------------------------------------------------------------
    #  Alertas por Email
    # ------------------------------------------------------------------
    def _save_alert_config(self):
        """Guarda la configuracion de alertas."""
        from app.config import load as load_config, save as save_config
        from PyQt5.QtWidgets import QMessageBox

        cfg = load_config()

        # Parsear recipients
        raw = self.ed_alert_recipients.text().strip()
        recipients = [e.strip() for e in raw.split(",") if e.strip()] if raw else []

        cfg["alerts"] = {
            "enabled": self.chk_alerts_enabled.isChecked(),
            "email": {
                "recipients": recipients,
                "cooldown_minutes": self.spn_alert_cooldown.value(),
            },
            "types": {
                "afip_error": self.chk_alert_afip.isChecked(),
                "sync_offline": self.chk_alert_sync.isChecked(),
                "db_error": self.chk_alert_db.isChecked(),
                "critical": self.chk_alert_critical.isChecked(),
            },
        }
        save_config(cfg)
        QMessageBox.information(self, "Alertas", "Configuracion de alertas guardada.")

    def _test_alert_email(self):
        """Envia un email de prueba del sistema de alertas."""
        from PyQt5.QtWidgets import QMessageBox

        # Guardar primero
        self._save_alert_config()

        try:
            from app.alert_manager import AlertManager
            mgr = AlertManager.get_instance()

            # Parsear recipients del campo
            raw = self.ed_alert_recipients.text().strip()
            recipients = [e.strip() for e in raw.split(",") if e.strip()] if raw else None

            ok, err = mgr.send_test_alert(recipients=recipients)
            if ok:
                QMessageBox.information(
                    self, "Alertas",
                    "Email de prueba enviado correctamente.\n"
                    "Revisa tu bandeja de entrada."
                )
            else:
                QMessageBox.warning(
                    self, "Alertas",
                    f"No se pudo enviar el email de prueba:\n{err}\n\n"
                    f"Verifica la configuracion SMTP en la pestana Reportes & Envios."
                )
        except Exception as e:
            QMessageBox.warning(
                self, "Alertas",
                f"Error al enviar email de prueba:\n{e}"
            )
