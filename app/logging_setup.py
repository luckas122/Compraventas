# app/logging_setup.py
# -*- coding: utf-8 -*-
"""
Configuración centralizada de logging con rotación automática.

Provee:
    - setup_root_logging(): configura el root logger con un RotatingFileHandler
      que escribe a %APPDATA%/CompraventasV2/logs/app.log (5 MB × 5 backups).
      Llamar UNA SOLA VEZ al inicio de la app (en main.py).
    - get_module_logger(name, filename=None): obtiene un logger por módulo.
      Si se pasa `filename`, le asigna un FileHandler rotativo dedicado.

Política de rotación:
    - Tamaño máximo por archivo: 5 MB
    - Backups: 5 archivos (app.log.1 .. app.log.5 en disco antes de descartar)
    - Encoding: UTF-8

Total máximo en disco por log: ~30 MB (1 actual + 5 backups). Suficiente para
un POS que opera 8h/día durante meses.
"""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Optional

# Tamaño y rotación
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
_BACKUP_COUNT = 5
_FORMAT = "[%(asctime)s] %(levelname)-7s %(name)s: %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"

_initialized = False


def _get_logs_dir() -> str:
    """Devuelve la carpeta de logs. Importa desde app.config si está disponible,
    sino usa AppData directo."""
    try:
        from app.config import _get_log_dir
        return _get_log_dir()
    except Exception:
        # Fallback: AppData/CompraventasV2/logs
        base = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        log_dir = os.path.join(base, "CompraventasV2", "logs")
        os.makedirs(log_dir, exist_ok=True)
        return log_dir


def _make_rotating_handler(log_path: str, level: int = logging.INFO) -> RotatingFileHandler:
    """Crea un RotatingFileHandler con la política estándar."""
    handler = RotatingFileHandler(
        log_path,
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATEFMT))
    return handler


def setup_root_logging(level: int = logging.INFO) -> None:
    """
    Configura el root logger con rotación automática.

    Llamar UNA SOLA VEZ al inicio de la app, antes de importar otros módulos
    que usen logging.getLogger().

    Idempotente: si ya está configurado, no duplica handlers.
    """
    global _initialized
    if _initialized:
        return

    log_path = os.path.join(_get_logs_dir(), "app.log")

    root = logging.getLogger()
    # Limpiar handlers preexistentes solo si son nuestros (evita pisar handlers de tests)
    for h in list(root.handlers):
        if getattr(h, "_compraventas_managed", False):
            root.removeHandler(h)

    handler = _make_rotating_handler(log_path, level=level)
    handler._compraventas_managed = True  # type: ignore[attr-defined]
    root.addHandler(handler)

    # Console handler también, para que durante desarrollo se vea en consola
    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(logging.Formatter("%(levelname)-7s %(name)s: %(message)s"))
    console._compraventas_managed = True  # type: ignore[attr-defined]
    root.addHandler(console)

    root.setLevel(level)

    _initialized = True
    logging.getLogger(__name__).info(
        "Logging inicializado. Archivo: %s (max %s MB × %s backups)",
        log_path, _MAX_BYTES // (1024 * 1024), _BACKUP_COUNT
    )


def get_module_logger(name: str, filename: Optional[str] = None,
                      level: int = logging.DEBUG) -> logging.Logger:
    """
    Devuelve un logger por módulo. Si se pasa `filename`, le agrega un
    FileHandler rotativo dedicado (en la carpeta de logs).

    Uso típico:
        logger = get_module_logger(__name__)                    # solo root + console
        logger = get_module_logger(__name__, "afip.log")        # con archivo dedicado

    Idempotente: no duplica handlers si se llama varias veces con mismo `filename`.
    """
    log = logging.getLogger(name)
    log.setLevel(level)

    if filename:
        log_path = os.path.join(_get_logs_dir(), filename)
        # Evitar duplicación: chequear si ya hay un handler apuntando al mismo archivo
        already = any(
            isinstance(h, RotatingFileHandler) and getattr(h, "baseFilename", "") == os.path.abspath(log_path)
            for h in log.handlers
        )
        if not already:
            handler = _make_rotating_handler(log_path, level=level)
            handler._compraventas_managed = True  # type: ignore[attr-defined]
            log.addHandler(handler)

    return log
