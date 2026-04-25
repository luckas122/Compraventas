# Tu local 2025 — Detalle por sección

> Documento de referencia funcional: qué hace cada pestaña / pantalla desde el lado del usuario.
> Versión: **6.5.1** · Complemento de [CLAUDE.md](CLAUDE.md) y [FUNCIONES.md](FUNCIONES.md).

Orden de tabs en la ventana principal (definido en `app/gui/main_window/core.py`):

| Índice | Tab | Mixin / Widget |
|---|---|---|
| 0 | Productos | `ProductosMixin` |
| 1 | Proveedores | `ProveedoresMixin` |
| 2 | Clientes | `CompradoresMixin` |
| 3 | Ventas | `VentasMixin` (+ `VentasFinalizacionMixin`, `VentasTicketMixin`) |
| dinámico | Historial | `HistorialVentasWidget` (incluye sub-tab Estadísticas) |
| dinámico | Configuración | `ConfiguracionMixin` |
| dinámico | Usuarios | `UsuariosMixin` (solo admin) |

---

## 1. Productos

**Archivo:** `app/gui/main_window/productos.py` (`ProductosMixin`).

Pestaña central de gestión de catálogo. Pensada para alta velocidad de carga y edición masiva.

**Formulario superior:**
- Código de Barra · Nombre · Precio · Categoría (opcional).
- Todo se fuerza a MAYÚSCULAS al guardar.
- Enter encadena entre campos.

**Búsqueda:**
- `QLineEdit` con debounce 250 ms.
- Acepta múltiples términos separados por coma/espacio (busca contra código, nombre, categoría, precio).
- Autocompletado mientras se tipea: sugiere `"CÓDIGO - NOMBRE"` (limitado a 50 entradas vía `LimitedFilterProxy` para evitar lag).

**Tabla:**
- Columnas: Sel (checkbox) · ID · Código · Nombre · Precio · Categoría.
- La selección persiste entre búsquedas (`_selected_product_ids`).

**Acciones:**
- Agregar / Actualizar (con validación de campos obligatorios).
- Eliminar seleccionados (confirmación).
- **Editar masivamente** (precio, nombre, categoría) sobre los seleccionados.
- **Importar Excel** (.xlsx) con detección de columnas.
- **Exportar Excel** del listado actual.
- **Imprimir códigos de barras** (con vista previa, usa la impresora configurada en `printers.barcode_printer`).
- **Ver últimos cambios masivos** (log interno por sesión: `_product_change_log`).
- **Detectar productos sin ventas en 90 días** (auditoría de movimiento).

**Sincronización:** cada cambio empuja a Firebase vía `_sync_push("producto", ...)`.

---

## 2. Proveedores

**Archivos:** `app/gui/main_window/proveedores_mixin.py` · `app/gui/proveedores.py` (`ProveedorService`).

CRUD simple de proveedores + pagos.

**Formulario:** Nombre · Teléfono · Número de Cuenta (banco) · CBU.
**Tabla:** Sel · ID · Nombre · Teléfono · Cuenta · CBU. Doble clic carga la fila en el formulario.

**Acciones:**
- Crear / Actualizar / Eliminar (con confirmación).
- **Pagos a Proveedor** (botón en Ventas o desde el dashboard) → abre `PagoProveedorDialog`:
  - Proveedor (selector o nuevo) · Monto · Método de pago (Efectivo / Tarjeta / Transferencia) · Pago de caja (checkbox) · Nota.
  - **Checkbox "Incluye IVA (21%)"** (v6.5.0): marca el pago como con IVA discriminado para que se sume al cálculo de IVA Compras del Historial.

**Sincronización:** push a Firebase tanto del proveedor como del pago.

---

## 3. Clientes (Compradores)

**Archivos:** `app/gui/main_window/compradores_mixin.py` · `app/gui/compradores.py` (`CompradorService`).

Datos fiscales para emisión de comprobantes AFIP.

**Formulario:** CUIT (11 dígitos, obligatorio) · Nombre · Domicilio · Localidad · Código Postal · **Condición Fiscal** (5 opciones: vacío, Responsable Inscripto, Monotributista, Consumidor Final, Exento).

