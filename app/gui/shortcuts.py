# -*- coding: utf-8 -*-
from typing import Callable, Dict, Optional
from dataclasses import dataclass
from PyQt5.QtCore import QObject, Qt
from PyQt5.QtWidgets import QShortcut, QLabel, QStatusBar, QApplication, QStyle
from PyQt5.QtGui import QKeySequence, QIcon
from app.config import load as load_config, save as save_config

@dataclass
class SectionMap:
    # letras (sin Ctrl+Shift en el config; el gestor las registra como Ctrl+Shift+letra)
    # usar "Delete" para Supr
    mapping: Dict[str, str]

DEFAULT_SECTION_MAP = {
    "productos": {"agregar": "A", "editar": "E", "eliminar": "Delete", "imprimir_codigo": "I"},
    "ventas":    {"finalizar": "V", "efectivo": "E", "tarjeta": "T", "devolucion": "D", "whatsapp": "W", "imprimir": "F", "guardar_borrador": "G", "abrir_borradores": "B", "sumar": "+", "restar": "-", "editar_cantidad": "C", "descuento_item": "X", "vaciar_cesta": "Z"},
}

DEFAULT_GLOBAL_MAP = {
    "productos": "F1",
    "proveedores": "F2",
    "ventas": "F3",
    "historial": "F4",
    "configuraciones": "F5",
    "usuarios": "F6",
}

def _cfg_shortcuts():
    cfg = load_config()
    sc = cfg.get("shortcuts") or {}
    if "global" not in sc:
        sc["global"] = dict(DEFAULT_GLOBAL_MAP)
    if "section" not in sc:
        sc["section"] = dict(DEFAULT_SECTION_MAP)
    if "section_mode_enabled" not in sc:
        sc["section_mode_enabled"] = True
    cfg["shortcuts"] = sc
    save_config(cfg)
    return sc

