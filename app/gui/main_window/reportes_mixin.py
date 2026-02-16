# app/gui/main_window/reportes_mixin.py
# -*- coding: utf-8 -*-
import logging

from PyQt5.QtCore import QTimer

logger = logging.getLogger(__name__)

class ReportesMixin:
    """
    Mixin para programar y ejecutar envíos automáticos de reportes del Historial.
    - Expone: _init_reports_scheduler(), _armar_reports_scheduler_desde_config(), _tick_reports_scheduler()
    - Requiere:
        * self.historial con método _crear_excel(path, for_freq="DAILY"/"WEEKLY"/"MONTHLY")
        * app.config.load/save
        * app.email_helper.send_historial_via_email
    """

    def _init_reports_scheduler(self):
        """Crea el QTimer, conecta el tick y arma el plan según config."""
        # Timer de 1 minuto
        self._reports_timer = QTimer(self)
        self._reports_timer.setInterval(60_000)
        self._reports_timer.timeout.connect(self._tick_reports_scheduler)

        # Armar reglas desde config y arrancar/detener
        self._armar_reports_scheduler_desde_config()
        try:
            if getattr(self, "_rep_sched", {}).get("enabled"):
                self._reports_timer.start()
                logger.info("[auto-send] timer activo (cada 60s).")
            else:
                self._reports_timer.stop()
                logger.info("[auto-send] timer detenido (disabled).")
        except Exception as e:
            logger.error("[auto-send] no pude arrancar el timer: %s", e)

    # === CONTENIDO MOVIDO DESDE core.py ===
    def _armar_reports_scheduler_desde_config(self):
        from app.config import load as load_config
        cfg = load_config()

        rep  = ((cfg.get("reports") or {}).get("historial") or {})
        auto = rep.get("auto_send") or {}

        # --- TZ y hora por defecto desde "general" ---
        general = cfg.get("general") or {}
        tz_name = general.get("timezone", "America/Argentina/Buenos_Aires")
        default_time = general.get("default_send_time", "20:30")  # HH:MM

        # --- Hora (HH:MM) ---
        time_str = (auto.get("time") or default_time or "20:30").strip()
        try:
            hh, mm = [int(x) for x in time_str.split(":")]
        except Exception:
            hh, mm = 20, 30

        # --- Frecuencia (normalizar español/inglés) ---
        def _norm_freq(s):
            s = (s or "").strip().lower()
            if s in ("diario", "daily"):   return "DAILY"
            if s in ("semanal", "weekly"): return "WEEKLY"
            if s in ("mensual", "monthly"):return "MONTHLY"
            return "DAILY"

        raw_freq = auto.get("freq") or auto.get("frequency") or "Diario"
        freq = _norm_freq(raw_freq)

        enabled = bool(auto.get("enabled", False))

        # --- Semanal: 1..7 (L..D) ---
        wdays = auto.get("weekdays") or [6]
        try:
            wdays = [int(x) for x in wdays]
        except Exception:
            wdays = [6]
        if not wdays:
            wdays = [6]

        # --- Mensual: día del mes o último día (None) ---
        month_day = auto.get("month_day")
        if isinstance(month_day, str) and month_day.isdigit():
            month_day = int(month_day)
        elif not isinstance(month_day, int):
            month_day = None  # None => último día (si cae domingo -> sábado)

        self._rep_sched = {
            "enabled": enabled,
            "freq": freq,             # DAILY | WEEKLY | MONTHLY
            "hh": hh, "mm": mm,
            "tz": tz_name,
            "weekdays": wdays,        # p.ej. [6] = sábado (si tu mapping es 1..7 L..D)
            "month_day": month_day,   # None => último día del mes
            "last_sent": auto.get("last_sent"),
        }

        logger.info("[auto-send] armado: enabled=%s, freq=%s, time=%02d:%02d, tz=%s, weekdays=%s, month_day=%s",
                    enabled, freq, hh, mm, tz_name, wdays, month_day)

    def _tick_reports_scheduler(self):
        """
        Se ejecuta 1 vez por minuto. Si coincide HH:MM según TZ y reglas, envía.
        - DAILY: siempre que coincida hora.
        - WEEKLY: si hoy es uno de 'weekdays' (1..7 L..D).
                  Además: si HOY es el día objetivo del mensual => enviar SEMANAL + MENSUAL juntos.
        - MONTHLY: si HOY es el día objetivo del mensual.
        """
        from datetime import datetime, timedelta, date
        try:
            rules = getattr(self, "_rep_sched", None)
            if not rules or not rules.get("enabled"):
                return

            # Hora local con zona horaria
            try:
                from zoneinfo import ZoneInfo  # py>=3.9
                tz = ZoneInfo(rules["tz"])
                now = datetime.now(tz)
            except Exception:
                now = datetime.now()

            hh, mm = rules["hh"], rules["mm"]
            freq_config = rules["freq"]           # DAILY | WEEKLY | MONTHLY
            last_sent = rules.get("last_sent")
            today_key = now.strftime("%Y-%m-%d")

            # Evitar reenvíos en el mismo día
            if last_sent == today_key:
                return

            # ¿Coincide la hora exacta?
            if not (now.hour == hh and now.minute == mm):
                return

            logger.info("[auto-send] %s -> coincide %02d:%02d (freq=%s)", now.isoformat(), hh, mm, freq_config)

            # ---- objetivo mensual ----
            def _monthly_target_day(_now, _rules):
                y, m = _now.year, _now.month
                if m == 12:
                    last_day = date(y, 12, 31)
                else:
                    first_next = date(y + (1 if m == 12 else 0), (1 if m == 12 else m + 1), 1)
                    last_day = first_next - timedelta(days=1)

                if _rules.get("month_day"):
                    d = max(1, min(_rules["month_day"], last_day.day))
                    return date(y, m, d)
                target = last_day
                if target.weekday() == 6:  # 0..6 (L..D); 6=Domingo
                    target = target - timedelta(days=1)
                return target

            monthly_target = _monthly_target_day(now, rules)

            # ---- decidir qué enviar ----
            freqs_to_send = []
            if freq_config == "DAILY":
                freqs_to_send = ["DAILY"]
            elif freq_config == "WEEKLY":
                py_wd = now.weekday()       # 0..6 (L..D)
                wd_1_7 = py_wd + 1          # 1..7 (L..D)
                regular_weekly = wd_1_7 in (rules.get("weekdays") or [6])
                if now.date() == monthly_target:
                    freqs_to_send = ["WEEKLY", "MONTHLY"]
                elif regular_weekly:
                    freqs_to_send = ["WEEKLY"]
            elif freq_config == "MONTHLY":
                if now.date() == monthly_target:
                    freqs_to_send = ["MONTHLY"]

            if not freqs_to_send:
                logger.info("[auto-send] no corresponde enviar en este tick.")
                return

            # ===== Generar y enviar =====
            import os, tempfile
            any_ok = False
            last_err = None

            for f in freqs_to_send:
                fd, fpath = tempfile.mkstemp(prefix="historial_", suffix=".xlsx")
                os.close(fd)
                try:
                    # Generar Excel desde la pestaña Historial
                    self.historial._crear_excel(fpath, for_freq=f)

                    # Enviar por correo
                    from app.email_helper import send_historial_via_email
                    ok, err = send_historial_via_email(
                        subject_prefix=None,
                        body="Se adjunta el reporte automático.",
                        attachments=[fpath]
                    )

                    if ok:
                        any_ok = True
                        logger.info("[auto-send] enviado OK: %s", f)
                        try:
                            from PyQt5.QtWidgets import QMessageBox
                            QMessageBox.information(self, "Reportes", f"Reporte {f.title()} enviado.")
                        except Exception:
                            pass
                    else:
                        last_err = err
                        logger.error("[auto-send] error enviando %s: %s", f, err)
                        try:
                            from PyQt5.QtWidgets import QMessageBox
                            QMessageBox.warning(self, "Reportes", f"No se pudo enviar reporte {f.title()}:\n{err}")
                        except Exception:
                            pass
                finally:
                    try:
                        if os.path.exists(fpath):
                            os.remove(fpath)
                    except Exception:
                        pass

            # Marcar 'last_sent' sólo si al menos uno salió OK
            if any_ok:
                from app.config import load as load_config, save as save_config
                cfg = load_config()
                rep = ((cfg.get("reports") or {}).get("historial") or {})
                auto = rep.get("auto_send") or {}
                auto["last_sent"] = today_key
                rep["auto_send"] = auto
                cfg["reports"]["historial"] = rep
                save_config(cfg)
                try:
                    self._rep_sched["last_sent"] = today_key
                except Exception:
                    pass

        except Exception as e:
            logger.error("[auto-send] error en scheduler: %s", e)
            return
