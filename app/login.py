from PyQt5.QtWidgets import QDialog, QFormLayout, QLineEdit, QDialogButtonBox, QMessageBox, QToolButton, QHBoxLayout, QInputDialog,QVBoxLayout, QWidget, QSizePolicy
from PyQt5.QtWidgets import QStyle
from app.repository import UsuarioRepo


class LoginDialog(QDialog):
    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Login")

        # Repositorio / sesión
        self.repo = UsuarioRepo(session)

        # --- Layouts: contenedor vertical + form ---
        outer = QVBoxLayout(self)
        form = QFormLayout()
        outer.addLayout(form)

        # --- Campos ---
        self.input_user = QLineEdit()
        self.input_pass = QLineEdit()
        self.input_pass.setEchoMode(QLineEdit.Password)

        form.addRow("Usuario:", self.input_user)
        form.addRow("Contraseña:", self.input_pass)

        # --- Botonera OK/Cancel ---
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.handle_login)
        buttons.rejected.connect(self.reject)

        # --- Botón Reset (root/root) ---
        self.btn_reset = QToolButton(self)
        self.btn_reset.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        self.btn_reset.setToolTip("Reset de usuarios (root/root)")
        self.btn_reset.clicked.connect(self._on_reset_users)

        # --- Botón Crear primer usuario (admin) ---
        self.btn_create_first = QToolButton(self)
        self.btn_create_first.setIcon(self.style().standardIcon(QStyle.SP_FileDialogNewFolder))
        self.btn_create_first.setToolTip("Crear primer usuario (admin)")
        self.btn_create_first.clicked.connect(self._on_create_first_user)

        # Mostrar/ocultar según si hay usuarios
        try:
            show_create = (len(self.repo.listar()) == 0)
        except Exception:
            show_create = False

        # --- Footer único ---
        footer = QHBoxLayout()
        footer.addWidget(self.btn_create_first)            # SIEMPRE lo añadimos al layout
        self.btn_create_first.setVisible(show_create)      # ...y controlamos visibilidad
        footer.addWidget(self.btn_reset)
        footer.addStretch(1)
        footer.addWidget(buttons)

        outer.addLayout(footer)

        # --- Ajustes visuales opcionales ---
        self.setMinimumWidth(420)
        # from PyQt5.QtWidgets import QSizePolicy
        self.btn_create_first.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.btn_reset.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

            
    def _on_create_first_user(self):
        dlg = CreateAdminDialog(self.repo.session, self)
        if dlg.exec_() == QDialog.Accepted and dlg.created_user:
            # Autorrellena el usuario recién creado para facilitar el primer login
            self.input_user.setText(dlg.created_user.username)
            QMessageBox.information(self, "Listo", "Usuario administrador creado. Ingresa la contraseña y pulsa Aceptar.")
        try:
            self.btn_create_first.setVisible(len(self.repo.listar()) == 0)
        except Exception:
            pass
    
    def handle_login(self):
        username = self.input_user.text().strip()
        password = self.input_pass.text()
        u = self.repo.verificar(username, password)
        if u:
            self.user = u
            self.accept()
        else:
            QMessageBox.warning(self, 'Error', 'Credenciales inválidas')
            
    def _on_reset_users(self):
        """
        Reset de contraseña de usuarios protegido por credenciales especiales root/root.
        Flujo:
        1) Pide 'usuario root' y 'contraseña root' (mostrar: introducir 'root').
        2) Permite elegir un usuario existente.
        3) Pide nueva contraseña (doble ingreso) y actualiza usando UsuarioRepo.
        """
        # 1) Desbloqueo por root/root
        user_root, ok = QInputDialog.getText(
            self, "Reset de usuarios",
            "Usuario root (escriba: root):"
        )
        if not ok:
            return
        pass_root, ok = QInputDialog.getText(
            self, "Reset de usuarios",
            "Contraseña root (escriba: root):",
            QLineEdit.Password
        )
        if not ok:
            return
        if (user_root or "").strip().lower() != "root" or (pass_root or "").strip().lower() != "root":
            QMessageBox.warning(self, "Acceso denegado", "Credenciales especiales incorrectas.")
            return

        # 2) Elegir usuario de la base
        try:
            usuarios = self.repo.listar()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo listar usuarios:\n{e}")
            return

        if not usuarios:
            QMessageBox.information(self, "Usuarios", "No hay usuarios registrados.")
            return

        nombres = [u.username for u in usuarios]
        nombre_sel, ok = QInputDialog.getItem(
            self, "Reset de contraseña",
            "Seleccione el usuario:", nombres, 0, False
        )
        if not ok:
            return

        target = next((u for u in usuarios if u.username == nombre_sel), None)
        if not target:
            QMessageBox.warning(self, "Usuarios", "Usuario no encontrado.")
            return

        # 3) Pedir nueva contraseña (doble ingreso)
        pw1, ok = QInputDialog.getText(self, "Nueva contraseña", "Ingrese nueva contraseña:", QLineEdit.Password)
        if not ok or not pw1:
            return
        pw2, ok = QInputDialog.getText(self, "Confirmar contraseña", "Repita la contraseña:", QLineEdit.Password)
        if not ok or pw1 != pw2:
            QMessageBox.warning(self, "Usuarios", "Las contraseñas no coinciden.")
            return

        # 4) Actualizar usando el repositorio (hash con Werkzeug en UsuarioRepo.actualizar)
        try:
            self.repo.actualizar(target.id, password=pw1)
            QMessageBox.information(self, "Usuarios", f"Contraseña actualizada para '{target.username}'.")
        except Exception as e:
            QMessageBox.critical(self, "Usuarios", f"No se pudo actualizar la contraseña:\n{e}")