class ShortcutManager(QObject):
    """
    - Registra F1..F6 (globales) para cambiar de pestaña.
    - Registra Ctrl+Shift+S para activar/desactivar 'modo por sección'.
    - Registra atajos por sección (Ctrl+Shift+letra), habilitando sólo los de la pestaña visible.
    - Muestra icono ON/OFF en la StatusBar (esquina inferior derecha).
    - Emite callbacks a la MainWindow (callables) sin acoplarla a nombres de métodos.
    """
    def __init__(self, main_window, callbacks: Optional[Dict[str, Callable]] = None):
        super().__init__(main_window)
        self.w = main_window
        self.callbacks = callbacks or {}
        self._shortcuts_global = []
        self._shortcuts_section: Dict[str, QShortcut] = {}
        self._current_section_key = None
        self._icon_label: Optional[LabeledIcon] = None

        sc = _cfg_shortcuts()
        self._global_map = dict(sc.get("global", {}))
        self._section_map = dict(sc.get("section", {}))
        self._section_mode_enabled = bool(sc.get("section_mode_enabled", True))

        # Icono ON/OFF en StatusBar
        self._ensure_status_icon()

        # Registrar globales (F1..F6)
        self._register_global_shortcuts()

        # Toggle del modo sección
        self._shortcut_toggle = QShortcut(QKeySequence("Ctrl+Shift+S"), self.w)
        self._shortcut_toggle.activated.connect(self.toggle_section_mode)

        # Registrar por sección para la pestaña inicial
        self.set_section_by_tabindex(self.w.tabs.currentIndex())

        # Seguir cambios de pestaña
        self.w.tabs.currentChanged.connect(self.set_section_by_tabindex)

        # Interceptar +/-/letras de cesta en QLineEdits de ventas
        QApplication.instance().installEventFilter(self)

    # ---------- Status icon ----------
    def _ensure_status_icon(self):
            sb = self.w.statusBar() if hasattr(self.w, "statusBar") else None
            if not sb:
                sb = self.w.statusBar()
            self._status_toggle = StatusToggleWidget(parent=self.w)
            self._status_toggle.clicked.connect(self.toggle_section_mode)
            sb.addPermanentWidget(self._status_toggle, stretch=0)
            self._refresh_icon()

    def _refresh_icon(self):
        # Texto del tooltip aclara el comportamiento
        txt_on  = "Atajos por sección ACTIVOS — usan solo la letra (A/E/...). Ctrl+Shift+S para desactivar."
        txt_off = "Atajos por sección INACTIVOS — requieren Ctrl+Shift+letra. Ctrl+Shift+S para activar."
        self._status_toggle.set_state(
            enabled=self._section_mode_enabled,
            tooltip_on=txt_on,
            tooltip_off=txt_off,
        )



    # ---------- Registro ----------
    def _register_global_shortcuts(self):
        # Limpia anteriores
        for sc in self._shortcuts_global:
            try: sc.setParent(None)
            except Exception: pass
        self._shortcuts_global.clear()

        # Mapa: pestaña -> índice (resuelto por MainWindow)
        for tabname, key in self._global_map.items():
            if not key: continue
            s = QShortcut(QKeySequence(key), self.w)
            s.activated.connect(lambda tn=tabname: self._invoke("nav." + tn))
            s.setContext(Qt.ApplicationShortcut)
            self._shortcuts_global.append(s)


    def _enable_all_globals(self):
        """Reactiva todos los atajos globales (F1..F6)."""
        for sc in self._shortcuts_global:
            try:
                sc.setEnabled(True)
            except Exception:
                pass
            
    def _disable_all_globals(self):
        """Desactiva temporalmente TODOS los atajos globales (F1..F6)."""
        for sc in self._shortcuts_global:
            try:
                sc.setEnabled(False)
            except Exception:
                pass


    def _mute_global_key(self, key_text: str):
        """
        Desactiva el/los atajo(s) global(es) cuyo QKeySequence coincide con key_text (p.ej. 'F1').
        Se llama cuando la sección activa usa esa F-key.
        """
        kt = (key_text or "").strip()
        if not kt:
            return
        for sc in self._shortcuts_global:
            try:
                # toString() da 'F1', 'F2', etc. en el locale actual
                if sc.key().toString().upper() == kt.upper():
                    sc.setEnabled(False)
            except Exception:
                pass


    def _clear_section_shortcuts(self):
        for k, sc in list(self._shortcuts_section.items()):
            try: sc.setParent(None)
            except Exception: pass
        self._shortcuts_section.clear()

    def _register_section_shortcuts(self, section_key: str):
        # Siempre (re)registramos; la diferencia es la COMBINACIÓN según el toggle.
        self._clear_section_shortcuts()
        self._current_section_key = section_key
        mapping = self._section_map.get(section_key, {}) or {}
        if not mapping:
        # No hay atajos para esta sección: reactivá globales por las dudas
            self._enable_all_globals()
            return

        # 1) Reactivar TODOS los globales y luego mutear solo los que choquen
        self._enable_all_globals()

        def _is_function_key(s: str) -> bool:
            # Acepta 'F1'..'F12' (may/min indistinto)
            s = (s or "").strip().upper()
            if not s.startswith("F"): return False
            try:
                n = int(s[1:])
                return 1 <= n <= 12
            except Exception:
                return False

        for action, keytxt in mapping.items():
            if not keytxt:
                continue

            kt = (keytxt or "").strip()

            # Regla especial: 'Delete' SIEMPRE sin combinaciones
            if kt.lower() == "delete" or action.lower() == "eliminar":
                keyseq = "Delete"

            # Teclas especiales que siempre van literales
            elif kt in ("+", "-"):
                keyseq = kt

            # Función: F1..F12 (siempre literal, ignora el toggle)
            elif _is_function_key(kt):
                keyseq = kt.upper()
                # Mutea global que use esta misma F-key
                self._mute_global_key(keyseq)

            else:
                # Letras: Toggle ON → letra sola; Toggle OFF → Ctrl+Shift+letra
                keyseq = kt if self._section_mode_enabled else f"Ctrl+Shift+{kt}"

            s = QShortcut(QKeySequence(keyseq), self.w)
            # Para que funcione aunque el foco esté en tablas/otros widgets
            s.setContext(Qt.ApplicationShortcut)
            s.activated.connect(lambda act=action: self._invoke(f"{section_key}.{act}"))
            self._shortcuts_section[action] = s



    # ---------- Toggle & sección vigente ----------
    def toggle_section_mode(self):
        self._section_mode_enabled = not self._section_mode_enabled
        cfg = load_config()
        sc = cfg.get("shortcuts") or {}
        sc["section_mode_enabled"] = self._section_mode_enabled
        cfg["shortcuts"] = sc
        save_config(cfg)
        # re-registrar los atajos de la sección visible
        self._register_section_shortcuts(self._current_section_key or self._guess_section_key())
        self._refresh_icon()

    def _guess_section_key(self) -> Optional[str]:
        ix = self.w.tabs.currentIndex()
        return self._tabindex_to_section(ix)
    
    def reload_from_config(self, reapply_current: bool = True):
        """
        Recarga los atajos desde la configuración persistida y re-registra
        globales y seccionales al instante (sin reiniciar la app).
        """
        try:
            sc = _cfg_shortcuts()  # lee config actual
            # Actualizar mapas en memoria
            self._global_map = dict(sc.get("global", {}))
            self._section_map = dict(sc.get("section", {}))
            self._section_mode_enabled = bool(sc.get("section_mode_enabled", True))
        except Exception:
            pass

        # Re-registrar globales
        try:
            self._register_global_shortcuts()
        except Exception:
            pass

        # Re-registrar atajos de la sección visible
        try:
            if reapply_current:
                self._register_section_shortcuts(self._current_section_key or self._guess_section_key())
        except Exception:
            pass

        # Refrescar indicador ON/OFF
        try:
            self._refresh_icon()
        except Exception:
            pass


    def set_section_by_tabindex(self, ix: int):
        key = self._tabindex_to_section(ix)
        self._register_section_shortcuts(key)

    def _tabindex_to_section(self, ix: int) -> Optional[str]:
        try:
            text = (self.w.tabs.tabText(ix) or "").strip().lower()
        except Exception:
            return None
        return self._text_to_section_key(text)

    def _text_to_section_key(self, text: str) -> Optional[str]:
        t = text.lower()
        if any(w in t for w in ("producto", "productos")):      return "productos"
        if any(w in t for w in ("proveedor", "proveedores")):    return "proveedores"
        if "venta" in t:                                         return "ventas"
        if "historial" in t:                                     return "historial"
        if any(w in t for w in ("config", "configuración", "configuraciones")):  return "configuraciones"
        if any(w in t for w in ("usuario", "usuarios")):         return "usuarios"
        return None

    def get_tab_index_for(self, logical_name: str) -> Optional[int]:
        n = self.w.tabs.count()
        for i in range(n):
            key = self._tabindex_to_section(i)
            if key == logical_name:
                return i
        return None

    # ---------- INDICADOR ----------

    def eventFilter(self, obj, event):
        """Intercepta teclas +/-/X/C/Z en QLineEdits para que funcionen como atajos de cesta."""
        try:
            from PyQt5.QtCore import QEvent
            if event.type() != QEvent.KeyPress:
                return False

            if not self._section_mode_enabled:
                return False

            if self._current_section_key != "ventas":
                return False

            from PyQt5.QtWidgets import QLineEdit
            if not isinstance(obj, QLineEdit):
                return False

            key_text = event.text()
            mapping = self._section_map.get("ventas", {})

            # Build reverse map of key -> action for special keys
            intercept_keys = {}
            for action, kt in mapping.items():
                kt_stripped = (kt or "").strip()
                if kt_stripped in ("+", "-"):
                    intercept_keys[kt_stripped] = action
                elif action in ("editar_cantidad", "descuento_item", "vaciar_cesta"):
                    # Single letter keys for cart actions
                    intercept_keys[kt_stripped.lower()] = action
                    intercept_keys[kt_stripped.upper()] = action

            if key_text in intercept_keys:
                action = intercept_keys[key_text]
                full_key = f"ventas.{action}"
                # Only intercept if it's in ALWAYS_ALLOWED
                cb = self.callbacks.get(full_key)
                if callable(cb):
                    cb()
                    return True  # consume the event
        except Exception:
            pass
        return False

    def _invoke(self, key: str):
        """
        Invoca el callback asociado a 'key'.

        - Si el modo por sección está activo, evitamos que las letras "roben"
          teclas mientras el usuario escribe en un input.
        - PERO dejamos pasar siempre los atajos globales nav.* (F1..F6),
          aunque el foco esté en el buscador.
        - También permitimos ciertos atajos específicos (borradores) que son útiles
          incluso cuando se está editando.
        """
        # Lista blanca de atajos que siempre funcionan, incluso con foco en input
        ALWAYS_ALLOWED = [
            "ventas.finalizar",
            "ventas.guardar_borrador",
            "ventas.abrir_borradores",
            "ventas.sumar",
            "ventas.restar",
            "ventas.editar_cantidad",
            "ventas.descuento_item",
            "ventas.vaciar_cesta",
        ]

        try:
            if self._section_mode_enabled and not key.startswith("nav.") and key not in ALWAYS_ALLOWED:
                from PyQt5.QtWidgets import QLineEdit, QTextEdit, QPlainTextEdit
                fw = QApplication.focusWidget()
                if isinstance(fw, (QLineEdit, QTextEdit, QPlainTextEdit)):
                    return
        except Exception:
            pass

        cb = self.callbacks.get(key)
        if callable(cb):
            cb()
        else:
            try:
                from PyQt5.QtWidgets import QMessageBox
                QMessageBox.information(self.w, "Acción", f"Acción no conectada: {key}")
            except Exception:
                pass


    # ---------- Ayuda ----------
    def get_shortcuts_help(self) -> str:
        sc = _cfg_shortcuts()
        global_map = sc.get("global", {})
        section_map = sc.get("section", {})
        lines = ["<b>Atajos globales</b>:"]
        for k in ("productos","proveedores","ventas","historial","configuraciones","usuarios"):
            if k in global_map:
                lines.append(f"• {global_map[k]} → {k.capitalize()}")
        lines.append("")
        lines.append("<b>Atajos por sección</b> (Ctrl+Shift + letra; Supr sin combinaciones):")
        for sec, mmap in section_map.items():
            pretty = ", ".join([f"{act} = {mmap[act]}" for act in mmap])
            lines.append(f"• {sec.capitalize()}: {pretty}")
        lines.append("")
        lines.append("<b>Atajos de cesta (Ventas)</b>: +/- sumar/restar cantidad, C editar cantidad, X descuento ítem, Z vaciar cesta.")
        lines.append("")
        lines.append("Toggle: Ctrl+Shift+S (activa/desactiva atajos por sección)")
        return "<br>".join(lines)

