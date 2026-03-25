# app/gui/dashboard_config.py
"""
Panel de configuracion del Dashboard web.
Permite personalizar titulo, cards visibles, columnas visibles,
intervalo de refresh, estilos (fuentes y colores), y sincronizar a Firebase.
"""
import logging

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QHBoxLayout, QGroupBox, QLabel,
    QCheckBox, QLineEdit, QPushButton, QMessageBox, QSpinBox, QScrollArea,
    QColorDialog, QFrame,
)
from app.config import load as load_config, save as save_config
from app.gui.qt_helpers import NoScrollComboBox

logger = logging.getLogger(__name__)


class DashboardConfigPanel(QWidget):
    """Panel de configuracion del dashboard web."""

    # Mapa de cards con sus labels
    CARD_LABELS = {
        "total_dia": "Total del dia",
        "efectivo": "Efectivo",
        "tarjeta": "Tarjeta",
        "cantidad": "Cantidad de ventas",
        "iva_ventas": "IVA Ventas (CAE)",
        "pagos_proveedores": "Pagos a Proveedores",
        "iva_compras": "IVA Compras",
    }

    # Mapa de columnas con sus labels
    COL_LABELS = {
        "ticket": "Ticket",
        "hora": "Hora",
        "sucursal": "Sucursal",
        "total": "Total",
        "pago": "Pago",
        "cuotas": "Cuotas",
        "cae": "CAE",
        "items": "Items",
    }

    # Colores configurables con sus labels
    COLOR_LABELS = {
        "color_header": "Header (fondo)",
        "color_card_total": "Card Total del dia",
        "color_efectivo": "Card Efectivo",
        "color_tarjeta": "Card Tarjeta",
        "color_cantidad": "Card Cantidad",
    }

    COLOR_DEFAULTS = {
        "color_header": "#1a237e",
        "color_card_total": "#1a237e",
        "color_efectivo": "#2e7d32",
        "color_tarjeta": "#ff9800",
        "color_cantidad": "#7b1fa2",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cfg = load_config()
        self._build_ui()
        self._load_config()

    # ------------------------------------------------------------------
    #  Utilidad: encontrar MainWindow subiendo por la jerarquia
    # ------------------------------------------------------------------
    def _find_main_window(self):
        """Recorre la jerarquia de parents hasta encontrar MainWindow."""
        w = self.parent()
        while w is not None:
            if hasattr(w, 'session') and hasattr(w, 'sucursal'):
                return w
            w = w.parent()
        return None

    # ------------------------------------------------------------------
    #  Construir la UI
    # ------------------------------------------------------------------
    def _build_ui(self):
        outer = QVBoxLayout(self)

        # Scroll area para todo el contenido
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        container = QWidget()
        root = QVBoxLayout(container)

        # ===== TITULO =====
        gb_titulo = QGroupBox("Titulo del Dashboard")
        lay_titulo = QFormLayout(gb_titulo)

        self.ed_titulo = QLineEdit()
        self.ed_titulo.setPlaceholderText("Tu Local 2025 - Dashboard")
        self.ed_titulo.setMinimumWidth(300)
        lay_titulo.addRow("Titulo:", self.ed_titulo)

        info = QLabel(
            "El titulo aparece en el header del dashboard web. "
            "Se sincroniza a Firebase para que el dashboard lo lea automaticamente."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #888; font-size: 10px;")
        lay_titulo.addRow(info)
        root.addWidget(gb_titulo)

        # ===== CARDS VISIBLES =====
        gb_cards = QGroupBox("Cards visibles en el Dashboard")
        lay_cards = QVBoxLayout(gb_cards)

        card_info = QLabel(
            "Selecciona que tarjetas de resumen se muestran en el dashboard web. "
            "Los cambios se aplican al guardar y sincronizar."
        )
        card_info.setWordWrap(True)
        card_info.setStyleSheet("color: #888; font-size: 10px;")
        lay_cards.addWidget(card_info)

        self.chk_cards = {}
        for key, label in self.CARD_LABELS.items():
            chk = QCheckBox(label)
            self.chk_cards[key] = chk
            lay_cards.addWidget(chk)

        root.addWidget(gb_cards)

        # ===== COLUMNAS VISIBLES =====
        gb_cols = QGroupBox("Columnas de la tabla de ventas")
        lay_cols = QVBoxLayout(gb_cols)

        col_info = QLabel(
            "Selecciona que columnas se muestran en la tabla de detalle de ventas. "
            "En moviles, algunas columnas se ocultan automaticamente por espacio."
        )
        col_info.setWordWrap(True)
        col_info.setStyleSheet("color: #888; font-size: 10px;")
        lay_cols.addWidget(col_info)

        self.chk_cols = {}
        for key, label in self.COL_LABELS.items():
            chk = QCheckBox(label)
            self.chk_cols[key] = chk
            lay_cols.addWidget(chk)

        root.addWidget(gb_cols)

        # ===== REFRESH INTERVAL =====
        gb_refresh = QGroupBox("Auto-refresh del Dashboard")
        lay_refresh = QFormLayout(gb_refresh)

        self.cmb_refresh = NoScrollComboBox()
        self.cmb_refresh.addItem("15 segundos", 15)
        self.cmb_refresh.addItem("30 segundos", 30)
        self.cmb_refresh.addItem("60 segundos", 60)
        self.cmb_refresh.addItem("120 segundos", 120)
        lay_refresh.addRow("Intervalo de auto-refresh:", self.cmb_refresh)

        refresh_info = QLabel(
            "Cada cuanto se actualizan automaticamente los datos en el dashboard web."
        )
        refresh_info.setWordWrap(True)
        refresh_info.setStyleSheet("color: #888; font-size: 10px;")
        lay_refresh.addRow(refresh_info)

        root.addWidget(gb_refresh)

        # ===== ESTILOS: TAMANOS DE FUENTE =====
        gb_fonts = QGroupBox("Tamanos de fuente")
        lay_fonts = QFormLayout(gb_fonts)

        font_info = QLabel(
            "Ajusta el tamano de texto (en pixeles) de cada elemento del dashboard. "
            "Los cambios se ven en el proximo refresh del dashboard web."
        )
        font_info.setWordWrap(True)
        font_info.setStyleSheet("color: #888; font-size: 10px;")
        lay_fonts.addRow(font_info)

        self.spn_font_titulo = QSpinBox()
        self.spn_font_titulo.setRange(14, 48)
        self.spn_font_titulo.setSuffix(" px")
        lay_fonts.addRow("Titulo (header):", self.spn_font_titulo)

        self.spn_font_cards = QSpinBox()
        self.spn_font_cards.setRange(16, 60)
        self.spn_font_cards.setSuffix(" px")
        lay_fonts.addRow("Valores de cards:", self.spn_font_cards)

        self.spn_font_labels = QSpinBox()
        self.spn_font_labels.setRange(8, 24)
        self.spn_font_labels.setSuffix(" px")
        lay_fonts.addRow("Labels de cards:", self.spn_font_labels)

        self.spn_font_tabla = QSpinBox()
        self.spn_font_tabla.setRange(10, 24)
        self.spn_font_tabla.setSuffix(" px")
        lay_fonts.addRow("Texto de tabla:", self.spn_font_tabla)

        root.addWidget(gb_fonts)

        # ===== ESTILOS: COLORES =====
        gb_colors = QGroupBox("Colores del Dashboard")
        lay_colors = QFormLayout(gb_colors)

        color_info = QLabel(
            "Personaliza los colores principales del dashboard web. "
            "Haz clic en el boton para abrir el selector de color."
        )
        color_info.setWordWrap(True)
        color_info.setStyleSheet("color: #888; font-size: 10px;")
        lay_colors.addRow(color_info)

        self.color_btns = {}
        for key, label in self.COLOR_LABELS.items():
            btn = QPushButton("  ")
            btn.setFixedSize(60, 28)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setProperty("color_key", key)
            btn.clicked.connect(lambda checked, k=key: self._pick_color(k))
            self.color_btns[key] = btn
            lay_colors.addRow(f"{label}:", btn)

        # Boton restaurar colores por defecto
        btn_reset_colors = QPushButton("Restaurar colores por defecto")
        btn_reset_colors.setStyleSheet(
            "color: #666; font-size: 11px; border: 1px solid #ccc; "
            "border-radius: 4px; padding: 4px 12px;"
        )
        btn_reset_colors.clicked.connect(self._reset_colors)
        lay_colors.addRow("", btn_reset_colors)

        root.addWidget(gb_colors)

        # ===== BOTONES =====
        row_btns = QHBoxLayout()
        row_btns.addStretch(1)

        btn_save = QPushButton("  Guardar y sincronizar  ")
        btn_save.setMinimumWidth(220)
        btn_save.setMinimumHeight(40)
        btn_save.setStyleSheet("""
            QPushButton {
                background: #1a237e; color: white;
                font-weight: bold; border-radius: 6px;
                padding: 8px 20px; font-size: 13px;
            }
            QPushButton:hover { background: #283593; }
        """)
        btn_save.clicked.connect(self._save_and_sync)
        row_btns.addWidget(btn_save)

        root.addLayout(row_btns)
        root.addStretch(1)

        scroll.setWidget(container)
        outer.addWidget(scroll)

    # ------------------------------------------------------------------
    #  Color picker helpers
    # ------------------------------------------------------------------
    def _update_color_btn(self, key, color_hex):
        """Actualiza el estilo del boton de color para mostrar el color actual."""
        btn = self.color_btns.get(key)
        if btn:
            btn.setStyleSheet(
                f"background: {color_hex}; border: 2px solid #999; border-radius: 4px;"
            )
            btn.setToolTip(color_hex)

    def _pick_color(self, key):
        """Abre el selector de color para la clave dada."""
        btn = self.color_btns.get(key)
        if not btn:
            return
        from PyQt5.QtGui import QColor
        current = btn.toolTip() or self.COLOR_DEFAULTS.get(key, "#000000")
        color = QColorDialog.getColor(QColor(current), self, f"Color: {self.COLOR_LABELS.get(key, key)}")
        if color.isValid():
            self._update_color_btn(key, color.name())

    def _reset_colors(self):
        """Restaura todos los colores a sus valores por defecto."""
        for key, default in self.COLOR_DEFAULTS.items():
            self._update_color_btn(key, default)

    # ------------------------------------------------------------------
    #  Cargar config actual en la UI
    # ------------------------------------------------------------------
    def _load_config(self):
        """Populate UI from config."""
        dash = self.cfg.get("dashboard", {})

        self.ed_titulo.setText(dash.get("titulo", "Tu Local 2025 - Dashboard"))

        cards_vis = dash.get("cards_visibles", {})
        for key, chk in self.chk_cards.items():
            chk.setChecked(bool(cards_vis.get(key, True)))

        cols_vis = dash.get("columnas_visibles", {})
        for key, chk in self.chk_cols.items():
            chk.setChecked(bool(cols_vis.get(key, True)))

        interval = dash.get("refresh_interval", 30)
        idx = self.cmb_refresh.findData(interval)
        if idx >= 0:
            self.cmb_refresh.setCurrentIndex(idx)

        # Estilos
        estilos = dash.get("estilos", {})
        self.spn_font_titulo.setValue(estilos.get("font_size_titulo", 22))
        self.spn_font_cards.setValue(estilos.get("font_size_cards", 28))
        self.spn_font_labels.setValue(estilos.get("font_size_labels", 12))
        self.spn_font_tabla.setValue(estilos.get("font_size_tabla", 14))

        for key, default in self.COLOR_DEFAULTS.items():
            color_hex = estilos.get(key, default)
            self._update_color_btn(key, color_hex)

    # ------------------------------------------------------------------
    #  Guardar + sincronizar a Firebase
    # ------------------------------------------------------------------
    def _save_and_sync(self):
        """Save to local config + push to Firebase."""
        cfg = load_config()

        # Recoger colores de los botones
        estilos = {
            "font_size_titulo": self.spn_font_titulo.value(),
            "font_size_cards": self.spn_font_cards.value(),
            "font_size_labels": self.spn_font_labels.value(),
            "font_size_tabla": self.spn_font_tabla.value(),
        }
        for key, default in self.COLOR_DEFAULTS.items():
            btn = self.color_btns.get(key)
            estilos[key] = (btn.toolTip() if btn else default) or default

        dash = {
            "titulo": self.ed_titulo.text().strip() or "Tu Local 2025 - Dashboard",
            "cards_visibles": {k: chk.isChecked() for k, chk in self.chk_cards.items()},
            "columnas_visibles": {k: chk.isChecked() for k, chk in self.chk_cols.items()},
            "refresh_interval": self.cmb_refresh.currentData() or 30,
            "estilos": estilos,
        }
        cfg["dashboard"] = dash
        save_config(cfg)
        logger.info("[Dashboard] Config guardada localmente")

        # Intentar sincronizar a Firebase
        synced = False
        try:
            mw = self._find_main_window()
            firebase_sync = getattr(mw, '_firebase_sync', None) if mw else None
            if firebase_sync and hasattr(firebase_sync, '_firebase_put'):
                ok = firebase_sync._firebase_put("config/dashboard", dash)
                synced = bool(ok is not None)
                if synced:
                    logger.info("[Dashboard] Config sincronizada a Firebase")
            else:
                # Fallback: REST directo con credenciales de config
                sync_cfg = cfg.get("sync", {})
                fb = sync_cfg.get("firebase", {})
                db_url = (fb.get("database_url") or "").rstrip("/")
                token = fb.get("auth_token") or ""
                if db_url and token:
                    import json
                    import urllib.request
                    url = f"{db_url}/config/dashboard.json?auth={token}"
                    data = json.dumps(dash).encode("utf-8")
                    req = urllib.request.Request(
                        url, data=data, method="PUT",
                        headers={"Content-Type": "application/json"}
                    )
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        synced = (resp.status == 200)
                    if synced:
                        logger.info("[Dashboard] Config sincronizada via REST directo")
        except Exception as e:
            logger.warning("[Dashboard] Error al sincronizar: %s", e)
            QMessageBox.warning(
                self, "Dashboard",
                f"Configuracion guardada localmente, pero hubo un error "
                f"al sincronizar con Firebase:\n{e}"
            )
            return

        if synced:
            QMessageBox.information(
                self, "Dashboard",
                "Configuracion guardada y sincronizada con Firebase.\n"
                "El dashboard web aplicara los cambios en el proximo refresh."
            )
        else:
            QMessageBox.information(
                self, "Dashboard",
                "Configuracion guardada localmente.\n"
                "Para sincronizar con el dashboard web, activa la sincronizacion "
                "Firebase en la pestana Sincronizacion."
            )
