# app/gui/sync_config.py
"""
Pestana de configuracion de Sincronizacion entre sucursales via Firebase.
"""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QHBoxLayout, QGroupBox, QLabel,
    QCheckBox, QComboBox, QLineEdit, QPushButton, QMessageBox, QSpinBox,
    QFrame, QProgressBar,
)
from app.config import load as load_config, save as save_config


class SyncConfigPanel(QWidget):
    """Panel de configuracion de sincronizacion via Firebase."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cfg = load_config()
        self._build_ui()
        self._load_config()

    # ------------------------------------------------------------------
    #  Utilidad: encontrar MainWindow subiendo por la jerarquia de widgets
    # ------------------------------------------------------------------
    def _find_main_window(self):
        """Recorre la jerarquia de parents hasta encontrar MainWindow."""
        w = self.parent()
        while w is not None:
            if hasattr(w, 'session') and hasattr(w, 'sucursal'):
                return w
            w = w.parent()
        return None

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

        # ===== SYNC INICIAL (diseño mejorado) =====
        gb_inicial = QGroupBox("Sincronizacion inicial")
        gb_inicial.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #4A90E2;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 18px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
                color: #4A90E2;
            }
        """)
        lay_inicial = QVBoxLayout(gb_inicial)
        lay_inicial.setContentsMargins(16, 8, 16, 16)
        lay_inicial.setSpacing(10)

        # Icono + descripcion
        row_desc = QHBoxLayout()
        lbl_icon = QLabel("☁️")
        lbl_icon.setStyleSheet("font-size: 28px;")
        lbl_icon.setFixedWidth(40)
        row_desc.addWidget(lbl_icon)

        lbl_inicial = QLabel(
            "<b>¿Ya tenias datos antes de activar la sync?</b><br>"
            "<span style='color:#666; font-size:11px;'>"
            "Usa este boton para subir todos los productos y proveedores "
            "existentes a Firebase. La otra sucursal los recibira "
            "automaticamente en la proxima sincronizacion.</span>"
        )
        lbl_inicial.setWordWrap(True)
        row_desc.addWidget(lbl_inicial, 1)
        lay_inicial.addLayout(row_desc)

        # Barra de progreso (oculta hasta que se usa)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #ccc;
                border-radius: 4px;
                text-align: center;
                height: 22px;
                background: #f0f0f0;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4A90E2, stop:1 #67B8F7);
                border-radius: 3px;
            }
        """)
        lay_inicial.addWidget(self.progress_bar)

        # Label de estado (oculto hasta que se usa)
        self.lbl_sync_progress = QLabel("")
        self.lbl_sync_progress.setAlignment(Qt.AlignCenter)
        self.lbl_sync_progress.setStyleSheet("color: #555; font-size: 11px;")
        lay_inicial.addWidget(self.lbl_sync_progress)

        # Boton principal
        self.btn_inicial = QPushButton("  Subir todos los datos a Firebase  ")
        self.btn_inicial.setCursor(Qt.PointingHandCursor)
        self.btn_inicial.setMinimumHeight(42)
        self.btn_inicial.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #5BA0F2, stop:1 #4A90E2);
                color: white;
                font-size: 13px;
                font-weight: bold;
                border: none;
                border-radius: 6px;
                padding: 10px 24px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #6BB0FF, stop:1 #5BA0F2);
            }
            QPushButton:pressed {
                background: #3A80D2;
            }
            QPushButton:disabled {
                background: #aaa;
                color: #ddd;
            }
        """)
        self.btn_inicial.clicked.connect(self._push_all_existing)
        lay_inicial.addWidget(self.btn_inicial)

        root.addWidget(gb_inicial)

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
            mw = self._find_main_window()
            if mw and hasattr(mw, "_reiniciar_sync_scheduler"):
                mw._reiniciar_sync_scheduler()
        except Exception:
            pass

    def _push_all_existing(self):
        """Sube todos los productos y proveedores existentes a Firebase."""
        cfg = load_config()
        sync_cfg = cfg.get("sync", {})
        if not sync_cfg.get("enabled", False):
            QMessageBox.warning(self, "Error", "Primero activa y guarda la configuracion de sync.")
            return

        reply = QMessageBox.question(
            self, "Sync inicial",
            "Esto subira TODOS los productos y proveedores a Firebase.\n"
            "Puede tardar varios minutos si hay muchos datos.\n\n"
            "¿Continuar?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        # Obtener sesion y sucursal desde MainWindow (subiendo por la jerarquia)
        mw = self._find_main_window()
        session = getattr(mw, 'session', None) if mw else None
        sucursal = getattr(mw, 'sucursal', 'Sarmiento') if mw else 'Sarmiento'

        if not session:
            QMessageBox.warning(
                self, "Error",
                "No se pudo acceder a la sesion de la app.\n"
                "Intenta cerrar y volver a abrir la ventana de configuracion."
            )
            return

        from app.firebase_sync import FirebaseSyncManager
        from PyQt5.QtWidgets import QApplication

        sync = FirebaseSyncManager(session, sucursal)

        # Mostrar barra de progreso y deshabilitar boton
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.btn_inicial.setEnabled(False)
        self.btn_inicial.setText("  Subiendo datos...  ")

        def progress_callback(current, total, tipo):
            pct = int((current / max(total, 1)) * 100)
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(current)
            self.progress_bar.setFormat(f"{tipo}: {current}/{total} ({pct}%)")
            self.lbl_sync_progress.setText(f"Subiendo {tipo}...")
            QApplication.processEvents()

        self.lbl_sync_progress.setText("Iniciando sync inicial...")
        QApplication.processEvents()

        try:
            result = sync.push_all_existing(callback=progress_callback)
            total_ok = result['productos'] + result['proveedores']
            errores = result['errores']

            self.progress_bar.setValue(self.progress_bar.maximum())
            self.progress_bar.setFormat("¡Completado!")

            self.lbl_sync_progress.setText(
                f"✓ {result['productos']} productos, "
                f"{result['proveedores']} proveedores subidos"
            )
            self.lbl_sync_progress.setStyleSheet(
                "color: #2E7D32; font-size: 12px; font-weight: bold;"
            )

            msg = (
                f"Sync inicial completada:\n\n"
                f"Productos subidos: {result['productos']}\n"
                f"Proveedores subidos: {result['proveedores']}\n"
                f"Errores: {errores}"
            )
            QMessageBox.information(self, "Sync inicial", msg)
        except Exception as e:
            self.lbl_sync_progress.setText(f"✗ Error: {e}")
            self.lbl_sync_progress.setStyleSheet(
                "color: #C62828; font-size: 11px; font-weight: bold;"
            )
            self.progress_bar.setFormat("Error")
            QMessageBox.critical(self, "Error", f"Error en sync inicial:\n{e}")
        finally:
            self.btn_inicial.setEnabled(True)
            self.btn_inicial.setText("  Subir todos los datos a Firebase  ")

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
