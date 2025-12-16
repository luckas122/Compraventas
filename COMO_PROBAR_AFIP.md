# Como Probar la Integracion AFIP

## Cambios Realizados

### 1. Campos AFIP agregados a models.py
- `afip_cae` - Codigo de Autorizacion Electronico
- `afip_cae_vencimiento` - Fecha de vencimiento del CAE
- `afip_numero_comprobante` - Numero de comprobante AFIP

### 2. Configuracion actualizada en app_config.json
- Seccion `fiscal` habilitada con:
  - `enabled: true`
  - CUIT de prueba: 20409378472
  - Access token configurado
  - URLs de API

### 3. Logica de ventas corregida (ventas.py)
- Ahora usa `afip_integration.py` (el cliente completo)
- Calcula subtotal e IVA automaticamente
- Guarda el CAE en la base de datos
- Muestra popup con resultado

### 4. Historial de ventas actualizado
- Agregadas columnas "CAE" y "Vto CAE"
- Muestra los comprobantes fiscales emitidos

## Como Probar

### Paso 1: Ejecutar el test de sandbox
```bash
python test_afip_simple.py
```

Debe mostrar:
```
Test 1: Autenticacion... OK
Test 2: Ultimo comprobante... OK
Test 3: Emitir factura de prueba... OK
TODOS LOS TESTS OK!
```

### Paso 2: Iniciar la aplicacion
```bash
python main.py
```

### Paso 3: Hacer una venta con TARJETA
1. Ve a la pestana "Ventas" (F3)
2. Agrega productos a la cesta
3. Selecciona "Tarjeta" como forma de pago
4. Haz clic en "Finalizar Venta"
5. Elige "No" en el dialogo de WhatsApp

### Paso 4: Verificar el resultado

Deberia aparecer un popup que dice:
```
AFIP - Factura Electronica

Comprobante electronico emitido correctamente.

CAE: XXXXXXXXXXXXXX
Vencimiento: YYYYMMDD
Numero de comprobante: NNNN
```

### Paso 5: Ver el CAE en el historial
1. Ve a la pestana "Historial" (F4)
2. Busca la venta recien creada
3. Deberia mostrar el CAE en las ultimas columnas

## Verificar la base de datos

Ejecuta:
```bash
python verificar_afip.py
```

Debe mostrar:
```
Columnas AFIP:
  afip_cae: True
  afip_cae_vencimiento: True
  afip_numero_comprobante: True

Ventas con CAE (AFIP): N
```

## Solución de Problemas

### No aparece popup de AFIP
- Verifica que `fiscal.enabled` este en `true` en `app_config.json`
- Verifica que seleccionaste "Tarjeta" como forma de pago
- Revisa la consola por errores

### Error al emitir factura
- Verifica tu access_token en https://app.afipsdk.com
- Asegurate de tener conexion a internet
- Revisa los logs en la consola

### No se ven las columnas CAE en historial
- Reinicia la aplicacion
- Verifica que exista una venta con tarjeta

### Las columnas existen pero estan vacias
- El CAE solo se guarda si la emision fue exitosa
- Verifica que no haya errores en la consola
- Ejecuta `python verificar_afip.py` para ver detalles

## Modo Produccion

IMPORTANTE: El sistema esta en modo SANDBOX (pruebas).

Para pasar a produccion:
1. Obten un access_token de produccion en https://app.afipsdk.com
2. Edita `app_config.json`:
   - `afip.environment: "prod"`
   - `fiscal.mode: "prod"`
   - Cambia el CUIT al de tu negocio
3. NUNCA uses el CUIT de prueba (20409378472) en produccion

## Contacto

Para problemas con AFIP SDK:
- Dashboard: https://app.afipsdk.com
- Documentacion: https://docs.afipsdk.com
- Soporte: info@afipsdk.com
