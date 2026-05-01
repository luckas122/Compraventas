# app/audit_logger.py
# -*- coding: utf-8 -*-
"""
Logger de actividad de alto nivel ("audit log").

Captura eventos relevantes para auditoria sin recolectar passwords ni datos
sensibles:
  - Clicks en QPushButton con texto > 3 chars (excluye botones sin label).
  - KeyPress: F1..F12 y atajos Ctrl+letra (skip QLineEdit Password / objectName "pass"/"clave").
  - TAB_CHANGE: cambio de pestaña en QTabWidget (via wire_tab_widgets()).
  - Apertura/cierre de QDialog (Show/Close).
  - Eventos custom registrados via audit_logger.log_action(...).

Salida: archivo "activity.log" en `audit.log_dir` (config) o, por defecto,
%APPDATA%/CompraventasV2/logs/.

Retencion: archivos de log mas viejos que `retention_days` (config) se borran
al arrancar la app.

Uso tipico (desde core.py post-login):
    from app.audit_logger import install_audit_filter, get_audit_logger, wire_tab_widgets

    install_audit_filter(QApplication.instance(),
        username_provider=lambda: "admin",
        sucursal_provider=lambda: "Sarmiento")
    wire_tab_widgets(self)              # despues de crear todas las tabs
    get_audit_logger().log_action("LOGIN", "user=admin")
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from typing import Callable, Optional

from PyQt5.QtCore import QObject, QEvent, Qt
from PyQt5.QtWidgets import QPushButton, QTabWidget, QDialog, QLineEdit, QApplication

from app.config import load as _load_cfg, _get_log_dir

_LOG_FILENAME = "activity.log"

# Rotacion (espejo de logging_setup pero con archivo dedicado)
_MAX_BYTES = 5 * 1024 * 1024
_BACKUP_COUNT = 5
_FORMAT = "[%(asctime)s] %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"


def _resolve_log_dir() -> str:
    """Resuelve la carpeta de log de auditoria desde config, con fallback al default.

    Si `audit.log_dir` esta configurado y es escribible, lo usa. Caso contrario,
    cae al default `%APPDATA%/CompraventasV2/logs`.
    """
    try:
        cfg_dir = ((_load_cfg().get("audit") or {}).get("log_dir") or "").strip()
    except Exception:
        cfg_dir = ""
    if cfg_dir:
        try:
            os.makedirs(cfg_dir, exist_ok=True)
            if os.access(cfg_dir, os.W_OK):
                return cfg_dir
        except Exception:
            pass
    return _get_log_dir()


def _make_audit_handler(path: str) -> RotatingFileHandler:
    h = RotatingFileHandler(path, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8")
    h.setLevel(logging.DEBUG)
    h.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATEFMT))
    h._compraventas_managed = True  # type: ignore[attr-defined]
    return h


class _AuditLogger:
    """Wrapper alrededor de un logger Python con metodos semanticos."""

    def __init__(self):
        self._logger = logging.getLogger("activity")
        self._logger.setLevel(logging.DEBUG)
        # No propagar a root (queremos archivo dedicado, no duplicar a app.log)
        self._logger.propagate = False

        self._username_provider: Optional[Callable[[], str]] = None
        self._sucursal_provider: Optional[Callable[[], str]] = None
        self._enabled = True
        self._current_path: str = ""
        # v6.6.3: rastrear tipos de excepcion en _ctx para no spamear el log
        self._reported_ctx_errors: set = set()

        # Configurar handler inicial
        self._install_handler(_resolve_log_dir())

    def _install_handler(self, log_dir: str) -> None:
        """Instala el RotatingFileHandler en `log_dir/activity.log`.

        Cierra y remueve cualquier handler de auditoria previo del mismo logger.
        Idempotente.
        """
        # Remover handlers manejados por nosotros previamente
        for h in list(self._logger.handlers):
            if getattr(h, "_compraventas_managed", False):
                try:
                    self._logger.removeHandler(h)
                    h.close()
                except Exception:
                    pass
        path = os.path.join(log_dir, _LOG_FILENAME)
        try:
            handler = _make_audit_handler(path)
            self._logger.addHandler(handler)
            self._current_path = os.path.abspath(path)
        except Exception as e:
            # No dejar al logger sin handler: usar app.log como fallback
            logging.getLogger(__name__).warning(
                "[audit] no se pudo instalar handler en %s: %s", path, e
            )

    def get_log_path(self) -> str:
        return self._current_path

    def relocate_log(self, new_dir: Optional[str]) -> None:
        """Mueve el log a una nueva carpeta. Si new_dir es None/inválido, vuelve al default."""
        old_path = self._current_path
        target_dir = (new_dir or "").strip()
        if target_dir:
            try:
                os.makedirs(target_dir, exist_ok=True)
                if not os.access(target_dir, os.W_OK):
                    target_dir = ""
            except Exception:
                target_dir = ""
        if not target_dir:
            target_dir = _get_log_dir()
        self._install_handler(target_dir)
        try:
            self._logger.info("%s RELOCATE: %s -> %s", self._ctx(), old_path, self._current_path)
        except Exception:
            pass

    def set_context_providers(self, username: Callable[[], str], sucursal: Callable[[], str]):
        self._username_provider = username
        self._sucursal_provider = sucursal

    def set_enabled(self, enabled: bool):
        self._enabled = bool(enabled)

    def is_enabled(self) -> bool:
        return self._enabled

    def _ctx(self) -> str:
        """v6.6.2: Formato explicito 'user=X suc=Y' (mas legible que [X@Y]).

        v6.6.3: si una excepcion en el provider lo rompe, capturamos el tipo
        en el log para diagnosticar (la primera vez por cada tipo de error).
        """
        try:
            u = (self._username_provider() if self._username_provider else "") or "?"
            s = (self._sucursal_provider() if self._sucursal_provider else "") or "?"
            return f"user={u:<12} suc={s:<12}"
        except Exception as e:
            etype = type(e).__name__
            if etype not in self._reported_ctx_errors:
                self._reported_ctx_errors.add(etype)
                try:
                    logging.getLogger(__name__).warning(
                        "[audit] _ctx() lanzo %s: %s. Provider devolviendo '?' por ahora.",
                        etype, e
                    )
                except Exception:
                    pass
            return f"user=?<{etype:<10} suc=?            "

    def log_action(self, kind: str, details: str = "") -> None:
        if not self._enabled:
            return
        try:
            # Formato: "[ts] user=X suc=Y KIND: details"
            self._logger.info("%s | %-15s%s", self._ctx(), kind,
                              (": " + details) if details else "")
        except Exception:
            # Nunca dejar que el logger rompa la app
            pass


# Singleton
_AUDIT: Optional[_AuditLogger] = None


def get_audit_logger() -> _AuditLogger:
    global _AUDIT
    if _AUDIT is None:
        _AUDIT = _AuditLogger()
    return _AUDIT


# ── eventFilter global de Qt ──────────────────────────────────────────────


def _is_password_context(obj) -> bool:
    """True si el objeto/parents son un campo de contraseña: skip auditoria."""
    try:
        # Subir hasta 3 niveles buscando un QLineEdit con echoMode Password
        node = obj
        for _ in range(3):
            if node is None:
                break
            if isinstance(node, QLineEdit):
                if node.echoMode() == QLineEdit.Password:
                    return True
                name = (node.objectName() or "").lower()
                if "pass" in name or "clave" in name or "secret" in name or "token" in name:
                    return True
            node = node.parent() if hasattr(node, "parent") else None
    except Exception:
        pass
    return False


def _key_label(event) -> Optional[str]:
    """Devuelve un label corto para teclas auditables, o None si no auditamos esta tecla."""
    try:
        k = event.key()
        mods = event.modifiers()
        # F1..F12
        if Qt.Key_F1 <= k <= Qt.Key_F12:
            return f"F{k - Qt.Key_F1 + 1}"
        # Ctrl + letra/dígito (no auditamos teclas alfabéticas sueltas)
        if mods & Qt.ControlModifier and not (mods & Qt.AltModifier):
            if Qt.Key_A <= k <= Qt.Key_Z:
                ch = chr(ord('A') + (k - Qt.Key_A))
                return f"Ctrl+{ch}"
            if Qt.Key_0 <= k <= Qt.Key_9:
                ch = chr(ord('0') + (k - Qt.Key_0))
                return f"Ctrl+{ch}"
    except Exception:
        pass
    return None


class _AuditEventFilter(QObject):
    """Captura clicks/dialogos/atajos de teclado de toda la app."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._logger = get_audit_logger()
        # Trackear ultimo dialogo abierto para capturar accept/reject
        self._tracked_dialogs = set()

    def eventFilter(self, obj, event):
        try:
            et = event.type()

            # ── Clicks en botones ────────────────────────────────────
            if et == QEvent.MouseButtonRelease and isinstance(obj, QPushButton):
                if not _is_password_context(obj):
                    txt = (obj.text() or "").strip()
                    if len(txt) > 3:  # ignorar botones cortos sin sentido (ej: "+", "X")
                        self._logger.log_action("CLICK", f'"{txt}"')

            # ── Atajos de teclado (F1..F12 y Ctrl+...) ───────────────
            elif et == QEvent.KeyPress:
                if not _is_password_context(obj):
                    label = _key_label(event)
                    if label is not None:
                        self._logger.log_action("KEY", label)

            # ── Apertura de dialogo ──────────────────────────────────
            elif et == QEvent.Show and isinstance(obj, QDialog):
                cls = type(obj).__name__
                if id(obj) not in self._tracked_dialogs:
                    self._tracked_dialogs.add(id(obj))
                    self._logger.log_action("DIALOG_OPEN", cls)

            # ── Cierre de dialogo ────────────────────────────────────
            elif et == QEvent.Close and isinstance(obj, QDialog):
                cls = type(obj).__name__
                if id(obj) in self._tracked_dialogs:
                    self._tracked_dialogs.discard(id(obj))
                    res = "accepted" if obj.result() == QDialog.Accepted else "closed"
                    self._logger.log_action("DIALOG_CLOSE", f"{cls} ({res})")

        except Exception:
            # Nunca dejar que el filtro rompa la app
            pass

        # Siempre devolver False: solo observar, no consumir
        return False


