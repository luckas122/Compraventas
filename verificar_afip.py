"""
Script para verificar que la integración AFIP funcionó correctamente.

Ejecutar:
    python verificar_afip.py

Este script verifica:
1. Que las columnas AFIP existan en la BD
2. Que haya ventas con CAE guardados
3. Muestra los detalles de las facturas AFIP
"""

import sqlite3
from pathlib import Path
import os
from datetime import datetime

def get_db_path():
    """Obtiene la ruta de la base de datos."""
    # Desarrollo: raíz del proyecto
    dev_path = Path(__file__).parent / "appcomprasventas.db"
    if dev_path.exists():
        return dev_path

    # Producción: APPDATA
    appdata = os.getenv('APPDATA')
    if appdata:
        prod_path = Path(appdata) / "CompraventasV2" / "appcomprasventas.db"
        if prod_path.exists():
            return prod_path

    return None

def verificar_columnas():
    """Verifica que las columnas AFIP existan."""
    db_path = get_db_path()

    if not db_path:
        print("❌ No se encontró la base de datos")
        return False

    print(f"📁 Base de datos: {db_path}")
    print()

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Obtener estructura de la tabla ventas
    cursor.execute("PRAGMA table_info(ventas)")
    columns = cursor.fetchall()

    print("📊 COLUMNAS DE LA TABLA VENTAS:")
    print("=" * 60)

    afip_columns = []
    for col in columns:
        col_id, name, tipo, notnull, default, pk = col
        if 'afip' in name.lower():
            afip_columns.append(name)
            print(f"   ✅ {name:30} {tipo}")

    print("=" * 60)
    print()

    if len(afip_columns) == 3:
        print("✅ Las 3 columnas AFIP existen correctamente")
        print(f"   • afip_cae")
        print(f"   • afip_cae_vencimiento")
        print(f"   • afip_numero_comprobante")
    else:
        print(f"⚠️  Solo {len(afip_columns)} de 3 columnas AFIP encontradas")
        print("   Ejecuta: python migrate_afip_fields.py")

    print()
    conn.close()
    return len(afip_columns) == 3

def verificar_ventas_afip():
    """Verifica ventas con datos AFIP."""
    db_path = get_db_path()

    if not db_path:
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Contar ventas totales
    cursor.execute("SELECT COUNT(*) FROM ventas")
    total_ventas = cursor.fetchone()[0]

    # Contar ventas con CAE
    cursor.execute("SELECT COUNT(*) FROM ventas WHERE afip_cae IS NOT NULL")
    ventas_con_cae = cursor.fetchone()[0]

    # Contar ventas con tarjeta
    cursor.execute("SELECT COUNT(*) FROM ventas WHERE modo_pago = 'Tarjeta'")
    ventas_tarjeta = cursor.fetchone()[0]

    print("📈 ESTADÍSTICAS DE VENTAS:")
    print("=" * 60)
    print(f"   Total de ventas:           {total_ventas}")
    print(f"   Ventas con tarjeta:        {ventas_tarjeta}")
    print(f"   Ventas con CAE (AFIP):     {ventas_con_cae}")
    print("=" * 60)
    print()

    if ventas_con_cae > 0:
        print(f"✅ ¡Hay {ventas_con_cae} venta(s) con factura AFIP!")
        print()

        # Mostrar detalles de las ventas con CAE
        cursor.execute("""
            SELECT
                id,
                numero_ticket,
                fecha,
                total,
                modo_pago,
                cuotas,
                afip_cae,
                afip_cae_vencimiento,
                afip_numero_comprobante
            FROM ventas
            WHERE afip_cae IS NOT NULL
            ORDER BY fecha DESC
            LIMIT 10
        """)

        ventas = cursor.fetchall()

        print("🧾 ÚLTIMAS FACTURAS ELECTRÓNICAS:")
        print("=" * 80)

        for venta in ventas:
            (vid, nro_ticket, fecha_str, total, modo_pago, cuotas,
             cae, cae_vto, nro_afip) = venta

            # Parsear fecha
            try:
                fecha = datetime.strptime(fecha_str, "%Y-%m-%d %H:%M:%S.%f")
                fecha_fmt = fecha.strftime("%d/%m/%Y %H:%M")
            except:
                try:
                    fecha = datetime.strptime(fecha_str, "%Y-%m-%d %H:%M:%S")
                    fecha_fmt = fecha.strftime("%d/%m/%Y %H:%M")
                except:
                    fecha_fmt = fecha_str

            print(f"   Ticket Nº {nro_ticket} | {fecha_fmt}")
            print(f"   Total: ${total:.2f} | {modo_pago}", end="")
            if cuotas:
                print(f" ({cuotas} cuotas)")
            else:
                print()
            print(f"   ✅ CAE: {cae}")
            print(f"   📅 Vencimiento: {cae_vto}")
            print(f"   🔢 Comprobante AFIP: {nro_afip}")
            print("   " + "-" * 76)

        print("=" * 80)
        print()

        # Verificar en AFIP SDK
        print("🌐 VERIFICACIÓN ONLINE:")
        print("=" * 60)
        print("   Para ver estas facturas en AFIP SDK:")
        print("   👉 https://app.afipsdk.com")
        print("   📁 Ir a 'Comprobantes' o 'Actividad'")
        print("=" * 60)
        print()

    elif ventas_tarjeta > 0:
        print(f"⚠️  Hay {ventas_tarjeta} venta(s) con tarjeta pero SIN CAE")
        print("   Posibles causas:")
        print("   • AFIP está deshabilitado en la configuración")
        print("   • Hubo un error al emitir (revisar logs)")
        print("   • La venta se hizo antes de integrar AFIP")
        print()
    else:
        print("ℹ️  No hay ventas con tarjeta todavía")
        print("   Haz una venta con tarjeta para probar AFIP")
        print()

    conn.close()

def verificar_configuracion():
    """Verifica la configuración AFIP."""
    import json

    config_path = Path(__file__).parent / "app" / "app_config.json"

    if not config_path.exists():
        print("⚠️  No se encontró app_config.json")
        return

    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    afip_config = config.get('afip', {})

    print("⚙️  CONFIGURACIÓN AFIP:")
    print("=" * 60)
    print(f"   Habilitado:        {'✅ Sí' if afip_config.get('enabled') else '❌ No'}")
    print(f"   Ambiente:          {afip_config.get('environment', 'N/A')}")
    print(f"   CUIT:              {afip_config.get('cuit', 'N/A')}")
    print(f"   Punto de venta:    {afip_config.get('punto_venta', 'N/A')}")
    print(f"   Solo tarjeta:      {'✅ Sí' if afip_config.get('only_card_payments') else '❌ No'}")

    token = afip_config.get('access_token', '')
    if token:
        print(f"   Access token:      {token[:15]}... (configurado)")
    else:
        print(f"   Access token:      ❌ NO CONFIGURADO")

    print("=" * 60)
    print()

    if not afip_config.get('enabled'):
        print("⚠️  AFIP está DESHABILITADO")
        print("   Para habilitar, edita app_config.json:")
        print('   "afip": { "enabled": true, ... }')
        print()

def main():
    print()
    print("=" * 60)
    print("   VERIFICACIÓN DE INTEGRACIÓN AFIP")
    print("=" * 60)
    print()

    # 1. Verificar configuración
    verificar_configuracion()

    # 2. Verificar columnas
    if not verificar_columnas():
        print("❌ Primero ejecuta: python migrate_afip_fields.py")
        return

    # 3. Verificar ventas
    verificar_ventas_afip()

    print("=" * 60)
    print()

if __name__ == '__main__':
    main()
