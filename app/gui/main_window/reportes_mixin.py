# app/gui/main_window/reportes_mixin.py
# -*- coding: utf-8 -*-
"""
Programación de envíos automáticos del Historial por email.

Soporta TRES frecuencias INDEPENDIENTES en paralelo: DAILY / WEEKLY / MONTHLY.
Cada una tiene su propio enabled, time, last_sent y parámetros específicos
(weekdays para WEEKLY, month_day para MONTHLY).

Estructura en app_config.json:
    "reports": {
      "historial": {
        "auto_send": {
          "daily":   {"enabled": true,  "time": "21:00", "last_sent": null},
          "weekly":  {"enabled": true,  "time": "21:30", "weekdays": [6], "last_sent": null},
          "monthly": {"enabled": false, "time": "22:00", "month_day": 1,  "last_sent": null}
        }
      }
    }

Backward compat: si encuentra el formato viejo (con "freq" único), lo migra
automáticamente la primera vez que se carga.
"""
import logging

from PyQt5.QtCore import QTimer

logger = logging.getLogger(__name__)


# ── Migración formato viejo → nuevo ───────────────────────────────────────────
def migrate_auto_send_to_v2(auto_legacy: dict) -> dict:
    """
    Convierte el formato viejo (un único `freq`) al nuevo (3 frecuencias paralelas).
    Idempotente: si ya está en formato nuevo, lo devuelve tal cual (con defaults
    completados).

    Formato viejo:
        {"enabled": bool, "freq": "Diario|Semanal|Mensual", "time": "HH:MM",
         "weekdays": [..1..7..], "month_day": int|None, "last_sent": "YYYY-MM-DD"|None}

    Formato nuevo:
        {"daily":   {"enabled": bool, "time": "HH:MM", "last_sent": ...},
         "weekly":  {"enabled": bool, "time": "HH:MM", "weekdays": [..1..7..], "last_sent": ...},
         "monthly": {"enabled": bool, "time": "HH:MM", "month_day": int|None, "last_sent": ...}}
    """
    if not isinstance(auto_legacy, dict):
        auto_legacy = {}

    # Detección: si ya tiene cualquiera de las tres claves nuevas, está migrado.
    is_new = any(k in auto_legacy for k in ("daily", "weekly", "monthly"))

    if is_new:
        # Completar defaults sin pisar lo existente
        result = {
            "daily":   dict(auto_legacy.get("daily")   or {}),
            "weekly":  dict(auto_legacy.get("weekly")  or {}),
            "monthly": dict(auto_legacy.get("monthly") or {}),
        }
    else:
        # Migración real desde formato viejo
        legacy_freq = (auto_legacy.get("freq") or auto_legacy.get("frequency") or "").strip().lower()
        legacy_enabled = bool(auto_legacy.get("enabled", False))
        legacy_time = (auto_legacy.get("time") or "21:00").strip()
        legacy_weekdays = auto_legacy.get("weekdays") or [6]
        legacy_month_day = auto_legacy.get("month_day")
        legacy_last_sent = auto_legacy.get("last_sent")

        def _is(*opts):
            return legacy_freq in opts

        result = {
            "daily": {
                "enabled": legacy_enabled and _is("diario", "daily"),
                "time": legacy_time,
                "last_sent": legacy_last_sent if _is("diario", "daily") else None,
            },
            "weekly": {
                "enabled": legacy_enabled and _is("semanal", "weekly"),
                "time": legacy_time,
                "weekdays": legacy_weekdays,
                "last_sent": legacy_last_sent if _is("semanal", "weekly") else None,
            },
            "monthly": {
                "enabled": legacy_enabled and _is("mensual", "monthly"),
                "time": legacy_time,
                "month_day": legacy_month_day,
                "last_sent": legacy_last_sent if _is("mensual", "monthly") else None,
            },
        }
        logger.info("[auto-send] migracion v1->v2: legacy_freq=%r enabled=%s -> %s",
                    legacy_freq, legacy_enabled, result)

    # Aplicar defaults faltantes en cada slot
    daily = result["daily"]
    daily.setdefault("enabled", False)
    daily.setdefault("time", "21:00")
    daily.setdefault("last_sent", None)

    weekly = result["weekly"]
    weekly.setdefault("enabled", False)
    weekly.setdefault("time", "21:00")
    wd = weekly.get("weekdays") or [6]
    try:
        wd = [int(x) for x in wd if 1 <= int(x) <= 7]
    except Exception:
        wd = [6]
    weekly["weekdays"] = wd or [6]
    weekly.setdefault("last_sent", None)

    monthly = result["monthly"]
    monthly.setdefault("enabled", False)
    monthly.setdefault("time", "21:00")
    md = monthly.get("month_day")
    if isinstance(md, str) and md.strip().isdigit():
        md = int(md)
    elif not isinstance(md, int):
        md = None  # None => último día del mes
    monthly["month_day"] = md
    monthly.setdefault("last_sent", None)

    return result