# Instalador (idempotente)
_FILTER: Optional[_AuditEventFilter] = None
_WIRED_TABS: set = set()  # ids de QTabWidget ya instrumentados


def install_audit_filter(app, username_provider: Callable[[], str], sucursal_provider: Callable[[], str]) -> None:
    """
    Instala el eventFilter global y configura los context providers.
    Idempotente.
    """
    global _FILTER

    audit = get_audit_logger()
    audit.set_context_providers(username_provider, sucursal_provider)

    # Cargar enabled desde config
    try:
        cfg_audit = (_load_cfg().get("audit") or {})
        audit.set_enabled(bool(cfg_audit.get("enabled", True)))
    except Exception:
        audit.set_enabled(True)

    if _FILTER is None:
        _FILTER = _AuditEventFilter(app)
        app.installEventFilter(_FILTER)

    # Loguear INIT con la ruta absoluta para que el usuario pueda verificar.
    try:
        audit.log_action("INIT", f"file={audit.get_log_path()}")
    except Exception:
        pass


def wire_tab_widgets(window) -> None:
    """Conecta el signal currentChanged de cada QTabWidget hijo de `window`.

    QApplication-level eventFilter no captura el cambio de pestaña (es una signal,
    no un evento). Esta función debe llamarse después de que todas las pestañas
    estén construidas.

    Idempotente: cada QTabWidget se conecta una sola vez (rastreado por id()).
    """
    audit = get_audit_logger()
    try:
        for tw in window.findChildren(QTabWidget):
            tid = id(tw)
            if tid in _WIRED_TABS:
                continue
            _WIRED_TABS.add(tid)
            # Closure que captura tw para reportar el nombre del tab
            def _on_changed(idx, _tw=tw):
                try:
                    name = _tw.objectName() or "tabs"
                    label = _tw.tabText(idx) if 0 <= idx < _tw.count() else "?"
                    audit.log_action("TAB_CHANGE", f"{name} -> {label}")
                except Exception:
                    pass
            tw.currentChanged.connect(_on_changed)
    except Exception as e:
        logging.getLogger(__name__).warning("[audit] wire_tab_widgets fallo: %s", e)