**Tabla:** Sel · ID · CUIT · Nombre · Domicilio · Localidad · Cód.Postal · Condición. Doble clic carga.

**Acciones:** Crear / Actualizar / Eliminar.

**Validaciones:** CUIT debe tener exactamente 11 dígitos (validación en UI).

**Uso:** al emitir Factura A o B se selecciona el cliente; sus datos se inyectan al payload AFIP y al ticket.

---

## 4. Ventas

**Archivos:** `app/gui/main_window/ventas.py` (UI) · `ventas_finalizacion_mixin.py` (flujo finalizar) · `ventas_ticket_mixin.py` (render ticket).

Pestaña operativa principal. Construida para uso intensivo con scanner.

### 4.1 Búsqueda y cesta

- `QLineEdit` con `QCompleter` (50 ítems) — busca por código o nombre.
- **Detección scanner vs tipeo:** timer 300 ms; si entra un Enter rápido se interpreta como scan y auto-agrega.
- **Cesta** (`table_cesta`): Código · Nombre · Cantidad · Precio Unit · Total. Doble clic en Cantidad o Precio para editar.
- **Descuentos por fila:** botones `%` y `$` aplican descuento sobre la línea (texto queda como `"80.00 → 64.00"`).
- **Borradores:** botón "Guardar" persiste la cesta como `VentaBorrador` para retomar luego; "Cargar borrador" la recupera.
- Botón "Vaciar cesta" + atajo.

### 4.2 Pago

Click "Finalizar" → abre dialogo según método elegido:

**`PagoEfectivoDialog`** (`app/gui/dialogs.py`):
- Monto abonado, vuelto calculado.
- Descuento global (% o fijo).
- Selector de tipo de comprobante AFIP: Ticket no fiscal · Factura A · Factura B · Factura B Mono · Nota de Crédito A/B.
- Si elige Factura A/B → datos del comprador (Cargar por CUIT desde la BD local).

**`PagoTarjetaDialog`**:
- Cuotas (1–12).
- Interés (% configurable).
- Mismo selector de comprobante.

### 4.3 Finalización

`VentasFinalizacionMixin.finalizar_venta()`:
1. Recalcula totales finales (con descuentos e intereses).
2. Si comprobante fiscal → llama `afip_integration.crear_factura()` (AfipSDK REST). Si AFIP devuelve error, ofrece reintentar o cancelar.
3. Guarda `Venta` + `VentaItem`s en SQLite.
4. Empuja a Firebase con `_sync_push("venta", ...)`.
5. Renderiza e imprime ticket (ver 4.4).
6. Limpia cesta y prepara nueva venta.

### 4.4 Ticket

`VentasTicketMixin` + `ventas_helpers.imprimir_ticket()`:
- Selecciona plantilla (slot1..slot10) según `template_<modo>_<comprobante>` o fallback `template_<modo>` o slot1.
- Sustituye placeholders (ver `DEVELOPMENT.md` §6.4 para lista completa).
- Dibuja en `QPainter` oversized (3× alto estimado) → escanea de abajo hacia arriba para encontrar el último píxel no-blanco → recorta con margen de 8 mm.
- Manda a la impresora configurada (`printers.ticket_printer`) o muestra preview.
- Opcional: enviar por WhatsApp Web (link con número del cliente).

### 4.5 Devoluciones / Notas de Crédito

`DevolucionDialog` permite:
- Buscar venta por Nº ticket.
- Marcar items a devolver.
- Emitir Nota de Crédito (A o B según factura original) vía AFIP.
- La NC queda asociada a la venta original (campo `nota_credito_cae`); el Historial la resta del total.

---

## 5. Historial de ventas

**Archivo:** `app/gui/historialventas.py` (`HistorialVentasWidget`).

Pestaña con dos sub-tabs.

### 5.1 Tab "Listado"

**Barra de filtros:**
- Desde · Hasta (`QDateEdit`).
- Sucursal (combo dinámico desde `business.sucursales`).
- **CAE: Todas / Sin CAE / Con CAE** (v6.5.1) — filtra por presencia de `afip_cae`.
- **Pago: Todos / Efectivo / Tarjeta** (v6.5.1) — filtra por `modo_pago`.
- Búsqueda libre (Nº ticket o texto).
- Botones rápidos: Hoy · Esta Semana · Este Mes · Mes Anterior.

