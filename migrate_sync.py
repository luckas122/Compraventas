#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script de migración para agregar tabla sync_log
Ejecutar UNA SOLA VEZ después de integrar el sistema de sincronización
"""

from app.database import engine, init_db
from app.models import Base, SyncLog
from sqlalchemy import inspect

def main():
    print("=" * 60)
    print("Migración: Sistema de Sincronización v1.0")
    print("=" * 60)

    # Verificar si la tabla ya existe
    inspector = inspect(engine)
    tablas_existentes = inspector.get_table_names()

    if 'sync_log' in tablas_existentes:
        print("\n✓ La tabla 'sync_log' ya existe en la base de datos.")
        print("  No es necesario ejecutar la migración.")
        return

    print("\n→ Creando tabla 'sync_log'...")

    try:
        # Crear todas las tablas que falten (incluyendo sync_log)
        Base.metadata.create_all(bind=engine)

        print("✓ Tabla 'sync_log' creada exitosamente.")
        print("\nDetalles de la tabla:")
        print("  - sync_id (String, UNIQUE, INDEX)")
        print("  - tipo (String): 'venta', 'producto', 'proveedor'")
        print("  - accion (String): 'create', 'update', 'delete'")
        print("  - timestamp (DateTime)")
        print("  - aplicado (Boolean)")
        print("  - sucursal_origen (String)")
        print("  - data_hash (String)")
        print("\nÍndices creados:")
        print("  - ix_sync_log_sync_id (UNIQUE)")
        print("  - ix_sync_log_tipo_timestamp")
        print("  - ix_sync_log_sucursal_timestamp")

        print("\n" + "=" * 60)
        print("Migración completada con éxito!")
        print("=" * 60)
        print("\nPróximos pasos:")
        print("1. Ir a Configuración → Sincronización")
        print("2. Configurar Gmail (SMTP + IMAP)")
        print("3. Probar conexión")
        print("4. Activar sincronización")
        print("\n¡Listo para sincronizar entre sucursales!")

    except Exception as e:
        print(f"\n❌ Error durante la migración: {e}")
        print("   Por favor, revisa el error y vuelve a intentar.")
        return

if __name__ == "__main__":
    main()
