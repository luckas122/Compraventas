# app/gui/progress_helpers.py
# -*- coding: utf-8 -*-
"""
Helpers para mostrar indicadores de progreso en operaciones largas.

Provee:
    - busy_dialog(parent, title, label): context manager para operaciones
      "indeterminadas" (no sabemos cuántos pasos). Muestra un QProgressDialog
      con barra animada y se cierra al salir del with.

    - ProgressContext(parent, title, total): context manager para operaciones
      "determinadas" (sabemos N pasos). Permite hacer ctx.step("descripcion").

Uso:

    from app.gui.progress_helpers import busy_dialog

    with busy_dialog(self, "Importando Excel", "Leyendo archivo..."):
        df = pd.read_excel(path)
        process(df)

    # O con pasos:

    with ProgressContext(self, "Sincronizando", total=3) as p:
        p.step("Conectando a Firebase...")
        do_connect()
        p.step("Descargando cambios...")
        do_pull()
        p.step("Aplicando cambios locales...")
        do_apply()
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Optional


@contextmanager
def busy_dialog(parent, title: str = "Procesando...", label: str = "Por favor esperá..."):
    """
    Context manager: muestra un QProgressDialog indeterminado durante la operación.

    Si Qt no está disponible, no muestra nada (no rompe).
    """
    dlg = None
    try:
        from PyQt5.QtWidgets import QProgressDialog
        from PyQt5.QtCore import Qt
        dlg = QProgressDialog(label, None, 0, 0, parent)  # 0,0 = barra animada
        dlg.setWindowTitle(title)
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setCancelButton(None)  # sin botón cancelar (operaciones no-cancelables)
        dlg.setMinimumDuration(0)  # mostrar inmediatamente
        dlg.show()
        # Procesar eventos para que el diálogo aparezca antes de bloquear
        try:
            from PyQt5.QtWidgets import QApplication
            QApplication.processEvents()
        except Exception:
            pass
    except Exception:
        # Sin Qt: dejar dlg=None, el yield igual procede
        dlg = None

    try:
        yield dlg
    finally:
        if dlg is not None:
            try:
                dlg.close()
                dlg.deleteLater()
            except Exception:
                pass


class ProgressContext:
    """
    Context manager para operaciones con N pasos conocidos.

    Uso:
        with ProgressContext(self, "Generando reporte", total=4) as p:
            p.step("Consultando ventas...")
            ...
            p.step("Generando Excel...")
            ...
    """

    def __init__(self, parent, title: str, total: int):
        self.parent = parent
        self.title = title
        self.total = max(1, int(total))
        self._dlg = None
        self._current = 0

    def __enter__(self):
        try:
            from PyQt5.QtWidgets import QProgressDialog
            from PyQt5.QtCore import Qt
            self._dlg = QProgressDialog(self.title + "...", None, 0, self.total, self.parent)
            self._dlg.setWindowTitle(self.title)
            self._dlg.setWindowModality(Qt.WindowModal)
            self._dlg.setCancelButton(None)
            self._dlg.setMinimumDuration(0)
            self._dlg.setValue(0)
            self._dlg.show()
            try:
                from PyQt5.QtWidgets import QApplication
                QApplication.processEvents()
            except Exception:
                pass
        except Exception:
            self._dlg = None
        return self

    def step(self, label: Optional[str] = None) -> None:
        """Avanza un paso. Opcionalmente cambia el label visible."""
        self._current = min(self._current + 1, self.total)
        if self._dlg is None:
            return
        try:
            if label:
                self._dlg.setLabelText(label)
            self._dlg.setValue(self._current)
            from PyQt5.QtWidgets import QApplication
            QApplication.processEvents()
        except Exception:
            pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._dlg is not None:
            try:
                self._dlg.setValue(self.total)
                self._dlg.close()
                self._dlg.deleteLater()
            except Exception:
                pass
        # No suprimir excepciones
        return False
