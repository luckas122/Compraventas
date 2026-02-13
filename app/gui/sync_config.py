# app/gui/sync_config.py
"""
Pestana de configuracion de Sincronizacion entre sucursales via Firebase.
"""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QHBoxLayout, QGroupBox, QLabel,
    QCheckBox, QComboBox, QLineEdit, QPushButton, QMessageBox, QSpinBox,
)
from app.config import load as load_config, save as save_config


class SyncConfigPanel(QWidget):
    """Panel de configuracion de sincronizacion via Firebase."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cfg = load_config()
        self._build_ui()
        self._load_config()

    def _build_ui(self):
        root = QVBoxLayout(self)

        # ===== ACTIVACION =====
        gb_act = QGroupBox("Activacion de sincronizacion")
        lay_act = QFormLayout(gb_act)

        self.chk_enabled = QCheckBox("Activar sincronizacion entre sucursales")
        lay_act.addRow(self.chk_enabled)

        info = QLabel(
            "La sincronizacion permite compartir ventas, productos y proveedores "
            "entre ambas sucursales automaticamente usando Firebase."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #888; font-size: 10px;")
        lay_act.addRow(info)
        root.addWidget(gb_act)

        # ===== MODO =====
        gb_modo = QGroupBox("Modo de sincronizacion")
        lay_modo = QFormLayout(gb_modo)

        self.cmb_modo = QComboBox()
        self.cmb_modo.addItem("Automatica (intervalo fijo)", "interval")
        self.cmb_modo.addItem("Manual (boton en status bar)", "manual")
        lay_modo.addRow("Modo:", self.cmb_modo)

        self.lbl_intervalo = QLabel("Intervalo:")
        self.spn_intervalo = QSpinBox()
        self.spn_intervalo.setRange(1, 60)
        self.spn_intervalo.setValue(5)
        self.spn_intervalo.setSuffix(" minutos")
        lay_modo.addRow(self.lbl_intervalo, self.spn_intervalo)

        self.cmb_modo.currentIndexChanged.connect(self._on_modo_changed)
        root.addWidget(gb_modo)

        # ===== FIREBASE =====
        gb_fb = QGroupBox("Firebase Realtime Database")
        lay_fb = QFormLayout(gb_fb)

        self.ed_db_url = QLineEdit()
        self.ed_db_url.setPlaceholderText("https://tu-proyecto.firebaseio.com")
        lay_fb.addRow("URL de base de datos:", self.ed_db_url)

        self.ed_auth_token = QLineEdit()
        self.ed_auth_token.setEchoMode(QLineEdit.Password)
        self.ed_auth_token.setPlaceholderText("Database secret (token de autenticacion)")
        lay_fb.addRow("Token de autenticacion:", self.ed_auth_token)

        help_fb = QLabel(
            '<a href="https://console.firebase.google.com/">Abrir Firebase Console</a> '
            '- Ve a Project Settings > Service accounts > Database secrets'
        )
        help_fb.setOpenExternalLinks(True)
        help_fb.setStyleSheet("color: #4A90E2; font-size: 10px;")
        lay_fb.addRow("", help_fb)
        root.addWidget(gb_fb)

        # ===== QUE SINCRONIZAR =====
        gb_que = QGroupBox("Que sincronizar")
        lay_que = QFormLayout(gb_que)

        lbl_ventas = QLabel("Ventas (siempre activo)")
        lbl_ventas.setStyleSheet("color: green; font-weight: bold;")
        lay_que.addRow(lbl_ventas)

        self.chk_sync_productos = QCheckBox("Sincronizar productos")
        self.chk_sync_productos.setToolTip(
            "Sincroniza productos entre sucursales.\n"
            "Se identifican por codigo de barras.\n"
            "Si hay conflicto, gana el ultimo cambio."
        )
        lay_que.addRow(self.chk_sync_productos)

        self.chk_sync_proveedores = QCheckBox("Sincronizar proveedores")
        self.chk_sync_proveedores.setToolTip(
            "Sincroniza proveedores entre sucursales.\n"
            "Se identifican por nombre.\n"
            "Si hay conflicto, gana el ultimo cambio."
        )
        lay_que.addRow(self.chk_sync_proveedores)
        root.addWidget(gb_que)

        # ===== BOTONES =====
        row_btns = QHBoxLayout()
        row_btns.addStretch(1)

        btn_test = QPushButton("Probar conexion")
        btn_test.clicked.connect(self._test_connection)
        row_btns.addWidget(btn_test)

        btn_save = QPushButton("Guardar configuracion")
        btn_save.clicked.connect(self._save_config)
        btn_save.setMinimumWidth(180)
        row_btns.addWidget(btn_save)

        root.addLayout(row_btns)
        root.addStretch(1)

        self._on_modo_changed()

    def _on_modo_changed(self):
        visible = (self.cmb_modo.currentData() == "interval")
        self.lbl_intervalo.setVisible(visible)
        self.spn_intervalo.setVisible(visible)

    def _load_config(self):
        sync_cfg = self.cfg.get("sync", {})

        self.chk_enabled.setChecked(sync_cfg.get("enabled", False))

        modo = sync_cfg.get("mode", "interval")
        idx = self.cmb_modo.findData(modo)
        if idx >= 0:
            self.cmb_modo.setCurrentIndex(idx)

        self.spn_intervalo.setValue(sync_cfg.get("interval_minutes", 5))

        fb = sync_cfg.get("firebase", {})
        self.ed_db_url.setText(fb.get("database_url", ""))
        self.ed_auth_token.setText(fb.get("auth_token", ""))

        self.chk_sync_productos.setChecked(sync_cfg.get("sync_productos", True))
        self.chk_sync_proveedores.setChecked(sync_cfg.get("sync_proveedores", True))

    def _save_config(self):
        cfg = load_config()

        # Preservar keys existentes que no editamos
        old_sync = cfg.get("sync", {})

        cfg["sync"] = {
            "enabled": self.chk_enabled.isChecked(),
            "mode": self.cmb_modo.currentData(),
            "interval_minutes": self.spn_intervalo.value(),
            "firebase": {
                "database_url": self.ed_db_url.text().strip().rstrip("/"),
                "auth_token": self.ed_auth_token.text().strip(),
            },
            "sync_productos": self.chk_sync_productos.isChecked(),
            "sync_proveedores": self.chk_sync_proveedores.isChecked(),
            "last_sync": old_sync.get("last_sync"),
            "last_processed_keys": old_sync.get("last_processed_keys", {}),
        }

        save_config(cfg)
        QMessageBox.information(self, "Sincronizacion", "Configuracion guardada correctamente.")

        # Reiniciar scheduler en ventana principal
        try:
            mw = self.parent()
            if mw and hasattr(mw, "_reiniciar_sync_scheduler"):
                mw._reiniciar_sync_scheduler()
        except Exception:
            pass

    def _test_connection(self):
        """Prueba la conexion con Firebase via REST API."""
        db_url = self.ed_db_url.text().strip().rstrip("/")
        token = self.ed_auth_token.text().strip()

        if not db_url:
            QMessageBox.warning(self, "Error", "Ingresa la URL de la base de datos Firebase.")
            return
        if not token:
            QMessageBox.warning(self, "Error", "Ingresa el token de autenticacion.")
            return

        try:
            import requests
            url = f"{db_url}/.json?auth={token}&shallow=true"
            resp = requests.get(url, timeout=10)

            if resp.status_code == 200:
                QMessageBox.information(
                    self, "Conexion exitosa",
                    "Se conecto correctamente a Firebase Realtime Database."
                )
            elif resp.status_code == 401:
                QMessageBox.warning(
                    self, "Error de autenticacion",
                    "El token es invalido. Verifica el Database Secret en Firebase Console."
                )
            elif resp.status_code == 404:
                QMessageBox.warning(
                    self, "No encontrado",
                    "La URL de la base de datos no es valida. Verificala en Firebase Console."
                )
            else:
                QMessageBox.warning(
                    self, "Error",
                    f"Error HTTP {resp.status_code}:\n{resp.text[:200]}"
                )
        except requests.ConnectionError:
            QMessageBox.warning(
                self, "Sin conexion",
                "No se pudo conectar. Verifica tu conexion a internet."
            )
        except requests.Timeout:
            QMessageBox.warning(
                self, "Timeout",
                "Firebase no respondio a tiempo. Intenta nuevamente."
            )
        except Exception as e:
            QMessageBox.warning(
                self, "Error",
                f"Error inesperado:\n{e}"
            )
