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
        self._build_ui()
        self._load_cfg()

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