def cleanup_old_logs(retention_days: int = 7) -> int:
    """
    Borra archivos de log de actividad mas viejos que `retention_days`.
    Devuelve cuántos archivos se borraron.

    Llamar al inicio de la app (despues del setup_root_logging).
    """
    # Buscar tanto en la carpeta default como en la configurada
    log_dirs = set()
    try:
        log_dirs.add(_get_log_dir())
    except Exception:
        pass
    try:
        log_dirs.add(_resolve_log_dir())
    except Exception:
        pass

    cutoff = datetime.now() - timedelta(days=max(1, int(retention_days)))
    deleted = 0
    for log_dir in log_dirs:
        try:
            for fname in os.listdir(log_dir):
                # Solo archivos relacionados al activity.log (incluye rotaciones .1, .2, etc)
                if not fname.startswith(_LOG_FILENAME):
                    continue
                path = os.path.join(log_dir, fname)
                try:
                    mtime = datetime.fromtimestamp(os.path.getmtime(path))
                    if mtime < cutoff:
                        os.remove(path)
                        deleted += 1
                except Exception:
                    continue
        except Exception:
            continue

    if deleted > 0:
        logging.getLogger(__name__).info(
            "[audit] %d archivo(s) viejo(s) de activity.log borrado(s) (retencion %d dias)",
            deleted, retention_days
        )
    return deleted
