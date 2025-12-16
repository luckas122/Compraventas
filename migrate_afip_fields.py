"""
Script de migración para agregar campos AFIP a la base de datos existente.

Ejecutar:
    python migrate_afip_fields.py

Este script agrega las columnas AFIP a la tabla ventas sin borrar datos existentes.
"""

import sqlite3
from pathlib import Path
import os

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

def migrate():
    """Agrega campos AFIP a la tabla ventas."""
    db_path = get_db_path()

    if not db_path:
        print("❌ No se encontró la base de datos")
        print("   La aplicación la creará automáticamente con los nuevos campos")
        return

    print(f"📁 Base de datos encontrada: {db_path}")

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Verificar si las columnas ya existen
        cursor.execute("PRAGMA table_info(ventas)")
        columns = [row[1] for row in cursor.fetchall()]

        campos_a_agregar = []

        if 'afip_cae' not in columns:
            campos_a_agregar.append('afip_cae VARCHAR')

        if 'afip_cae_vencimiento' not in columns:
            campos_a_agregar.append('afip_cae_vencimiento VARCHAR')

        if 'afip_numero_comprobante' not in columns:
            campos_a_agregar.append('afip_numero_comprobante INTEGER')

        if not campos_a_agregar:
            print("✅ Las columnas AFIP ya existen en la base de datos")
            print("   No se requiere migración")
            conn.close()
            return

        print(f"\n🔧 Agregando {len(campos_a_agregar)} columnas:")

        for campo in campos_a_agregar:
            sql = f"ALTER TABLE ventas ADD COLUMN {campo}"
            print(f"   - {campo.split()[0]}...")
            cursor.execute(sql)

        conn.commit()
        conn.close()

        print("\n✅ Migración completada exitosamente")
        print("   Las columnas AFIP han sido agregadas a la tabla ventas")
        print("\n📊 Columnas agregadas:")
        for campo in campos_a_agregar:
            print(f"   • {campo}")

    except Exception as e:
        print(f"\n❌ Error durante la migración: {e}")
        print("\n💡 Alternativa: Borra appcomprasventas.db y la app lo recreará")
        return

if __name__ == '__main__':
    print("=" * 60)
    print("   MIGRACIÓN DE BASE DE DATOS - CAMPOS AFIP")
    print("=" * 60)
    print()
    migrate()
    print()
    print("=" * 60)
