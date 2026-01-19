from datetime import time
from typing import List
import os
try:
    from PyQt5.QtCore import Qt, pyqtSignal
    from PyQt5.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox,
        QListWidget, QListWidgetItem, QTimeEdit, QMessageBox, QGroupBox, QSizePolicy,QLineEdit, QSpinBox, QFileDialog
    )
except Exception:
    from PySide2.QtCore import Qt, Signal as pyqtSignal
    from PySide2.QtWidgets import (
        QLineEdit, QSpinBox, QFileDialog
    )

class BackupConfigPanel(QWidget):
    backupProgramacionGuardada = pyqtSignal(dict)
    backupManualSolicitado = pyqtSignal()
    backupRestaurarSolicitado = pyqtSignal()


    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.MinimumExpanding)

        # El parent es ConfiguracionMixin, no MainWindow directamente
        # Necesitamos obtener el MainWindow desde el parent
        self.main_window = parent

        self._build_ui()
        self._load_cfg()

    def get_main_window(self):
        """
        Obtiene el MainWindow navegando por la jerarquía.
        ConfiguracionMixin es parte de MainWindow (herencia múltiple).
        """
        # El parent (ConfiguracionMixin) ES el MainWindow porque usa herencia múltiple
        if self.main_window and hasattr(self.main_window, 'session'):
            return self.main_window

        # Si no, intentar con parent()
        widget = self.parent()
        while widget:
            if hasattr(widget, 'session') and hasattr(widget, 'usuario_actual'):
                return widget
            widget = widget.parent()

        return None

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

