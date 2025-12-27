# Changelog - Compraventas

Todos los cambios notables de este proyecto serán documentados en este archivo.

---

## [2.6.0] - 2025-12-26

### Agregado
- **🎉 Fase 2 de Sincronización: Productos y Proveedores**
  - Sincronización automática de productos entre sucursales
    - Identificación por código de barras (clave única)
    - Acción UPSERT: crea si no existe, actualiza si ya existe
    - Prevención de duplicados con hashing MD5
  - Sincronización automática de proveedores entre sucursales
    - Identificación por nombre (clave única)
    - Acción UPSERT: crea si no existe, actualiza si ya existe
    - Prevención de duplicados con hashing MD5
  - Checkboxes habilitados en UI de configuración
  - Tooltips explicativos para cada opción de sincronización
  - Documentación completa en `SYNC_FASE2_PRODUCTOS_PROVEEDORES.md`

### Modificado
- **app/sync_manager.py:**
  - `detectar_cambios_pendientes()` - Detecta cambios en productos/proveedores
  - `generar_paquete_cambios()` - Incluye productos/proveedores en paquete JSON
  - `aplicar_paquete()` - Routing para aplicar productos/proveedores
  - `_aplicar_producto_upsert()` - NUEVO método para aplicar productos
  - `_aplicar_proveedor_upsert()` - NUEVO método para aplicar proveedores
- **app/gui/sync_config.py:**
  - Checkboxes de productos/proveedores ahora habilitados (antes disabled)
  - Label "✓ Ventas (siempre activo)" agregado
  - Tooltips informativos en checkboxes
- **app/app_config.json:**
  - Agregada sección "sync" completa si faltaba
  - Valores por defecto para `sync_productos` y `sync_proveedores`

### Técnico
- `app/sync_manager.py:40-71` - Detección de cambios en productos/proveedores
- `app/sync_manager.py:157-218` - Serialización de productos/proveedores
- `app/sync_manager.py:401-404` - Routing en `aplicar_paquete()`
- `app/sync_manager.py:477-535` - Métodos `_aplicar_producto_upsert()` y `_aplicar_proveedor_upsert()`
- `app/gui/sync_config.py:148-173` - UI actualizada con checkboxes habilitados
- `app/app_config.json:213-232` - Configuración de sincronización

### Notas de Actualización
- **IMPORTANTE:** Esta versión habilita la sincronización de productos y proveedores
- Para activar: Config → Sincronización → Marcar checkboxes correspondientes
- Los productos se sincronizan por código de barras (debe ser único)
- Los proveedores se sincronizan por nombre (debe ser único)
- Primera sincronización puede tomar tiempo si hay muchos productos
- Sistema usa hashing MD5 para evitar reenviar datos no modificados

### Flujo de Prueba
1. Configurar Gmail en ambas sucursales (misma cuenta)
2. Habilitar sincronización y marcar checkboxes de productos/proveedores
3. Agregar producto en Sucursal A
4. Esperar 5 minutos (o hacer sync manual)
5. Verificar que producto aparece en Sucursal B
6. Editar producto en Sucursal B
7. Verificar que cambios se reflejan en Sucursal A

---

## [2.5.2] - 2025-12-26

### Corregido
- **CRÍTICO - Updater:** Corregido error de detección de directorio de instalación en ejecutables PyInstaller
  - Problema: `install_dir` usaba `Path.cwd()` en lugar de detectar la ubicación real del ejecutable
  - Solución: Ahora usa `sys.executable` cuando está en modo frozen (PyInstaller ONEDIR)
  - Error resuelto: "Windows no puede encontrar el archivo C:\Users\...\app\Tu local 2025.exe"
  - Afecta: `updater.py:249-257`

- **CRÍTICO - Build:** Corregido error "No suitable Python runtime found" en build.bat
  - Problema: El comando `py -3.11` no encontraba el runtime de Python
  - Solución: Reemplazado `py -3.11` por `python` para usar el Python del venv activado
  - Afecta: Todo el flujo de build.bat

- **CRÍTICO - Sync Config:** Corregida caída de aplicación al probar conexión SMTP/IMAP en ejecutable compilado
  - Problema: PyInstaller no incluía certificados SSL ni módulos SSL necesarios, causando crash silencioso
  - Solución implementada en 3 capas:
    1. `build.spec` - Agregados módulos SSL (_ssl, _hashlib, smtplib, imaplib, email.*) a hiddenimports
    2. `build.spec` - Incluidos certificados SSL de certifi como data files
    3. `sync_config.py` - Logging detallado que guarda en `app/logs/sync_test_connection.log` para debugging
  - Afecta: `build.spec:21-50,74-80` y `app/gui/sync_config.py:245-431`

### Agregado
- **Sistema de logging detallado para prueba de conexión sync**
  - Log completo en `app/logs/sync_test_connection.log`
  - Información capturada:
    - Versión de Python y estado frozen
    - Módulos SSL disponibles (\_ssl, \_hashlib, OPENSSL_VERSION)
    - Estado de certificados certifi
    - Debug completo de conexiones SMTP/IMAP con traceback
    - Mensajes de error específicos con tipo de excepción
  - Útil para diagnosticar problemas de SSL/certificados en PyInstaller

### Técnico
- `updater.py:249-257` - Detección correcta con `getattr(sys, 'frozen', False)` y `sys.executable`
- `build.bat:14,22-24,37,42` - Cambio de `py -3.11` a `python` en todos los comandos
- `build.spec:21-50` - Agregados 11 módulos SSL/email a hiddenimports
- `build.spec:74-80` - Incluidos certificados certifi como data files
- `app/gui/sync_config.py:245-431` - Reescrita función `_test_connection()` con logging completo

