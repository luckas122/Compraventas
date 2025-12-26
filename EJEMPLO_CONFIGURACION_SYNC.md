# 📝 Ejemplo de Configuración - Sincronización

## Configuración Recomendada para tu Caso

### Escenario: Dos perfumerías (Sarmiento y Salta) con Gmail compartido

---

## 🔧 Configuración en `app_config.json`

Después de configurar desde la UI, tu archivo quedará así:

```json
{
  "sync": {
    "enabled": true,
    "mode": "on_change",
    "interval_minutes": 5,
    "gmail_smtp": {
      "host": "smtp.gmail.com",
      "port": 587,
      "username": "perfumeriasu@gmail.com",
      "password": "abcd efgh ijkl mnop"
    },
    "gmail_imap": {
      "host": "imap.gmail.com",
      "port": 993,
      "username": "perfumeriasu@gmail.com",
      "password": "abcd efgh ijkl mnop"
    },
    "sync_productos": false,
    "sync_proveedores": false,
    "last_sync": "2025-12-26T14:30:00"
  }
}
```

**Notas:**
- `enabled: true` → Sincronización activa
- `mode: "on_change"` → Solo sincroniza cuando detecta cambios (RECOMENDADO)
- `username` y `password` → Mismos para SMTP e IMAP
- `password` → **Contraseña de aplicación de Gmail** (NO tu contraseña normal)

---

## 📧 Cómo Generar Contraseña de Aplicación en Gmail

### Paso 1: Activar Verificación en Dos Pasos

1. Ir a: https://myaccount.google.com/security
2. En "Acceso a Google", click en "Verificación en dos pasos"
3. Seguir los pasos para activarla (si no está activada)

### Paso 2: Generar Contraseña de Aplicación

1. Ir a: https://myaccount.google.com/apppasswords
2. En "Selecciona la app", elegir "Otra (nombre personalizado)"
3. Escribir: "Compraventas Sincronización"
4. Click "Generar"
5. Gmail te mostrará una contraseña de 16 caracteres:
   ```
   abcd efgh ijkl mnop
   ```
6. **COPIAR ESTA CONTRASEÑA** (no podrás verla nuevamente)
7. Pegarla en la configuración de SMTP y IMAP

### Paso 3: Habilitar IMAP

1. Abrir Gmail
2. Click en engranaje (⚙️) → "Ver toda la configuración"
3. Ir a pestaña "Reenvío y correo POP/IMAP"
4. En sección "Acceso IMAP", seleccionar:
   - ✅ "Habilitar IMAP"
5. Scroll abajo → "Guardar cambios"

---

## 🖥️ Configuración en la Aplicación

### SUCURSAL SARMIENTO

1. **Abrir app en PC de Sarmiento**
2. **F5** (Configuraciones) → Tab "Sincronización"
3. Llenar formulario:

```
┌─────────────────────────────────────────────────┐
│ ACTIVACIÓN                                      │
├─────────────────────────────────────────────────┤
│ ☑ Activar sincronización entre sucursales      │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│ MODO DE SINCRONIZACIÓN                          │
├─────────────────────────────────────────────────┤
│ Modo: [Solo cuando hay cambios detectados ▼]   │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│ GMAIL SMTP (para enviar sincronizaciones)       │
├─────────────────────────────────────────────────┤
│ Host:        smtp.gmail.com                     │
│ Puerto:      587                                │
│ Usuario:     perfumeriasu@gmail.com             │
│ Contraseña:  •••• •••• •••• ••••                │
│                                                  │
│ → ¿Cómo generar contraseña de aplicación?       │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│ GMAIL IMAP (para recibir sincronizaciones)      │
├─────────────────────────────────────────────────┤
│ Host:        imap.gmail.com                     │
│ Puerto:      993                                │
│ Usuario:     perfumeriasu@gmail.com             │
│ Contraseña:  •••• •••• •••• ••••                │
│                                                  │
│ Nota: Usa la misma cuenta de Gmail para SMTP    │
│       e IMAP. La aplicación se enviará emails   │
│       a sí misma.                               │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│ OPCIONES AVANZADAS                              │
├─────────────────────────────────────────────────┤
│ ☐ Sincronizar productos (Fase 2)               │
│ ☐ Sincronizar proveedores (Fase 2)             │
└─────────────────────────────────────────────────┘

              [Probar conexión] [Guardar configuración]
```

4. Click **"Probar conexión"**
   - Debe mostrar: "Conexión exitosa a SMTP e IMAP"
   - Si falla, revisar contraseña de aplicación

5. Click **"Guardar configuración"**

6. **Verificar indicador en status bar:**
   ```
   🔄 Sync activa
   ```

### SUCURSAL SALTA

**Repetir exactamente los mismos pasos** en el PC de la sucursal Salta.

⚠️ **IMPORTANTE:** Usar **la misma cuenta de Gmail** (perfumeriasu@gmail.com) en ambas sucursales.

---

## 🧪 Prueba de Funcionamiento

### Prueba 1: Venta en Sarmiento → Aparece en Salta

1. **En Sarmiento:**
   - Hacer una venta de prueba: $1000
   - Finalizar venta
   - Observar status bar: `⏳ Cambios pendientes`
   - Esperar 30 segundos
   - Status bar cambia a: `✓ Sync: hace un momento (1↑ 0↓)`

2. **En Salta:**
   - Esperar 30 segundos
   - Status bar muestra: `✓ Sync: hace un momento (0↑ 1↓)`
   - Ir a **Historial de Ventas** (F4)
   - Filtrar por "Todas las sucursales"
   - **Verificar que aparece la venta de Sarmiento** ✅

### Prueba 2: Venta en Salta → Aparece en Sarmiento

