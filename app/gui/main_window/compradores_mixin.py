# app/gui/main_window/compradores_mixin.py
# -*- coding: utf-8 -*-

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QHBoxLayout,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QComboBox,
)

from app.gui.common import ICON_SIZE, MIN_BTN_HEIGHT, icon

CONDICIONES_FISCALES = [
    "",
    "Responsable Inscripto",
    "Monotributista",
    "Consumidor Final",
    "Exento",
]


class CompradoresMixin:

    def tab_compradores(self):
        w = QWidget()
        lay = QVBoxLayout()
        form = QFormLayout()

        self.input_comp_cuit = QLineEdit()
        self.input_comp_cuit.setPlaceholderText("CUIT/CUIL 11 dígitos")
        self.input_comp_cuit.setMaxLength(11)
        form.addRow("CUIT:", self.input_comp_cuit)

        self.input_comp_nombre = QLineEdit()
        self.input_comp_nombre.setPlaceholderText("Nombre y Apellido")
        form.addRow("Nombre:", self.input_comp_nombre)

        self.input_comp_domicilio = QLineEdit()
        self.input_comp_domicilio.setPlaceholderText("Dirección")
        form.addRow("Domicilio:", self.input_comp_domicilio)

        self.input_comp_localidad = QLineEdit()
        self.input_comp_localidad.setPlaceholderText("Ciudad / Localidad")
        form.addRow("Localidad:", self.input_comp_localidad)

        self.input_comp_codigo_postal = QLineEdit()
        self.input_comp_codigo_postal.setPlaceholderText("Código postal")
        form.addRow("Cód. Postal:", self.input_comp_codigo_postal)

        self.input_comp_condicion = QComboBox()
        self.input_comp_condicion.addItems(CONDICIONES_FISCALES)
        form.addRow("Condición:", self.input_comp_condicion)

        # Enter en último campo → agregar
        self.input_comp_codigo_postal.returnPressed.connect(self.agregar_comprador)

        # Botones
        btn_add = QPushButton()
        btn_add.setIcon(icon('add.svg'))
        btn_add.setIconSize(ICON_SIZE)
        btn_add.setToolTip('Agregar/Actualizar')
        btn_add.clicked.connect(self.agregar_comprador)
        btn_add.setMinimumHeight(MIN_BTN_HEIGHT)

        btn_del = QPushButton()
        btn_del.setIcon(icon('delete.svg'))
        btn_del.setIconSize(ICON_SIZE)
        btn_del.setToolTip('Eliminar seleccionados')
        btn_del.clicked.connect(self.eliminar_compradores)
        btn_del.setMinimumHeight(MIN_BTN_HEIGHT)

        hb = QHBoxLayout()
        hb.addWidget(btn_add)
        hb.addWidget(btn_del)
        form.addRow(hb)

        # Tabla
        self.table_compradores = QTableWidget()
        self.table_compradores.setColumnCount(8)
        self.table_compradores.setHorizontalHeaderLabels(
            ['Sel', 'ID', 'CUIT', 'Nombre', 'Domicilio', 'Localidad', 'Cód.Postal', 'Condición']
        )
        self.table_compradores.setSortingEnabled(True)
        hdr = self.table_compradores.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.Interactive)
        hdr.setStretchLastSection(True)
        self.table_compradores.setColumnWidth(0, 28)
        self.table_compradores.setColumnWidth(1, 40)
        self.table_compradores.setColumnWidth(2, 110)
        self.table_compradores.setColumnWidth(3, 180)
        self.table_compradores.setColumnWidth(4, 180)
        self.table_compradores.setColumnWidth(5, 120)
        self.table_compradores.setColumnWidth(6, 80)

        lay.addLayout(form)
        lay.addWidget(self.table_compradores)
        w.setLayout(lay)

        self.table_compradores.cellDoubleClicked.connect(self._on_comp_dblclick)
        self.cargar_lista_compradores()
        return w

    def cargar_lista_compradores(self):
        comps = self.compradores_svc.listar_todos()
        self.table_compradores.setRowCount(len(comps))
        for r, c in enumerate(comps):
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            chk.setCheckState(Qt.Unchecked)
            self.table_compradores.setItem(r, 0, chk)

            vals = [c.id, c.cuit or '', c.nombre or '', c.domicilio or '',
                    c.localidad or '', c.codigo_postal or '', c.condicion or '']
            for col, val in enumerate(vals):
                it = QTableWidgetItem(str(val))
                it.setFlags(Qt.ItemIsEnabled)
                self.table_compradores.setItem(r, col + 1, it)

    def agregar_comprador(self):
        cuit = self.input_comp_cuit.text().strip()
        if not cuit or len(cuit) != 11:
            QMessageBox.warning(self, 'Atención', 'El CUIT debe tener 11 dígitos.')
            return

        nombre = self.input_comp_nombre.text().strip()
        domicilio = self.input_comp_domicilio.text().strip()
        localidad = self.input_comp_localidad.text().strip()
        codigo_postal = self.input_comp_codigo_postal.text().strip()
        condicion = self.input_comp_condicion.currentText()

        c = self.compradores_svc.guardar_o_actualizar(
            cuit=cuit, nombre=nombre, domicilio=domicilio,
            localidad=localidad, codigo_postal=codigo_postal,
            condicion=condicion,
        )
        # v6.7.0: replicar cliente a otras sucursales via Firebase
        if c is not None and hasattr(self, '_sync_push'):
            try:
                self._sync_push("comprador", c)
            except Exception:
                pass
        self.statusBar().showMessage('Cliente guardado', 3000)
        self.limpiar_inputs_comprador()
        self.cargar_lista_compradores()

    def eliminar_compradores(self):
        if QMessageBox.question(
            self, 'Confirmar', '¿Eliminar clientes seleccionados?',
            QMessageBox.Yes | QMessageBox.No
        ) != QMessageBox.Yes:
            return

        eliminados = 0
        cuits_borrados = []
        for r in range(self.table_compradores.rowCount()):
            if self.table_compradores.item(r, 0).checkState() == Qt.Checked:
                cid = int(self.table_compradores.item(r, 1).text())
                # v6.7.0: capturar el CUIT antes de eliminar para poder propagar la baja
                cuit_item = self.table_compradores.item(r, 2)
                cuit_val = cuit_item.text().strip() if cuit_item else ""
                if self.compradores_svc.eliminar(cid):
                    eliminados += 1
                    if cuit_val:
                        cuits_borrados.append(cuit_val)

        # v6.7.0: replicar bajas a otras sucursales
        if cuits_borrados and hasattr(self, '_sync_push'):
            for _cuit in cuits_borrados:
                try:
                    self._sync_push("comprador_del", _cuit)
                except Exception:
                    pass

        self.statusBar().showMessage(f'Clientes eliminados: {eliminados}', 3000)
        self.cargar_lista_compradores()

    def limpiar_inputs_comprador(self):
        self.input_comp_cuit.clear()
        self.input_comp_nombre.clear()
        self.input_comp_domicilio.clear()
        self.input_comp_localidad.clear()
        self.input_comp_codigo_postal.clear()
        self.input_comp_condicion.setCurrentIndex(0)

    def _on_comp_dblclick(self, row, col):
        get = self.table_compradores.item

        def txt(r, c):
            it = get(r, c)
            return it.text() if it else ""

        self.input_comp_cuit.setText(txt(row, 2))
        self.input_comp_nombre.setText(txt(row, 3))
        self.input_comp_domicilio.setText(txt(row, 4))
        self.input_comp_localidad.setText(txt(row, 5))
        self.input_comp_codigo_postal.setText(txt(row, 6))

        condicion_txt = txt(row, 7)
        idx = self.input_comp_condicion.findText(condicion_txt)
        if idx >= 0:
            self.input_comp_condicion.setCurrentIndex(idx)
        else:
            self.input_comp_condicion.setCurrentIndex(0)
