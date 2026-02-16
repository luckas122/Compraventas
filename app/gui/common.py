# Auto-generado: separación de GUI sin cambios funcionales
import logging
import os, sys
from PyQt5.QtCore import Qt, QSize, QEvent, QObject
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QCheckBox
from pathlib import Path

logger = logging.getLogger(__name__)

# Mantener ruta de iconos respecto a esta ubicación (app/gui/ -> ../../icons)
_here = Path(__file__).resolve()
_dist = Path(getattr(sys, "executable", "")) .parent if getattr(sys, "frozen", False) else _here.parents[3]
_candidates = [
    _here.parents[2] / "icons",                 # .../repo/icons
    _dist / "_internal" / "icons",              # dist/_internal/icons
    _dist / "icons",                            # dist/icons (espejo)
]
for _p in _candidates:
    if _p.exists():
        BASE_ICONS_PATH = str(_p)
        break
else:
    BASE_ICONS_PATH = str(_candidates[-1])
MIN_BTN_HEIGHT = 60
ICON_SIZE = QSize(32, 32)
# --- Live Search (Ventas) ---
LIVE_SEARCH_FONT_PT = 14          # tamaño de letra del popup
LIVE_SEARCH_ROW_PAD = 8           # padding vertical por ítem
LIVE_SEARCH_MIN_WIDTH = 520       # ancho mínimo del popup
LIVE_SEARCH_INPUT_HEIGHT = 36     # alto del QLineEdit de ventas

def icon(name):
    full = os.path.join(BASE_ICONS_PATH, name)
    if not os.path.exists(full):
        logger.warning("Icono no encontrado: %s", full)
    return QIcon(full)

def _safe_viewport(table):
    try:
        return table.viewport() if table is not None else None
    except Exception:
        return None

class FullCellCheckFilter(QObject):
    def __init__(self, table, check_col, parent=None):
        super().__init__(parent)
        self.table = table
        self.check_col = check_col

    def eventFilter(self, obj, event):
        vp = _safe_viewport(self.table)
        if obj is vp and event.type() == QEvent.MouseButtonRelease:
            index = self.table.indexAt(event.pos())
            if index.isValid() and index.column() == self.check_col:
                w = self.table.cellWidget(index.row(), self.check_col)
                if w:
                    box = w.findChild(QCheckBox)
                    if box:
                        box.toggle()
                        return True
        return False

def _mouse_release_event_type():
    # Si alguna vez migrás a PyQt6, solo cambiás esto
    return QEvent.MouseButtonRelease

def _checked_states():
    return (Qt.Checked, Qt.Unchecked)

# --- Estilo para botones dentro de celdas (acciones) ---
CELL_BTN_RADIUS = 11
CELL_BTN_PADDING = 0  # sin padding para que no se corten

CELL_BUTTONS_CSS = f"""
QPushButton[role="cell"] {{
  border: 1px solid rgba(120,120,140,0.25);
  border-radius: {CELL_BTN_RADIUS}px;
  padding: {CELL_BTN_PADDING}px;
  background: transparent;
}}
QPushButton[role="cell"]:hover {{
  background: #e9e6ff;   /* celeste-violeta suave */
}}
"""

# --- Estilos centralizados para TODOS los botones ---
BUTTON_STYLES = """
/* Botón primario (azul) */
QPushButton[role="primary"] {
    background-color: #1976d2;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: bold;
}
QPushButton[role="primary"]:hover {
    background-color: #1565c0;
}
QPushButton[role="primary"]:pressed {
    background-color: #0d47a1;
}

/* Botón secundario (gris) */
QPushButton[role="secondary"] {
    background-color: #f5f5f5;
    color: #333;
    border: 1px solid #ccc;
    border-radius: 6px;
    padding: 8px 16px;
}
QPushButton[role="secondary"]:hover {
    background-color: #e0e0e0;
}

/* Botón peligro (rojo) */
QPushButton[role="danger"] {
    background-color: #d32f2f;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: bold;
}
QPushButton[role="danger"]:hover {
    background-color: #c62828;
}

/* Botón éxito (verde) */
QPushButton[role="success"] {
    background-color: #2e7d32;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: bold;
}
QPushButton[role="success"]:hover {
    background-color: #1b5e20;
}

/* Hover genérico para botones sin role */
QPushButton:hover {
    background-color: rgba(0, 0, 0, 0.05);
}

/* Botón inline (pequeño, para dentro de formularios) */
QPushButton[role="inline"] {
    border: 1px solid rgba(120,120,140,0.3);
    border-radius: 4px;
    padding: 2px 8px;
    background: transparent;
}
QPushButton[role="inline"]:hover {
    background: #e3f2fd;
}
"""
