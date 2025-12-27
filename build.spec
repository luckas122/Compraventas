# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_submodules, collect_data_files
from PyInstaller.building.build_main import Analysis, PYZ, EXE, COLLECT
from PyInstaller.building.datastruct import Tree

# 🆕 Importar versión
try:
    from version import __version__, __app_name__
except ImportError:
    __version__ = "1.0.0"
    __app_name__ = "TuLocalV12025"

APP_NAME    = __app_name__
VERSION     = __version__
ENTRY       = "main.py"

# Ruta absoluta al icono, relativa al propio .spec
BASE_DIR   = os.path.abspath(os.path.dirname(__name__))
ICON_PATH  = os.path.join(BASE_DIR, "assets", "shop_106574.ico")
hiddenimports = list(set(
    collect_submodules("PyQt5")
     + collect_submodules("app")
     + [
        "barcode", "barcode.writer",
        "openpyxl",
        "PyQt5.QtSvg",
        "PyQt5.QtMultimedia",
        "PIL", "PIL.Image", "PIL._imaging",
        # 🆕 Añadir módulos del updater
        "urllib.request",
        "urllib.error",
        "json",
        "tempfile",
        "subprocess",
        "app.gui.main_window.configuracion_mixin",
        "app.gui.main_window.core",
        # 🆕 Módulos SSL necesarios para sync
        "ssl",
        "smtplib",
        "imaplib",
        "_ssl",
        "_hashlib",
        "email",
        "email.mime",
        "email.mime.multipart",
        "email.mime.text",
        "email.mime.application",
    ]
))

qt_datas = collect_data_files("PyQt5", includes=[
    "Qt/plugins/platforms/*",
    "Qt/plugins/imageformats/*",
    "Qt/plugins/iconengines/*",
    "Qt/plugins/styles/*",
    "Qt/plugins/svg/*",
    "Qt/plugins/audio/*",
    "Qt/plugins/mediaservice/*",
    "Qt5/plugins/platforms/*",
    "Qt5/plugins/imageformats/*",
    "Qt5/plugins/iconengines/*",
    "Qt5/plugins/styles/*",
    "Qt5/plugins/svg/*",
    "Qt5/plugins/audio/*",
    "Qt5/plugins/mediaservice/*",
])

# Ficheros individuales
app_datas = [
    ("app/app_config.json", "app"),
    # 🆕 Scripts auxiliares necesarios para funcionalidad
    ("delete_db_helper.py", "."),  # Helper para eliminar DB y reiniciar
    ("updater.py", "."),            # Sistema de actualizaciones
    ("version.py", "."),            # Información de versión
]

# 🆕 Incluir certificados SSL de certifi para conexiones HTTPS/SMTP/IMAP
try:
    import certifi
    cert_file = certifi.where()
    app_datas.append((cert_file, "certifi"))
except ImportError:
    pass

# RECURSOS: añadir como datas en vez de trees
if os.path.isdir("assets"):
    for root, dirs, files in os.walk("assets"):
        for file in files:
            file_path = os.path.join(root, file)
            dest_dir = root  # mantiene estructura de carpetas
            app_datas.append((file_path, dest_dir))

if os.path.isdir("icons"):
    for root, dirs, files in os.walk("icons"):
        for file in files:
            file_path = os.path.join(root, file)
            dest_dir = root
            app_datas.append((file_path, dest_dir))

# BD semilla -> 'db'
db_candidates = [
    ("data",                 "db"),
    ("db",                   "db"),
    ("database",             "db"),
    ("app/app.db",           "db"),
    ("database.sqlite3",     "db"),
    ("appcomprasventas.db",  "db"),
]
for src, dest in db_candidates:
    if os.path.isdir(src):
        for root, dirs, files in os.walk(src):
            for file in files:
                file_path = os.path.join(root, file)
                app_datas.append((file_path, dest))
    elif os.path.exists(src):
        app_datas.append((src, dest))

a = Analysis(
    [ENTRY],
    pathex=["."],
    binaries=[],
    datas=qt_datas + app_datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=["pyi_rth_bootstrap.py"],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    [],  # NO incluir a.binaries, a.zipfiles, a.datas aquí
    exclude_binaries=True,  # IMPORTANTE: esto hace que sea onedir
    name=APP_NAME,  # 🔄 Nombre sin versión (para actualizaciones automáticas)
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    icon=ICON_PATH if os.path.exists(ICON_PATH) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=APP_NAME,
)