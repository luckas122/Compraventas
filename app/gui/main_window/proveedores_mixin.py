# app/gui/main_window/proveedores_mixin.py
# -*- coding: utf-8 -*-

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QHBoxLayout,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QLabel
)

# Importa lo que tu UI de Proveedores usa de common (iconos, tamaños, etc.)
from app.gui.common import ICON_SIZE, MIN_BTN_HEIGHT, icon

class ProveedoresMixin:
    # ---------------- Proveedores ----------------
    def tab_proveedores(self):
        w=QWidget(); l=QVBoxLayout(); form=QFormLayout()
        self.input_prov_nombre=QLineEdit(); self.input_prov_telefono=QLineEdit()
        self.input_prov_cuenta=QLineEdit(); self.input_prov_cbu=QLineEdit()
        form.addRow('Nombre:',self.input_prov_nombre)
        form.addRow('Teléfono:',self.input_prov_telefono)
        form.addRow('Cuenta:',self.input_prov_cuenta)
        form.addRow('CBU:',self.input_prov_cbu)
        self.input_prov_cbu.returnPressed.connect(self.agregar_proveedor)
        btn_pa = QPushButton()
        btn_pa.setIcon(icon('add.svg'))
        btn_pa.setIconSize(ICON_SIZE)
        btn_pa.setToolTip('Agregar/Actualizar')
        btn_pa.clicked.connect(self.agregar_proveedor)
        btn_pa.setMinimumHeight(MIN_BTN_HEIGHT)
        btn_pd = QPushButton()
        btn_pd.setIcon(icon('delete.svg'))
        btn_pd.setIconSize(ICON_SIZE)
        btn_pd.setToolTip('Eliminar seleccionados')
        btn_pd.clicked.connect(self.eliminar_proveedores)
        btn_pd.setMinimumHeight(MIN_BTN_HEIGHT)

        hb2 = QHBoxLayout()
        hb2.addWidget(btn_pa)
        hb2.addWidget(btn_pd)
        form.addRow(hb2)        
        self.table_proveedores=QTableWidget(); self.table_proveedores.setColumnCount(6)
        self.table_proveedores.setHorizontalHeaderLabels(['Sel','ID','Nombre','Teléfono','Cuenta','CBU'])
        self.table_proveedores.setSortingEnabled(True)
        self.table_proveedores.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        l.addLayout(form); l.addWidget(self.table_proveedores); w.setLayout(l)
        self.table_proveedores.cellDoubleClicked.connect(self._on_prov_dblclick)  # NUEVO

        self.cargar_lista_proveedores(); return w

    def cargar_lista_proveedores(self):
        provs = self.proveedores.listar_todos()  # NUEVO
        self.table_proveedores.setRowCount(len(provs))
        for r, p in enumerate(provs):
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            chk.setCheckState(Qt.Unchecked)
            self.table_proveedores.setItem(r, 0, chk)

            for c, val in enumerate([p.id, p.nombre, p.telefono or '', p.numero_cuenta or '', p.cbu or '']):
                it = QTableWidgetItem(str(val))
                it.setFlags(Qt.ItemIsEnabled)
                self.table_proveedores.setItem(r, c + 1, it)

    def agregar_proveedor(self):
        nom = self.input_prov_nombre.text().strip()
        tel = self.input_prov_telefono.text().strip()
        cta = self.input_prov_cuenta.text().strip()
        cbu = self.input_prov_cbu.text().strip()

        p = self.proveedores.crear_o_actualizar_por_nombre(
            nombre=nom, telefono=tel, numero_cuenta=cta, cbu=cbu
        )
        if p is None:
            QMessageBox.warning(self, 'Atención', 'El nombre del proveedor es obligatorio.')
            return

        self.statusBar().showMessage('Proveedor guardado', 3000)
        self.limpiar_inputs_proveedor()
        self.cargar_lista_proveedores()

    def eliminar_proveedores(self):
        if QMessageBox.question(
            self, 'Confirmar', '¿Eliminar proveedores seleccionados?',
            QMessageBox.Yes | QMessageBox.No
        ) != QMessageBox.Yes:
            return

        eliminados = 0
        for r in range(self.table_proveedores.rowCount()):
            if self.table_proveedores.item(r, 0).checkState() == Qt.Checked:
                pid = int(self.table_proveedores.item(r, 1).text())
                if self.proveedores.eliminar(pid):
                    eliminados += 1

        self.statusBar().showMessage(f'Proveedores eliminados: {eliminados}', 3000)
        self.cargar_lista_proveedores()

    def limpiar_inputs_proveedor(self):
        for fld in (self.input_prov_nombre,self.input_prov_telefono,
                    self.input_prov_cuenta,self.input_prov_cbu):
            fld.clear()
            
            
    def _on_prov_dblclick(self, row: int, col: int):
        """
        Carga en el formulario los datos del proveedor de la fila doble clickeada.
        Columnas esperadas en self.table_proveedores:
        0 = check, 1 = id, 2 = nombre, 3 = teléfono, 4 = cuenta, 5 = CBU
        """
        get = self.table_proveedores.item

        def txt(r, c):
            it = get(r, c)
            return it.text() if it else ""

        # Completar inputs del formulario
        self.input_prov_nombre.setText(txt(row, 2))
        self.input_prov_telefono.setText(txt(row, 3))
        self.input_prov_cuenta.setText(txt(row, 4))
        self.input_prov_cbu.setText(txt(row, 5))
        
        