### Notas de Actualización
- Esta versión corrige 3 bugs críticos reportados en v2.5.1
- Si actualizas desde v2.5.0 o v2.5.1, esta versión resuelve todos los problemas conocidos
- El updater ahora funciona correctamente en distribuciones ONEDIR
- Build.bat funciona sin requerir configuración del Python launcher
- La prueba de conexión de sincronización ya no causa crashes
- **IMPORTANTE:** Si tu `app_config.json` no tiene la sección "sync", cópiala del template o usa los valores por defecto:
  - IMAP puerto: 993 (no 987)
  - SMTP puerto: 587

---

## [2.5.1] - 2025-12-26

### Corregido
- **Updater:** Corregido error al relanzar la aplicación después de actualizar
  - Problema: El updater intentaba ejecutar `{__app_name__}.exe` generando rutas incorrectas cuando el nombre tiene espacios
  - Solución: Ahora detecta automáticamente el nombre del ejecutable dentro del ZIP descargado
  - Afecta a: Usuarios que actualizan desde GitHub releases con ZIP ONEDIR
- **Updater:** Mejorado manejo de nombres con espacios en carpetas temporales
- **Updater:** Escapado correcto de rutas en scripts PowerShell para accesos directos

### Técnico
- `updater.py:267-277` - Detección automática del ejecutable usando `glob("*.exe")`
- `updater.py:377` - Reemplazo de espacios en nombres de carpetas temporales
- `updater.py:383-384` - Escapado de comillas para PowerShell

---

## [2.5.0] - 2025-12-26

### Agregado
- **Sistema de sincronización automática entre sucursales vía Gmail**
  - Sincronización de ventas completas entre Sarmiento y Salta
  - Tres modos configurables:
    - Intervalo fijo (cada X minutos)
    - Detección de cambios (solo cuando hay cambios nuevos)
    - Manual (botón en status bar)
  - Pestaña "Sincronización" en Configuraciones
  - Indicador visual en status bar mostrando estado en tiempo real
  - Modelo `SyncLog` para auditoría completa de sincronizaciones
  - Detección automática de cambios pendientes
  - Prevención de duplicados con UUID único y hash MD5
  - Script de migración `migrate_sync.py` para actualizar base de datos

### Archivos Nuevos
- `app/sync_manager.py` (443 líneas) - Lógica completa de sincronización
- `app/gui/sync_config.py` (283 líneas) - Interfaz de configuración
- `migrate_sync.py` - Script de migración de base de datos

### Modificado
- `app/models.py` - Agregado modelo `SyncLog` con índices optimizados
- `app/app_config.json` - Nueva sección `"sync"` con configuración por defecto
- `app/gui/main_window/configuracion_mixin.py` - Integrada pestaña "Sincronización"
- `app/gui/main_window/core.py` - Integrado scheduler y lógica de sincronización (129 líneas)

### Documentación
- `RESUMEN_SINCRONIZACION.md` - Visión general del sistema
- `INSTRUCCIONES_SINCRONIZACION.md` - Guía de integración técnica
- `EJEMPLO_CONFIGURACION_SYNC.md` - Tutorial paso a paso con ejemplos
- `PREPARAR_VERSION_2.5.md` - Guía para preparar releases
- `RESUMEN_FINAL_v2.5.md` - Estado completo del sistema

### Seguridad
- Soporte para contraseñas de aplicación de Gmail
- Validación de origen en sincronizaciones (no aplica cambios propios)
- Detección de duplicados por hash MD5
- Log completo de todas las sincronizaciones en tabla `sync_log`

### Notas de Actualización
- **IMPORTANTE:** Ejecutar `migrate_sync.py` ANTES de usar sincronización
  - O borrar la base de datos (se recrea automáticamente con `sync_log`)
- Configurar Gmail con contraseña de aplicación (no contraseña normal)
- Habilitar IMAP en Gmail para recibir sincronizaciones
- Fase 1: Solo sincroniza ventas (productos/proveedores en Fase 2)

### Requisitos
- Gmail con contraseña de aplicación
- IMAP habilitado en Gmail
- Conexión a internet (para sincronización)
- Misma cuenta de Gmail en ambas sucursales

---

## [2.0.0] - 2025-12-XX

### Agregado
- Pestaña de Estadísticas en Historial de Ventas (solo admin)
- Gráficos con matplotlib:
  - Ventas diarias (barras)
  - Comparativa por sucursal
  - Top 10 productos
  - Distribución de formas de pago (torta)
- Botones de rango rápido (Hoy, Semana, Mes, Mes Anterior)
- Auto-actualización al cambiar a la pestaña

### Modificado
- Sistema AFIP/CAE restaurado y funcional
- `app/afip_integration.py` restaurado
- Método `_afip_emitir_si_corresponde()` en ventas.py

### Corregido
- Problema de gráficos superpuestos en Estadísticas
- CAE se genera correctamente en pagos con tarjeta

---

## Formato del Changelog

Este changelog sigue el formato [Keep a Changelog](https://keepachangelog.com/es/1.0.0/).

### Tipos de cambios:
- **Agregado** - Nuevas funcionalidades
- **Modificado** - Cambios en funcionalidades existentes
- **Obsoleto** - Funcionalidades que serán removidas
- **Eliminado** - Funcionalidades eliminadas
- **Corregido** - Corrección de bugs
- **Seguridad** - Vulnerabilidades corregidas
