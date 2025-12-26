# 🔄 Sistema de Sincronización entre Sucursales - RESUMEN

## ✅ ¿Qué se implementó?

He implementado un **sistema completo de sincronización automática** entre tus dos sucursales usando Gmail como canal de comunicación.

---

## 📋 Características Principales

### 1. **Tres Modos de Sincronización**

#### 🕐 Modo Intervalo Fijo
- Sincroniza cada X minutos (configurable: 1-60 minutos)
- Ideal para: Mantener ambas sucursales actualizadas constantemente
- Ejemplo: Cada 5 minutos envía y recibe cambios automáticamente

#### 🔍 Modo Detección de Cambios (RECOMENDADO)
- Solo sincroniza cuando detecta cambios nuevos
- Ahorra ancho de banda y reduce emails
- Revisa cada 30 segundos si hay cambios pendientes
- Si encuentra cambios, sincroniza inmediatamente

#### 👆 Modo Manual
- Sincronización bajo demanda
- Botón "🔄 Sincronizar" en la barra de estado
- Ideal para: Control total sobre cuándo sincronizar

---

### 2. **¿Qué se sincroniza?**

**FASE 1 (Implementada):**
- ✅ **Ventas completas** (todas las ventas nuevas)
  - Datos de la venta (total, descuento, interés, forma de pago)
  - Items de la venta (productos, cantidades, precios)
  - Datos AFIP/CAE (si aplica)
  - Fecha, sucursal, número de ticket

**FASE 2 (Planificada):**
- ⏳ Productos (crear, editar, eliminar)
- ⏳ Proveedores
- ⏳ Resolución de conflictos avanzada

---

### 3. **Pestaña de Configuración Completa**

En **Configuración → Sincronización** encontrarás:

#### Sección 1: Activación
- Switch ON/OFF para activar/desactivar todo el sistema

#### Sección 2: Modo de Sincronización
- Selector de modo (Intervalo / Detección de cambios / Manual)
- Intervalo en minutos (si aplica)

#### Sección 3: Gmail SMTP (Envío)
- Host: smtp.gmail.com
- Puerto: 587
- Usuario: tu-email@gmail.com
- Contraseña: **Contraseña de aplicación de Gmail**
- Link directo para generar contraseña

#### Sección 4: Gmail IMAP (Recepción)
- Host: imap.gmail.com
- Puerto: 993
- Usuario: mismo que SMTP
- Contraseña: misma que SMTP
- Nota: Usa la misma cuenta para ambos

#### Sección 5: Opciones Avanzadas
- Sincronizar productos (Fase 2 - deshabilitado)
- Sincronizar proveedores (Fase 2 - deshabilitado)

#### Botones:
- **Probar conexión**: Verifica SMTP e IMAP antes de guardar
- **Guardar configuración**: Guarda y activa la sincronización

---

### 4. **Indicador Visual en Barra de Estado**

El sistema muestra en tiempo real el estado de la sincronización:

| Icono | Mensaje | Significado |
|-------|---------|-------------|
| ✓ | Sync: hace 2 min (1↑ 0↓) | Última sincronización exitosa hace 2 minutos. Envió 1 venta, recibió 0. |
| ⏳ | Cambios pendientes | Hay cambios locales esperando sincronizarse |
| 🔄 | Sync activa | Sistema activo, esperando próximo ciclo |
| ⚠️ | Sync: 2 errores | Hubo errores (click para ver detalles) |
| 🔴 | Sync error: ... | Error crítico en última sincronización |

---

## 🔧 Archivos Creados/Modificados

### Nuevos archivos (5):
1. **app/sync_manager.py** (443 líneas)
   - Clase `SyncManager` con toda la lógica de sincronización
   - Genera paquetes JSON con cambios
   - Envía por SMTP
   - Recibe por IMAP
   - Aplica cambios a la BD local
   - Detecta duplicados con hash MD5

2. **app/gui/sync_config.py** (283 líneas)
   - Widget completo de configuración UI
   - Formularios para SMTP/IMAP
   - Validación y prueba de conexión
   - Auto-guarda al cambiar configuración

3. **INSTRUCCIONES_SINCRONIZACION.md**
   - Guía completa de integración
   - Código listo para copiar/pegar
   - Ejemplos de uso

4. **migrate_sync.py**
   - Script de migración de BD
   - Crea tabla `sync_log`
   - Ejecutar UNA VEZ antes de usar

5. **RESUMEN_SINCRONIZACION.md** (este archivo)

### Archivos modificados (3):
1. **app/models.py**
   - Agregado modelo `SyncLog` (14 líneas)

2. **app/app_config.json**
   - Agregada sección `"sync"` con configuración por defecto

