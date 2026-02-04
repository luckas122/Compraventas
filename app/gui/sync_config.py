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
from app.config import load as load_config, save as save_config, get_log_dir


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

        # Puerto SMTP con checkbox de bloqueo
        row_smtp_port = QHBoxLayout()
        self.spn_smtp_port = QSpinBox()
        self.spn_smtp_port.setRange(1, 65535)
        self.spn_smtp_port.setValue(587)
        self.spn_smtp_port.setEnabled(False)  # Bloqueado por defecto
        self.chk_edit_smtp_port = QCheckBox("Permitir edición")
        self.chk_edit_smtp_port.toggled.connect(self.spn_smtp_port.setEnabled)
        row_smtp_port.addWidget(self.spn_smtp_port)
        row_smtp_port.addWidget(self.chk_edit_smtp_port)
        row_smtp_port.addStretch()
        lay_smtp.addRow("Puerto:", row_smtp_port)

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

        # Puerto IMAP con checkbox de bloqueo
        row_imap_port = QHBoxLayout()
        self.spn_imap_port = QSpinBox()
        self.spn_imap_port.setRange(1, 65535)
        self.spn_imap_port.setValue(993)
        self.spn_imap_port.setEnabled(False)  # Bloqueado por defecto
        self.chk_edit_imap_port = QCheckBox("Permitir edición")
        self.chk_edit_imap_port.toggled.connect(self.spn_imap_port.setEnabled)
        row_imap_port.addWidget(self.spn_imap_port)
        row_imap_port.addWidget(self.chk_edit_imap_port)
        row_imap_port.addStretch()
        lay_imap.addRow("Puerto:", row_imap_port)

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
        gb_avanzado = QGroupBox("¿Qué sincronizar?")
        lay_avanzado = QFormLayout(gb_avanzado)

        # Ventas siempre se sincronizan (no tiene checkbox)
        lbl_ventas = QLabel("✓ Ventas (siempre activo)")
        lbl_ventas.setStyleSheet("color: green; font-weight: bold;")
        lay_avanzado.addRow(lbl_ventas)

        self.chk_sync_productos = QCheckBox("Sincronizar productos")
        self.chk_sync_productos.setEnabled(True)  # ✅ Ahora habilitado en Fase 2
        self.chk_sync_productos.setToolTip(
            "Si está marcado, sincroniza todos los productos entre sucursales.\n"
            "Los productos se identifican por código de barras.\n"
            "Si un producto existe en ambas sucursales, se actualiza con los datos más recientes."
        )
        lay_avanzado.addRow(self.chk_sync_productos)

        self.chk_sync_proveedores = QCheckBox("Sincronizar proveedores")
        self.chk_sync_proveedores.setEnabled(True)  # ✅ Ahora habilitado en Fase 2
        self.chk_sync_proveedores.setToolTip(
            "Si está marcado, sincroniza todos los proveedores entre sucursales.\n"
            "Los proveedores se identifican por nombre.\n"
            "Si un proveedor existe en ambas sucursales, se actualiza con los datos más recientes."
        )
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
        """Prueba la conexión SMTP e IMAP con logging detallado"""
        import smtplib
        import imaplib
        import ssl
        import sys
        import traceback
        import logging
        from datetime import datetime
        from pathlib import Path

        # 🆕 Configurar logging detallado a archivo
        log_dir = Path(get_log_dir())
        log_file = log_dir / "sync_test_connection.log"

        # Crear logger específico
        logger = logging.getLogger("sync_test")
        logger.setLevel(logging.DEBUG)

        # Handler a archivo
        fh = logging.FileHandler(log_file, mode='a', encoding='utf-8')
        fh.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        fh.setFormatter(formatter)
        logger.addHandler(fh)

        logger.info("="*80)
        logger.info(f"INICIO PRUEBA DE CONEXIÓN - {datetime.now()}")
        logger.info(f"Python: {sys.version}")
        logger.info(f"Frozen: {getattr(sys, 'frozen', False)}")
        logger.info(f"Executable: {sys.executable}")

        errores = []

        # Probar importaciones críticas
        try:
            logger.info("Verificando módulos SSL...")
            import _ssl
            logger.info(f"  ✓ _ssl disponible: {_ssl}")
            import _hashlib
            logger.info(f"  ✓ _hashlib disponible: {_hashlib}")
            logger.info(f"  ✓ ssl.OPENSSL_VERSION: {ssl.OPENSSL_VERSION}")

            # Verificar certificados
            try:
                import certifi
                cert_path = certifi.where()
                logger.info(f"  ✓ certifi disponible: {cert_path}")
                logger.info(f"  ✓ Archivo existe: {Path(cert_path).exists()}")
            except ImportError:
                logger.warning("  ⚠ certifi NO disponible")

        except Exception as e:
            logger.error(f"  ✗ Error en módulos SSL: {e}")
            logger.error(traceback.format_exc())

        # Probar SMTP
        logger.info("\n--- PRUEBA SMTP ---")
        try:
            host = self.ed_smtp_host.text().strip()
            port = self.spn_smtp_port.value()
            user = self.ed_smtp_user.text().strip()
            pwd = self.ed_smtp_pass.text()

            logger.info(f"Host: {host}")
            logger.info(f"Port: {port}")
            logger.info(f"User: {user}")
            logger.info(f"Pass: {'***' if pwd else '(vacío)'}")

            if not host:
                errores.append("SMTP: Host requerido")
                logger.warning("Host vacío")
            elif not user or not pwd:
                errores.append("SMTP: Usuario y contraseña requeridos")
                logger.warning("Usuario o contraseña vacíos")
            else:
                logger.info("Intentando conexión SMTP...")

                # Intentar con certifi si está disponible
                try:
                    import certifi
                    context = ssl.create_default_context(cafile=certifi.where())
                    logger.info("Usando certificados de certifi")
                except ImportError:
                    context = ssl.create_default_context()
                    logger.info("Usando certificados del sistema")

                logger.info(f"Contexto SSL creado: {context}")

                with smtplib.SMTP(host, port, timeout=10) as server:
                    logger.info("Conexión SMTP establecida")
                    server.set_debuglevel(1)  # Debug SMTP
                    server.starttls(context=context)
                    logger.info("STARTTLS exitoso")
                    server.login(user, pwd)
                    logger.info("Login SMTP exitoso")

        except smtplib.SMTPAuthenticationError as e:
            msg = f"SMTP: Error de autenticación. Usa contraseña de aplicación, no tu contraseña normal."
            errores.append(msg)
            logger.error(f"SMTPAuthenticationError: {e}")
            logger.error(traceback.format_exc())
        except Exception as e:
            msg = f"SMTP: {type(e).__name__}: {str(e)}"
            errores.append(msg)
            logger.error(f"Error SMTP: {e}")
            logger.error(traceback.format_exc())

        # Probar IMAP
        logger.info("\n--- PRUEBA IMAP ---")
        try:
            host = self.ed_imap_host.text().strip()
            port = self.spn_imap_port.value()
            user = self.ed_imap_user.text().strip()
            pwd = self.ed_imap_pass.text()

            logger.info(f"Host: {host}")
            logger.info(f"Port: {port}")
            logger.info(f"User: {user}")
            logger.info(f"Pass: {'***' if pwd else '(vacío)'}")

            if not host:
                errores.append("IMAP: Host requerido")
                logger.warning("Host vacío")
            elif not user or not pwd:
                errores.append("IMAP: Usuario y contraseña requeridos")
                logger.warning("Usuario o contraseña vacíos")
            else:
                logger.info("Intentando conexión IMAP...")

                # Intentar con certifi si está disponible
                try:
                    import certifi
                    context = ssl.create_default_context(cafile=certifi.where())
                    logger.info("Usando certificados de certifi")
                except ImportError:
                    context = ssl.create_default_context()
                    logger.info("Usando certificados del sistema")

                logger.info(f"Contexto SSL creado: {context}")

                mail = imaplib.IMAP4_SSL(host, port, ssl_context=context)
                logger.info("Conexión IMAP SSL establecida")
                mail.login(user, pwd)
                logger.info("Login IMAP exitoso")
                mail.logout()
                logger.info("Logout IMAP exitoso")

        except imaplib.IMAP4.error as e:
            msg = f"IMAP: Error de autenticación. Verifica que IMAP esté habilitado en Gmail."
            errores.append(msg)
            logger.error(f"IMAP4.error: {e}")
            logger.error(traceback.format_exc())
        except Exception as e:
            msg = f"IMAP: {type(e).__name__}: {str(e)}"
            errores.append(msg)
            logger.error(f"Error IMAP: {e}")
            logger.error(traceback.format_exc())

        # Mostrar resultado
        logger.info("\n--- RESULTADO ---")
        if errores:
            logger.warning(f"Errores encontrados: {len(errores)}")
            for err in errores:
                logger.warning(f"  - {err}")

            QMessageBox.warning(
                self,
                "Prueba de conexión",
                f"Errores encontrados:\n\n" + "\n".join(errores) +
                f"\n\nLog detallado en:\n{log_file}"
            )
        else:
            logger.info("✓ Conexión exitosa a SMTP e IMAP")
            QMessageBox.information(
                self,
                "Prueba de conexión",
                f"Conexión exitosa a SMTP e IMAP.\n\nLog en:\n{log_file}"
            )

        logger.info(f"FIN PRUEBA - {datetime.now()}")
        logger.info("="*80 + "\n")

        # Limpiar handler
        logger.removeHandler(fh)
        fh.close()
