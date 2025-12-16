"""Test simple de AFIP sin caracteres especiales."""
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

print("=" * 60)
print("TEST AFIP - SANDBOX")
print("=" * 60)
print()

# Verificar config
print("Configuracion:")
print(f"  Habilitado: {afip_config.get('enabled')}")
print(f"  Ambiente: {afip_config.get('environment')}")
print(f"  CUIT: {afip_config.get('cuit')}")
print(f"  Access Token: {afip_config.get('access_token')[:20]}...")
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

# Test 1: Autenticacion
print("Test 1: Autenticacion...")
try:
    token, sign = cliente.get_auth_token()
    print(f"  OK - Token obtenido: {token[:30]}...")
    print()
except Exception as e:
    print(f"  ERROR: {e}")
    sys.exit(1)

# Test 2: Ultimo comprobante
print("Test 2: Ultimo comprobante...")
try:
    ultimo = cliente.get_ultimo_comprobante(cliente.FACTURA_B)
    print(f"  OK - Ultimo comprobante: {ultimo}")
    print(f"  Proximo numero: {ultimo + 1}")
    print()
except Exception as e:
    print(f"  ERROR: {e}")
    sys.exit(1)

# Test 3: Emitir factura
print("Test 3: Emitir factura de prueba...")
try:
    response = cliente.emitir_factura_b(
        items=[
            {"nombre": "Producto 1", "cantidad": 1, "precio": 100.00}
        ],
        total=121.00,
        subtotal=100.00,
        iva=21.00
    )

    if response.success:
        print(f"  OK - Factura emitida")
        print(f"  CAE: {response.cae}")
        print(f"  Vencimiento: {response.cae_vencimiento}")
        print(f"  Numero: {response.numero_comprobante}")
    else:
        print(f"  ERROR: {response.error_message}")
        sys.exit(1)
except Exception as e:
    print(f"  ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()
print("=" * 60)
print("TODOS LOS TESTS OK!")
print("=" * 60)
