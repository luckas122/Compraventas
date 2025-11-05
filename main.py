import sys
from PyQt5.QtWidgets import QApplication, QDialog
from PyQt5.QtGui import QFont
from PyQt5.QtCore import QTimer

from app.database import init_db, SessionLocal
from app.login import LoginDialog, CreateAdminDialog
from app.repository import UsuarioRepo

#  Importar sistema de actualizaciones
try:
    from version import __version__, __app_name__
    from updater import check_updates_on_startup
    UPDATER_AVAILABLE = True
except ImportError:
    __version__ = "1.0.0"
    __app_name__ = "TuLocalV12025"
    UPDATER_AVAILABLE = False


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

    # (mantengo tu estilo de checkbox)
    app.setStyleSheet("""
        QCheckBox::indicator { width: 22px; height: 22px; }
        QCheckBox { margin: 0; padding: 0; }
    """)

    # (mantengo tu fuente global)
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
        
        # 🆕 VERIFICAR ACTUALIZACIONES AL INICIAR (después de 3 segundos)
        if UPDATER_AVAILABLE:
            def check_updates():
                try:
                    check_updates_on_startup(window, auto_install=False)
                except Exception as e:
                    print(f"[UPDATER] Error al verificar actualizaciones: {e}")
            
            QTimer.singleShot(3000, check_updates)  # 3 segundos después de iniciar
        
        window.showMaximized()
        sys.exit(app.exec_())

    # Canceló login
    sys.exit(0)