# PLANTILLAS PREDEFINIDAS DE TICKETS - v2.0

## 📄 PLANTILLA 1: EFECTIVO - RESUMIDO (Minimalista)

**Uso:** Para ventas rápidas en efectivo, ticket compacto

```
{{centerb: {{business}}}}
{{center: {{direccion}}}}
{{center: Ticket Nº {{ticket.numero}} - {{ticket.fecha_hora}}}}
{{hr}}
{{items}}
{{hr}}
{{right: Subtotal: {{totales.subtotal}}}}
{{rightb: TOTAL: {{totales.total}}}}
{{hr}}
{{left: Forma de pago: {{pago.modo}}}}
{{left: Abonado: {{abonado}}}}
{{left: Vuelto: {{vuelto}}}}
{{hr}}
{{center: ¡Gracias por su compra!}}
```

**Vista previa:**
```
         PERFUMERIA SUSI
    Pte. Sarmiento 1695, Gerli
  Ticket Nº 123 - 2024-12-25 14:30
────────────────────────────────────
7791290786691 — Suavizante Felicia...
1 × $55.00                    $55.00
7790828104655 — Jabón en pan paq...
2 × $18.00                    $36.00
────────────────────────────────────
                    Subtotal: $91.00
                      TOTAL: $91.00
────────────────────────────────────
Forma de pago: Efectivo
Abonado: $100.00
Vuelto: $9.00
────────────────────────────────────
       ¡Gracias por su compra!
```

---

## 📄 PLANTILLA 2: EFECTIVO - DETALLADO (Completo)

**Uso:** Para ventas con descuentos/intereses, información completa

```
{{centerb: {{business}}}}
{{center: {{direccion}}}}
{{center: Sucursal {{sucursal}}}}
{{center: CUIT: 20-40937847-2}}
{{center: IVA Responsable: Consumidor Final}}
{{hr}}
{{centerb: COMPROBANTE DE VENTA}}
{{center: Ticket Nº {{ticket.numero}}}}
{{center: Fecha: {{ticket.fecha_hora}}}}
{{hr}}
{{centerb: DETALLE DE PRODUCTOS}}
{{items}}
{{hr}}
{{centerb: RESUMEN}}
{{left: Subtotal:                    {{totales.subtotal}}}}
{{left: Descuento:                   {{totales.descuento}}}}
{{left: Interés:                     {{totales.interes}}}}
{{hr}}
{{leftb: TOTAL A PAGAR:              {{totales.total}}}}
{{hr}}
{{centerb: FORMA DE PAGO}}
{{left: Método: {{pago.modo}}}}
{{left: Abonado: {{abonado}}}}
{{left: Vuelto: {{vuelto}}}}
{{hr}}
{{center: ¡Gracias por su compra!}}
{{center: Vuelva pronto}}
{{center: Tel: +54 11 1234-5678}}
```

**Vista previa:**
```
         PERFUMERIA SUSI
    Pte. Sarmiento 1695, Gerli
        Sucursal Sarmiento
   CUIT: 20-40937847-2
IVA Responsable: Consumidor Final
────────────────────────────────────
      COMPROBANTE DE VENTA
        Ticket Nº 123
    Fecha: 2024-12-25 14:30
────────────────────────────────────
     DETALLE DE PRODUCTOS
7791290786691 — Suavizante Felicia...
1 × $55.00                    $55.00
7790828104655 — Jabón en pan paq...
2 × $18.00                    $36.00
662425026821 — Tampones Tamaño M...
3 × $30.50                    $91.50
────────────────────────────────────
            RESUMEN
Subtotal:                   $182.50
Descuento:                   $10.00
Interés:                      $0.00
────────────────────────────────────
TOTAL A PAGAR:              $172.50
────────────────────────────────────
        FORMA DE PAGO
Método: Efectivo
Abonado: $200.00
Vuelto: $27.50
────────────────────────────────────
      ¡Gracias por su compra!
          Vuelva pronto
      Tel: +54 11 1234-5678
```

---

## 💳 PLANTILLA 3: TARJETA CON CAE - RESUMIDO (Compacto con AFIP)

