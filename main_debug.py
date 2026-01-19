import logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(levelname)s - %(message)s',
    handlers=[logging.FileHandler('debug.log', 'w', 'utf-8')]
)

# Luego ejecuta tu aplicación normalmente
from main import *