#----UI: Encendido, carpeta y retención
        box_onoff = QGroupBox("Automáticos y destino", self)
        lay_onoff = QVBoxLayout(box_onoff)

        row_on = QHBoxLayout()
        self.chk_enabled = QCheckBox("Activar backups automáticos", box_onoff)
        row_on.addWidget(self.chk_enabled)
        row_on.addStretch()
        lay_onoff.addLayout(row_on)

        row_dir = QHBoxLayout()
        self.edt_dir = QLineEdit(box_onoff)
        btn_dir = QPushButton("Cambiar…", box_onoff)
        row_dir.addWidget(QLabel("Carpeta destino:", box_onoff))
        row_dir.addWidget(self.edt_dir, 1)
        row_dir.addWidget(btn_dir)
        lay_onoff.addLayout(row_dir)

        row_ret = QHBoxLayout()
        self.spn_keep_daily = QSpinBox(box_onoff)
        self.spn_keep_daily.setRange(1, 365)
        self.spn_keep_daily.setValue(15)  # por defecto 15 días
        row_ret.addWidget(QLabel("Retener diarios (días):", box_onoff))
        row_ret.addWidget(self.spn_keep_daily)
        row_ret.addStretch()
        lay_onoff.addLayout(row_ret)

        root.addWidget(box_onoff)
        btn_dir.clicked.connect(self._choose_dir)

        # Días
        box_days = QGroupBox("Días para ejecutar backups", self)
        lay_days = QVBoxLayout(box_days)
        row_days = QHBoxLayout()
        self.chk = []
        nombres = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
        for i, n in enumerate(nombres):
            c = QCheckBox(n, box_days)
            c.setProperty("dindex", i)  # lunes=0
            row_days.addWidget(c)
            self.chk.append(c)
        lay_days.addLayout(row_days)
        btn_all = QPushButton("Seleccionar todos", box_days)
        btn_none = QPushButton("Ninguno", box_days)
        row2 = QHBoxLayout()
        row2.addWidget(btn_all)
        row2.addWidget(btn_none)
        row2.addStretch()
        lay_days.addLayout(row2)
        root.addWidget(box_days)

        btn_all.clicked.connect(lambda: [c.setChecked(True) for c in self.chk])
        btn_none.clicked.connect(lambda: [c.setChecked(False) for c in self.chk])

        # Horarios
        box_times = QGroupBox("Horarios (al menos 2)", self)
        lay_times = QVBoxLayout(box_times)

        self.list_times = QListWidget(box_times)
        lay_times.addWidget(self.list_times)

        row_time_add = QHBoxLayout()
        self.time_edit = QTimeEdit(box_times)
        self.time_edit.setDisplayFormat("HH:mm")
        row_time_add.addWidget(QLabel("Hora:", box_times))
        row_time_add.addWidget(self.time_edit)
        btn_add = QPushButton("Agregar hora", box_times)
        btn_del = QPushButton("Eliminar seleccionada", box_times)
        row_time_add.addWidget(btn_add)
        row_time_add.addWidget(btn_del)
        row_time_add.addStretch()
        lay_times.addLayout(row_time_add)

        btn_add.clicked.connect(self._add_time)
        btn_del.clicked.connect(self._del_selected)
        root.addWidget(box_times)

        # Acciones
        row_actions = QHBoxLayout()
        self.btn_guardar = QPushButton("Guardar programación de backups", self)
        self.btn_manual = QPushButton("Hacer backup ahora", self)
        self.btn_restore = QPushButton("Restaurar desde backup", self)
        row_actions.addWidget(self.btn_guardar)
        row_actions.addWidget(self.btn_manual)
        row_actions.addStretch()
        row_actions.addWidget(self.btn_restore)
        root.addLayout(row_actions)

        # Botón de acción peligrosa (discreto)
        row_danger = QHBoxLayout()
        row_danger.addStretch()

        self.btn_delete_db = QPushButton("Eliminar Base de Datos", self)
        self.btn_delete_db.setStyleSheet("""
            QPushButton {
                background-color: #d32f2f;
                color: white;
                padding: 4px 10px;
                font-size: 9pt;
            }
            QPushButton:hover {
                background-color: #c62828;
            }
        """)
        self.btn_delete_db.clicked.connect(self._delete_database)
        row_danger.addWidget(self.btn_delete_db)

        root.addLayout(row_danger)


        self.btn_restore.clicked.connect(lambda: self.backupRestaurarSolicitado.emit())
        self.btn_guardar.clicked.connect(self._save_clicked)
        self.btn_manual.clicked.connect(lambda: self.backupManualSolicitado.emit())

        root.addStretch()

    def _add_time(self):
        t = self.time_edit.time()
        s = f"{t.hour():02d}:{t.minute():02d}"
        if not self._exists_time(s):
            self.list_times.addItem(QListWidgetItem(s))

    def _del_selected(self):
        for it in self.list_times.selectedItems():
            self.list_times.takeItem(self.list_times.row(it))

    def _exists_time(self, s: str) -> bool:
        for i in range(self.list_times.count()):
            if self.list_times.item(i).text() == s:
                return True
        return False

    def _get_days(self) -> List[int]:
        # lunes=0 ... domingo=6
        return [c.property("dindex") for c in self.chk if c.isChecked()]

    def _get_times(self) -> List[str]:
        return [self.list_times.item(i).text() for i in range(self.list_times.count())]

    def _load_cfg(self):
        try:
            from app.config import load as load_config
        except Exception:
            load_config = None

        if not load_config:
            # defaults si no hay config helpers
            self.chk[0].setChecked(True)
            self.chk[2].setChecked(True)
            self.chk[4].setChecked(True)
            for s in ("10:00", "18:00"):
                self.list_times.addItem(QListWidgetItem(s))
            return

        cfg = load_config() or {}
        bk = (cfg.get("backup") or {})
        days = bk.get("days") or [0, 2, 4]
        times = bk.get("times") or ["10:00", "18:00"]
        for c in self.chk:
            c.setChecked(c.property("dindex") in days)
        self.list_times.clear()
        for s in times:
            self.list_times.addItem(QListWidgetItem(s))
            
        bk = (cfg.get("backup") or {})
        self.chk_enabled.setChecked(bk.get("enabled", True))

        default_dir = os.path.join(
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")),
            "backups"
        )
        self.edt_dir.setText(bk.get("dir") or default_dir)

        ret = bk.get("retention_days") or {}
        self.spn_keep_daily.setValue(int(ret.get("daily", 15)))

