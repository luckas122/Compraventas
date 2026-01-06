# version.py
"""
Control de versiones para App Compras y Ventas
⚠️ IMPORTANTE: Actualiza __version__ y __github_repo__ antes de cada release
"""

__version__ = "3.0.1"
__app_name__ = "Tu local 2025"   # nombre visible (puede tener espacio)
__github_repo__ = "luckas122/Compraventas"
__release_url__ = f"https://api.github.com/repos/{__github_repo__}/releases/latest"

def get_version_tuple():
    """Retorna la versión como tupla de enteros para comparaciones."""
    return tuple(map(int, __version__.split('.')))
if __name__ == "__main__":
    print(f"{__app_name__} v{__version__}")
    print(f"Repositorio: {__github_repo__}")
