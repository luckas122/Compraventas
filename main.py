import sys
from PyQt5.QtWidgets import QApplication, QDialog
from PyQt5.QtGui import QFont, QIcon, QFontDatabase

from app.database import init_db, SessionLocal
from app.login import LoginDialog, CreateAdminDialog
from app.repository import UsuarioRepo

# Información de versión
from version import __version__, __app_name__


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
        print(f"[BACKUP] Error verificando backup de config: {e}")

    # Configuración general: minimizar a bandeja al cerrar
    try:
        from app.config import load as load_config
        cfg_main = load_config()
        gen_main = cfg_main.get("general") or {}
        if gen_main.get("minimize_to_tray_on_close", False):
            # Si está activado, que NO se cierre el proceso cuando se cierra la última ventana
            app.setQuitOnLastWindowClosed(False)
    except Exception as e:
        print(f"[CONFIG] No se pudo aplicar minimize_to_tray_on_close: {e}")

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
        print(f"[ICON] No se pudo asignar icono global: {e}")

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
                        print(f"[FONT] Roboto cargada correctamente: {families[0]}")
                break
    except Exception as e:
        print(f"[FONT] Error cargando Roboto: {e}")

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

        window = MainWindow(es_admin=es_admin)
        
        window.showMaximized()
        sys.exit(app.exec_())

    # Canceló login
    sys.exit(0)