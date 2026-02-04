# app/gui/reportes_config.py
from typing import List
from PyQt5.QtCore import Qt, QTime
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QGroupBox, QFormLayout, QHBoxLayout, QLabel, QCheckBox,
    QComboBox, QTimeEdit, QLineEdit, QPushButton, QListWidget, QListWidgetItem,
    QMessageBox, QSpinBox
)
from app.config import load as load_config, save as save_config
from app.email_helper import send_mail_with_attachments
import tempfile, os

MAX_RECIP = 6

class ReportesCorreoConfig(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.cfg = load_config()
        root = QVBoxLayout(self)

        # -------- Programación --------
        gb_prog = QGroupBox("Programación de envíos automáticos")
        f_prog = QFormLayout(gb_prog)

        self.chk_enabled = QCheckBox("Activar envíos programados")
        self.cmb_freq = QComboBox(); self.cmb_freq.addItems(["Diario", "Semanal", "Mensual"])
        self.time_send = QTimeEdit(); self.time_send.setDisplayFormat("HH:mm")
        self.time_send.setAlignment(Qt.AlignCenter); self.time_send.setMinimumWidth(90)

        row_prog = QHBoxLayout()
        row_prog.addWidget(QLabel("Frecuencia:")); row_prog.addWidget(self.cmb_freq)
        row_prog.addSpacing(12)
        row_prog.addWidget(QLabel("Hora:")); row_prog.addWidget(self.time_send)
        row_prog.addStretch(1)

        f_prog.addRow(self.chk_enabled)
        f_prog.addRow(row_prog)

        btn_save_prog = QPushButton("Guardar programación")
        btn_save_prog.clicked.connect(self._save_prog)
        f_prog.addRow(btn_save_prog)

        root.addWidget(gb_prog)

        # -------- Contenido --------
        gb_cont = QGroupBox("Contenido del Excel por frecuencia")
        f_cont = QFormLayout(gb_cont)

        # Diario
        self.chk_d_vd   = QCheckBox("Ventas diarias")
        self.chk_d_pmv  = QCheckBox("Productos más vendidos")
        row_d = QHBoxLayout(); row_d.addWidget(self.chk_d_vd); row_d.addWidget(self.chk_d_pmv); row_d.addStretch(1)
        f_cont.addRow(QLabel("Diario:"), row_d)

        # Semanal
        self.chk_s_vd   = QCheckBox("Ventas diarias")
        self.chk_s_rs   = QCheckBox("Resumen semanal")
        self.chk_s_pmv  = QCheckBox("Productos más vendidos")
        self.chk_s_cmp2 = QCheckBox("Comparativa vs 2 semanas anteriores")
        row_s = QHBoxLayout()
        for w in (self.chk_s_vd, self.chk_s_rs, self.chk_s_pmv, self.chk_s_cmp2):
            row_s.addWidget(w)
        row_s.addStretch(1)
        f_cont.addRow(QLabel("Semanal:"), row_s)

        # Mensual
        self.chk_m_vpd  = QCheckBox("Ventas por día")
        self.chk_m_rsm  = QCheckBox("Resumen semanal del mes")
        self.chk_m_pmv  = QCheckBox("Productos más vendidos")
        self.chk_m_cmp2 = QCheckBox("Comparativa vs 2 meses anteriores")
        row_m = QHBoxLayout()
        for w in (self.chk_m_vpd, self.chk_m_rsm, self.chk_m_pmv, self.chk_m_cmp2):
            row_m.addWidget(w)
        row_m.addStretch(1)
        f_cont.addRow(QLabel("Mensual:"), row_m)

        btn_save_cont = QPushButton("Guardar contenido")
        btn_save_cont.clicked.connect(self._save_content)
        f_cont.addRow(btn_save_cont)

        root.addWidget(gb_cont)
        
        # --- NUEVO: controles de Semanal y Mensual ---
        row_week = QWidget()
        hl_week = QHBoxLayout(row_week); hl_week.setContentsMargins(0,0,0,0); hl_week.setSpacing(4)
        self._chk_weekdays = []  # lista de QCheckBox con propiedad 'weekday' 1..7
        for i, name in enumerate(["L","M","X","J","V","S","D"], start=1):
            cb = QCheckBox(name)
            cb.setProperty("weekday", i)  # 1..7
            self._chk_weekdays.append(cb)
            hl_week.addWidget(cb)
        hl_week.addStretch(1)
        f_prog.addRow("Días (Semanal):", row_week)

        row_month = QWidget()
        hl_month = QHBoxLayout(row_month); hl_month.setContentsMargins(0,0,0,0); hl_month.setSpacing(6)
        self.spn_month_day = QSpinBox()
        self.spn_month_day.setRange(1, 31)
        self.spn_month_day.setValue(1)
        hl_month.addWidget(self.spn_month_day)
        hl_month.addStretch(1)
        f_prog.addRow("Día del mes:", row_month)

        # -------- Correo / SMTP --------
        gb_mail = QGroupBox("Correo / SMTP (Gmail)")
        f_mail = QFormLayout(gb_mail)

        self.ed_sender = QLineEdit()
        self.lst_rcpts = QListWidget(); self.lst_rcpts.setFixedHeight(80)
        row_rcpt_btns = QHBoxLayout()
        btn_add = QPushButton("+"); btn_add.setFixedWidth(28)
        btn_del = QPushButton("–"); btn_del.setFixedWidth(28)
        row_rcpt_btns.addWidget(btn_add); row_rcpt_btns.addWidget(btn_del); row_rcpt_btns.addStretch(1)

        def _add_recipient():
            if self.lst_rcpts.count() >= MAX_RECIP:
                QMessageBox.warning(self, "Correo", f"Máximo {MAX_RECIP} destinatarios.")
                return
            it = QListWidgetItem("nuevo@correo.com")
            it.setFlags(it.flags() | Qt.ItemIsEditable)
            self.lst_rcpts.addItem(it)
            self.lst_rcpts.editItem(it)
        def _del_recipient():
            for it in self.lst_rcpts.selectedItems():
                row = self.lst_rcpts.row(it)
                self.lst_rcpts.takeItem(row)

        btn_add.clicked.connect(_add_recipient)
        btn_del.clicked.connect(_del_recipient)

        self.ed_host = QLineEdit(); self.ed_port = QLineEdit(); self.ed_port.setPlaceholderText("587 o 465")
        self.cmb_tls = QComboBox(); self.cmb_tls.addItems(["STARTTLS (587)", "SSL (465)"])
        self.ed_user = QLineEdit(); self.ed_pwd = QLineEdit(); self.ed_pwd.setEchoMode(QLineEdit.Password)

        btn_test_login = QPushButton("Probar conexión SMTP")
        btn_test_login.clicked.connect(self._test_login)

        btn_save_mail = QPushButton("Guardar correo/SMTP")
        btn_save_mail.clicked.connect(self._save_mail)

        f_mail.addRow("Remitente:", self.ed_sender)
        f_mail.addRow(QLabel("Destinatarios:"), self.lst_rcpts)
        f_mail.addRow("", row_rcpt_btns)
        f_mail.addRow("Host:", self.ed_host)
        row_hp = QHBoxLayout(); row_hp.addWidget(QLabel("Puerto:")); row_hp.addWidget(self.ed_port); row_hp.addSpacing(12); row_hp.addWidget(QLabel("Seguridad:")); row_hp.addWidget(self.cmb_tls); row_hp.addStretch(1)
        f_mail.addRow("", row_hp)
        f_mail.addRow("Usuario:", self.ed_user)
        f_mail.addRow("Contraseña:", self.ed_pwd)
        f_mail.addRow(btn_test_login)
        f_mail.addRow(btn_save_mail)

        root.addWidget(gb_mail)
        root.addStretch(1)

        self._load_all()

    # ---------- load/save ----------
    def _load_all(self):
        cfg = self.cfg
        # Prog
        a = (((cfg.get("reports") or {}).get("historial") or {}).get("auto_send") or {})
        auto = ((cfg.get("reports") or {}).get("historial") or {}).get("auto_send") or {}

        # Semanal
        wd = auto.get("weekdays", [1,2,3,4,5,6,7])
        try:
            wd = list(map(int, wd))
        except Exception:
            wd = [1,2,3,4,5,6,7]
        for cb in getattr(self, "_chk_weekdays", []):
            cb.setChecked(int(cb.property("weekday")) in wd)

        # Mensual
        md = int(auto.get("month_day", 1) or 1)
        self.spn_month_day.setValue(max(1, min(31, md)))
        
        self.chk_enabled.setChecked(bool(a.get("enabled", False)))
        freq = (a.get("freq") or a.get("frequency") or "Diario")
        i = self.cmb_freq.findText(freq); self.cmb_freq.setCurrentIndex(0 if i < 0 else i)
        t = (a.get("time") or "21:00")
        hh, mm = (t.split(":") + ["0"])[:2]
        self.time_send.setTime(QTime(int(hh), int(mm)))

        # Contenido
        ec = (((cfg.get("reports") or {}).get("historial") or {}).get("export_content") or {})
        daily   = set([s.lower() for s in (ec.get("daily")   or [])])
        weekly  = set([s.lower() for s in (ec.get("weekly")  or [])])
        monthly = set([s.lower() for s in (ec.get("monthly") or [])])

        self.chk_d_vd.setChecked("ventas_diarias" in daily)
        self.chk_d_pmv.setChecked("productos_mas_vendidos" in daily)

        self.chk_s_vd.setChecked("ventas_diarias" in weekly)
        self.chk_s_rs.setChecked("resumen_semanal" in weekly)
        self.chk_s_pmv.setChecked("productos_mas_vendidos" in weekly)
        self.chk_s_cmp2.setChecked("comparativa_2_semanas" in weekly)

        self.chk_m_vpd.setChecked("ventas_por_dia" in monthly)
        self.chk_m_rsm.setChecked("resumen_semanal_del_mes" in monthly)
        self.chk_m_pmv.setChecked("productos_mas_vendidos" in monthly)
        self.chk_m_cmp2.setChecked("comparativa_2_meses" in monthly)

        # Mail
        e = (cfg.get("email") or {})
        s = (e.get("smtp") or {})
        self.ed_sender.setText(e.get("sender") or "")
        self.lst_rcpts.clear()
        for r in (e.get("recipients") or []):
            it = QListWidgetItem(r); it.setFlags(it.flags() | Qt.ItemIsEditable)
            self.lst_rcpts.addItem(it)

        self.ed_host.setText(s.get("host") or "smtp.gmail.com")
        p = int(s.get("port") or 587)
        self.ed_port.setText(str(p))
        self.cmb_tls.setCurrentIndex(0 if p == 587 else 1)
        self.ed_user.setText(s.get("username") or "")
        self.ed_pwd.setText(s.get("password") or "")

    def _save_prog(self):
        from app.config import load as load_config, save as save_config
        cfg = load_config()
        reports = cfg.get("reports") or {}
        hist = reports.get("historial") or {}

        # Asegurar el dict auto_send existente
        auto = hist.get("auto_send") or {}

        # Básicos
        auto["enabled"] = self.chk_enabled.isChecked()
        auto["freq"]    = self.cmb_freq.currentText()            # "Diario" | "Semanal" | "Mensual"
        auto["time"]    = self.time_send.time().toString("HH:mm")
        # preservar last_sent si existía
        auto["last_sent"] = (hist.get("auto_send") or {}).get("last_sent")

        # Semanal: lista de días marcados (1..7 L..D) si esos checks existen
        if hasattr(self, "_chk_weekdays") and self._chk_weekdays:
            auto["weekdays"] = [
                int(cb.property("weekday")) for cb in self._chk_weekdays if cb.isChecked()
            ]
        else:
            # por defecto, todos los días (compat)
            auto["weekdays"] = auto.get("weekdays", [1, 2, 3, 4, 5, 6, 7])

        # Mensual: día del mes si el spin existe (1..31)
        if hasattr(self, "spn_month_day") and self.spn_month_day is not None:
            try:
                auto["month_day"] = int(self.spn_month_day.value())
            except Exception:
                auto["month_day"] = auto.get("month_day", 1)

        # Guardar de vuelta
        hist["auto_send"] = auto
        reports["historial"] = hist
        cfg["reports"] = reports

        ok = save_config(cfg)
        from PyQt5.QtWidgets import QMessageBox
        QMessageBox.information(
            self,
            "Programación",
            "Programación guardada." if ok else "Error al guardar."
        )
        
        # Reiniciar el scheduler vivo en la ventana principal
        try:
            mw = self.parent()
            if mw and hasattr(mw, "_armar_reports_scheduler_desde_config"):
                mw._armar_reports_scheduler_desde_config()
                if getattr(mw, "_rep_sched", {}).get("enabled"):
                    mw._reports_timer.start()
                else:
                    mw._reports_timer.stop()
        except Exception:
            pass


    def _save_content(self):
        cfg = load_config()
        reports = cfg.get("reports") or {}
        hist = reports.get("historial") or {}
        ec = {
            "daily":   [k for k, b in {
                "ventas_diarias": self.chk_d_vd.isChecked(),
                "productos_mas_vendidos": self.chk_d_pmv.isChecked()
            }.items() if b],
            "weekly":  [k for k, b in {
                "ventas_diarias": self.chk_s_vd.isChecked(),
                "resumen_semanal": self.chk_s_rs.isChecked(),
                "productos_mas_vendidos": self.chk_s_pmv.isChecked(),
                "comparativa_2_semanas": self.chk_s_cmp2.isChecked()
            }.items() if b],
            "monthly": [k for k, b in {
                "ventas_por_dia": self.chk_m_vpd.isChecked(),
                "resumen_semanal_del_mes": self.chk_m_rsm.isChecked(),
                "productos_mas_vendidos": self.chk_m_pmv.isChecked(),
                "comparativa_2_meses": self.chk_m_cmp2.isChecked()
            }.items() if b]
        }
        hist["export_content"] = ec
        reports["historial"] = hist
        cfg["reports"] = reports
        save = save_config(cfg)
        QMessageBox.information(self, "Contenido", "Contenido guardado." if save else "Error al guardar.")

    def _save_mail(self):
        cfg = load_config()
        e = cfg.get("email") or {}
        e["sender"] = self.ed_sender.text().strip()
        rec = []
        for i in range(self.lst_rcpts.count()):
            r = (self.lst_rcpts.item(i).text() or "").strip()
            if r: rec.append(r)
        e["recipients"] = rec[:MAX_RECIP]
        s = e.get("smtp") or {}
        s["host"] = self.ed_host.text().strip() or "smtp.gmail.com"
        try:
            port = int(self.ed_port.text() or "587")
        except Exception:
            port = 587
        s["port"] = port
        s["use_tls"] = (self.cmb_tls.currentIndex() == 0)  # 0: 587 STARTTLS, 1: 465 SSL
        s["username"] = self.ed_user.text().strip()
        s["password"] = self.ed_pwd.text()
        e["smtp"] = s
        cfg["email"] = e
        save = save_config(cfg)
        QMessageBox.information(self, "Correo", "Correo/SMTP guardado." if save else "Error al guardar.")

    def _test_login(self):
        try:
            # mail “en seco” sin adjuntos
            send_mail_with_attachments("Prueba SMTP", "Prueba de conexión OK.", [self.ed_sender.text().strip()] or [])
            QMessageBox.information(self, "SMTP", "Conexión / envío de prueba OK (revisá tu bandeja).")
        except Exception as ex:
            QMessageBox.warning(self, "SMTP", f"Falló la conexión/envío: {ex}")
