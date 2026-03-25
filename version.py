# version.py
"""
Control de versiones para App Compras y Ventas
"""

__version__ = "5.2.0"
__app_name__ = "Tu local 2025"

def get_version_tuple():
    """Retorna la versión como tupla de enteros para comparaciones."""
    return tuple(map(int, __version__.split('.')))

if __name__ == "__main__":
    print(f"{__app_name__} v{__version__}")