Los filtros se combinan en AND. Los dos combos CAE/Pago siempre visibles. Re-filtrado en vivo (refrescar al cambiar cualquier filtro).

**Tabla:** 15 columnas — Nº Ticket · Fecha/Hora · Sucursal · Forma Pago · Cuotas · Interés · Descuento · Monto x cuota · Total · Pagado · Vuelto · CAE · Vto CAE · Comentario · ID (oculta).

Doble clic en fila → diálogo con detalle de items.

**Resumen al pie** (`lbl_resumen`):
```
N ventas — Efectivo $X — Tarjeta $Y — Total $Z — Total CAE $C — IVA Ventas $IV — IVA Compras $IC
```
- Notas de Crédito restadas de Efectivo/Tarjeta/Total/Total CAE.
- IVA Ventas: `total_cae * 21/121`.
- IVA Compras: pagos a proveedor con `incluye_iva = True`, calculado `monto * 21/121`.

**Exportación:** botón "Exportar Excel" genera `.xlsx` con autoajuste de columnas (engine openpyxl con fallback a xlsxwriter).

### 5.2 Tab "Estadísticas"

Mismos filtros del Listado se aplican.

- **KPI cards:** Total · Cantidad · Promedio · Interés.
- **Gráfico de barras:** ventas por día (matplotlib embebido).
- **Gráfico de torta:** distribución Efectivo vs Tarjeta.
- **Top productos:** ranking por monto.
- **Comparativa entre sucursales:** dos sub-gráficos (Total por sucursal, Cantidad por sucursal). Solo visible si Sucursal=Todas.

---

## 6. Configuración

**Archivo:** `app/gui/main_window/configuracion_mixin.py`.

Pestaña con sub-tabs:

### General
- **Modo noche:** suave / medio / negro.
- Fuente de la app: Roboto / Segoe UI / Arial / Tahoma. Tamaño: 10/12/14 pt.
- Color de hover de botones (color picker).
- Zona horaria (default `America/Argentina/Buenos_Aires`).
- Sucursal por defecto al iniciar.

### Impresoras
- Impresora de tickets (térmica o PDF).
- Impresora de códigos de barras (separada).

### Tickets
- 10 slots de plantilla con nombres editables.
- 9 asignaciones fijas:
  - `template_efectivo`, `template_tarjeta`
  - `template_efectivo_factura_a/b/b_mono`
  - `template_tarjeta_factura_a/b/b_mono`
  - `template_nota_credito_a/b`
- Asignaciones personalizadas (`custom_assignments`).
- Editor visual `SmartTemplateEditor`:
  - Autocompletado al escribir `{{` (50+ placeholders).
  - Syntax highlighting (verde=válido, rojo=inválido, azul=formato).
  - Toolbar con bloques pre-armados.
  - Preview en tiempo real (`QPrintPreview`).

### Scanner
- Puerto serial · baud rate · timeout (si aplica al hardware del local).

### AFIP
- CUIT del comercio · ambiente test/prod · CUITs por sucursal · puntos de venta por sucursal · API key AfipSDK.

### Backups
- Habilitar / deshabilitar.
- `daily_times`: lista de horarios diarios.
- `weekly`: día (1–7 ISO) + hora.
- Retención y compresión.
- Botón "Hacer backup ahora" + selector "Restaurar desde ZIP".

### Sincronización Firebase
- URL · token · intervalo en minutos.
- Botón "Sincronizar ahora".

### Reportes
- Programar envío automático del Historial por email (DAILY / WEEKLY / MONTHLY) a hora fija.
- Destinatarios.
- Botón "Enviar reporte ahora".

### Alertas
- SMTP server · puerto · usuario · contraseña.
- Habilitar alertas críticas (errores de AFIP, sync, backups).
- Botón "Enviar email de prueba".

### Atajos
- Editor para los `shortcuts` (globales y por sección). Ver `app/gui/shortcuts.py`.

---

## 7. Usuarios

**Archivo:** `app/gui/main_window/usuarios_mixin.py` (solo accesible para admin).

CRUD de usuarios:
- Username · Password (mostrada como puntos) · Admin (checkbox).
- Validación: username único, password obligatoria al crear.
- Tabla: ID · Usuario · Admin (Sí/No). Click carga la fila.