**Uso:** Para pagos con tarjeta, ticket compacto pero con datos fiscales

```
{{centerb: {{business}}}}
{{center: {{direccion}}}}
{{center: Ticket Nº {{ticket.numero}} - {{ticket.fecha_hora}}}}
{{hr}}
{{items}}
{{hr}}
{{rightb: TOTAL: {{totales.total}}}}
{{hr}}
{{left: Forma de pago: {{pago.modo}}}}
{{left: Cuotas: {{pago.cuotas}} × {{pago.monto_cuota}}}}
{{hr}}
{{centerb: COMPROBANTE ELECTRÓNICO AFIP}}
{{left: CAE: XXXXXXXXXXXXXXXX}}
{{left: Vencimiento: DD/MM/YYYY}}
{{hr}}
{{center: ¡Gracias por su compra!}}
```

**Vista previa:**
```
         PERFUMERIA SUSI
    Pte. Sarmiento 1695, Gerli
  Ticket Nº 123 - 2024-12-25 14:30
────────────────────────────────────
7791290786691 — Suavizante Felicia...
1 × $55.00                    $55.00
7790828104655 — Jabón en pan paq...
2 × $18.00                    $36.00
────────────────────────────────────
                      TOTAL: $91.00
────────────────────────────────────
Forma de pago: Tarjeta
Cuotas: 3 × $30.33
────────────────────────────────────
   COMPROBANTE ELECTRÓNICO AFIP
CAE: 74123456789012
Vencimiento: 02/01/2025
────────────────────────────────────
       ¡Gracias por su compra!
```

---

## 💳 PLANTILLA 4: TARJETA CON CAE - DETALLADO (Completo Fiscal)

**Uso:** Para pagos con tarjeta, máxima información fiscal y comercial

```
{{centerb: {{business}}}}
{{center: {{direccion}}}}
{{center: Sucursal {{sucursal}}}}
{{center: CUIT: 20-40937847-2}}
{{center: IVA Responsable: Consumidor Final}}
{{center: Inicio de Actividades: 01/01/2020}}
{{hr}}
{{centerb: FACTURA B}}
{{centerb: COMPROBANTE DE VENTA}}
{{center: Ticket Nº {{ticket.numero}}}}
{{center: Fecha: {{ticket.fecha_hora}}}}
{{hr}}
{{centerb: DETALLE DE PRODUCTOS}}
{{items}}
{{hr}}
{{centerb: RESUMEN}}
{{left: Subtotal (sin IVA):          {{totales.subtotal}}}}
{{left: Descuento aplicado:          {{totales.descuento}}}}
{{left: Interés por cuotas:          {{totales.interes}}}}
{{hr}}
{{leftb: TOTAL CON IVA:              {{totales.total}}}}
{{hr}}
{{centerb: FORMA DE PAGO}}
{{left: Método: {{pago.modo}}}}
{{left: Cantidad de cuotas: {{pago.cuotas}}}}
{{left: Importe por cuota: {{pago.monto_cuota}}}}
{{hr}}
{{centerb: COMPROBANTE AUTORIZADO}}
{{centerb: ADMINISTRACIÓN FEDERAL DE}}
{{centerb: INGRESOS PÚBLICOS - AFIP}}
{{hr}}
{{left: Nº Comprobante: XXXXX}}
{{left: CAE: XXXXXXXXXXXXXXXX}}
{{left: Fecha de Vto. CAE: DD/MM/YYYY}}
{{hr}}
{{center: ───────────────────────────────}}
{{center: DOCUMENTO NO VÁLIDO COMO FACTURA}}
{{center: ───────────────────────────────}}
{{hr}}
{{center: ¡Gracias por su compra!}}
{{center: Consultas: +54 11 1234-5678}}
{{center: Instagram: @perfumeriasu}}
{{center: Vuelva pronto}}
```