def _parse_hhmm(time_str: str, default=(21, 0)):
    """Parsea 'HH:MM' devolviendo (hh, mm). Tolerante a errores."""
    try:
        hh, mm = [int(x) for x in (time_str or "").strip().split(":")]
        return hh, mm
    except Exception:
        return default


class ReportesMixin:
    """
    Mixin para programar y ejecutar envíos automáticos de reportes del Historial.
    Soporta DAILY/WEEKLY/MONTHLY simultáneos e independientes.

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
            sched = getattr(self, "_rep_sched", {}) or {}
            any_enabled = any(
                (sched.get(k) or {}).get("enabled")
                for k in ("daily", "weekly", "monthly")
            )
            if any_enabled:
                self._reports_timer.start()
                logger.info("[auto-send] timer activo (cada 60s).")
            else:
                self._reports_timer.stop()
                logger.info("[auto-send] timer detenido (todas las frecuencias deshabilitadas).")
        except Exception as e:
            logger.error("[auto-send] no pude arrancar el timer: %s", e)

    def _armar_reports_scheduler_desde_config(self):
        """
        Lee config y arma `self._rep_sched` con el nuevo formato:
            {
              "tz": str,
              "daily":   {"enabled", "hh", "mm", "last_sent"},
              "weekly":  {"enabled", "hh", "mm", "weekdays", "last_sent"},
              "monthly": {"enabled", "hh", "mm", "month_day", "last_sent"}
            }
        Migra el formato viejo automáticamente si lo detecta.
        """
        from app.config import load as load_config, save as save_config

        cfg = load_config()
        rep = ((cfg.get("reports") or {}).get("historial") or {})
        auto_raw = rep.get("auto_send") or {}

        # Migrar al formato v2 (idempotente)
        auto_v2 = migrate_auto_send_to_v2(auto_raw)

        # Si la migración produjo un cambio real respecto a lo guardado, persistir
        # (para que la próxima sesión no migre de nuevo y la UI lea el formato nuevo).
        try:
            had_legacy = ("freq" in auto_raw) or ("frequency" in auto_raw)
            had_new = any(k in auto_raw for k in ("daily", "weekly", "monthly"))
            if had_legacy and not had_new:
                cfg["reports"]["historial"]["auto_send"] = auto_v2
                save_config(cfg)
                logger.info("[auto-send] config migrada y persistida a formato v2.")
        except Exception as _mig_err:
            logger.warning("[auto-send] no se pudo persistir migracion: %s", _mig_err)

        # TZ desde general
        general = cfg.get("general") or {}
        tz_name = general.get("timezone", "America/Argentina/Buenos_Aires")

        # Construir la estructura de scheduler runtime
        d = auto_v2["daily"]
        w = auto_v2["weekly"]
        m = auto_v2["monthly"]

        d_hh, d_mm = _parse_hhmm(d.get("time"), (21, 0))
        w_hh, w_mm = _parse_hhmm(w.get("time"), (21, 0))
        m_hh, m_mm = _parse_hhmm(m.get("time"), (21, 0))

        self._rep_sched = {
            "tz": tz_name,
            "daily": {
                "enabled": bool(d.get("enabled")),
                "hh": d_hh, "mm": d_mm,
                "last_sent": d.get("last_sent"),
            },
            "weekly": {
                "enabled": bool(w.get("enabled")),
                "hh": w_hh, "mm": w_mm,
                "weekdays": list(w.get("weekdays") or [6]),
                "last_sent": w.get("last_sent"),
            },
            "monthly": {
                "enabled": bool(m.get("enabled")),
                "hh": m_hh, "mm": m_mm,
                "month_day": m.get("month_day"),
                "last_sent": m.get("last_sent"),
            },
        }

        logger.info(
            "[auto-send] armado: tz=%s | daily=%s@%02d:%02d | weekly=%s@%02d:%02d wd=%s | monthly=%s@%02d:%02d md=%s",
            tz_name,
            self._rep_sched["daily"]["enabled"], d_hh, d_mm,
            self._rep_sched["weekly"]["enabled"], w_hh, w_mm, self._rep_sched["weekly"]["weekdays"],
            self._rep_sched["monthly"]["enabled"], m_hh, m_mm, self._rep_sched["monthly"]["month_day"],
        )

    def _tick_reports_scheduler(self):
        """
        Se ejecuta 1 vez por minuto. Evalúa las TRES frecuencias independientemente.
        Cada una tiene su propio last_sent → no se bloquean entre sí.
        """
        from datetime import datetime, timedelta, date

        try:
            sched = getattr(self, "_rep_sched", None)
            if not sched:
                return

            # Hora local con zona horaria
            try:
                from zoneinfo import ZoneInfo  # py>=3.9
                tz = ZoneInfo(sched["tz"])
                now = datetime.now(tz)
            except Exception:
                now = datetime.now()

            today_key = now.strftime("%Y-%m-%d")

            # Calcular día objetivo del mensual una sola vez (lo necesita weekly y monthly)
            def _monthly_target_day(_now, month_day):
                y, m = _now.year, _now.month
                if m == 12:
                    last_day = date(y, 12, 31)
                else:
                    first_next = date(y + (1 if m == 12 else 0), (1 if m == 12 else m + 1), 1)
                    last_day = first_next - timedelta(days=1)
                if month_day:
                    d_clamped = max(1, min(int(month_day), last_day.day))
                    return date(y, m, d_clamped)
                target = last_day
                if target.weekday() == 6:  # domingo -> sábado
                    target = target - timedelta(days=1)
                return target

            freqs_to_send = []  # lista de tuplas (freq_label, slot_dict)

            # ---- DAILY ----
            d = sched.get("daily") or {}
            if d.get("enabled"):
                if d.get("last_sent") != today_key and now.hour == d["hh"] and now.minute == d["mm"]:
                    freqs_to_send.append(("DAILY", "daily"))

            # ---- WEEKLY ----
            w = sched.get("weekly") or {}
            if w.get("enabled"):
                py_wd = now.weekday()       # 0..6 (L..D)
                wd_1_7 = py_wd + 1          # 1..7 (L..D)
                weekdays = w.get("weekdays") or [6]
                if (
                    w.get("last_sent") != today_key
                    and now.hour == w["hh"] and now.minute == w["mm"]
                    and wd_1_7 in weekdays
                ):
                    freqs_to_send.append(("WEEKLY", "weekly"))

            # ---- MONTHLY ----
            m = sched.get("monthly") or {}
            if m.get("enabled"):
                target = _monthly_target_day(now, m.get("month_day"))
                if (
                    m.get("last_sent") != today_key
                    and now.hour == m["hh"] and now.minute == m["mm"]
                    and now.date() == target
                ):
                    freqs_to_send.append(("MONTHLY", "monthly"))

            if not freqs_to_send:
                return

            logger.info("[auto-send] %s -> disparando %s",
                        now.isoformat(), [x[0] for x in freqs_to_send])

            # ===== Generar y enviar =====
            self._enviar_reportes_programados(freqs_to_send, today_key, now)

        except Exception as e:
            logger.error("[auto-send] error en scheduler: %s", e, exc_info=True)
            return

    def _enviar_reportes_programados(self, freqs_to_send, today_key, now):
        """
        Genera el Excel y dispara el SmtpWorker para cada frecuencia que tocó enviar.
        Cada éxito persiste su propio last_sent (independiente).
        """
        import os, tempfile
        from app.config import load as load_config, save as save_config
        from app.gui.historialventas import SmtpWorker

        all_paths = []  # [(freq_label, slot_key, fpath)]
        for freq_label, slot_key in freqs_to_send:
            fd, fpath = tempfile.mkstemp(prefix="historial_", suffix=".xlsx")
            os.close(fd)
            try:
                self.historial._crear_excel(fpath, for_freq=freq_label)
                all_paths.append((freq_label, slot_key, fpath))
            except Exception as ex:
                logger.error("[auto-send] error generando Excel %s: %s", freq_label, ex, exc_info=True)
                try:
                    os.remove(fpath)
                except Exception:
                    pass

        if not all_paths:
            return

        # Cargar config de email una vez
        cfg_mail = load_config()
        email_cfg = (cfg_mail.get("email") or {})
        recips = list(filter(None, email_cfg.get("recipients") or []))
        if not recips:
            logger.error("[auto-send] no hay destinatarios configurados.")
            for _, _, p in all_paths:
                try: os.remove(p)
                except Exception: pass
            return

        subj_prefix = email_cfg.get("subject_prefix") or "[Historial]"

        for freq_label, slot_key, fpath in all_paths:
            subj = f"{subj_prefix} Reporte {freq_label.title()} {today_key}"
            body_text = self._build_report_body(freq_label, today_key)

            worker = SmtpWorker(subj, body_text, recips, [fpath])
            if not hasattr(self, '_report_workers'):
                self._report_workers = []
            self._report_workers.append(worker)

            # Closure por slot para persistir last_sent independiente
            def _make_callback(_freq=freq_label, _slot=slot_key, _path=fpath, _worker=worker):
                def _on_done(ok, err):
                    if ok:
                        logger.info("[auto-send] enviado OK: %s", _freq)
                        try:
                            cfg2 = load_config()
                            rep = ((cfg2.get("reports") or {}).get("historial") or {})
                            auto = rep.get("auto_send") or {}
                            # Migrar si todavía está en formato viejo (raro pero por seguridad)
                            auto = migrate_auto_send_to_v2(auto)
                            slot = auto.get(_slot) or {}
                            slot["last_sent"] = today_key
                            auto[_slot] = slot
                            rep["auto_send"] = auto
                            cfg2.setdefault("reports", {})["historial"] = rep
                            save_config(cfg2)
                            # Reflejar en runtime
                            try:
                                self._rep_sched[_slot]["last_sent"] = today_key
                            except Exception:
                                pass
                        except Exception as _persist_err:
                            logger.warning("[auto-send] no se pudo persistir last_sent[%s]: %s",
                                           _slot, _persist_err)
                    else:
                        logger.error("[auto-send] error enviando %s: %s", _freq, err)
                    # Cleanup tmp y referencia worker
                    try:
                        if os.path.exists(_path):
                            os.remove(_path)
                    except Exception:
                        pass
                    try:
                        self._report_workers.remove(_worker)
                    except Exception:
                        pass
                return _on_done

            worker.finished.connect(_make_callback())
            worker.start()

    def _build_report_body(self, freq_label: str, today_key: str) -> str:
        """Arma el cuerpo del email con resumen de IVA del día."""
        body_lines = ["Se adjunta el reporte automatico.", ""]
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
            except Exception as _pag_err:
                logger.debug("[auto-send] no se pudieron leer pagos para IVA compras: %s", _pag_err)

            _saldo = round(_iva_compras - _iva_ventas, 2)

            body_lines.append(f"--- Resumen del dia {today_key} ({freq_label}) ---")
            body_lines.append(f"Total Ventas: ${_total_ventas:,.2f}  ({_cant} ventas)")
            body_lines.append("")
            body_lines.append("--- IVA ---")
            body_lines.append(f"IVA Compras (pagos proveedores): ${_iva_compras:,.2f}")
            body_lines.append(f"IVA Ventas (con CAE): ${_iva_ventas:,.2f}")
            body_lines.append(f"Saldo IVA (compras - ventas): ${_saldo:,.2f}")
        except Exception as _ex:
            logger.warning("[auto-send] no se pudo calcular IVA para body: %s", _ex)

        return "\n".join(body_lines)
