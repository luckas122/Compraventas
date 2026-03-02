import logging
import sys
from PyQt5.QtWidgets import QApplication, QDialog
from PyQt5.QtGui import QFont, QIcon, QFontDatabase

from app.database import init_db, SessionLocal
from app.login import LoginDialog, CreateAdminDialog
from app.repository import UsuarioRepo

# Información de versión
from version import __version__, __app_name__

logger = logging.getLogger(__name__)


if __name__ == "__main__":
    # 1) Resetear log UNA vez por arranque
    from app.utils_timing import reset_log
    reset_log()

    # 2) Inicializar BD
    init_db()

    # 3) Crear app Qt
    app = QApplication(sys.argv)
    app.setApplicationName(__app_name__)
    app.setApplicationVersion(__version__)

    # 3.5) Verificar si hay backup de configuración pendiente (después de actualización)
    try:
        from app.config import has_pending_backup, restore_from_backup, delete_backup
        from PyQt5.QtWidgets import QMessageBox
        import subprocess

        if has_pending_backup():
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Question)
            msg.setWindowTitle("Configuración anterior detectada")
            msg.setText(
                "Se detectó una configuración guardada de una versión anterior.\n\n"
                "¿Desea restaurar su configuración anterior?\n"
                "(Esto incluye ajustes de SMTP, AFIP, tickets, etc.)"
            )
            msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            msg.setDefaultButton(QMessageBox.Yes)
            btn_yes = msg.button(QMessageBox.Yes)
            btn_yes.setText("Sí, restaurar")
            btn_no = msg.button(QMessageBox.No)
            btn_no.setText("No, usar nueva")

            respuesta = msg.exec_()

            if respuesta == QMessageBox.Yes:
                if restore_from_backup():
                    QMessageBox.information(
                        None,
                        "Configuración restaurada",
                        "La configuración se restauró correctamente.\n"
                        "La aplicación se reiniciará para aplicar los cambios."
                    )
                    # Reiniciar la aplicación
                    import os
                    if getattr(sys, 'frozen', False):
                        # Modo frozen: reiniciar el exe directamente
                        os.startfile(sys.executable)
                    else:
                        # Modo desarrollo
                        subprocess.Popen([sys.executable] + sys.argv)
                    sys.exit(0)
                else:
                    QMessageBox.warning(
                        None,
                        "Error",
                        "No se pudo restaurar la configuración.\n"
                        "Se usará la configuración por defecto."
                    )
                    delete_backup()
            else:
                # Usuario eligió no restaurar, eliminar backup
                delete_backup()
                QMessageBox.information(
                    None,
                    "Configuración nueva",
                    "Se usará la configuración por defecto."
                )
    except Exception as e:
        logger.error("[BACKUP] Error verificando backup de config: %s", e)

    # 3.6) Detección de actualización: mostrar diálogo ANTES del login
    try:
        from app.config import load as _load_cfg_upd, save as _save_cfg_upd, CONFIG_PATH as _cfg_path
        from app.config import restore_from_path as _restore_from_path, _get_app_data_dir
        from PyQt5.QtWidgets import QMessageBox, QInputDialog, QLineEdit, QFileDialog
        import os as _os

        _cfg_upd = _load_cfg_upd()
        _last_ver = _cfg_upd.get("_last_version", "")
        _config_exists = _os.path.exists(_cfg_path)

        _show_update_dialog = False
        if _config_exists:
            if _last_ver and _last_ver != __version__:
                _show_update_dialog = True
            elif not _last_ver:
                # Config existe pero sin _last_version: primera vez que detectamos
                _has_real_data = bool(
                    _cfg_upd.get("sync", {}).get("enabled")
                    or _cfg_upd.get("sucursal")
                    or _cfg_upd.get("printers")
                    or _cfg_upd.get("general")
                )
                if _has_real_data:
                    _show_update_dialog = True
                else:
                    _cfg_upd["_last_version"] = __version__
                    _save_cfg_upd(_cfg_upd)

        if _show_update_dialog:
            _ver_anterior = _last_ver or "anterior"
            _msg_upd = QMessageBox()
            _msg_upd.setWindowTitle("Actualización detectada")
            _msg_upd.setIcon(QMessageBox.Question)
            _msg_upd.setText(
                f"Se actualizó de v{_ver_anterior} a v{__version__}.\n\n"
                f"Tu configuración anterior se ha detectado.\n"
                f"¿Qué querés hacer?"
            )
            _btn_mantener = _msg_upd.addButton("Mantener configuración", QMessageBox.AcceptRole)
            _btn_restaurar = _msg_upd.addButton("Restaurar desde archivo...", QMessageBox.ActionRole)
            _btn_eliminar = _msg_upd.addButton("Eliminar todo y empezar de nuevo", QMessageBox.DestructiveRole)
            _msg_upd.setDefaultButton(_btn_mantener)
            _msg_upd.exec_()

            _clicked = _msg_upd.clickedButton()

            if _clicked == _btn_mantener:
                _cfg_upd["_last_version"] = __version__
                _save_cfg_upd(_cfg_upd)

            elif _clicked == _btn_restaurar:
                _path_r, _ = QFileDialog.getOpenFileName(
                    None, "Elegir app_config.json", "",
                    "JSON (*.json);;Todos (*.*)"
                )
                if _path_r:
                    if _restore_from_path(_path_r):
                        _cfg_new = _load_cfg_upd()
                        _cfg_new["_last_version"] = __version__
                        _save_cfg_upd(_cfg_new)
                        QMessageBox.information(
                            None, "Restauración exitosa",
                            "Configuración restaurada.\n"
                            "La aplicación se reiniciará para aplicar los cambios."
                        )
                        if getattr(sys, 'frozen', False):
                            _os.startfile(sys.executable)
                        else:
                            subprocess.Popen([sys.executable] + sys.argv)
                        sys.exit(0)
                    else:
                        QMessageBox.warning(None, "Error", "No se pudo restaurar la configuración.")
                        _cfg_upd["_last_version"] = __version__
                        _save_cfg_upd(_cfg_upd)
                else:
                    # Canceló el diálogo de archivo → mantener
                    _cfg_upd["_last_version"] = __version__
                    _save_cfg_upd(_cfg_upd)

            elif _clicked == _btn_eliminar:
                # Autenticación: intentar con admin de BD, o admin/admin como fallback
                _autenticado = False
                _session_tmp = SessionLocal()
                _repo_tmp = UsuarioRepo(_session_tmp)
                _usuarios = _repo_tmp.listar()
                _admins = [u for u in _usuarios if u.es_admin]

                if _admins:
                    # Intentar con contraseña admin x2
                    _admin_user = _admins[0]
                    _pw1, _ok1 = QInputDialog.getText(
                        None, "Confirmación 1/2",
                        f"Contraseña de '{_admin_user.username}' (1/2):",
                        QLineEdit.Password
                    )
                    if _ok1 and _pw1:
                        if _repo_tmp.verificar(_admin_user.username, _pw1):
                            _pw2, _ok2 = QInputDialog.getText(
                                None, "Confirmación 2/2",
                                f"Confirme contraseña de '{_admin_user.username}' (2/2):",
                                QLineEdit.Password
                            )
                            if _ok2 and _pw2 and _repo_tmp.verificar(_admin_user.username, _pw2):
                                _autenticado = True
                            else:
                                QMessageBox.critical(None, "Error", "Contraseña incorrecta en segunda confirmación.")
                        else:
                            # Contraseña admin falló, ofrecer admin/admin como fallback
                            QMessageBox.warning(None, "Contraseña incorrecta",
                                "Contraseña de administrador incorrecta.\n"
                                "Puede intentar con las credenciales alternativas: admin/admin")
                            _pw_alt, _ok_alt = QInputDialog.getText(
                                None, "Credenciales alternativas",
                                "Ingrese contraseña alternativa (admin):",
                                QLineEdit.Password
                            )
                            if _ok_alt and _pw_alt == "admin":
                                _autenticado = True
                elif not _usuarios:
                    # BD vacía, permitir directamente
                    _resp_vacia = QMessageBox.warning(
                        None, "Confirmar eliminación",
                        "No hay usuarios en la base de datos.\n"
                        "¿Confirma que desea eliminar todo?",
                        QMessageBox.Yes | QMessageBox.No, QMessageBox.No
                    )
                    _autenticado = (_resp_vacia == QMessageBox.Yes)
                else:
                    # Hay usuarios pero ningún admin → ofrecer admin/admin
                    _pw_alt2, _ok_alt2 = QInputDialog.getText(
                        None, "Credenciales de eliminación",
                        "Ingrese contraseña de eliminación (admin):",
                        QLineEdit.Password
                    )
                    if _ok_alt2 and _pw_alt2 == "admin":
                        _autenticado = True

                _session_tmp.close()

                if _autenticado:
                    # Confirmar una última vez
                    _resp_final = QMessageBox.warning(
                        None, "ELIMINAR TODO",
                        "Esta acción eliminará:\n\n"
                        "- Base de datos completa (productos, ventas, proveedores, usuarios)\n"
                        "- Configuración de la aplicación\n"
                        "- Cola de sincronización y logs\n\n"
                        "NO SE PUEDE DESHACER.\n"
                        "La aplicación se reiniciará como nueva.",
                        QMessageBox.Ok | QMessageBox.Cancel,
                        QMessageBox.Cancel
                    )
                    if _resp_final == QMessageBox.Ok:
                        import tempfile
                        from pathlib import Path as _Path
                        from app.database import DB_PATH

                        _db_path_str = str(DB_PATH)
                        _app_data = _get_app_data_dir()

                        _files_del = [
                            _db_path_str,
                            _db_path_str + "-shm",
                            _db_path_str + "-wal",
                            _cfg_path,
                            _os.path.join(_app_data, "sync_queue.json"),
                            _os.path.join(_app_data, "config_restore.marker"),
                        ]
                        _logs_dir = _os.path.join(_app_data, "logs")

                        _del_cmds = []
                        for _f in _files_del:
                            _del_cmds.append(f'if exist "{_f}" del /f /q "{_f}"')
                        _del_cmds.append(f'if exist "{_logs_dir}" rmdir /s /q "{_logs_dir}"')

                        if getattr(sys, 'frozen', False):
                            _app_exe = sys.executable
                            _relaunch = f'start "" "{_app_exe}"'
                        else:
                            _app_exe = str(_Path(__file__).resolve())
                            _relaunch = f'start "" "{sys.executable}" "{_app_exe}"'

                        _temp_dir = _Path(tempfile.gettempdir()) / "TuLocal2025_cleanup"
                        _temp_dir.mkdir(parents=True, exist_ok=True)
                        _bat = _temp_dir / "cleanup.bat"
                        _bat_content = f"""@echo off
echo Esperando que la aplicacion se cierre...
timeout /t 3 /nobreak >nul
echo Eliminando base de datos y configuracion...
{chr(10).join(_del_cmds)}
echo Eliminacion completada.
echo Reiniciando aplicacion...
{_relaunch}
del "%~f0"
"""
                        _bat.write_text(_bat_content, encoding="utf-8")
                        subprocess.Popen(
                            ['cmd', '/c', str(_bat)],
                            creationflags=subprocess.CREATE_NO_WINDOW
                        )
                        _os._exit(0)
                    else:
                        # Canceló la confirmación final → mantener
                        _cfg_upd["_last_version"] = __version__
                        _save_cfg_upd(_cfg_upd)
                else:
                    # No autenticado → mantener configuración
                    _cfg_upd["_last_version"] = __version__
                    _save_cfg_upd(_cfg_upd)

    except Exception as e:
        logger.error("[UPDATE] Error en detección de actualización: %s", e)

    # Configuración general: minimizar a bandeja al cerrar
    try:
        from app.config import load as load_config
        cfg_main = load_config()
        gen_main = cfg_main.get("general") or {}
        if gen_main.get("minimize_to_tray_on_close", False):
            # Si está activado, que NO se cierre el proceso cuando se cierra la última ventana
            app.setQuitOnLastWindowClosed(False)
    except Exception as e:
        logger.error("[CONFIG] No se pudo aplicar minimize_to_tray_on_close: %s", e)

    # Icono global de la aplicación (para ventanas y barra de tareas)
    try:
        from pathlib import Path

        # Modo congelado (EXE con PyInstaller)
        if getattr(sys, "frozen", False):
            base = Path(sys.executable).parent
            candidates = [
                base / "assets" / "shop_106574.ico",
                base / "_internal" / "assets" / "shop_106574.ico",
            ]
        else:
            # Modo desarrollo (python main.py desde el repo)
            here = Path(__file__).resolve().parent
            candidates = [
                here / "assets" / "shop_106574.ico",
                here / "app" / "assets" / "shop_106574.ico",
            ]

        for p in candidates:
            if p.exists():
                app.setWindowIcon(QIcon(str(p)))
                break
    except Exception as e:
        logger.warning("[ICON] No se pudo asignar icono global: %s", e)

    # (mantengo tu estilo de checkbox)
    app.setStyleSheet("""
        QCheckBox::indicator { width: 22px; height: 22px; }
        QCheckBox { margin: 0; padding: 0; }
    """)

    # Cargar fuente Roboto desde assets
    roboto_loaded = False
    try:
        from pathlib import Path

        if getattr(sys, "frozen", False):
            base = Path(sys.executable).parent
            font_candidates = [
                base / "assets" / "Roboto.ttf",
                base / "_internal" / "assets" / "Roboto.ttf",
            ]
        else:
            here = Path(__file__).resolve().parent
            font_candidates = [
                here / "assets" / "Roboto.ttf",
            ]

        for font_path in font_candidates:
            if font_path.exists():
                font_id = QFontDatabase.addApplicationFont(str(font_path))
                if font_id != -1:
                    families = QFontDatabase.applicationFontFamilies(font_id)
                    if families:
                        roboto_loaded = True
                        logger.info("[FONT] Roboto cargada correctamente: %s", families[0])
                break
    except Exception as e:
        logger.warning("[FONT] Error cargando Roboto: %s", e)

    # Fuente global: Roboto si está disponible, sino Arial como fallback
    if roboto_loaded:
        app.setFont(QFont("Roboto", 10))
    else:
        app.setFont(QFont("Arial", 10))

    # 4) Sesión y chequeo de primer usuario
    session = SessionLocal()
    if len(UsuarioRepo(session).listar()) == 0:
        # No hay usuarios: lanzar asistente para crear el primero (admin)
        wizard = CreateAdminDialog(session)
        if wizard.exec_() != QDialog.Accepted:
            # Canceló el asistente: salir de la app
            sys.exit(0)

    # 5) Login habitual
    dlg = LoginDialog(session)
    if dlg.exec_() == QDialog.Accepted and getattr(dlg, "user", None):
        es_admin = getattr(dlg.user, "es_admin", False)

        # Importar aquí evita efectos colaterales al cargar GUI
        from app.gui.main_window import MainWindow

        window = MainWindow(es_admin=es_admin, username=getattr(dlg.user, "username", ""))
        
        window.showMaximized()
        sys.exit(app.exec_())

    # Canceló login
    sys.exit(0)