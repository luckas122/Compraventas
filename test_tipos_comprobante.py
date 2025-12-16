"""
Script para probar todos los tipos de comprobante AFIP.

IMPORTANTE: Este script usa el ambiente de pruebas de AFIP SDK.
No consume créditos reales.

Uso:
    python test_tipos_comprobante.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.afip_integration import AfipSDKClient, AfipConfig

# Cargar config
config_path = Path(__file__).parent / "app" / "app_config.json"
with open(config_path, 'r', encoding='utf-8') as f:
    config = json.load(f)

afip_config = config.get('afip', {})

print("=" * 70)
print("TEST DE TIPOS DE COMPROBANTE AFIP")
print("=" * 70)
print()

# Verificar config
print("Configuracion:")
print(f"  Habilitado: {afip_config.get('enabled')}")
print(f"  Ambiente: {afip_config.get('environment')}")
print(f"  CUIT: {afip_config.get('cuit')}")
print()

# Crear cliente
cfg = AfipConfig(
    access_token=afip_config.get('access_token', ''),
    environment=afip_config.get('environment', 'dev'),
    cuit=afip_config.get('cuit', '20409378472'),
    punto_venta=afip_config.get('punto_venta', 1),
    enabled=afip_config.get('enabled', False)
)

cliente = AfipSDKClient(cfg)

# Datos de prueba
items = [
    {"nombre": "Producto Test 1", "cantidad": 1, "precio": 100.00},
    {"nombre": "Producto Test 2", "cantidad": 1, "precio": 50.00}
]
total = 181.50  # $150 + 21% IVA
subtotal = 150.00
iva = 31.50

print("-" * 70)
print("TEST 1: FACTURA B (Monotributista a Consumidor Final)")
print("-" * 70)
try:
    response = cliente.emitir_factura_b(
        items=items,
        total=total,
        subtotal=subtotal,
        iva=iva
    )

    if response.success:
        print(f"OK - Factura B emitida")
        print(f"  CAE: {response.cae}")
        print(f"  Vencimiento: {response.cae_vencimiento}")
        print(f"  Numero: {response.numero_comprobante}")
    else:
        print(f"ERROR: {response.error_message}")
except Exception as e:
    print(f"EXCEPCION: {e}")

print()
print("-" * 70)
print("TEST 2: FACTURA C (Consumidor Final, sin IVA discriminado)")
print("-" * 70)
try:
    response = cliente.emitir_factura_c(
        items=items,
        total=total  # Total incluye IVA pero no se discrimina
    )

    if response.success:
        print(f"OK - Factura C emitida")
        print(f"  CAE: {response.cae}")
        print(f"  Vencimiento: {response.cae_vencimiento}")
        print(f"  Numero: {response.numero_comprobante}")
    else:
        print(f"ERROR: {response.error_message}")
except Exception as e:
    print(f"EXCEPCION: {e}")

print()
print("-" * 70)
print("TEST 3: FACTURA A (Resp. Inscripto a Resp. Inscripto)")
print("-" * 70)
print("NOTA: Factura A requiere CUIT del cliente")
print("      Usando CUIT de prueba: 20123456789")
try:
    response = cliente.emitir_factura_a(
        items=items,
        total=total,
        subtotal=subtotal,
        iva=iva,
        doc_numero=20123456789  # CUIT de prueba
    )

    if response.success:
        print(f"OK - Factura A emitida")
        print(f"  CAE: {response.cae}")
        print(f"  Vencimiento: {response.cae_vencimiento}")
        print(f"  Numero: {response.numero_comprobante}")
    else:
        print(f"ERROR: {response.error_message}")
except Exception as e:
    print(f"EXCEPCION: {e}")

print()
print("=" * 70)
print("FIN DE LOS TESTS")
print("=" * 70)
print()
print("RESUMEN:")
print("- Factura B: Para monotributistas vendiendo a consumidor final")
print("- Factura C: Para consumidor final vendiendo (sin discriminar IVA)")
print("- Factura A: Para resp. inscripto vendiendo a otro resp. inscripto")
print()
print("Para cambiar el tipo en la app:")
print("1. Ir a Configuracion -> Facturacion")
print("2. Elegir el tipo de comprobante")
print("3. Guardar")
print()
