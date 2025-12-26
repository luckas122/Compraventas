# 📦 Preparación de Versión 2.5 - Sistema de Sincronización

## Cambios Principales en v2.5

### ✨ Nueva Funcionalidad
- **Sistema de sincronización entre sucursales** vía Gmail
- 3 modos: Intervalo fijo, Detección de cambios, Manual
- Pestaña "Sincronización" en Configuraciones
- Indicador visual en status bar
- Detección automática de cambios
- Prevención de duplicados

### 🔧 Archivos Modificados
- `app/models.py` - Nuevo modelo `SyncLog`
- `app/app_config.json` - Nueva sección `sync`
- `app/gui/main_window/configuracion_mixin.py` - Nueva pestaña
- `app/gui/main_window/core.py` - Integración de sincronización

### 📝 Archivos Nuevos
- `app/sync_manager.py` - Lógica de sincronización
- `app/gui/sync_config.py` - UI de configuración
- `migrate_sync.py` - Script de migración de BD
- Documentación completa (3 archivos .md)

---

## 🚀 Pasos para Preparar la Actualización

### 1. Actualizar archivo `version.py`

```python
# version.py
__version__ = "2.5.0"
__app_name__ = "Compraventas"
```

### 2. Crear CHANGELOG para v2.5

Crea o actualiza `CHANGELOG.md`:

```markdown
# Changelog

## [2.5.0] - 2025-12-26

### Agregado
- Sistema de sincronización automática entre sucursales vía Gmail
- Tres modos de sincronización: intervalo fijo, detección de cambios, manual
- Pestaña "Sincronización" en Configuraciones con formularios SMTP/IMAP
- Indicador visual de estado de sincronización en barra de estado
- Modelo `SyncLog` para auditoría de sincronizaciones
- Detección inteligente de cambios pendientes
- Prevención de duplicados con hash MD5 y UUID
- Script de migración `migrate_sync.py` para actualizar base de datos
- Documentación completa del sistema (RESUMEN, INSTRUCCIONES, EJEMPLOS)

### Modificado
- `app/models.py` - Agregado modelo `SyncLog`
- `app/app_config.json` - Nueva sección `sync` con configuración
- `app/gui/main_window/configuracion_mixin.py` - Integrada pestaña de sincronización
- `app/gui/main_window/core.py` - Integrado scheduler y lógica de sincronización

### Seguridad
- Soporte para contraseñas de aplicación de Gmail
- Validación de origen en sincronizaciones
- Detección de duplicados por hash

### Notas de Actualización
- **IMPORTANTE:** Ejecutar `migrate_sync.py` ANTES de usar la sincronización
- Configurar Gmail con contraseña de aplicación (no contraseña normal)
- Habilitar IMAP en Gmail para recibir sincronizaciones
- Fase 1: Solo sincroniza ventas (productos en Fase 2)
```

### 3. Organizar Archivos para Distribución

Crea una carpeta `release/v2.5.0/`:

```
release/v2.5.0/
├── CompraventasV2_v2.5.0.exe        # Ejecutable PyInstaller
├── migrate_sync.py                   # Script de migración
├── CHANGELOG.md                      # Cambios de esta versión
├── docs/
│   ├── RESUMEN_SINCRONIZACION.md
│   ├── INSTRUCCIONES_SINCRONIZACION.md
│   └── EJEMPLO_CONFIGURACION_SYNC.md
└── README_ACTUALIZACION.txt         # Instrucciones rápidas
```

### 4. Crear `README_ACTUALIZACION.txt`