#-- PERSISTIR ENABLED,CARPETA Y RETENCION

    def _save_clicked(self):
            days = self._get_days()
            times = sorted(set(self._get_times()))
            if len(times) < 2:
                QMessageBox.warning(self, "Backups", "Debes definir al menos dos horarios.")
                return
            if not days:
                QMessageBox.warning(self, "Backups", "Selecciona al menos un día.")
                return

            payload = {
                "enabled": bool(self.chk_enabled.isChecked()),
                "dir": (self.edt_dir.text().strip() or None),
                "days": days,
                "times": times,
                "retention_days": {"daily": int(self.spn_keep_daily.value())},
                # limpiar campos legacy para evitar horarios fantasma
                "daily_times": [],
                "weekly": {"enabled": False}
            }

            try:
                from app.config import load as load_config, save as save_config
                cfg = load_config() or {}
                bk = (cfg.get("backup") or {})
                bk.update(payload)
                cfg["backup"] = bk
                save_config(cfg)
            except Exception:
                pass

            self.backupProgramacionGuardada.emit(payload)
            QMessageBox.information(self, "Backups", "Programación de backups guardada.")



#------CARPETA DESTINO
    def _choose_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Elegir carpeta para backups", self.edt_dir.text().strip() or "")
        if d:
            self.edt_dir.setText(d)

    def _delete_database(self):
        """
        Elimina la base de datos completa con triple validación de contraseña de administrador.
        """
        from PyQt5.QtWidgets import QInputDialog
        from app.repository import UsuarioRepo

        # Obtener MainWindow usando el método dedicado
        main_window = self.get_main_window()

        if not main_window:
            QMessageBox.critical(self, "Error",
                "No se pudo acceder a la ventana principal.\n"
                "Detalles de debug:\n"
                f"- parent: {self.parent()}\n"
                f"- parent type: {type(self.parent())}\n"
                f"- has session: {hasattr(self.parent(), 'session') if self.parent() else 'N/A'}")
            return

        try:
            session = main_window.session
            # MainWindow almacena es_admin como boolean, no como usuario_actual
            es_admin = getattr(main_window, 'es_admin', False)

            # Verificar que el usuario actual sea administrador
            if not es_admin:
                QMessageBox.warning(self, "Acceso Denegado",
                                  "Solo los administradores pueden eliminar la base de datos.")
                return

            # Obtener usuarios admin desde el repositorio para validación de contraseña
            from app.repository import UsuarioRepo
            repo = UsuarioRepo(session)
            usuarios_admin = [u for u in repo.listar() if u.es_admin]

            if not usuarios_admin:
                QMessageBox.critical(self, "Error",
                    "No se encontraron usuarios administradores en el sistema.")
                return

            # Si hay un solo admin, usarlo directamente; si hay múltiples, pedir selección
            if len(usuarios_admin) == 1:
                usuario_actual = usuarios_admin[0]
            else:
                # Si hay múltiples, pedir selección
                from PyQt5.QtWidgets import QInputDialog
                nombres = [u.username for u in usuarios_admin]
                nombre_sel, ok = QInputDialog.getItem(
                    self, "Seleccionar Administrador",
                    "Seleccione su usuario administrador:", nombres, 0, False
                )
                if not ok:
                    return
                usuario_actual = next(u for u in usuarios_admin if u.username == nombre_sel)

        except Exception as e:
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "Error",
                f"No se pudo verificar permisos:\n{e}")
            return

        # Advertencia final
        reply = QMessageBox.question(
            self, "⚠️ CONFIRMACIÓN FINAL",
            "¿Está ABSOLUTAMENTE SEGURO de que desea eliminar TODA la base de datos?\n\n"
            "Esta acción:\n"
            "• Eliminará TODOS los productos\n"
            "• Eliminará TODAS las ventas\n"
            "• Eliminará TODOS los proveedores\n"
            "• Eliminará TODOS los usuarios\n"
            "• NO SE PUEDE DESHACER\n\n"
            "Deberá ingresar su contraseña de administrador 3 VECES para confirmar.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        # Triple validación de contraseña
        repo = UsuarioRepo(session)
        username = usuario_actual.username

        for intento in range(1, 4):
            password, ok = QInputDialog.getText(
                self,
                f"Validación {intento}/3",
                f"Ingrese su contraseña de administrador ({intento}/3):",
                QLineEdit.Password
            )

            if not ok:
                QMessageBox.information(self, "Cancelado", "Operación cancelada.")
                return

            # Verificar contraseña
            usuario_verificado = repo.verificar(username, password)
            if not usuario_verificado:
                QMessageBox.critical(
                    self, "Error de Validación",
                    f"Contraseña incorrecta en el intento {intento}/3.\n\n"
                    "Operación cancelada por seguridad."
                )
                return

        # Si llegamos aquí, las 3 contraseñas fueron correctas
        QMessageBox.information(
            self, "Validación Exitosa",
            "Contraseña verificada 3 veces.\n\n"
            "Procediendo a eliminar la base de datos..."
        )

        # Eliminar la base de datos
        try:
            import os
            import sys
            import subprocess
            from pathlib import Path

            # Obtener la ruta real de la base de datos desde la sesión
            db_path = None
            try:
                bind = getattr(session, "bind", None)
                if bind is not None and getattr(bind, "url", None) is not None:
                    if bind.url.get_backend_name() == "sqlite":
                        db_path = bind.url.database
            except Exception as e:
                QMessageBox.critical(self, "Error",
                    f"No se pudo obtener la ruta de la base de datos:\n{e}")
                return

            if not db_path:
                QMessageBox.critical(self, "Error",
                    "No se pudo determinar la ruta de la base de datos.")
                return

            if not os.path.exists(db_path):
                QMessageBox.warning(self, "Base de Datos",
                                  f"No se encontró la base de datos en:\n{db_path}")
                return

            # Determinar la ruta del ejecutable/script principal
            if getattr(sys, 'frozen', False):
                # Ejecutable (PyInstaller)
                app_path = sys.executable
                is_frozen = True
            else:
                # Modo desarrollo: backup_config.py -> gui/ -> app/ -> raíz/
                app_path = str(Path(__file__).parent.parent.parent / "main.py")
                is_frozen = False

            # Cerrar TODAS las sesiones de la base de datos
            try:
                # Cerrar la sesión actual
                session.close()

                # Intentar cerrar el engine completo y forzar checkpoint WAL
                from app.database import engine

                # CRÍTICO: Forzar checkpoint de WAL antes de cerrar
                # Esto libera los archivos -wal y -shm
                try:
                    with engine.connect() as conn:
                        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                        conn.commit()
                except Exception as wal_err:
                    print(f"[DELETE_DB] No se pudo hacer WAL checkpoint: {wal_err}")

                # Dispose del engine (cierra todas las conexiones)
                engine.dispose()

                # Esperar un momento para que SQLite libere los file handles
                import time
                time.sleep(1)
            except Exception as e:
                print(f"[DELETE_DB] Advertencia al cerrar sesiones: {e}")

            # Lanzar script de eliminación (diferente según frozen o desarrollo)
            try:
                if is_frozen:
                    # En frozen: usar script .bat que está junto al .exe
                    exe_dir = Path(sys.executable).parent
                    bat_script = exe_dir / "delete_db_and_restart.bat"

                    if not bat_script.exists():
                        # Debug: mostrar contenido del directorio
                        import os
                        files_in_dir = "\n".join([f"  - {f}" for f in os.listdir(exe_dir)][:20])
                        QMessageBox.critical(self, "Error",
                            f"No se encontró el script de eliminación en:\n{bat_script}\n\n"
                            f"Directorio del .exe: {exe_dir}\n\n"
                            f"Archivos encontrados:\n{files_in_dir}")
                        return

                    # Lanzar el .bat con ventana visible
                    subprocess.Popen(
                        ['cmd', '/c', str(bat_script), db_path, app_path],
                        creationflags=subprocess.CREATE_NEW_CONSOLE
                    )
                else:
                    # En desarrollo: usar módulo Python
                    subprocess.Popen(
                        [sys.executable, "-m", "app.delete_db_manager", db_path, app_path],
                        creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0
                    )
            except Exception as e:
                QMessageBox.critical(self, "Error",
                    f"No se pudo lanzar el proceso de eliminación:\n{e}")
                return

            # Cerrar la aplicación INMEDIATAMENTE sin mostrar más mensajes
            # IMPORTANTE: Usar os._exit() para forzar cierre completo del proceso
            # QApplication.quit() no cierra inmediatamente, deja conexiones abiertas
            import os
            import sys

            # Forzar cierre inmediato del proceso (no espera event loop)
            os._exit(0)

        except Exception as e:
            import traceback
            traceback.print_exc()
            QMessageBox.critical(
                self, "Error al Eliminar",
                f"No se pudo eliminar la base de datos:\n\n{e}"
            )