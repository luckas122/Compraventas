# app/gui/main_window/backups_mixin.py
# -*- coding: utf-8 -*-

from datetime import datetime, timedelta
import os
import zipfile
import shutil
import threading
import time as time_mod
from pathlib import Path        # si usas Path(...)
import tempfile

from PyQt5.QtWidgets import QFileDialog, QMessageBox
import sqlite3
try:
    from app.database import SessionLocal
except Exception:
    SessionLocal = None

class BackupsMixin:
    """
    Mixin del programador de backups.
    Requisitos creados por MainWindow.__init__:
      - self.session (si tu backup lo usa)
      - Config leída desde app.config.load()
    Atributos que este mixin esperará/creará:
      - self._backup_thread (thread en background)
      - self._stop_backup_evt (threading.Event para cortar el loop)
      - self.cfg_edt_bk_dir, self.cfg_chk_bk_enabled (widgets en la pestaña Configuración)
    """

    # Llamar una vez desde MainWindow.__init__:
    def _init_backups(self):
        """Arma configuración y lanza/corta el scheduler de backups según la config actual."""
        try:
            self._setup_backups()
        except Exception as e:
            try:
                QMessageBox.warning(self, "Backups", f"No se pudo inicializar backups:\n{e}")
            except Exception:
                print("[backups] init error:", e)
