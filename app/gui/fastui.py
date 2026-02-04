# -*- coding: utf-8 -*-
from PyQt5.QtWidgets import QComboBox
from PyQt5.QtCore import QSignalBlocker

"""def populate_combo_fast(combo: QComboBox, items, clear=True):
    if combo is None:
        return
    blocker = QSignalBlocker(combo)
    combo.setUpdatesEnabled(False)
    try:
        if clear:
            combo.clear()
        combo.addItems([str(x) for x in items])
        combo.setMaxVisibleItems(30)
        combo.setInsertPolicy(QComboBox.NoInsert)
    finally:
        combo.setUpdatesEnabled(True)
        del blocker
"""
# -*- coding: utf-8 -*-
from PyQt5.QtCore import QStringListModel, QSortFilterProxyModel, Qt
from PyQt5.QtWidgets import QComboBox, QListView

def make_filterable_combo(combo: QComboBox, items):
    """
    Convierte un QComboBox en 'editable + filtrable' sin repoblar.
    Usa un proxy que filtra por el texto del lineEdit del combo.
    """
    if combo is None:
        return

    # Modelo base con todos los items
    model = QStringListModel([str(x) for x in items], combo)

    # Proxy que filtra 'contiene' (case-insensitive)
    proxy = QSortFilterProxyModel(combo)
    proxy.setSourceModel(model)
    proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
    proxy.setFilterFixedString("")

    # Configurar el combo
    combo.setEditable(True)
    combo.setInsertPolicy(QComboBox.NoInsert)
    combo.setModel(proxy)
    combo.setView(QListView(combo))
    combo.view().setUniformItemSizes(True)
    combo.setMaxVisibleItems(30)

    # Filtrado en vivo por lo que escribe el usuario
    le = combo.lineEdit()
    if le is not None:
        le.textChanged.connect(proxy.setFilterFixedString)

    # Guardar referencias para poder actualizar después
    combo._fast_model = model
    combo._fast_proxy = proxy

def update_filterable_combo(combo: QComboBox, items):
    """Actualiza la lista sin perder el filtrado ni repintar de más."""
    if combo is None or not hasattr(combo, "_fast_model"):
        return
    combo.blockSignals(True)
    try:
        combo._fast_model.setStringList([str(x) for x in items])
    finally:
        combo.blockSignals(False)