Login al iniciar la app: `app/login.py` (`LoginDialog`). Si no hay usuarios → `CreateAdminDialog` para crear el primer admin.

Permisos: acciones sensibles (eliminar, editar masivo, restaurar backup) llaman `MainWindow._ensure_admin(reason)` que pide la contraseña de admin antes de proceder.

---

## 8. Reportes

**Archivo:** `app/gui/main_window/reportes_mixin.py`.

Programador de envíos automáticos (timer de 60 s):

- **DAILY:** todos los días a HH:MM.
- **WEEKLY:** día específico (1–7 ISO) + HH:MM.
- **MONTHLY:** día del mes (1–31, o último si None) + HH:MM.

Cada disparo genera un Excel del Historial con los filtros configurados y lo manda por SMTP a los destinatarios (`SmtpWorker` en thread separado).

---

## 9. Backups

**Archivo:** `app/gui/main_window/backups_mixin.py`.

- **Automáticos:** thread background con `_stop_backup_evt`. Lee `backup.daily_times` + `backup.weekly`.
- **Manual:** botón "Hacer backup ahora".
- **Formato:** ZIP con `appcomprasventas.db` + dump de schema + `app_config.json`.
- **Retención:** elimina backups más viejos que el límite configurado.
- **Restore:** diálogo para seleccionar ZIP, verifica integridad, reemplaza la BD actual (con confirmación + bloqueo previo de la sesión SQLAlchemy).

---

## 10. Sincronización Firebase

**Archivos:** `app/firebase_sync.py` (`FirebaseSyncManager`) · `app/gui/main_window/sync_mixin.py` (UI/bandeja).

- Bidireccional (push + pull) cada `sync.interval_minutes`.
- Tipos sincronizados: **productos · ventas · proveedores · pagos_proveedores** (último agregado en v6.5.0).
- Anti-eco: cada cambio lleva `sucursal_origen`; al pull se descarta si origen == sucursal local.
- **Bandeja del sistema:** ícono opcional con menú (Mostrar · Hacer backup ahora · Salir).
- **Sonido `pip.wav`:** se reproduce al agregar producto a cesta exitosamente (`_beep_ok()` en `sync_mixin.py`, asset en `assets/sounds/pip.wav`).

---

## 11. Dashboard HTML (standalone)

**Archivo:** `dashboard/dashboard.html`.

SPA web (HTML/CSS/JS puro, sin frameworks pesados) que se sirve estática (Firebase Hosting o local).

### Tab Ventas (Resumen)
- Cards principales: Monto Total · Cantidad de Ventas (con sub-totales Efectivo/Tarjeta).
- **Cards CAE (v6.5.0):**
  - **Monto Ventas con CAE** (verde) + sub `Efectivo $X · Tarjeta $Y`.
  - **Cantidad Ventas con CAE** (azul) + sub `Efectivo · Tarjeta`.
- Filtros por sucursal y fecha.
- Excluye automáticamente ventas anuladas por NC.

### Tab Precios
- Tabla con Código · Nombre · Precio actual · Variación % · Último cambio.
- Búsqueda en vivo.
- Edición desde el dashboard que se sincroniza con la app vía Firebase.

### Tab Proveedores (v6.5.0)
- Formulario para registrar pagos: Proveedor (dropdown + opción "Otro") · Monto · Método · Pago de caja · Nota · **Incluye IVA (21%)**.
- POST a `cambios/pagos_proveedores` con la misma forma que la app local.
- Tabla con últimos N pagos (filtrados por sucursal/fecha).
- La app local hace pull cada `sync.interval_minutes` y lo replica en su BD.

---

## 12. Atajos de teclado

**Archivo:** `app/gui/shortcuts.py` (`ShortcutManager`). Configurables en `app_config.json → shortcuts`.

**Globales (default):**
- F1 → Productos · F2 → Proveedores · F3 → Ventas · F4 → Clientes · F5 → Historial · F6 → Configuración.
- F7 → Nueva venta.

**Por sección:** cada pestaña define sus propios atajos en `shortcuts.section.<nombre>` (ej: en Ventas, `A`=agregar, `E`=editar cantidad, etc.).
