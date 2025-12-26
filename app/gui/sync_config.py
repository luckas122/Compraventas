# app/gui/sync_config.py
"""
Pestaña de configuración de Sincronización entre sucursales
"""
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QHBoxLayout, QGroupBox, QLabel,
    QCheckBox, QComboBox, QLineEdit, QPushButton, QMessageBox, QSpinBox,
    QTextEdit, QFrame
)
from app.config import load as load_config, save as save_config


class SyncConfigPanel(QWidget):
    """Panel de configuración de sincronización"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cfg = load_config()
        self._build_ui()
        self._load_config()

    def _build_ui(self):
        """Construye la interfaz"""
        root = QVBoxLayout(self)

        # ===== GRUPO: ACTIVACIÓN =====
        gb_activacion = QGroupBox("Activación de sincronización")
        lay_act = QFormLayout(gb_activacion)

        self.chk_enabled = QCheckBox("Activar sincronización entre sucursales")
        lay_act.addRow(self.chk_enabled)

        info_label = QLabel(
            "La sincronización permite compartir ventas y productos entre "
            "ambas sucursales automáticamente usando Gmail."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #888; font-size: 10px;")
        lay_act.addRow(info_label)

        root.addWidget(gb_activacion)

        # ===== GRUPO: MODO DE SINCRONIZACIÓN =====
        gb_modo = QGroupBox("Modo de sincronización")
        lay_modo = QFormLayout(gb_modo)

        self.cmb_modo = QComboBox()
        self.cmb_modo.addItem("Automática (intervalo fijo)", "interval")
        self.cmb_modo.addItem("Solo cuando hay cambios detectados", "on_change")
        self.cmb_modo.addItem("Manual (botón en status bar)", "manual")
        lay_modo.addRow("Modo:", self.cmb_modo)

        # Intervalo (solo visible si modo = interval)
        self.lbl_intervalo = QLabel("Intervalo de sincronización:")
        self.spn_intervalo = QSpinBox()
        self.spn_intervalo.setRange(1, 60)
        self.spn_intervalo.setValue(5)
        self.spn_intervalo.setSuffix(" minutos")
        lay_modo.addRow(self.lbl_intervalo, self.spn_intervalo)

        # Conectar cambio de modo para mostrar/ocultar intervalo
        self.cmb_modo.currentIndexChanged.connect(self._on_modo_changed)

        root.addWidget(gb_modo)

        # ===== GRUPO: CONFIGURACIÓN GMAIL SMTP =====
        gb_smtp = QGroupBox("Gmail SMTP (para enviar sincronizaciones)")
        lay_smtp = QFormLayout(gb_smtp)

        self.ed_smtp_host = QLineEdit()
        self.ed_smtp_host.setText("smtp.gmail.com")
        self.ed_smtp_host.setPlaceholderText("smtp.gmail.com")
        lay_smtp.addRow("Host:", self.ed_smtp_host)

        self.spn_smtp_port = QSpinBox()
        self.spn_smtp_port.setRange(1, 65535)
        self.spn_smtp_port.setValue(587)
        lay_smtp.addRow("Puerto:", self.spn_smtp_port)

        self.ed_smtp_user = QLineEdit()
        self.ed_smtp_user.setPlaceholderText("tu-email@gmail.com")
        lay_smtp.addRow("Usuario:", self.ed_smtp_user)

        self.ed_smtp_pass = QLineEdit()
        self.ed_smtp_pass.setEchoMode(QLineEdit.Password)
        self.ed_smtp_pass.setPlaceholderText("Contraseña de aplicación de Gmail")
        lay_smtp.addRow("Contraseña:", self.ed_smtp_pass)

        help_smtp = QLabel(
            '<a href="https://support.google.com/accounts/answer/185833">¿Cómo generar contraseña de aplicación?</a>'
        )
        help_smtp.setOpenExternalLinks(True)
        help_smtp.setStyleSheet("color: #4A90E2; font-size: 10px;")
        lay_smtp.addRow("", help_smtp)

        root.addWidget(gb_smtp)

        # ===== GRUPO: CONFIGURACIÓN GMAIL IMAP =====
        gb_imap = QGroupBox("Gmail IMAP (para recibir sincronizaciones)")
        lay_imap = QFormLayout(gb_imap)

        self.ed_imap_host = QLineEdit()
        self.ed_imap_host.setText("imap.gmail.com")
        self.ed_imap_host.setPlaceholderText("imap.gmail.com")
        lay_imap.addRow("Host:", self.ed_imap_host)

        self.spn_imap_port = QSpinBox()
        self.spn_imap_port.setRange(1, 65535)
        self.spn_imap_port.setValue(993)
        lay_imap.addRow("Puerto:", self.spn_imap_port)

        self.ed_imap_user = QLineEdit()
        self.ed_imap_user.setPlaceholderText("tu-email@gmail.com (mismo que SMTP)")
        lay_imap.addRow("Usuario:", self.ed_imap_user)

        self.ed_imap_pass = QLineEdit()
        self.ed_imap_pass.setEchoMode(QLineEdit.Password)
        self.ed_imap_pass.setPlaceholderText("Contraseña de aplicación de Gmail")
        lay_imap.addRow("Contraseña:", self.ed_imap_pass)

        info_imap = QLabel(
            "Nota: Usa la misma cuenta de Gmail para SMTP e IMAP. "
            "La aplicación se enviará emails a sí misma."
        )
        info_imap.setWordWrap(True)
        info_imap.setStyleSheet("color: #888; font-size: 10px;")
        lay_imap.addRow(info_imap)

        root.addWidget(gb_imap)

        # ===== GRUPO: OPCIONES AVANZADAS =====
        gb_avanzado = QGroupBox("Opciones avanzadas")
        lay_avanzado = QFormLayout(gb_avanzado)

        self.chk_sync_productos = QCheckBox("Sincronizar productos (Fase 2)")
        self.chk_sync_productos.setEnabled(False)  # Fase 2
        lay_avanzado.addRow(self.chk_sync_productos)

        self.chk_sync_proveedores = QCheckBox("Sincronizar proveedores (Fase 2)")
        self.chk_sync_proveedores.setEnabled(False)  # Fase 2
        lay_avanzado.addRow(self.chk_sync_proveedores)

        root.addWidget(gb_avanzado)

        # ===== BOTONES DE ACCIÓN =====
        row_btns = QHBoxLayout()
        row_btns.addStretch(1)

        btn_test = QPushButton("Probar conexión")
        btn_test.clicked.connect(self._test_connection)
        row_btns.addWidget(btn_test)

        btn_save = QPushButton("Guardar configuración")
        btn_save.clicked.connect(self._save_config)
        btn_save.setMinimumWidth(180)
        row_btns.addWidget(btn_save)

        root.addLayout(row_btns)

        root.addStretch(1)

        # Actualizar visibilidad inicial
        self._on_modo_changed()

    def _on_modo_changed(self):
        """Muestra/oculta el campo de intervalo según el modo seleccionado"""
        modo = self.cmb_modo.currentData()
        visible = (modo == "interval")
        self.lbl_intervalo.setVisible(visible)
        self.spn_intervalo.setVisible(visible)

    def _load_config(self):
        """Carga la configuración desde app_config.json"""
        sync_cfg = self.cfg.get("sync", {})

        # Activación
        self.chk_enabled.setChecked(sync_cfg.get("enabled", False))

        # Modo
        modo = sync_cfg.get("mode", "interval")
        idx = self.cmb_modo.findData(modo)
        if idx >= 0:
            self.cmb_modo.setCurrentIndex(idx)

        # Intervalo
        self.spn_intervalo.setValue(sync_cfg.get("interval_minutes", 5))

        # SMTP
        smtp = sync_cfg.get("gmail_smtp", {})
        self.ed_smtp_host.setText(smtp.get("host", "smtp.gmail.com"))
        self.spn_smtp_port.setValue(smtp.get("port", 587))
        self.ed_smtp_user.setText(smtp.get("username", ""))
        self.ed_smtp_pass.setText(smtp.get("password", ""))

        # IMAP
        imap = sync_cfg.get("gmail_imap", {})
        self.ed_imap_host.setText(imap.get("host", "imap.gmail.com"))
        self.spn_imap_port.setValue(imap.get("port", 993))
        self.ed_imap_user.setText(imap.get("username", ""))
        self.ed_imap_pass.setText(imap.get("password", ""))

        # Avanzado (Fase 2)
        self.chk_sync_productos.setChecked(sync_cfg.get("sync_productos", False))
        self.chk_sync_proveedores.setChecked(sync_cfg.get("sync_proveedores", False))

    def _save_config(self):
        """Guarda la configuración en app_config.json"""
        cfg = load_config()

        sync_cfg = {
            "enabled": self.chk_enabled.isChecked(),
            "mode": self.cmb_modo.currentData(),
            "interval_minutes": self.spn_intervalo.value(),
            "gmail_smtp": {
                "host": self.ed_smtp_host.text().strip(),
                "port": self.spn_smtp_port.value(),
                "username": self.ed_smtp_user.text().strip(),
                "password": self.ed_smtp_pass.text()
            },
            "gmail_imap": {
                "host": self.ed_imap_host.text().strip(),
                "port": self.spn_imap_port.value(),
                "username": self.ed_imap_user.text().strip(),
                "password": self.ed_imap_pass.text()
            },
            "sync_productos": self.chk_sync_productos.isChecked(),
            "sync_proveedores": self.chk_sync_proveedores.isChecked(),
            "last_sync": cfg.get("sync", {}).get("last_sync")  # Preservar
        }

        cfg["sync"] = sync_cfg
        save_config(cfg)

        QMessageBox.information(self, "Sincronización", "Configuración guardada correctamente.")

        # Reiniciar el scheduler de sync en la ventana principal
        try:
            mw = self.parent()
            if mw and hasattr(mw, "_reiniciar_sync_scheduler"):
                mw._reiniciar_sync_scheduler()
        except Exception:
            pass

    def _test_connection(self):
        """Prueba la conexión SMTP e IMAP"""
        import smtplib
        import imaplib

        errores = []

        # Probar SMTP
        try:
            host = self.ed_smtp_host.text().strip()
            port = self.spn_smtp_port.value()
            user = self.ed_smtp_user.text().strip()
            pwd = self.ed_smtp_pass.text()

            if not user or not pwd:
                errores.append("SMTP: Usuario y contraseña requeridos")
            else:
                with smtplib.SMTP(host, port, timeout=10) as server:
                    server.starttls()
                    server.login(user, pwd)
        except Exception as e:
            errores.append(f"SMTP: {str(e)}")

        # Probar IMAP
        try:
            host = self.ed_imap_host.text().strip()
            port = self.spn_imap_port.value()
            user = self.ed_imap_user.text().strip()
            pwd = self.ed_imap_pass.text()

            if not user or not pwd:
                errores.append("IMAP: Usuario y contraseña requeridos")
            else:
                mail = imaplib.IMAP4_SSL(host, port)
                mail.login(user, pwd)
                mail.logout()
        except Exception as e:
            errores.append(f"IMAP: {str(e)}")

        # Mostrar resultado
        if errores:
            QMessageBox.warning(
                self,
                "Prueba de conexión",
                "Errores encontrados:\n\n" + "\n".join(errores)
            )
        else:
            QMessageBox.information(
                self,
                "Prueba de conexión",
                "Conexión exitosa a SMTP e IMAP."
            )
