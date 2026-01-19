# app/gui/main_window/usuarios_mixin.py
# -*- coding: utf-8 -*-

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QCheckBox, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QInputDialog, QComboBox, QGroupBox,QFileDialog,QStyle,
)


from app.gui.common import ICON_SIZE, MIN_BTN_HEIGHT, icon

class UsuariosMixin:
 # ---------------- Usuarios ----------------
    def tab_usuarios(self):
        w = QWidget()
        layout = QVBoxLayout()

        form = QFormLayout()
        self.user_username = QLineEdit()
        self.user_password = QLineEdit()
        self.user_password.setEchoMode(QLineEdit.Password)
        self.user_admin = QCheckBox()
        form.addRow('Usuario:', self.user_username)
        form.addRow('Contraseña:', self.user_password)
        form.addRow('Admin:', self.user_admin)

        hb = QHBoxLayout()
        btn_add = QPushButton()
        btn_add.setIcon(self.style().standardIcon(QStyle.SP_DialogYesButton))
        btn_add.setToolTip('Crear usuario')
        btn_add.clicked.connect(self.crear_usuario)
        btn_edit = QPushButton()
        btn_edit.setIcon(self.style().standardIcon(QStyle.SP_FileDialogDetailedView))
        btn_edit.setToolTip('Actualizar usuario')
        btn_edit.clicked.connect(self.actualizar_usuario)
        btn_del = QPushButton()
        btn_del.setIcon(self.style().standardIcon(QStyle.SP_TrashIcon))
        btn_del.setToolTip('Eliminar usuario')
        btn_del.clicked.connect(self.eliminar_usuario)
        hb.addWidget(btn_add)
        hb.addWidget(btn_edit)
        hb.addWidget(btn_del)
        form.addRow(hb)

        layout.addLayout(form)

        self.table_usuarios = QTableWidget()
        self.table_usuarios.setColumnCount(3)
        self.table_usuarios.setHorizontalHeaderLabels(['ID','Usuario','Admin'])
        self.table_usuarios.cellClicked.connect(self.cargar_usuario)
        layout.addWidget(self.table_usuarios)

        w.setLayout(layout)
        self.cargar_lista_usuarios()
        self.selected_user_id = None
        return w

    def cargar_lista_usuarios(self):
        usuarios = self.user_repo.listar()
        self.table_usuarios.setRowCount(len(usuarios))
        for r, u in enumerate(usuarios):
            self.table_usuarios.setItem(r,0,QTableWidgetItem(str(u.id)))
            self.table_usuarios.setItem(r,1,QTableWidgetItem(u.username))
            self.table_usuarios.setItem(r,2,QTableWidgetItem('Sí' if u.es_admin else 'No'))

    def cargar_usuario(self, row, col):
        self.user_username.setText(self.table_usuarios.item(row,1).text())
        self.user_admin.setChecked(self.table_usuarios.item(row,2).text()=='Sí')
        self.selected_user_id = int(self.table_usuarios.item(row,0).text())

    def crear_usuario(self):
            username = self.user_username.text().strip()
            password = self.user_password.text()
            es_admin = self.user_admin.isChecked()
            if not username or not password:
                QMessageBox.warning(self,'Error','Usuario y contraseña requeridos')
                return
            if self.user_repo.obtener_por_username(username):
                QMessageBox.warning(self,'Error','Usuario ya existe')
                return
            self.user_repo.crear(username,password,es_admin)
            self.cargar_lista_usuarios()
            self.limpiar_form_usuario()

    def actualizar_usuario(self):
        if not getattr(self,'selected_user_id',None):
            return
        username = self.user_username.text().strip()
        password = self.user_password.text() or None
        es_admin = self.user_admin.isChecked()
        self.user_repo.actualizar(self.selected_user_id, username=username, password=password, es_admin=es_admin)
        self.cargar_lista_usuarios()
        self.limpiar_form_usuario()

    def eliminar_usuario(self):
        if not getattr(self,'selected_user_id',None):
            return
        if QMessageBox.question(self,'Confirmar','¿Eliminar usuario seleccionado?', QMessageBox.Yes|QMessageBox.No) != QMessageBox.Yes:
            return
        self.user_repo.eliminar(self.selected_user_id)
        self.cargar_lista_usuarios()
        self.limpiar_form_usuario()

    def limpiar_form_usuario(self):
        self.user_username.clear()
        self.user_password.clear()
        self.user_admin.setChecked(False)
        self.selected_user_id = None  