# =========================
    #   Backups programados
    # =========================
    def _setup_backups(self):
        """
        Arranca (o reinicia) el programador de backups leyendo la config actual.
        Soporta:
        - backup.daily_times (o compat: backup.times_daily)
        - backup.weekly {enabled, weekday(1..7), time('HH:MM')}
        - backup.enabled
        """
        from threading import Event, Thread
        from datetime import datetime, timedelta
        from app.config import load as load_config

        # Si había uno viejo, lo detengo
        try:
            if getattr(self, "_stop_backup_evt", None):
                self._stop_backup_evt.set()
        except Exception:
            pass

        cfg = load_config()
        bk = (cfg.get("backup") or {})
        if not bk.get("enabled", True):
            print("[BACKUP] Programados desactivados.")
            self._backup_thread = None
            return

        # ---- normalización simple (sin helpers externos) ----
        daily_times = bk.get("daily_times") or bk.get("times_daily") or []
        wcfg = bk.get("weekly") or {}
        w_enabled = bool(wcfg.get("enabled", True))
        w_day = int(wcfg.get("weekday", 7))        # 1..7 (ISO)
        w_time = (wcfg.get("time") or "23:30")

        # Calcula y muestra el "próximo"
        def next_dt():
            now = datetime.now()
            bk_days = list(bk.get("days") or [])
            bk_times = list(bk.get("times") or [])

            candidates = []

            # NUEVO: days + times
            if bk_days and bk_times:
                def _mins(hhmm):
                    h, m = [int(x) for x in hhmm.split(":")]
                    return h * 60 + m
                times_m = sorted({_mins(t) for t in bk_times})

                today = now.weekday()  # 0..6
                now_m = now.hour * 60 + now.minute

                # todos los horarios que queden HOY por delante
                if today in bk_days:
                    for tm in times_m:
                        if tm > now_m:
                            h, m = divmod(tm, 60)
                            candidates.append((now.replace(hour=h, minute=m, second=0, microsecond=0), "daily"))

                # y el primer horario del PRÓXIMO día válido
                for add in range(1, 8):
                    d = (today + add) % 7
                    if d in bk_days:
                        base = now + timedelta(days=add)
                        base = base.replace(second=0, microsecond=0)
                        h, m = divmod(times_m[0], 60)
                        candidates.append((base.replace(hour=h, minute=m), "daily"))
                        break

            # LEGACY: solo si NO hay days+times
            else:
                # daily_times
                daily_times = bk.get("daily_times") or bk.get("times_daily") or []
                for t in daily_times:
                    try:
                        h, m = [int(x) for x in t.split(":")]
                        dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
                        if dt <= now:
                            dt += timedelta(days=1)
                        candidates.append((dt, "daily"))
                    except Exception:
                        pass

                # weekly
                wcfg = bk.get("weekly") or {}
                if bool(wcfg.get("enabled", True)):
                    try:
                        h, m = [int(x) for x in (wcfg.get("time") or "23:30").split(":")]
                        want = (int(wcfg.get("weekday", 7)) - 1) % 7
                        add = (want - now.weekday()) % 7
                        dtw = now.replace(hour=h, minute=m, second=0, microsecond=0) + timedelta(days=add)
                        if dtw <= now:
                            dtw += timedelta(days=7)
                        candidates.append((dtw, "weekly"))
                    except Exception:
                        pass

            if not candidates:
                return None, None

            candidates.sort(key=lambda x: x[0])
            return candidates[0]

        nxt, kind = next_dt()
        if nxt:
            secs = int((nxt - datetime.now()).total_seconds())
            print(f"[BACKUP] Próximo ({kind}) → {nxt:%Y-%m-%d %H:%M:%S} (en {max(0, secs)}s)")
        else:
            print("[BACKUP] No hay horarios configurados.")
            return

        # Señal de parada + hilo
        self._stop_backup_evt = Event()

        t = Thread(target=self._backup_scheduler_loop, name="BackupScheduler", daemon=True)
        t.start()
        self._backup_thread = t
        
    def _stop_backups(self):
    #Detiene el hilo/loop de backups si está corriendo.
        try:
            if getattr(self, "_stop_backup_evt", None):
                self._stop_backup_evt.set()
        except Exception:
            pass
        self._backup_thread = None
        
        
    def _backup_scheduler_loop(self):
        """
        Bucle del programador de backups.
        - Si existen backup.days (0..6) y backup.times (['HH:MM', ...]), usa SOLO ese esquema.
        - Si NO existen days+times, cae al esquema legacy: daily_times y/o weekly.
        - Muestra en consola el próximo disparo y ejecuta self._run_backup(kind) al llegar la hora.
        - Espera en tramos cancelables con self._stop_backup_evt.
        """
        from datetime import datetime, timedelta
        from app.config import load as load_config

        stop_evt = getattr(self, "_stop_backup_evt", None)

        while True:
            # Salida ordenada
            if stop_evt and stop_evt.is_set():
                print("[BACKUP] Scheduler detenido.")
                return

            # Cargar configuración actual en cada ciclo (permite cambios en caliente)
            cfg = load_config() or {}
            bk = (cfg.get("backup") or {})

            if not bk.get("enabled", True):
                print("[BACKUP] Programados desactivados (loop).")
                return

            now = datetime.now()
            candidates = []

            # Nuevo esquema: days + times
            bk_days = list(bk.get("days") or [])
            bk_times = list(bk.get("times") or [])

            if bk_days and bk_times:
                def _mins(hhmm: str):
                    try:
                        h, m = [int(x) for x in hhmm.split(":")]
                        return h * 60 + m
                    except Exception:
                        return None

                times_m = sorted({tm for tm in (_mins(t) for t in bk_times) if tm is not None})
                today = now.weekday()  # 0..6 (lunes=0)
                now_m = now.hour * 60 + now.minute

                # Hoy: primer horario restante
                if today in bk_days:
                    for tm in times_m:
                        if tm > now_m:
                            h, m = divmod(tm, 60)
                            candidates.append((now.replace(hour=h, minute=m, second=0, microsecond=0), "daily"))
                            break

                # Próximo día válido: primer horario del día
                if not candidates:
                    for add in range(1, 8):
                        d = (today + add) % 7
                        if d in bk_days:
                            base = now + timedelta(days=add)
                            base = base.replace(second=0, microsecond=0)
                            if times_m:
                                h, m = divmod(times_m[0], 60)
                                candidates.append((base.replace(hour=h, minute=m), "daily"))
                            break

            else:
                # Legacy: daily_times
                daily_times = bk.get("daily_times") or bk.get("times_daily") or []
                for t in daily_times:
                    try:
                        h, m = [int(x) for x in t.split(":")]
                        dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
                        if dt <= now:
                            dt += timedelta(days=1)
                        candidates.append((dt, "daily"))
                    except Exception:
                        pass

                # Legacy: weekly
                wcfg = bk.get("weekly") or {}
                if bool(wcfg.get("enabled", True)):
                    try:
                        h, m = [int(x) for x in (wcfg.get("time") or "23:30").split(":")]
                        want = (int(wcfg.get("weekday", 7)) - 1) % 7  # 1..7 → 0..6
                        add = (want - now.weekday()) % 7
                        dtw = now.replace(hour=h, minute=m, second=0, microsecond=0) + timedelta(days=add)
                        if dtw <= now:
                            dtw += timedelta(days=7)
                        candidates.append((dtw, "weekly"))
                    except Exception:
                        pass

            if not candidates:
                print("[BACKUP] Sin horarios configurados. Reviso en 60s…")
                if stop_evt and stop_evt.wait(60):
                    print("[BACKUP] Scheduler detenido.")
                    return
                continue

            candidates.sort(key=lambda x: x[0])
            nxt, kind = candidates[0]
            wait = max(1, int((nxt - datetime.now()).total_seconds()))
            print(f"[BACKUP] Próximo ({kind}) → {nxt:%Y-%m-%d %H:%M:%S} (en {wait}s)")

            # Espera cancelable en tramos cortos
            slept = 0
            while slept < wait:
                chunk = min(30, wait - slept)
                if stop_evt and stop_evt.wait(chunk):
                    print("[BACKUP] Scheduler detenido.")
                    return
                slept += chunk

            # Ejecutar backup
            try:
                print(f"[BACKUP] Ejecutando tipo={kind}…")
            except Exception:
                pass

            try:
                self._run_backup(kind or "daily")
            except Exception as e:
                print(f"[BACKUP] Error al ejecutar: {e!r}")

            # Pequeña espera para evitar doble disparo en el mismo minuto
            if stop_evt and stop_evt.wait(2):
                print("[BACKUP] Scheduler detenido.")
                return


    def _calc_next_backup_datetime(self, ref_dt: datetime):
        from app.config import load as load_config
        """
        Devuelve (datetime_siguiente, tag) donde tag ∈ {"daily","weekly"} según sea el más próximo.
        """
        cfg = load_config()
        bk = (cfg or {}).get("backup") or {}
        daily_times = list((bk.get("daily_times") or []))
        weekly = bk.get("weekly") or {"weekday": 7, "time": "23:30"}

        cands = []

        # — diarios —
        for hhmm in daily_times:
            try:
                h, m = [int(x) for x in hhmm.split(":")]
            except Exception:
                continue
            cand = ref_dt.replace(hour=h, minute=m, second=0, microsecond=0)
            if cand <= ref_dt:
                cand = cand + timedelta(days=1)
            cands.append((cand, "daily"))

        # — semanal —
        # weekday: 1..7 (L..D)  → convertir a 0..6 para Python (Lunes=0)
        try:
            wd_conf = int(weekly.get("weekday", 7))
            wd_py = (wd_conf - 1) % 7
            h, m = [int(x) for x in str(weekly.get("time", "23:30")).split(":")]
        except Exception:
            wd_py, h, m = 6, 23, 30  # domingo 23:30 por defecto

        # próximo weekly
        cand_w = ref_dt.replace(hour=h, minute=m, second=0, microsecond=0)
        # avanzar hasta el weekday correcto
        while cand_w.weekday() != wd_py or cand_w <= ref_dt:
            cand_w = cand_w + timedelta(days=1)
        cands.append((cand_w, "weekly"))

        if not cands:
            return None, None

        cands.sort(key=lambda t: t[0])
        return cands[0]
    
    def _calc_next_backup(self, bk):
        """
        Calcula el próximo datetime y el tipo ('daily' o 'weekly') según 'bk' normalizado.
        """
        from datetime import datetime, timedelta
        now = datetime.now()

        candidates = []

        # diarios
        for hhmm in (bk.get("daily_times") or []):
            try:
                h, m = [int(x) for x in hhmm.split(":")]
            except Exception:
                continue
            dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if dt <= now:
                dt += timedelta(days=1)
            candidates.append((dt, "daily"))

        # semanal
        w = bk.get("weekly") or {}
        if w.get("enabled", True):
            weekday = int(w.get("weekday", 7))  # 1..7
            h, m = [int(x) for x in (w.get("time") or "23:30").split(":")]
            # datetime.weekday(): lunes=0..domingo=6 => mapeo 1..7 a 0..6
            want = (weekday - 1) % 7
            days_a = (want - now.weekday()) % 7
            dtw = now.replace(hour=h, minute=m, second=0, microsecond=0) + timedelta(days=days_a)
            if dtw <= now:
                dtw += timedelta(days=7)
            candidates.append((dtw, "weekly"))

        if not candidates:
            return None, None

        candidates.sort(key=lambda x: x[0])
        return candidates[0]
    
    def _run_backup(self, tag: str, dest_override: str = None):
        """
        Realiza backup ZIP (nivel configurable) de:
        - Base SQLite (copia segura mediante API backup)
        - app_config.json
        Archiva como: <dest>/<tag>-YYYYmmdd-HHMMSS.zip

        Devuelve: ruta completa del ZIP creado, o None si falla.
        """
        print(f"[BACKUP] Ejecutando tipo={tag} …")
        try:
            from app.config import load as load_config, CONFIG_PATH
        except Exception:
            CONFIG_PATH = None
            from app.config import load as load_config

        cfg = load_config()
        bk  = (cfg or {}).get("backup") or {}
        # --------- destino ---------
        dest_dir = dest_override or (bk.get("dir") or "")
        dest_dir = dest_dir.strip()

        if dest_dir:
            # Normaliza: soporta "~" y %VARIABLES%
            dest_dir = os.path.abspath(os.path.expanduser(os.path.expandvars(dest_dir)))
        else:
            # ./backups junto al proyecto (fallback)
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            dest_dir = os.path.join(base_dir, "backups")

        try:
            os.makedirs(dest_dir, exist_ok=True)
        except Exception as e:
            print(f"[BACKUP] No se pudo crear la carpeta destino '{dest_dir}': {e!r}")
            return None
        # --------- localizar DB (preferir self.session) ---------
        db_path = None
        try:
            # 1) Intentar con la sesión ya abierta en la app
            bind = getattr(getattr(self, "session", None), "bind", None)
            if bind is not None and getattr(bind, "url", None) is not None:
                if bind.url.get_backend_name() == "sqlite":
                    db_path = bind.url.database
        except Exception:
            db_path = None

        if not db_path:
            # 2) Fallback: sesión efímera
            try:
                _s = SessionLocal()
                try:
                    bind = getattr(_s, "bind", None)
                    if bind is not None and getattr(bind, "url", None) is not None:
                        if bind.url.get_backend_name() == "sqlite":
                            db_path = bind.url.database
                finally:
                    _s.close()
            except Exception as e:
                print(f"[BACKUP] No se pudo obtener la ruta de la base: {e!r}")

        if not db_path or not os.path.exists(db_path):
            print(f"[BACKUP] Ruta de DB inválida o inexistente: {db_path}")
            return None

        # --------- compresión ----------
        try:
            level = int(((bk.get("compress") or {}).get("level", 9)))
        except Exception:
            level = 9
        level = max(0, min(9, level))

        ts       = datetime.now().strftime("%Y%m%d-%H%M%S")
        zip_name = f"{tag}-{ts}.zip"
        zip_path = os.path.join(dest_dir, zip_name)

        # Copia segura de SQLite a un archivo temporal .sqlite
        tmp_copy = db_path + ".backup_tmp.sqlite"
        try:
            # Preferir backup por API nativa (segura con BD en uso)
            try:
                with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as src, \
                    sqlite3.connect(tmp_copy) as dst:
                    src.backup(dst)
            except Exception as e_api:
                # Fallback: copia directa
                try:
                    shutil.copy2(db_path, tmp_copy)
                except Exception as e_cp:
                    print(f"[BACKUP] Error copiando DB (api:{e_api!r} / copy:{e_cp!r})")
                    return None

            # Empaquetar ZIP
            with zipfile.ZipFile(
                zip_path,
                mode="w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=level
            ) as zf:
                # DB
                zf.write(tmp_copy, arcname=os.path.basename(db_path))
                # Config JSON (si existe)
                if CONFIG_PATH and os.path.exists(CONFIG_PATH):
                    zf.write(CONFIG_PATH, arcname="app_config.json")

            print(f"[BACKUP] OK → {zip_path}")
        finally:
            # limpiar temporal
            try:
                if os.path.exists(tmp_copy):
                    os.remove(tmp_copy)
            except Exception:
                pass

        # --------- limpieza (retención) ----------
        try:
            self._cleanup_old_backups(dest_dir, tag)
        except Exception as e:
            print(f"[BACKUP] Limpieza falló: {e!r}")

        return zip_path
    
    
    def _cleanup_old_backups(self, dest_dir: str, tag: str):
        from app.config import load as load_config
        """
        Borra backups más viejos que 'retention_days[tag]'.
        """
        cfg = load_config()
        bk = (cfg or {}).get("backup") or {}
        ret = (bk.get("retention_days") or {})
        days = int(ret.get(tag, 30 if tag == "daily" else 180))

        now = datetime.now()
        for name in os.listdir(dest_dir):
            if not name.lower().endswith(".zip"):
                continue
            if not name.startswith(f"{tag}-"):
                continue
            full = os.path.join(dest_dir, name)
            try:
                mtime = datetime.fromtimestamp(os.path.getmtime(full))
                if (now - mtime).days > days:
                    os.remove(full)
                    print(f"[BACKUP] Eliminado viejo: {name}")
            except Exception:
                pass
            
    def _restore_from_zip(self):
        from PyQt5.QtWidgets import QFileDialog, QMessageBox, QApplication
        import os, zipfile, tempfile, shutil, sqlite3

        # 1) Seguridad: requerir admin (si aplicás gating en otras acciones)
        try:
            if hasattr(self, "_ensure_admin") and not self._ensure_admin("restaurar la base de datos"):
                return
        except Exception:
            pass

        # 2) Selección del ZIP
        path, _ = QFileDialog.getOpenFileName(self, "Elegir backup (.zip)", "", "Backups (*.zip)")
        if not path:
            return

        # 3) Confirmación fuerte (esto reemplaza la DB)
        if QMessageBox.question(
            self, "Confirmar restauración",
            "La base de datos actual será reemplazada.\n"
            "Se hará un backup automático antes de continuar.\n\n"
            "¿Deseás seguir?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        ) != QMessageBox.Yes:
            return

        # 4) Detectar ruta actual de la DB (preferir bind de la sesión)
        db_path = None
        try:
            bind = getattr(getattr(self, "session", None), "bind", None)
            if bind is not None and getattr(bind, "url", None) is not None:
                if bind.url.get_backend_name() == "sqlite":
                    db_path = bind.url.database
        except Exception:
            db_path = None

        if not db_path or not os.path.exists(db_path):
            QMessageBox.critical(self, "Restaurar", "No se pudo ubicar el archivo de base de datos actual.")
            return

        # 5) Backup previo automático
        try:
            self._run_backup(tag="pre-restore")
        except Exception:
            pass  # si falla, igual seguimos (el usuario ya confirmó)

        # 6) Abrir ZIP y localizar la DB adentro
        try:
            zf = zipfile.ZipFile(path, "r")
        except Exception as e:
            QMessageBox.critical(self, "Restaurar", f"ZIP inválido:\n{e}")
            return

        basename = os.path.basename(db_path)
        member_db = None
        try:
            # Preferir nombre exacto; si no, tomar el primer .db/.sqlite que haya
            names = zf.namelist()
            for n in names:
                low = n.lower()
                if os.path.basename(n) == basename:
                    member_db = n
                    break
            if not member_db:
                for n in names:
                    low = n.lower()
                    if low.endswith(".db") or low.endswith(".sqlite"):
                        member_db = n
                        break
            if not member_db:
                QMessageBox.critical(self, "Restaurar", "El ZIP no contiene una base de datos reconocible.")
                zf.close()
                return

            tmpdir = tempfile.mkdtemp(prefix="restore_db_")
            tmp_src = zf.extract(member_db, path=tmpdir)
        except Exception as e:
            try: zf.close()
            except Exception: pass
            QMessageBox.critical(self, "Restaurar", f"No se pudo extraer la base:\n{e}")
            return

        # 7) (Opcional) Restaurar también app_config.json
        restore_cfg = False
        try:
            from app.config import CONFIG_PATH  # ya existe en tu proyecto
            if "app_config.json" in zf.namelist():
                restore_cfg = (QMessageBox.question(
                    self, "Config",
                    "Se encontró 'app_config.json' en el backup.\n¿Restaurar también la configuración?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No
                ) == QMessageBox.Yes)
        except Exception:
            CONFIG_PATH = None
            restore_cfg = False

        # 8) Cerrar conexiones a la DB antes de reemplazar
        try:
            if getattr(self, "session", None):
                try:
                    self.session.close()
                except Exception:
                    pass
                try:
                    if getattr(self.session, "bind", None) and hasattr(self.session.bind, "dispose"):
                        self.session.bind.dispose()
                except Exception:
                    pass
        except Exception:
            pass

        # 9) Reemplazar de forma segura
        try:
            # Método robusto: copiar por encima (la app ya cerró conexiones)
            shutil.copy2(tmp_src, db_path)
        except Exception as e:
            QMessageBox.critical(self, "Restaurar", f"No se pudo reemplazar la base actual:\n{e}")
            try: shutil.rmtree(tmpdir, ignore_errors=True)
            except Exception: pass
            try: zf.close()
            except Exception: pass
            return

        # 10) Restaurar config si procede
        if restore_cfg and CONFIG_PATH:
            try:
                cfg_tmp = None
                for n in zf.namelist():
                    if os.path.basename(n) == "app_config.json":
                        cfg_tmp = zf.extract(n, path=tmpdir)
                        break
                if cfg_tmp:
                    shutil.copy2(cfg_tmp, CONFIG_PATH)
            except Exception as e:
                QMessageBox.warning(self, "Config", f"No se pudo restaurar app_config.json:\n{e}")

        # Limpieza
        try: zf.close()
        except Exception: pass
        try: shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception: pass

        # 11) Avisar y cerrar para reiniciar (evita inconsistencias de sesión)
        QMessageBox.information(
            self, "Restauración completa",
            "La restauración finalizó correctamente.\nReiniciando la aplicación…"
        )
        self._restart_application()
        return
        

    
    def _restart_application(self):
        import sys, os, subprocess
        try:
            from PyQt5.QtCore import QProcess, QCoreApplication
        except Exception:
            from PySide2.QtCore import QProcess, QCoreApplication

        exe  = sys.executable
        args = list(sys.argv)

        # 1) Intento Qt nativo (recomendado)
        try:
            ok = QProcess.startDetached(exe, args)
        except Exception:
            ok = False

        # 2) Fallback estándar de Python
        if not ok:
            try:
                subprocess.Popen([exe] + args, close_fds=True)
                ok = True
            except Exception:
                ok = False

        # 3) Último recurso (dev): reejecutar el proceso actual
        if not ok:
            try:
                os.execv(exe, [exe] + args)
                return
            except Exception:
                pass

        # Cerrar esta instancia si ya lanzamos la nueva
        QCoreApplication.exit(0)
        


            
            
    def _choose_backup_dir(self):
        from PyQt5.QtWidgets import QFileDialog
        d = QFileDialog.getExistingDirectory(self, "Elegir carpeta para backups")
        if d:
            self.cfg_edt_bk_dir.setText(d)

    
    
    
    def _backup_now_from_ui(self):
        from PyQt5.QtWidgets import QMessageBox
        try:
            path = self._run_backup(tag="manual")
            if path:
                QMessageBox.information(self, "Backup", f"Backup creado:\n{path}")
            else:
                QMessageBox.warning(self, "Backup", "No se pudo crear el backup.")
        except Exception as e:
            QMessageBox.critical(self, "Backup", f"Error:\n{e}")
    
    
    def _browse_backup_dir(self):
        from PyQt5.QtWidgets import QFileDialog
        path = QFileDialog.getExistingDirectory(self, "Elegir carpeta de backups", self.cfg_edt_bk_dir.text().strip() or "")
        if path:
            self.cfg_edt_bk_dir.setText(path)
            
    
    def _backup_cfg_normalized(self):
        """
        Devuelve un dict 'bk' normalizado con estas claves:
        - enabled: bool
        - dir: str | None
        - daily_times: List[str]          # ['HH:MM', ...]
        - weekly: { 'enabled': bool, 'weekday': 1..7, 'time': 'HH:MM' }
        - retention_days: { 'daily': int, 'weekly': int }   # weekly en días
        - compress: { 'format': 'zip', 'level': 0..9 }
        Lee claves viejas si hiciera falta (times_daily / retention).
        """
        from app.config import load as load_config
        cfg = load_config()
        bk = (cfg or {}).get("backup") or {}

        # compat: times_daily -> daily_times
        daily_times = bk.get("daily_times")
        if not daily_times:
            daily_times = bk.get("times_daily") or []

        # compat: retention -> retention_days (weekly_weeks -> weekly días)
        ret = bk.get("retention_days")
        if not ret:
            r_old = bk.get("retention") or {}
            daily_d = int(r_old.get("daily_days", 30))
            weekly_w = int(r_old.get("weekly_weeks", 12))
            ret = {"daily": daily_d, "weekly": weekly_w * 7}
        else:
            # asegurar tipos
            ret = {
                "daily": int(ret.get("daily", 30)),
                "weekly": int(ret.get("weekly", 180))
            }

        weekly = bk.get("weekly") or {}
        weekly_enabled = bool(weekly.get("enabled", True))
        weekday = int(weekly.get("weekday", 7))
        wtime = (weekly.get("time") or "23:30")


        return {
    "enabled": bool(bk.get("enabled", True)),
    "dir": bk.get("dir"),
    "days": list(bk.get("days") or []),
    "times": list(bk.get("times") or []),
    "daily_times": list(daily_times),
    "weekly": {
        "enabled": weekly_enabled,
        "weekday": weekday,
        "time": wtime
    },
    "retention_days": ret,
    "compress": (bk.get("compress") or {"format": "zip", "level": 9})
}