1. **En Salta:**
   - Hacer venta: $2000
   - Finalizar
   - Status bar: `⏳ Cambios pendientes` → `✓ Sync: hace un momento (1↑ 0↓)`

2. **En Sarmiento:**
   - Esperar 30 segundos
   - Status bar: `✓ Sync: hace un momento (0↑ 1↓)`
   - Historial → Ver venta de Salta ✅

### Prueba 3: Ventas simultáneas

1. **En Sarmiento:** Venta $500
2. **En Salta:** Venta $750 (al mismo tiempo)
3. Esperar 1 minuto
4. Ambas sucursales deben mostrar: `✓ Sync: hace un momento (1↑ 1↓)`
5. Historial en ambas: 2 ventas (una de cada sucursal) ✅

---

## 📊 Verificación en Base de Datos

### Consultar log de sincronizaciones

```sql
-- Ver últimas 10 sincronizaciones
SELECT
    id,
    tipo,
    accion,
    sucursal_origen,
    timestamp,
    aplicado
FROM sync_log
ORDER BY timestamp DESC
LIMIT 10;
```

### Ejemplo de resultado:

```
id | tipo  | accion | sucursal_origen | timestamp           | aplicado
---+-------+--------+-----------------+---------------------+---------
 1 | venta | create | Sarmiento       | 2025-12-26 14:30:00 | 1
 2 | venta | create | Salta           | 2025-12-26 14:31:00 | 1
 3 | venta | create | Sarmiento       | 2025-12-26 14:35:00 | 1
```

### Verificar ventas sincronizadas

```sql
-- Ver ventas de ambas sucursales
SELECT
    numero_ticket,
    sucursal,
    fecha,
    total,
    modo_pago
FROM ventas
ORDER BY fecha DESC
LIMIT 20;
```

---

## 🔍 Interpretación del Indicador

El indicador en la barra de estado muestra:

```
✓ Sync: hace 2 min (1↑ 0↓)
```

Desglose:
- `✓` = Sincronización exitosa
- `hace 2 min` = Última sincronización hace 2 minutos
- `(1↑ 0↓)` = Envió 1 registro, recibió 0

### Otros estados posibles:

```
⏳ Cambios pendientes
```
Hay ventas locales que no se han sincronizado aún. Espera 30 segundos.

```
🔄 Sync activa
```
Sistema funcionando, esperando cambios o próximo intervalo.

```
⚠️ Sync: 2 errores
```
Hubo problemas en la última sincronización. Revisar logs.

```
🔴 Sync error: SMTP authentication failed
```
Error crítico. Revisar credenciales de Gmail.

---

## 🎯 Configuraciones Alternativas

### Si prefieres sincronización automática cada X minutos:

```json
{
  "sync": {
    "enabled": true,
    "mode": "interval",
    "interval_minutes": 3,
    ...
  }
}
```

En la UI:
- Modo: "Automática (intervalo fijo)"
- Intervalo: 3 minutos

### Si prefieres control manual:

```json
{
  "sync": {
    "enabled": true,
    "mode": "manual",
    ...
  }
}
```

En la UI:
- Modo: "Manual (botón en status bar)"
- Aparecerá botón "🔄 Sincronizar"

---

## 📧 Emails de Sincronización en Gmail

Cuando el sistema sincroniza, verás emails como:

```
De:   perfumeriasu@gmail.com
Para: perfumeriasu@gmail.com
Asunto: [SYNC] Sarmiento - 2025-12-26T14:30:00

Sincronización automática
Sucursal: Sarmiento
Timestamp: 2025-12-26T14:30:00
Cambios: 3 registros

Adjunto: sync_a3f7b2c1.json (2.5 KB)
```

**Notas:**
- Estos emails se marcan como leídos automáticamente después de procesarse
- Puedes crear un filtro en Gmail para archivarlos automáticamente
- NO los borres manualmente si quieres un historial completo

---

## ✅ Checklist de Configuración

Antes de poner en producción, verifica:

- [ ] Contraseña de aplicación generada en Gmail
- [ ] IMAP habilitado en Gmail
- [ ] Configuración guardada en ambas sucursales
- [ ] Prueba de conexión exitosa en ambas
- [ ] Modo "Detección de cambios" seleccionado
- [ ] Status bar muestra "🔄 Sync activa" en ambas
- [ ] Prueba de venta realizada y sincronizada correctamente
- [ ] Historial muestra ventas de ambas sucursales
- [ ] Tabla `sync_log` creada (ejecutar migrate_sync.py)

---

## 🆘 Solución de Problemas Comunes

### Error: "SMTP: autenticación fallida"

**Causa:** Contraseña incorrecta o no es contraseña de aplicación.

**Solución:**
1. Generar nueva contraseña de aplicación
2. Copiar completa (16 caracteres)
3. Pegar en configuración (sin espacios extra)
4. Guardar y probar conexión

### Error: "IMAP: Permission denied"

**Causa:** IMAP no habilitado en Gmail.

**Solución:**
1. Gmail → Configuración → Reenvío y correo POP/IMAP
2. Habilitar IMAP
3. Guardar cambios
4. Probar conexión nuevamente

### No sincroniza pero no hay errores

**Verificar:**
1. Sincronización activada (checkbox marcado)
2. Modo correcto seleccionado
3. Credenciales guardadas
4. Firewall/antivirus no bloquea puertos 587 y 993

**Solución rápida:**
1. Cambiar a modo "Intervalo fijo" con 1 minuto
2. Hacer venta de prueba
3. Esperar 1 minuto
4. Verificar status bar

---

**¡Listo! Con esta configuración tus dos sucursales estarán 100% sincronizadas.**

---

**Autor:** Claude Code
**Fecha:** 26 de Diciembre de 2025
