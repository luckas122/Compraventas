"""
Script de prueba para validar la integración AFIP en modo sandbox.
Este script NO consume créditos, usa el CUIT de prueba de AFIP SDK.

Uso:
    python test_afip_sandbox.py

Requisitos:
    1. Tener cuenta en https://app.afipsdk.com
    2. Obtener ACCESS_TOKEN del dashboard
    3. Configurar en app/app_config.json
"""

import json
import sys
import logging
from pathlib import Path

# Configurar logging para ver debug
logging.basicConfig(
    level=logging.DEBUG,
    format='%(levelname)s - %(name)s - %(message)s'
)

# Agregar el directorio app al path
sys.path.insert(0, str(Path(__file__).parent))

from app.afip_integration import AfipSDKClient, AfipConfig


def cargar_config():
    """Carga la configuración desde app_config.json."""
    config_path = Path(__file__).parent / "app" / "app_config.json"

    if not config_path.exists():
        print(f"❌ No se encontró {config_path}")
        return None

    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    return config.get('afip', {})


def verificar_config(afip_config):
    """Verifica que la configuración esté completa."""
    print("=" * 60)
    print("VERIFICACIÓN DE CONFIGURACIÓN")
    print("=" * 60)

    errores = []

    # Verificar campos obligatorios
    if not afip_config.get('enabled'):
        errores.append("⚠️  AFIP está deshabilitado (enabled: false)")
    else:
        print("✅ AFIP habilitado")

    if not afip_config.get('access_token'):
        errores.append("❌ Falta access_token")
    else:
        token = afip_config['access_token']
        print(f"✅ Access token configurado ({token[:10]}...)")

    if afip_config.get('environment') != 'dev':
        errores.append(f"⚠️  Ambiente no es 'dev': {afip_config.get('environment')}")
    else:
        print("✅ Ambiente: dev (sandbox)")

    cuit = afip_config.get('cuit', '')
    if cuit != '20409378472':
        errores.append(f"⚠️  CUIT no es el de prueba: {cuit}")
        print(f"⚠️  CUIT: {cuit} (recomendado: 20409378472 para pruebas)")
    else:
        print(f"✅ CUIT de prueba: {cuit}")

    print(f"✅ Punto de venta: {afip_config.get('punto_venta', 1)}")
    print(f"✅ Solo pagos con tarjeta: {afip_config.get('only_card_payments', True)}")

    print()

    if errores:
        print("❌ ERRORES ENCONTRADOS:")
        for error in errores:
            print(f"   {error}")
        print()
        return False

    print("✅ Configuración válida para pruebas")
    print()
    return True


def test_autenticacion(cliente):
    """Prueba la autenticación con AFIP."""
    print("=" * 60)
    print("TEST 1: AUTENTICACIÓN")
    print("=" * 60)

    try:
        token, sign = cliente.get_auth_token()
        print(f"✅ Token obtenido exitosamente")
        print(f"   Token: {token[:50]}...")
        print(f"   Sign: {sign[:50]}...")
        print()
        return True
    except Exception as e:
        print(f"❌ Error al autenticar: {e}")
        print()
        return False


def test_ultimo_comprobante(cliente):
    """Prueba obtener el último número de comprobante."""
    print("=" * 60)
    print("TEST 2: CONSULTAR ÚLTIMO COMPROBANTE")
    print("=" * 60)

    try:
        ultimo_nro = cliente.get_ultimo_comprobante(cliente.FACTURA_B)
        print(f"✅ Último comprobante autorizado: {ultimo_nro}")
        print(f"   Próximo número disponible: {ultimo_nro + 1}")
        print()
        return True
    except Exception as e:
        print(f"❌ Error al consultar: {e}")
        print()
        return False