3. **app/gui/main_window/configuracion_mixin.py**
   - Agregada pestaña "Sincronización" en tabs (16 líneas)

---

## 🚀 Pasos para Activar (Para Ti)

### Paso 1: Ejecutar Migración de BD
```bash
python migrate_sync.py
```

### Paso 2: Integrar en MainWindow
Abre el archivo `INSTRUCCIONES_SINCRONIZACION.md` y copia el código de integración en tu archivo principal (core.py o similar). Son 6 métodos simples.

### Paso 3: Configurar Gmail
1. Abre Gmail
2. Genera contraseña de aplicación: https://myaccount.google.com/apppasswords
3. Habilita IMAP en Gmail (Configuración → Reenvío y correo POP/IMAP)

### Paso 4: Configurar en la App
1. Ejecuta la aplicación
2. Ve a **Configuración → Sincronización**
3. Activa sincronización
4. Configura Gmail (misma cuenta en SMTP e IMAP)
5. Prueba conexión
6. Selecciona modo "Detección de cambios" (recomendado)
7. Guarda

### Paso 5: Repetir en Segunda Sucursal
Haz lo mismo en la segunda sucursal usando **la misma cuenta de Gmail**.

---

## 🎯 Cómo Funciona

### Flujo de Sincronización

```
SUCURSAL A                         GMAIL                    SUCURSAL B
──────────                         ─────                    ──────────

1. Venta nueva
   ($5000)
           │
           ├─→ Genera JSON
           │   {venta_id: 123,
           │    sucursal: "Sarmiento",
           │    total: 5000, ...}
           │
           ├─→ Envía email SMTP ──→  [Inbox Gmail]
           │   Asunto: [SYNC] ...
           │   Adjunto: sync_abc.json
           │
           └─→ Registra en sync_log
               (sync_id, tipo: venta,
                accion: create)


                                     [Inbox Gmail]  ←────┐
                                           │              │
                                           │              │
                                     Revisa IMAP     (cada 30s)
                                      cada 30s            │
                                           │              │
                                           ├─→ Descarga sync_abc.json
                                           │
                                           ├─→ Verifica no es de esta sucursal
                                           │
                                           ├─→ Verifica no fue aplicado antes
                                           │
                                           ├─→ Aplica venta en BD local
                                           │   INSERT INTO ventas...
                                           │
                                           ├─→ Registra en sync_log
                                           │
                                           └─→ Marca email como leído

                                                          Venta visible en
                                                          Historial Salta
```

---

## 🔒 Seguridad

### Detección de Duplicados
- Cada cambio tiene un `sync_id` único (UUID)
- Hash MD5 del contenido detecta duplicados
- Tabla `sync_log` registra todo lo aplicado
- Si un cambio ya fue aplicado, se ignora

### Validación de Origen
- Cada paquete incluye `sucursal_origen`
- No se aplica si es de la misma sucursal
- Previene loops infinitos

### Privacidad
- Los emails se envían a la misma cuenta
- Gmail solo actúa como intermediario
- Datos en tránsito: cifrado TLS (SMTP/IMAP)

---

## 📊 Base de Datos

### Nueva Tabla: `sync_log`

```sql
CREATE TABLE sync_log (
    id INTEGER PRIMARY KEY,
    sync_id VARCHAR UNIQUE NOT NULL,  -- UUID del cambio
    tipo VARCHAR NOT NULL,             -- 'venta', 'producto', 'proveedor'
    accion VARCHAR NOT NULL,           -- 'create', 'update', 'delete'
    timestamp DATETIME NOT NULL,       -- Cuándo se generó
    aplicado BOOLEAN NOT NULL,         -- TRUE si fue aplicado
    sucursal_origen VARCHAR NOT NULL,  -- 'Sarmiento' o 'Salta'
    data_hash VARCHAR NULL             -- Hash MD5 para detectar duplicados
);

-- Índices para performance
CREATE INDEX ix_sync_log_sync_id ON sync_log(sync_id);
CREATE INDEX ix_sync_log_tipo_timestamp ON sync_log(tipo, timestamp);
CREATE INDEX ix_sync_log_sucursal_timestamp ON sync_log(sucursal_origen, timestamp);
```

### Ejemplo de registro:

```json
{
  "id": 1,
  "sync_id": "a3f7b2c1-4d5e-6f7g-8h9i-0j1k2l3m4n5o",
  "tipo": "venta",
  "accion": "create",
  "timestamp": "2025-12-26T14:30:00",
  "aplicado": true,
  "sucursal_origen": "Sarmiento",
  "data_hash": "d41d8cd98f00b204e9800998ecf8427e"
}
```

---

## 🛠️ Troubleshooting

