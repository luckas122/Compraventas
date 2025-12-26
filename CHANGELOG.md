# Changelog - Compraventas

Todos los cambios notables de este proyecto serán documentados en este archivo.

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