```txt
═══════════════════════════════════════════════════════════
  COMPRAVENTAS V2.5.0 - SINCRONIZACIÓN ENTRE SUCURSALES
═══════════════════════════════════════════════════════════

¡Nueva funcionalidad: Sincronización automática entre sucursales!

═══════════════════════════════════════════════════════════
  PASOS PARA ACTUALIZAR DESDE v2.0
═══════════════════════════════════════════════════════════

1. HACER BACKUP
   - Ir a Configuración → Backups → "Hacer backup ahora"
   - Guardar el archivo .zip en lugar seguro

2. CERRAR LA APLICACIÓN ACTUAL

3. REEMPLAZAR EL EJECUTABLE
   - Reemplazar CompraventasV2.exe con el nuevo

4. EJECUTAR MIGRACIÓN DE BASE DE DATOS
   - Abrir terminal/CMD en la carpeta de la app
   - Ejecutar: python migrate_sync.py
   - Esperar mensaje "Migración completada con éxito!"

5. ABRIR LA APLICACIÓN
   - Ejecutar CompraventasV2.exe normalmente
   - Verificar que abre sin errores

6. CONFIGURAR SINCRONIZACIÓN (Opcional)
   - Ir a Configuración → Sincronización
   - Seguir instrucciones en docs/RESUMEN_SINCRONIZACION.md

═══════════════════════════════════════════════════════════
  NOVEDADES EN v2.5.0
═══════════════════════════════════════════════════════════

✓ Sincronización automática de ventas entre sucursales
✓ Tres modos: intervalo fijo, detección de cambios, manual
✓ Indicador en barra de estado (✓ Sync: hace 2 min)
✓ Configuración completa por UI (Gmail SMTP/IMAP)
✓ Detección inteligente de cambios pendientes
✓ Prevención de duplicados automática

═══════════════════════════════════════════════════════════
  DOCUMENTACIÓN
═══════════════════════════════════════════════════════════

- docs/RESUMEN_SINCRONIZACION.md      → Visión general
- docs/INSTRUCCIONES_SINCRONIZACION.md → Guía técnica
- docs/EJEMPLO_CONFIGURACION_SYNC.md   → Configuración paso a paso

═══════════════════════════════════════════════════════════
  SOPORTE
═══════════════════════════════════════════════════════════

¿Problemas con la actualización?
- Revisar CHANGELOG.md para cambios completos
- Consultar documentación en carpeta docs/
- Restaurar backup si es necesario

═══════════════════════════════════════════════════════════
```

### 5. Compilar con PyInstaller

```bash
# Comando para generar ejecutable
pyinstaller --name="CompraventasV2_v2.5.0" \
            --onefile \
            --windowed \
            --icon=icon.ico \
            --add-data="app;app" \
            --add-data="assets;assets" \
            main.py
```

O si tienes un `.spec`:

```bash
pyinstaller compraventas.spec
```

### 6. Verificar que el Ejecutable Incluye Todo

Después de compilar, verificar que incluye:
- ✅ Todos los módulos de `app/`
- ✅ `app/sync_manager.py`
- ✅ `app/gui/sync_config.py`
- ✅ Assets e iconos
- ✅ Configuración `app_config.json`

### 7. Crear archivo de migración embebido

Si quieres que la migración sea automática en el primer inicio, modifica `main.py`:

```python
# main.py
from app.database import init_db, SessionLocal
from app.models import Base
from sqlalchemy import inspect

def auto_migrate():
    """Migración automática al iniciar"""
    engine = SessionLocal().bind
    inspector = inspect(engine)

    # Verificar si sync_log existe
    if 'sync_log' not in inspector.get_table_names():
        print("[MIGRACIÓN] Creando tabla sync_log...")
        Base.metadata.create_all(bind=engine)
        print("[MIGRACIÓN] ✓ Tabla sync_log creada")

if __name__ == "__main__":
    init_db()
    auto_migrate()  # Migración automática

    # ... resto del código ...
```

---

## 📋 Checklist Pre-Lanzamiento

Antes de distribuir v2.5.0, verificar:

### Funcionalidad
- [ ] Sincronización funciona en modo "intervalo"
- [ ] Sincronización funciona en modo "detección de cambios"
- [ ] Sincronización funciona en modo "manual"
- [ ] Indicador visual aparece en status bar
- [ ] Prueba de conexión SMTP/IMAP funciona
- [ ] Ventas se sincronizan correctamente
- [ ] No hay duplicados en sincronización
- [ ] Historial se actualiza al recibir ventas

### Base de Datos
- [ ] Migración crea tabla `sync_log`
- [ ] Índices de `sync_log` están creados
- [ ] No hay errores al guardar en `sync_log`

### Configuración
- [ ] Pestaña "Sincronización" aparece en Configuraciones
- [ ] Todos los campos se guardan correctamente
- [ ] Configuración persiste entre reinicios

