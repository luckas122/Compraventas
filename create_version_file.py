from version import __version__, __app_name__
with open("version_info.txt", "w", encoding="utf-8") as f:
    f.write(f"{__app_name__} v{__version__}\n")
print("version_info.txt generado.")