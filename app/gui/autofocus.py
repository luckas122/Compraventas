# app/gui/autofocus.py
from PyQt5.QtCore import QObject, QTimer

class AutoFocusManager(QObject):
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.main_window.tabs.currentChanged.connect(self.on_tab_changed)
        
    def on_tab_changed(self, index):
        """Auto-focus cuando se cambia de pestaña"""
        # Pestaña de Ventas - focus en buscador
        if index == 2:  # Índice de ventas
            QTimer.singleShot(100, self.focus_ventas_buscador)
        # Pestaña de Productos - focus en buscador
        elif index == 0:  # Índice de productos
            QTimer.singleShot(100, self.focus_productos_buscador)
    
    def focus_ventas_buscador(self):
        """Enfocar el buscador de ventas"""
        if hasattr(self.main_window, 'input_venta_buscar'):
            self.main_window.input_venta_buscar.setFocus()
            self.main_window.input_venta_buscar.selectAll()
    
    def focus_productos_buscador(self):
        """Enfocar el buscador de productos"""
        if hasattr(self.main_window, 'input_buscar'):
            self.main_window.input_buscar.setFocus()
            self.main_window.input_buscar.selectAll()