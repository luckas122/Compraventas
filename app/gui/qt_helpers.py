# -*- coding: utf-8 -*-
from contextlib import contextmanager
from PyQt5.QtWidgets import (
    QStyledItemDelegate, QApplication, QStyleOptionButton, QStyle, QComboBox,
)
from PyQt5.QtCore import Qt, QEvent, QRect
from PyQt5.QtGui import QFont


class NoScrollComboBox(QComboBox):
    """QComboBox que ignora el scroll del mouse a menos que tenga foco.
    Evita cambios accidentales al hacer scroll en una página con combos."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.StrongFocus)

    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


@contextmanager
def freeze_table(table):
    """Desactiva repintado/señales/ordenamiento mientras se tocan muchas celdas."""
    if table is None:
        yield
        return
    sorting = False
    try:
        sorting = table.isSortingEnabled()
    except Exception:
        pass
    try:
        table.setUpdatesEnabled(False)
        table.blockSignals(True)
        if sorting:
            table.setSortingEnabled(False)
        yield
    finally:
        try:
            if sorting:
                table.setSortingEnabled(True)
        except Exception:
            pass
        table.blockSignals(False)
        table.setUpdatesEnabled(True)
        
class FullCellCheckDelegate(QStyledItemDelegate):
    def __init__(self, parent=None, column=0, padding=4):
        super().__init__(parent)
        self.column = column
        self.padding = padding
        self._last_checked_row = None
        self._shift_on_press = False

    def paint(self, painter, option, index):
        if index.column() != self.column:
            return super().paint(painter, option, index)

        # Pintar fondo/selección estándar
        super().paint(painter, option, index)

        # Checkbox ocupando la celda con padding
        checked = (index.data(Qt.CheckStateRole) == Qt.Checked)
        cb_opt = QStyleOptionButton()
        cb_opt.state = QStyle.State_Enabled | (QStyle.State_On if checked else QStyle.State_Off)
        cb_opt.rect  = option.rect.adjusted(self.padding, self.padding, -self.padding, -self.padding)
        QApplication.style().drawControl(QStyle.CE_CheckBox, cb_opt, painter)

    def editorEvent(self, event, model, option, index):
        if index.column() != self.column:
            return super().editorEvent(event, model, option, index)

        # Capturar Shift en Press (más confiable que en Release en Windows)
        if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            self._shift_on_press = bool(QApplication.keyboardModifiers() & Qt.ShiftModifier)
            return True  # consumir press para evitar selección nativa de Qt

        # Togglear en MouseButtonRelease
        if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            curr = index.data(Qt.CheckStateRole)
            new_state = Qt.Unchecked if curr == Qt.Checked else Qt.Checked

            if self._shift_on_press and self._last_checked_row is not None:
                # Shift+Click: seleccionar/deseleccionar rango
                start = min(self._last_checked_row, index.row())
                end = max(self._last_checked_row, index.row())
                for r in range(start, end + 1):
                    idx = model.index(r, self.column)
                    model.setData(idx, new_state, Qt.CheckStateRole)
            else:
                model.setData(index, new_state, Qt.CheckStateRole)

            self._last_checked_row = index.row()
            self._shift_on_press = False
            return True

        # Evitar que el doble click entre en edición / togglee de nuevo
        if event.type() == QEvent.MouseButtonDblClick:
            return True

        # Teclado
        if event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
            curr = index.data(Qt.CheckStateRole)
            new_state = Qt.Unchecked if curr == Qt.Checked else Qt.Checked
            model.setData(index, new_state, Qt.CheckStateRole)
            return True

        return super().editorEvent(event, model, option, index)