### Error: "SMTP: autenticación fallida"
✅ **Solución:** Usa contraseña de aplicación, no tu contraseña normal de Gmail.
   - Genera aquí: https://myaccount.google.com/apppasswords

### Error: "IMAP: No se pudo conectar"
✅ **Solución:** Verifica que IMAP esté habilitado en Gmail.
   - Gmail → Configuración → Reenvío y correo POP/IMAP → Habilitar IMAP

### No sincroniza automáticamente
✅ **Verificar:**
   1. Sincronización activada en Configuración
   2. Modo seleccionado correctamente
   3. Credenciales SMTP/IMAP guardadas
   4. Status bar muestra "🔄 Sync activa"

### Ventas duplicadas
✅ **Solución:** El sistema previene duplicados automáticamente con:
   - sync_id único
   - Hash MD5 del contenido
   - Verificación de numero_ticket + sucursal

### ¿Cómo ver el log de sincronizaciones?
```sql
SELECT
    sync_id,
    tipo,
    accion,
    sucursal_origen,
    timestamp,
    aplicado
FROM sync_log
ORDER BY timestamp DESC
LIMIT 20;
```

---

## 📈 Monitoreo

### Métricas en Status Bar

El indicador muestra:
- **Tiempo** desde última sincronización
- **Enviados (↑)**: Cuántos registros envió esta sucursal
- **Recibidos (↓)**: Cuántos registros recibió de otra sucursal
- **Estado**: ✓ OK | ⏳ Pendiente | ⚠️ Warning | 🔴 Error

### Logs en Consola

Si ejecutas en modo desarrollo, verás:
```
[SYNC] Enviados: 3, Recibidos: 1
[SYNC] Errores: []
[email-helper] enviado OK a ['tu-email@gmail.com']
```

---

## 🎓 Preguntas Frecuentes

**P: ¿Funciona sin internet?**
R: No. Requiere conexión a internet para acceder a Gmail. Pero cuando vuelva la conexión, sincronizará todo lo pendiente.

**P: ¿Puedo sincronizar más de 2 sucursales?**
R: Sí, pero requiere modificaciones. El sistema actual está diseñado para 2. Con cambios menores podrías agregar más.

**P: ¿Qué pasa si ambas sucursales venden el mismo producto simultáneamente?**
R: Se registran ambas ventas correctamente. El sistema sincroniza ventas completas, no inventario. En Fase 2 se agregará sincronización de stock.

**P: ¿Cuánto espacio ocupa en Gmail?**
R: Cada venta genera ~1-5 KB. Con 100 ventas/día = ~500 KB/día = 15 MB/mes. Insignificante.

**P: ¿Puedo usar otro servicio que no sea Gmail?**
R: Sí, cualquier servidor SMTP/IMAP. Solo cambia los datos de configuración.

**P: ¿Sincroniza reportes y estadísticas?**
R: No directamente. Sincroniza las ventas, y luego cada sucursal genera sus propios reportes con todos los datos (locales + sincronizados).

---

## 🚦 Próximos Pasos (Fase 2)

Características planificadas para el futuro:

1. **Sincronización de Productos**
   - Cuando agregas/editas producto en Sarmiento → se actualiza en Salta
   - Sincronización bidireccional

2. **Sincronización de Proveedores**
   - Mantener catálogo unificado

3. **Resolución de Conflictos Avanzada**
   - Si ambas sucursales modifican el mismo producto
   - Opciones: última escritura gana / merge inteligente / manual

4. **Compresión de Datos**
   - Para paquetes grandes (>100 ventas)

5. **Panel de Historial de Sync en UI**
   - Ver todas las sincronizaciones pasadas
   - Filtrar por fecha, tipo, sucursal

6. **Notificaciones**
   - Alerta cuando llegan cambios importantes
   - Resumen diario por email

---

## ✨ Conclusión

Has recibido un **sistema profesional de sincronización** que:

- ✅ Sincroniza ventas automáticamente entre sucursales
- ✅ Usa Gmail (gratis, confiable, sin servidor propio)
- ✅ Tres modos configurables según tus necesidades
- ✅ Detección inteligente de cambios
- ✅ Prevención de duplicados
- ✅ Interfaz gráfica completa
- ✅ Indicador visual en tiempo real
- ✅ Base de datos auditada (sync_log)

**Todo listo para integrar en ~30 minutos** siguiendo INSTRUCCIONES_SINCRONIZACION.md

---

**Cualquier duda, consulta el archivo INSTRUCCIONES_SINCRONIZACION.md para detalles técnicos.**

---

**Autor:** Claude Code
**Versión:** 1.0
**Fecha:** 26 de Diciembre de 2025