def test_emitir_factura(cliente):
    """Prueba emitir una factura de prueba."""
    print("=" * 60)
    print("TEST 3: EMITIR FACTURA B DE PRUEBA")
    print("=" * 60)

    # Factura de ejemplo: $121 (IVA incluido)
    total = 121.00
    subtotal = 100.00
    iva = 21.00

    print(f"Emitiendo factura de prueba:")
    print(f"  Total: ${total:.2f}")
    print(f"  Subtotal: ${subtotal:.2f}")
    print(f"  IVA (21%): ${iva:.2f}")
    print()

    try:
        response = cliente.emitir_factura_b(
            items=[
                {"nombre": "Producto de prueba 1", "cantidad": 1, "precio": 50.00},
                {"nombre": "Producto de prueba 2", "cantidad": 2, "precio": 25.00}
            ],
            total=total,
            subtotal=subtotal,
            iva=iva
        )

        if response.success:
            print("✅ FACTURA EMITIDA EXITOSAMENTE")
            print(f"   CAE: {response.cae}")
            print(f"   Vencimiento CAE: {response.cae_vencimiento}")
            print(f"   Número de comprobante: {response.numero_comprobante}")
            print()
            print("🎉 La integración está funcionando correctamente!")
            print()
            return True
        else:
            print(f"❌ AFIP rechazó la factura: {response.error_message}")
            print()
            if response.raw_response:
                print("Respuesta completa:")
                print(json.dumps(response.raw_response, indent=2))
            print()
            return False

    except Exception as e:
        print(f"❌ Error al emitir factura: {e}")
        import traceback
        traceback.print_exc()
        print()
        return False


def main():
    """Función principal."""
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 10 + "TEST DE INTEGRACIÓN AFIP - MODO SANDBOX" + " " * 9 + "║")
    print("║" + " " * 58 + "║")
    print("║" + " " * 5 + "Este script NO consume créditos reales" + " " * 14 + "║")
    print("║" + " " * 5 + "Usa el CUIT de prueba: 20409378472" + " " * 18 + "║")
    print("╚" + "=" * 58 + "╝")
    print()

    # 1. Cargar configuración
    afip_config = cargar_config()
    if not afip_config:
        print("❌ No se pudo cargar la configuración")
        return

    # 2. Verificar configuración
    if not verificar_config(afip_config):
        print("⚠️  Corrige los errores en app/app_config.json antes de continuar")
        print()
        print("Configuración recomendada para pruebas:")
        print(json.dumps({
            "afip": {
                "enabled": True,
                "environment": "dev",
                "access_token": "TU_ACCESS_TOKEN_AQUI",
                "cuit": "20409378472",
                "punto_venta": 1,
                "only_card_payments": True
            }
        }, indent=2))
        print()
        return

    # 3. Crear cliente AFIP
    config = AfipConfig(
        access_token=afip_config.get('access_token', ''),
        environment=afip_config.get('environment', 'dev'),
        cuit=afip_config.get('cuit', '20409378472'),
        punto_venta=afip_config.get('punto_venta', 1),
        enabled=afip_config.get('enabled', False)
    )

    cliente = AfipSDKClient(config)

    # 4. Ejecutar tests
    resultados = []

    resultados.append(("Autenticación", test_autenticacion(cliente)))

    if resultados[-1][1]:  # Solo continuar si autenticación fue exitosa
        resultados.append(("Último comprobante", test_ultimo_comprobante(cliente)))
        resultados.append(("Emitir factura", test_emitir_factura(cliente)))

    # 5. Resumen
    print("=" * 60)
    print("RESUMEN DE PRUEBAS")
    print("=" * 60)

    for nombre, exito in resultados:
        estado = "✅ OK" if exito else "❌ FALLÓ"
        print(f"{nombre:.<40} {estado}")

    print()

    total_ok = sum(1 for _, ok in resultados if ok)
    total_tests = len(resultados)

    if total_ok == total_tests:
        print(f"🎉 TODOS LOS TESTS PASARON ({total_ok}/{total_tests})")
        print()
        print("Próximos pasos:")
        print("1. ✅ Integrar en ventas.py (llamar a afip_integration.py)")
        print("2. ✅ Agregar campos CAE a models.py")
        print("3. ✅ Imprimir CAE en el ticket")
        print("4. ⏳ Cuando estés listo, configurar para producción")
    else:
        print(f"⚠️  ALGUNOS TESTS FALLARON ({total_ok}/{total_tests})")
        print()
        print("Revisa los errores arriba y:")
        print("1. Verifica tu access_token en https://app.afipsdk.com")
        print("2. Asegúrate de tener conexión a internet")
        print("3. Consulta AFIP_INTEGRACION.md para más ayuda")

    print()


if __name__ == '__main__':
    main()
