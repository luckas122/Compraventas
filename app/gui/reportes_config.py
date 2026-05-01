# app/gui/reportes_config.py
from typing import List
from PyQt5.QtCore import Qt, QTime
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QGroupBox, QFormLayout, QHBoxLayout, QLabel, QCheckBox,
    QTimeEdit, QLineEdit, QPushButton, QListWidget, QListWidgetItem,
    QMessageBox, QSpinBox
)
from app.config import load as load_config, save as save_config
from app.gui.qt_helpers import NoScrollComboBox
import tempfile, os

MAX_RECIP = 6

class ReportesCorreoConfig(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.cfg = load_config()
        root = QVBoxLayout(self)

        # -------- Programación (3 frecuencias INDEPENDIENTES) --------
        gb_prog = QGroupBox("Programación de envíos automáticos (las 3 frecuencias funcionan en paralelo)")
        f_prog = QVBoxLayout(gb_prog)

        # --- Diario ---
        gb_daily = QGroupBox("Diario")
        gd = QHBoxLayout(gb_daily); gd.setContentsMargins(8, 4, 8, 4)
        self.chk_daily_enabled = QCheckBox("Activar")
        self.time_daily = QTimeEdit(); self.time_daily.setDisplayFormat("HH:mm")
        self.time_daily.setAlignment(Qt.AlignCenter); self.time_daily.setMinimumWidth(90)
        gd.addWidget(self.chk_daily_enabled)
        gd.addSpacing(12)
        gd.addWidget(QLabel("Hora:")); gd.addWidget(self.time_daily)
        gd.addStretch(1)
        f_prog.addWidget(gb_daily)

        # --- Semanal ---
        gb_weekly = QGroupBox("Semanal")
        gw = QVBoxLayout(gb_weekly); gw.setContentsMargins(8, 4, 8, 4); gw.setSpacing(4)
        gw_row1 = QHBoxLayout()
        self.chk_weekly_enabled = QCheckBox("Activar")
        self.time_weekly = QTimeEdit(); self.time_weekly.setDisplayFormat("HH:mm")
        self.time_weekly.setAlignment(Qt.AlignCenter); self.time_weekly.setMinimumWidth(90)
        gw_row1.addWidget(self.chk_weekly_enabled)
        gw_row1.addSpacing(12)
        gw_row1.addWidget(QLabel("Hora:")); gw_row1.addWidget(self.time_weekly)
        gw_row1.addStretch(1)
        gw.addLayout(gw_row1)

        gw_row2 = QHBoxLayout()
        gw_row2.addWidget(QLabel("Días:"))
        self._chk_weekdays = []  # lista de QCheckBox con propiedad 'weekday' 1..7
        for i, name in enumerate(["L", "M", "X", "J", "V", "S", "D"], start=1):
            cb = QCheckBox(name)
            cb.setProperty("weekday", i)  # 1..7 (L..D)
            self._chk_weekdays.append(cb)
            gw_row2.addWidget(cb)
        gw_row2.addStretch(1)
        gw.addLayout(gw_row2)
        f_prog.addWidget(gb_weekly)

        # --- Mensual ---
        gb_monthly = QGroupBox("Mensual")
        gm = QHBoxLayout(gb_monthly); gm.setContentsMargins(8, 4, 8, 4)
        self.chk_monthly_enabled = QCheckBox("Activar")
        self.time_monthly = QTimeEdit(); self.time_monthly.setDisplayFormat("HH:mm")
        self.time_monthly.setAlignment(Qt.AlignCenter); self.time_monthly.setMinimumWidth(90)
        self.spn_month_day = QSpinBox(); self.spn_month_day.setRange(1, 31); self.spn_month_day.setValue(1)
        gm.addWidget(self.chk_monthly_enabled)
        gm.addSpacing(12)
        gm.addWidget(QLabel("Hora:")); gm.addWidget(self.time_monthly)
        gm.addSpacing(12)
        gm.addWidget(QLabel("Día del mes:")); gm.addWidget(self.spn_month_day)
        gm.addStretch(1)
        f_prog.addWidget(gb_monthly)

        btn_save_prog = QPushButton("Guardar programación")
        btn_save_prog.clicked.connect(self._save_prog)
        f_prog.addWidget(btn_save_prog)

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
        self.cmb_tls = NoScrollComboBox(); self.cmb_tls.addItems(["STARTTLS (587)", "SSL (465)"])
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

        # -------- WhatsApp --------
        gb_wa = QGroupBox("WhatsApp")
        f_wa = QFormLayout(gb_wa)

        self.chk_wa_pedir_tel = QCheckBox("Pedir número de teléfono antes de enviar")
        self.chk_wa_pedir_tel.setToolTip(
            "Si está activo, al enviar ticket por WhatsApp se pedirá un número.\n"
            "Útil cuando el contacto no está guardado en el teléfono."
        )
        f_wa.addRow(self.chk_wa_pedir_tel)

        row_dir = QHBoxLayout()
        self.ed_wa_ticket_dir = QLineEdit()
        self.ed_wa_ticket_dir.setPlaceholderText("Carpeta para guardar tickets PDF...")
        self.ed_wa_ticket_dir.setReadOnly(True)
        btn_wa_browse = QPushButton("Examinar...")
        btn_wa_browse.clicked.connect(self._browse_wa_ticket_dir)
        btn_wa_clear = QPushButton("Por defecto")
        btn_wa_clear.setToolTip("Usar carpeta por defecto (%APPDATA%/CompraventasV2/Tickets)")
        btn_wa_clear.clicked.connect(lambda: self.ed_wa_ticket_dir.clear())
        row_dir.addWidget(self.ed_wa_ticket_dir, 1)
        row_dir.addWidget(btn_wa_browse)
        row_dir.addWidget(btn_wa_clear)
        f_wa.addRow("Guardar tickets en:", row_dir)

        btn_save_wa = QPushButton("Guardar WhatsApp")
        btn_save_wa.clicked.connect(self._save_whatsapp)
        f_wa.addRow(btn_save_wa)

        root.addWidget(gb_wa)
        root.addStretch(1)

        self._load_all()

    # ---------- load/save ----------
    def _load_all(self):
        cfg = self.cfg
        # Prog: leer auto_send con migración automática a formato v2
        from app.gui.main_window.reportes_mixin import migrate_auto_send_to_v2
        auto_raw = ((cfg.get("reports") or {}).get("historial") or {}).get("auto_send") or {}
        auto = migrate_auto_send_to_v2(auto_raw)

        def _set_time(widget, time_str, default=(21, 0)):
            try:
                hh, mm = [int(x) for x in (time_str or "").split(":")]
            except Exception:
                hh, mm = default
            widget.setTime(QTime(hh, mm))

        # --- Diario ---
        d = auto.get("daily") or {}
        self.chk_daily_enabled.setChecked(bool(d.get("enabled", False)))
        _set_time(self.time_daily, d.get("time"), (21, 0))

        # --- Semanal ---
        w = auto.get("weekly") or {}
        self.chk_weekly_enabled.setChecked(bool(w.get("enabled", False)))
        _set_time(self.time_weekly, w.get("time"), (21, 0))
        wd = w.get("weekdays") or [6]
        try:
            wd = [int(x) for x in wd]
        except Exception:
            wd = [6]
        for cb in getattr(self, "_chk_weekdays", []):
            cb.setChecked(int(cb.property("weekday")) in wd)

        # --- Mensual ---
        m = auto.get("monthly") or {}
        self.chk_monthly_enabled.setChecked(bool(m.get("enabled", False)))
        _set_time(self.time_monthly, m.get("time"), (21, 0))
        md = m.get("month_day")
        try:
            md = int(md) if md else 1
        except Exception:
            md = 1
        self.spn_month_day.setValue(max(1, min(31, md)))

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

        # WhatsApp
        wa = cfg.get("whatsapp") or {}
        self.chk_wa_pedir_tel.setChecked(bool(wa.get("pedir_telefono", True)))
        self.ed_wa_ticket_dir.setText(wa.get("ticket_save_dir") or "")

    def _save_prog(self):
        """Guarda las 3 frecuencias independientes en formato v2."""
        from app.config import load as load_config, save as save_config
        from app.gui.main_window.reportes_mixin import migrate_auto_send_to_v2
        cfg = load_config()
        reports = cfg.get("reports") or {}
        hist = reports.get("historial") or {}

        # Migrar lo que esté guardado (preserva last_sent existente)
        prev_auto = migrate_auto_send_to_v2(hist.get("auto_send") or {})

        # Días seleccionados para Semanal (1..7 L..D)
        wdays = [
            int(cb.property("weekday"))
            for cb in getattr(self, "_chk_weekdays", []) if cb.isChecked()
        ] or [6]  # fallback: sábado

        try:
            month_day = int(self.spn_month_day.value())
        except Exception:
            month_day = 1

        new_auto = {
            "daily": {
                "enabled": self.chk_daily_enabled.isChecked(),
                "time": self.time_daily.time().toString("HH:mm"),
                "last_sent": (prev_auto.get("daily") or {}).get("last_sent"),
            },
            "weekly": {
                "enabled": self.chk_weekly_enabled.isChecked(),
                "time": self.time_weekly.time().toString("HH:mm"),
                "weekdays": wdays,
                "last_sent": (prev_auto.get("weekly") or {}).get("last_sent"),
            },
            "monthly": {
                "enabled": self.chk_monthly_enabled.isChecked(),
                "time": self.time_monthly.time().toString("HH:mm"),
                "month_day": month_day,
                "last_sent": (prev_auto.get("monthly") or {}).get("last_sent"),
            },
        }

        # Guardar de vuelta
        hist["auto_send"] = new_auto
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
                # Arrancar si alguna frecuencia quedó activa
                sched = getattr(mw, "_rep_sched", {}) or {}
                any_enabled = any(
                    (sched.get(k) or {}).get("enabled")
                    for k in ("daily", "weekly", "monthly")
                )
                if any_enabled:
                    mw._reports_timer.start()
                else:
                    mw._reports_timer.stop()
        except Exception as _e:
            import logging as _logging
            _logging.getLogger(__name__).warning("[reportes_config] no se pudo reiniciar scheduler: %s", _e)


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
        from app.gui.historialventas import SmtpWorker
        from PyQt5.QtWidgets import QProgressDialog
        from PyQt5.QtCore import Qt

        sender = self.ed_sender.text().strip()
        if not sender:
            QMessageBox.warning(self, "SMTP", "Ingresá un remitente antes de probar.")
            return

        progress = QProgressDialog("Probando conexión SMTP...", "Cancelar", 0, 0, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()

        self._test_worker = SmtpWorker(
            "Prueba SMTP", "Prueba de conexión OK.",
            [sender], parent=self
        )

        def _on_finished(ok, err):
            progress.close()
            if ok:
                QMessageBox.information(self, "SMTP", "Conexión / envío de prueba OK (revisá tu bandeja).")
            else:
                QMessageBox.warning(self, "SMTP", f"Falló la conexión/envío: {err}")
            self._test_worker = None

        self._test_worker.finished.connect(_on_finished)
        progress.canceled.connect(lambda: (
            self._test_worker.terminate() if self._test_worker and self._test_worker.isRunning() else None
        ))
        self._test_worker.start()

    def _browse_wa_ticket_dir(self):
        from PyQt5.QtWidgets import QFileDialog
        d = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta para tickets")
        if d:
            self.ed_wa_ticket_dir.setText(d)

    def _save_whatsapp(self):
        cfg = load_config()
        wa = cfg.get("whatsapp") or {}
        wa["pedir_telefono"] = self.chk_wa_pedir_tel.isChecked()
        ticket_dir = self.ed_wa_ticket_dir.text().strip()
        wa["ticket_save_dir"] = ticket_dir if ticket_dir else None
        cfg["whatsapp"] = wa
        ok = save_config(cfg)
        QMessageBox.information(self, "WhatsApp", "Configuración guardada." if ok else "Error al guardar.")
