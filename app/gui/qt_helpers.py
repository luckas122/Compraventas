# -*- coding: utf-8 -*-
from contextlib import contextmanager
from PyQt5.QtWidgets import QStyledItemDelegate, QApplication,QStyleOptionButton,QStyle
from PyQt5.QtCore import Qt, QEvent, QRect
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QStyledItemDelegate, QApplication, QStyleOptionButton, QStyle
from PyQt5.QtCore import Qt, QEvent


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

        # — SOLO togglear en MouseButtonRelease —
        if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            curr = index.data(Qt.CheckStateRole)
            new_state = Qt.Unchecked if curr == Qt.Checked else Qt.Checked
            model.setData(index, new_state, Qt.CheckStateRole)
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