**Vista previa:**
```
         PERFUMERIA SUSI
    Pte. Sarmiento 1695, Gerli
        Sucursal Sarmiento
       CUIT: 20-40937847-2
IVA Responsable: Consumidor Final
  Inicio de Actividades: 01/01/2020
────────────────────────────────────
           FACTURA B
      COMPROBANTE DE VENTA
        Ticket Nº 123
    Fecha: 2024-12-25 14:30
────────────────────────────────────
     DETALLE DE PRODUCTOS
7791290786691 — Suavizante Felicia...
1 × $55.00                    $55.00
7790828104655 — Jabón en pan paq...
2 × $18.00                    $36.00
662425026821 — Tampones Tamaño M...
3 × $30.50                    $91.50
────────────────────────────────────
            RESUMEN
Subtotal (sin IVA):         $182.50
Descuento aplicado:          $10.00
Interés por cuotas:           $5.00
────────────────────────────────────
TOTAL CON IVA:              $177.50
────────────────────────────────────
        FORMA DE PAGO
Método: Tarjeta
Cantidad de cuotas: 6
Importe por cuota: $29.58
────────────────────────────────────
     COMPROBANTE AUTORIZADO
    ADMINISTRACIÓN FEDERAL DE
    INGRESOS PÚBLICOS - AFIP
────────────────────────────────────
Nº Comprobante: 00012
CAE: 74123456789012
Fecha de Vto. CAE: 02/01/2025
────────────────────────────────────
  ─────────────────────────────
  DOCUMENTO NO VÁLIDO COMO FACTURA
  ─────────────────────────────
────────────────────────────────────
      ¡Gracias por su compra!
   Consultas: +54 11 1234-5678
     Instagram: @perfumeriasu
          Vuelva pronto
```

---

## 📋 RESUMEN DE PLANTILLAS

| # | Nombre | Tipo | Extensión | Uso Principal |
|---|--------|------|-----------|---------------|
| 1 | Efectivo Resumido | Minimalista | ~15 líneas | Ventas rápidas efectivo |
| 2 | Efectivo Detallado | Completo | ~30 líneas | Ventas con desc/int efectivo |
| 3 | Tarjeta CAE Resumido | Compacto | ~18 líneas | Ventas rápidas tarjeta |
| 4 | Tarjeta CAE Detallado | Fiscal Completo | ~45 líneas | Ventas formales tarjeta |

---

## 🎨 CARACTERÍSTICAS DE DISEÑO

### Plantillas Resumidas (1 y 3):
- ✅ Solo información esencial
- ✅ Máximo 20 líneas
- ✅ Rápido de imprimir
- ✅ Ahorro de papel
- ✅ Ideal para volumen alto

### Plantillas Detalladas (2 y 4):
- ✅ Información completa
- ✅ Datos fiscales completos
- ✅ Información de contacto
- ✅ Mensajes personalizados
- ✅ Ideal para clientes que requieren comprobante formal

---

## 🔄 IMPLEMENTACIÓN TÉCNICA

Las plantillas se agregarán a `app_config.json` en:

```json
{
  "ticket": {
    "templates_predefined": {
      "efectivo_resumido": "...",
      "efectivo_detallado": "...",
      "tarjeta_resumido": "...",
      "tarjeta_detallado": "..."
    },
    "slot_names": {
      "slot1": "Efectivo Resumido",
      "slot2": "Efectivo Detallado",
      "slot3": "Tarjeta Resumido",
      "slot4": "Tarjeta Detallado"
    },
    "slots": {
      "slot1": "",
      "slot2": "",
      "slot3": "",
      "slot4": ""
    }
  }
}
```

---

## ✨ NOTAS IMPORTANTES

1. **Placeholders dinámicos**: Si un valor no existe (ej: descuento = 0), se muestra "-"
2. **Datos AFIP**: Los placeholders CAE se reemplazan automáticamente si existen en la venta
3. **Longitud de nombres**: Los nombres de productos se recortan automáticamente a 28 caracteres
4. **Separadores**: `{{hr}}` dibuja una línea horizontal completa
5. **Alineación**: `{{center:}}`, `{{right:}}`, `{{left:}}` controlan la alineación
6. **Negrita**: `{{centerb:}}`, `{{rightb:}}`, `{{leftb:}}` aplican negrita + alineación