# --- Widget vistoso en la StatusBar (icono + pill ON/OFF, clickeable) ---
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel
from PyQt5.QtCore import pyqtSignal

class StatusToggleWidget(QWidget):
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._icon = QLabel(self)
        self._pill = QLabel(self)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 0, 8, 0)
        lay.setSpacing(6)
        lay.addWidget(self._icon)
        lay.addWidget(self._pill)
        self.setCursor(Qt.PointingHandCursor)
        self._apply_off_style()

    def mouseReleaseEvent(self, ev):
        self.clicked.emit()
        super().mouseReleaseEvent(ev)

    def set_state(self, enabled: bool, tooltip_on: str, tooltip_off: str):
        style = QApplication.style()
        if enabled:
            ico = style.standardIcon(QStyle.SP_DialogYesButton)
            self._icon.setPixmap(ico.pixmap(18, 18))
            self._pill.setText("Atajos de teclas activos")
            self._apply_on_style()
            self.setToolTip(tooltip_on)
        else:
            ico = style.standardIcon(QStyle.SP_DialogNoButton)
            self._icon.setPixmap(ico.pixmap(18, 18))
            self._pill.setText("Atajos de teclas desactivados")
            self._apply_off_style()
            self.setToolTip(tooltip_off)

    def _apply_on_style(self):
        self._pill.setStyleSheet(
            "QLabel { padding: 2px 8px; border-radius: 10px; "
            "background: #1e7e34; color: white; font-weight: 600; }"
        )

    def _apply_off_style(self):
        self._pill.setStyleSheet(
            "QLabel { padding: 2px 8px; border-radius: 10px; "
            "background: #ff0000; color: white; font-weight: 600; }"
        )
