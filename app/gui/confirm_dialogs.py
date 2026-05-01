# app/gui/confirm_dialogs.py
# -*- coding: utf-8 -*-
"""
Helpers para diálogos de confirmación antes de operaciones destructivas.

En lugar de un genérico "¿Está seguro? Sí/No", estos helpers muestran
detalles relevantes (cantidad, total, ejemplos) para que el usuario sepa
exactamente qué va a perder.

Uso típico:

    from app.gui.confirm_dialogs import confirm_destructive

    if confirm_destructive(
        self,
        title="Eliminar productos",
        action="Vas a eliminar los siguientes productos:",
        items_count=15,
        total=None,
        sample=["ARROZ X1KG", "AZUCAR X500G", "..."],
        warning="Esta accion NO se puede deshacer."
    ):
        do_delete()
"""
from __future__ import annotations

from typing import Iterable, Optional


def confirm_destructive(
    parent,
    title: str,
    action: str,
    items_count: Optional[int] = None,
    total: Optional[float] = None,
    sample: Optional[Iterable[str]] = None,
    warning: str = "Esta accion NO se puede deshacer.",
    default_no: bool = True,
) -> bool:
    """
    Muestra un QMessageBox.question con detalles de la operación.

    Args:
        parent: widget padre (puede ser None).
        title: título del diálogo.
        action: descripción principal (ej: "Vas a eliminar 5 productos").
        items_count: cantidad de elementos afectados (opcional).
        total: monto involucrado en pesos (opcional).
        sample: primeros N nombres/identificadores afectados, para mostrar (opcional).
        warning: aviso final. Por default avisa que es irreversible.
        default_no: si True (default), el botón "No" queda como default
                    (más seguro: enter no destruye).

    Returns:
        True si el usuario confirma, False si cancela o cierra.
    """
    try:
        from PyQt5.QtWidgets import QMessageBox
    except Exception:
        # Sin Qt disponible (testing): comportamiento conservador
        return False

    parts = [action]
    if items_count is not None:
        parts.append(f"\n{items_count} elemento(s) afectado(s).")
    if total is not None:
        try:
            from app.utils.format import fmt_money
            parts.append(f"Total involucrado: {fmt_money(total)}.")
        except Exception:
            parts.append(f"Total involucrado: ${total:,.2f}.")
    if sample:
        sample_list = list(sample)
        if sample_list:
            shown = sample_list[:5]
            extra = len(sample_list) - len(shown)
            parts.append("\nEjemplos:")
            for s in shown:
                parts.append(f"  - {s}")
            if extra > 0:
                parts.append(f"  ... y {extra} mas.")
    if warning:
        parts.append(f"\n{warning}")

    text = "\n".join(parts)

    msg = QMessageBox(parent)
    msg.setWindowTitle(title)
    msg.setIcon(QMessageBox.Warning)
    msg.setText(text)
    msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
    msg.setDefaultButton(QMessageBox.No if default_no else QMessageBox.Yes)

    # Customizar texto botones
    yes_btn = msg.button(QMessageBox.Yes)
    no_btn = msg.button(QMessageBox.No)
    if yes_btn:
        yes_btn.setText("Si, continuar")
    if no_btn:
        no_btn.setText("Cancelar")

    return msg.exec_() == QMessageBox.Yes


def confirm_simple(parent, title: str, question: str, default_no: bool = True) -> bool:
    """
    Confirmación simple sí/no, sin detalles. Para casos donde no hay info útil
    que mostrar más allá de la pregunta.
    """
    try:
        from PyQt5.QtWidgets import QMessageBox
    except Exception:
        return False

    msg = QMessageBox(parent)
    msg.setWindowTitle(title)
    msg.setIcon(QMessageBox.Question)
    msg.setText(question)
    msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
    msg.setDefaultButton(QMessageBox.No if default_no else QMessageBox.Yes)
    return msg.exec_() == QMessageBox.Yes
