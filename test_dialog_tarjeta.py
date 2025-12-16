"""
Script rápido para probar el diálogo de pago con tarjeta.

Uso:
    python test_dialog_tarjeta.py
"""

import sys
from PyQt5.QtWidgets import QApplication
from app.gui.dialogs import PagoTarjetaDialog

if __name__ == '__main__':
    app = QApplication(sys.argv)

    # Crear diálogo con un total de ejemplo
    dlg = PagoTarjetaDialog(total_actual=1500.00)

    if dlg.exec_():
        datos = dlg.get_datos()
        print("\n" + "="*60)
        print("DATOS INGRESADOS:")
        print("="*60)
        print(f"Cuotas: {datos['cuotas']}")
        print(f"Interés: {datos['interes_pct']}%")
        print(f"Tipo de comprobante: {datos['tipo_comprobante']}")
        print(f"CUIT del cliente: {datos['cuit_cliente'] or '(no ingresado)'}")
        print("="*60)
    else:
        print("\nUsuario canceló el diálogo")

    sys.exit(0)
