# version.py
"""
Control de versiones para App Compras y Ventas
⚠️ IMPORTANTE: Actualiza __version__ y __github_repo__ antes de cada release
"""

__version__ = "1.0.0"
__app_name__ = "TuLocalV12025"
__github_repo__ = "TU-USUARIO/TU-REPOSITORIO"  # 🔴 CAMBIAR ESTO
__release_url__ = f"https://api.github.com/repos/{__github_repo__}/releases/latest"

def get_version_tuple():
    """Retorna la versión como tupla de enteros para comparaciones."""
    return tuple(map(int, __version__.split('.')))

if __name__ == "__main__":
    print(f"{__app_name__} v{__version__}")
    print(f"Repositorio: {__github_repo__}")