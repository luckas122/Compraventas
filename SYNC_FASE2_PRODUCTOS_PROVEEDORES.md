# Sincronización Fase 2: Productos y Proveedores

## ✅ Implementado en v2.6.0

La Fase 2 de sincronización agrega soporte para sincronizar **productos** y **proveedores** entre sucursales, además de las ventas que ya se sincronizaban en la Fase 1.

---

## 🎯 Características Nuevas

### 1. Sincronización de Productos

- **Identificación única:** Código de barras
- **Acción:** UPSERT (create o update)
- **Lógica:**
  - Si el producto NO existe en la sucursal remota → se CREA
  - Si el producto YA existe (mismo código de barras) → se ACTUALIZA con los datos recibidos
- **Campos sincronizados:**
  - `codigo_barra` (clave única)
  - `nombre`
  - `precio`
  - `categoria`
  - `telefono`
  - `numero_cuenta`
  - `cbu`

**Ejemplo de uso:**
- Sucursal Sarmiento agrega un nuevo producto "Perfume X" con código de barras "123456"
- Sincronización automática
- Sucursal Salta recibe el producto y lo crea en su base de datos
- Ahora ambas sucursales tienen el mismo catálogo

### 2. Sincronización de Proveedores

- **Identificación única:** Nombre del proveedor
- **Acción:** UPSERT (create o update)
- **Lógica:**
  - Si el proveedor NO existe en la sucursal remota → se CREA
  - Si el proveedor YA existe (mismo nombre) → se ACTUALIZA con los datos recibidos
- **Campos sincronizados:**
  - `nombre` (clave única)
  - `telefono`
  - `numero_cuenta`
  - `cbu`

**Ejemplo de uso:**
- Sucursal Salta agrega un nuevo proveedor "Distribuidora ABC"
- Sincronización automática
- Sucursal Sarmiento recibe el proveedor y lo crea en su base de datos
- Ambas sucursales comparten la lista de proveedores

---

## 🔧 Configuración

### Habilitar sincronización de productos/proveedores

1. Ir a **Configuración → Sincronización**
2. En la sección "¿Qué sincronizar?":
   - ✓ Ventas (siempre activo)
   - ☐ Sincronizar productos → **Marcar checkbox**
   - ☐ Sincronizar proveedores → **Marcar checkbox**
3. Click "Guardar"

### Configuración en app_config.json

```json
{
  "sync": {
    "enabled": true,
    "mode": "interval",
    "interval_minutes": 5,
    "gmail_smtp": {
      "host": "smtp.gmail.com",
      "port": 587,
      "username": "tu-email@gmail.com",
      "password": "tu-contraseña-de-aplicación"
    },
    "gmail_imap": {
      "host": "imap.gmail.com",
      "port": 993,
      "username": "tu-email@gmail.com",
      "password": "tu-contraseña-de-aplicación"
    },
    "sync_productos": true,       ← Activar
    "sync_proveedores": true,     ← Activar
    "last_sync": null
  }
}
```

---

## 🔄 Cómo Funciona

### Flujo de Sincronización

```
┌─────────────────────────────────────────────────────────────┐
│ SUCURSAL SARMIENTO                                          │
│                                                             │
│ 1. Usuario agrega producto "Shampoo XYZ" (código: 789)     │
│ 2. Sincronización detecta cambio pendiente                 │
│ 3. Genera paquete JSON con el producto                     │
│ 4. Envía email a Gmail con adjunto sync_xxxxx.json         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
                           │
                           │ GMAIL
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ SUCURSAL SALTA                                              │
│                                                             │
│ 1. Sincronización descarga emails no leídos de Gmail       │
│ 2. Detecta email de Sarmiento con [SYNC] en asunto         │
│ 3. Parsea JSON adjunto                                     │
│ 4. Busca producto por código de barras 789                 │
│    - NO existe → CREAR producto nuevo                      │
│    - SÍ existe → ACTUALIZAR con nuevos datos               │
│ 5. Registra en SyncLog para evitar duplicados              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Prevención de Duplicados

El sistema usa **hashing MD5** para detectar si un producto/proveedor ya fue sincronizado:

```python
# Calcular hash del producto
producto_data = {
    "codigo_barra": "789",
    "nombre": "Shampoo XYZ",
    "precio": 1500.0,
    ...
}
data_hash = md5(json.dumps(producto_data, sort_keys=True))

# Verificar si ya existe en SyncLog
ya_sincronizado = db.query(SyncLog).filter(
    SyncLog.tipo == "producto",
    SyncLog.data_hash == data_hash,
    SyncLog.sucursal_origen == "Sarmiento"
).first()

if ya_sincronizado:
    # No enviar de nuevo (evita spam)
    pass
else:
    # Enviar por primera vez
    enviar_sync_via_gmail(producto_data)