### Documentación
- [ ] CHANGELOG.md actualizado
- [ ] Documentación completa incluida
- [ ] README_ACTUALIZACION.txt claro y conciso

### Compatibilidad
- [ ] Usuarios de v2.0 pueden actualizar sin perder datos
- [ ] Backup antes de actualizar funciona
- [ ] Si no se configura sync, la app funciona igual que v2.0

---

## 📂 Estructura de Carpetas para Entrega

```
CompraventasV2_v2.5.0_Release/
│
├── CompraventasV2_v2.5.0.exe         ← Ejecutable principal
├── migrate_sync.py                    ← Script de migración
├── CHANGELOG.md                       ← Cambios de versión
├── README_ACTUALIZACION.txt           ← Instrucciones rápidas
│
├── docs/                              ← Documentación
│   ├── RESUMEN_SINCRONIZACION.md
│   ├── INSTRUCCIONES_SINCRONIZACION.md
│   └── EJEMPLO_CONFIGURACION_SYNC.md
│
└── assets/                            ← Iconos (si no están embebidos)
    └── icons/
        ├── sync.svg
        └── ...
```

---

## 🎯 Pasos para el Usuario Final

### Usuarios Nuevos (Primera instalación)
1. Descomprimir carpeta
2. Ejecutar `CompraventasV2_v2.5.0.exe`
3. Seleccionar sucursal
4. (Opcional) Configurar sincronización

### Usuarios Actualizando desde v2.0
1. Hacer backup desde la app actual
2. Cerrar aplicación
3. Reemplazar ejecutable viejo con `CompraventasV2_v2.5.0.exe`
4. Ejecutar `migrate_sync.py` (solo una vez)
5. Abrir aplicación
6. (Opcional) Configurar sincronización en F5 → Sincronización

---

## 🔐 Notas de Seguridad

### Gmail - Contraseñas de Aplicación
- **NO usar contraseña normal de Gmail**
- Generar contraseña de aplicación en: https://myaccount.google.com/apppasswords
- Habilitar verificación en dos pasos primero
- Habilitar IMAP en configuración de Gmail

### Datos Sensibles
- Las sincronizaciones viajan cifradas (TLS en SMTP/IMAP)
- Los emails solo van a la misma cuenta (no salen de Gmail)
- Contraseñas se guardan en `app_config.json` (advertir al usuario)

---

## 📊 Métricas de la Actualización

### Código Nuevo
- **~1000 líneas** de código Python
- **2 módulos nuevos** (sync_manager, sync_config)
- **1 modelo nuevo** (SyncLog)
- **3 métodos** en MainWindow

### Impacto en Tamaño
- Ejecutable: **+~50 KB** (estimado)
- Dependencias: No se agregan nuevas

### Compatibilidad
- **100% compatible** con v2.0
- **No rompe** funcionalidad existente
- **Opcional**: Si no se activa sync, funciona igual que antes

---

## ✅ Verificación Final

Antes de distribuir, ejecutar estos tests:

```bash
# Test 1: Instalación limpia
1. Borrar BD
2. Ejecutar app
3. Verificar que crea sync_log automáticamente

# Test 2: Actualización desde v2.0
1. Copiar BD de v2.0
2. Ejecutar migrate_sync.py
3. Verificar que agrega sync_log sin borrar datos

# Test 3: Sincronización
1. Configurar Gmail
2. Hacer venta en Sucursal A
3. Verificar que aparece en Sucursal B
4. Verificar indicador en status bar

# Test 4: Desactivar sync
1. Desmarcar "Activar sincronización"
2. Guardar
3. Verificar que indicador desaparece
4. Verificar que app funciona normalmente
```

---

## 🎉 Listo para Distribuir

Una vez completados todos los pasos:

1. Comprimir carpeta completa en: `CompraventasV2_v2.5.0.zip`
2. Crear release en GitHub (si usas)
3. Enviar a usuarios con `README_ACTUALIZACION.txt`
4. Dar soporte según documentación

---

**¡Versión 2.5.0 lista para producción!**

Fecha de release: 2025-12-26
Autor: Tu Nombre
Versión anterior: 2.0.0