# --- Crear primer usuario (admin) ---
from PyQt5.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QDialogButtonBox,
    QMessageBox, QCheckBox
)
from sqlalchemy.exc import IntegrityError
from app.repository import UsuarioRepo

class CreateAdminDialog(QDialog):
    """
    Asistente para crear el PRIMER usuario del sistema (admin).
    """
    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Crear primer usuario (Administrador)")
        self.repo = UsuarioRepo(session)

        layout = QFormLayout(self)

        self.input_user = QLineEdit()
        self.input_user.setPlaceholderText("Ej.: admin")
        self.input_pass = QLineEdit()
        self.input_pass.setEchoMode(QLineEdit.Password)
        self.input_pass.setPlaceholderText("Contraseña")
        self.input_pass2 = QLineEdit()
        self.input_pass2.setEchoMode(QLineEdit.Password)
        self.input_pass2.setPlaceholderText("Repite la contraseña")

        self.chk_admin = QCheckBox("Dar permisos de administrador")
        self.chk_admin.setChecked(True)
        self.chk_admin.setEnabled(False)

        layout.addRow("Usuario:", self.input_user)
        layout.addRow("Contraseña:", self.input_pass)
        layout.addRow("Repetir contraseña:", self.input_pass2)
        layout.addRow("", self.chk_admin)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

        self.created_user = None

    def _on_accept(self):
        username = self.input_user.text().strip()
        pw1 = self.input_pass.text()
        pw2 = self.input_pass2.text()

        if not username or not pw1 or not pw2:
            QMessageBox.warning(self, "Crear usuario", "Completa todos los campos.")
            return
        if pw1 != pw2:
            QMessageBox.warning(self, "Crear usuario", "Las contraseñas no coinciden.")
            return
        try:
            self.created_user = self.repo.crear(username, pw1, es_admin=True)
        except IntegrityError:
            QMessageBox.warning(self, "Crear usuario", f"El usuario '{username}' ya existe.")
            return
        except Exception as e:
            QMessageBox.critical(self, "Crear usuario", f"No se pudo crear el usuario:\n{e}")
            return

        QMessageBox.information(self, "Crear usuario", f"Usuario '{username}' creado como administrador.")
        self.accept()