```

---

## 📊 Estructura del Paquete JSON

Ejemplo de paquete de sincronización con productos y proveedores:

```json
{
  "sync_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "sucursal_origen": "Sarmiento",
  "timestamp": "2025-12-26T21:30:00",
  "cambios": [
    {
      "sync_id": "prod-uuid-1",
      "tipo": "producto",
      "accion": "upsert",
      "data": {
        "id": 42,
        "codigo_barra": "789",
        "nombre": "Shampoo XYZ",
        "precio": 1500.0,
        "categoria": "Higiene",
        "telefono": null,
        "numero_cuenta": null,
        "cbu": null
      },
      "hash": "a1b2c3d4e5f6..."
    },
    {
      "sync_id": "prov-uuid-2",
      "tipo": "proveedor",
      "accion": "upsert",
      "data": {
        "id": 10,
        "nombre": "Distribuidora ABC",
        "telefono": "011-1234-5678",
        "numero_cuenta": "1234567890",
        "cbu": "0000001100001234567890"
      },
      "hash": "f6e5d4c3b2a1..."
    },
    {
      "sync_id": "venta-uuid-3",
      "tipo": "venta",
      "accion": "create",
      "data": {
        "id": 100,
        "sucursal": "Sarmiento",
        "fecha": "2025-12-26T20:00:00",
        "modo_pago": "Efectivo",
        "total": 3000.0,
        "items": [...]
      },
      "hash": "1a2b3c4d5e6f..."
    }
  ]
}
```

---

## ⚠️ Consideraciones Importantes

### 1. Conflictos de Actualización

Si dos sucursales modifican el mismo producto/proveedor:
- **Gana el último:** La última sincronización recibida sobrescribe los datos
- **Recomendación:** Designar una sucursal "maestra" para gestionar catálogo

### 2. Performance

- **Primera sincronización:** Puede tomar tiempo si hay muchos productos
- **Sincronizaciones subsecuentes:** Solo envía productos/proveedores modificados (detectados por hash)

### 3. Claves Únicas

- **Productos:** Código de barras DEBE ser único
- **Proveedores:** Nombre DEBE ser único
- Si hay duplicados, pueden generarse conflictos

### 4. Eliminación

- **Fase 2 NO sincroniza eliminaciones** (solo create/update)
- Si eliminas un producto en Sarmiento, NO se eliminará en Salta
- **Solución futura:** Agregar acción "delete" en Fase 3

---

## 🧪 Cómo Probar

### Prueba 1: Sincronizar Productos

1. **En Sucursal Sarmiento:**
   - Ir a Productos → Agregar Producto
   - Código: `TEST001`
   - Nombre: `Producto de Prueba`
   - Precio: `100`
   - Guardar

2. **Configurar Sync:**
   - Config → Sincronización
   - Habilitar sincronización
   - Marcar "Sincronizar productos"
   - Configurar Gmail (misma cuenta en ambas sucursales)
   - Guardar

3. **Esperar sincronización automática** (o hacer sync manual)

4. **En Sucursal Salta:**
   - Ir a Productos
   - Buscar código `TEST001`
   - **Debería aparecer** el producto con nombre "Producto de Prueba"

### Prueba 2: Actualizar Producto

1. **En Sucursal Salta:**
   - Editar producto `TEST001`
   - Cambiar precio a `150`
   - Guardar

2. **Esperar sincronización**

3. **En Sucursal Sarmiento:**
   - Buscar producto `TEST001`
   - **Precio debería ser `150`** (actualizado)

### Prueba 3: Sincronizar Proveedores

1. **En Sucursal Sarmiento:**
   - Ir a Proveedores → Agregar Proveedor
   - Nombre: `Proveedor Test`
   - Teléfono: `011-1234-5678`
   - Guardar

2. **Configurar Sync:**
   - Marcar "Sincronizar proveedores"
   - Guardar

3. **En Sucursal Salta:**
   - Ir a Proveedores
   - **Debería aparecer** "Proveedor Test"

---

## 📝 Cambios en el Código

### Archivos Modificados:

1. **app/sync_manager.py**
   - Líneas 40-71: `detectar_cambios_pendientes()` - Detecta cambios en productos/proveedores
   - Líneas 157-218: `generar_paquete_cambios()` - Serializa productos/proveedores
   - Líneas 401-404: `aplicar_paquete()` - Routing para productos/proveedores
   - Líneas 477-508: `_aplicar_producto_upsert()` - NUEVO método
   - Líneas 510-535: `_aplicar_proveedor_upsert()` - NUEVO método

2. **app/gui/sync_config.py**
   - Líneas 148-173: UI actualizada con checkboxes habilitados
   - Líneas 234-236: Cargar checkboxes desde config
   - Líneas 258-259: Guardar checkboxes en config

3. **app/app_config.json**
   - Líneas 213-232: Sección "sync" con `sync_productos` y `sync_proveedores`

---

## 🚀 Próximos Pasos (Fase 3 - Futuro)

- [ ] Sincronización de eliminaciones (acción "delete")
- [ ] Resolución de conflictos más sofisticada (timestamps, versionado)
- [ ] Sincronización incremental optimizada (solo cambios desde última sync)
- [ ] Dashboard de sincronización con estadísticas
- [ ] Log visual de sincronizaciones en la UI

---

## ✅ Checklist Pre-Producción

Antes de usar en producción:

- [ ] Probar sincronización de productos entre sucursales
- [ ] Probar sincronización de proveedores entre sucursales
- [ ] Verificar que productos duplicados (mismo código de barras) se actualizan correctamente
- [ ] Verificar que proveedores duplicados (mismo nombre) se actualizan correctamente
- [ ] Probar sincronización con muchos productos (100+)
- [ ] Verificar que SyncLog no crece infinitamente (limpiar logs antiguos periódicamente)
- [ ] Documentar flujo de trabajo para usuarios finales

---

**Fecha de implementación:** 2025-12-26
**Versión:** 2.6.0
**Estado:** ✅ LISTO PARA PRUEBAS
