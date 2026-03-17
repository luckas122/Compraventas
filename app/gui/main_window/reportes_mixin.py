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
        from app.config import load as load_config, save as save_config
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

            # Generar Excel y enviar en hilo separado para no bloquear la UI
            from app.gui.historialventas import SmtpWorker
            from app.email_helper import send_historial_via_email

            all_paths = []
            for f in freqs_to_send:
                fd, fpath = tempfile.mkstemp(prefix="historial_", suffix=".xlsx")
                os.close(fd)
                try:
                    self.historial._crear_excel(fpath, for_freq=f)
                    all_paths.append((f, fpath))
                except Exception as ex:
                    logger.error("[auto-send] error generando Excel %s: %s", f, ex)
                    try:
                        os.remove(fpath)
                    except Exception:
                        pass

            if not all_paths:
                return

            # Enviar cada reporte en un worker thread
            for freq_name, fpath in all_paths:
                cfg_mail = load_config()
                email_cfg = (cfg_mail.get("email") or {})
                recips = list(filter(None, email_cfg.get("recipients") or []))
                if not recips:
                    logger.error("[auto-send] no hay destinatarios configurados.")
                    continue

                subj_prefix = email_cfg.get("subject_prefix") or "[Historial]"
                subj = f"{subj_prefix} Reporte {freq_name.title()} {today_key}"

                # Construir body con resumen IVA
                _body_lines = ["Se adjunta el reporte automatico.", ""]
                try:
                    from datetime import datetime as _dt_cls
                    _d = _dt_cls.strptime(today_key, "%Y-%m-%d").date()
                    _desde = _dt_cls.combine(_d, _dt_cls.min.time())
                    _hasta = _dt_cls.combine(_d, _dt_cls.max.time())

                    _ventas_rep = self.venta_repo.listar_por_rango(_desde, _hasta, None)
                    _total_ventas = sum(v.total for v in _ventas_rep)
                    _cant = len(_ventas_rep)

                    _iva_v_cae = [v for v in _ventas_rep if getattr(v, 'afip_cae', None)]
                    _total_cae = sum(v.total for v in _iva_v_cae)
                    _iva_ventas = round(_total_cae - _total_cae / 1.21, 2)

                    _iva_compras = 0.0
                    try:
                        _pagos = self.pago_prov_repo.listar_por_rango(_desde, _hasta, None)
                        _total_pag = sum(float(getattr(p, 'monto', 0) or 0) for p in _pagos)
                        _iva_compras = round(_total_pag - _total_pag / 1.21, 2)
                    except Exception:
                        pass

                    _saldo = round(_iva_compras - _iva_ventas, 2)

                    _body_lines.append(f"--- Resumen del dia {today_key} ---")
                    _body_lines.append(f"Total Ventas: ${_total_ventas:,.2f}  ({_cant} ventas)")
                    _body_lines.append("")
                    _body_lines.append("--- IVA ---")
                    _body_lines.append(f"IVA Compras (pagos proveedores): ${_iva_compras:,.2f}")
                    _body_lines.append(f"IVA Ventas (con CAE): ${_iva_ventas:,.2f}")
                    _body_lines.append(f"Saldo IVA (compras - ventas): ${_saldo:,.2f}")
                except Exception as _ex:
                    logger.warning("[auto-send] no se pudo calcular IVA para body: %s", _ex)

                _body_text = "\n".join(_body_lines)

                worker = SmtpWorker(subj, _body_text, recips, [fpath])
                # Guardar referencia para evitar GC
                if not hasattr(self, '_report_workers'):
                    self._report_workers = []
                self._report_workers.append(worker)

                def _on_done(ok, err, _freq=freq_name, _path=fpath, _worker=worker):
                    if ok:
                        logger.info("[auto-send] enviado OK: %s", _freq)
                        # Marcar last_sent
                        try:
                            cfg2 = load_config()
                            rep = ((cfg2.get("reports") or {}).get("historial") or {})
                            auto = rep.get("auto_send") or {}
                            auto["last_sent"] = today_key
                            rep["auto_send"] = auto
                            cfg2["reports"]["historial"] = rep
                            save_config(cfg2)
                            self._rep_sched["last_sent"] = today_key
                        except Exception:
                            pass
                    else:
                        logger.error("[auto-send] error enviando %s: %s", _freq, err)
                    # Limpiar archivo temporal
                    try:
                        if os.path.exists(_path):
                            os.remove(_path)
                    except Exception:
                        pass
                    # Quitar referencia al worker
                    try:
                        self._report_workers.remove(_worker)
                    except Exception:
                        pass

                worker.finished.connect(_on_done)
                worker.start()

        except Exception as e:
            logger.error("[auto-send] error en scheduler: %s", e)
            return
