# README.md

# Compraventas V2

**Release Candidate 1 — 2025-10-16**  
Sistema de punto de venta con gestión de productos, ventas, devoluciones, reportes automáticos y copias de seguridad programadas.

---

## 🧭 Visión general
Compraventas V2 es una aplicación de escritorio (Qt + Python) pensada para locales minoristas. Permite cargar y vender productos con lector de código de barras, imprimir tickets, gestionar devoluciones, programar reportes por correo y realizar/restaurar backups de la base de datos con retención automática.

---

## ✨ Características clave
- **Ventas rápidas** con escaneo, descuentos por ítem y globales, interés opcional y cálculo de vuelto.
- **Devoluciones** seguras por número de ticket (control de sucursal par/impar), con mensaje claro de caja: *“Se debe regresar = Total anterior − Total actual”*.
- **Impresión de tickets** con plantilla configurable (QPrinter) y vista previa.
- **Productos**: alta/edición, búsqueda en vivo, importación desde Excel/CSV, exportación, edición masiva y generación/impresión de códigos de barras.
- **Proveedores**: CRUD básico (nombre, teléfono, cuenta/CBU).
- **Usuarios**: login con rol, gestión de usuarios y flag de **admin**.
- **Historial** de ventas: filtros por fecha y modo de pago, exportación a Excel.
- **Reportes & Envíos** por email con programación independiente (diario/semanal/mensual) y configuración SMTP.
- **Backups**: pestaña dedicada con activación, carpeta destino, selección de **días** y **múltiples horarios** (mín. 2), **backup manual**, **restaurar** desde ZIP y **retención** de N días.
- **Tema oscuro** y variantes, aplicados **al instante**.
- **UI responsiva**: todas las pestañas de Configuración con `QScrollArea`.

---

## 👤 Roles y permisos

### Operador (Usuario)
- **Ventas**: alta/edición de ítems, descuentos/interés, cobro, impresión de ticket.
- **Devoluciones**: ejecutar (si el admin lo permite) con recálculo y mensaje *“Se debe regresar …”*.
- **Historial**: consulta/exportación.
- **Interfaz**: cambio de modo oscuro y variantes.
- **Backups**: *Hacer backup ahora* y *Restaurar* (opcional según permisos locales).

### Administrador
- Todo lo anterior, más:
- **Usuarios**: alta/edición/baja, cambio de contraseña y marcar como admin.
- **Productos**: importación/exportación, edición masiva, códigos de barras.
- **Reportes & Envíos**: programación de correos (guardar → rearma scheduler al instante), SMTP.
- **Backups**: activar/desactivar, elegir carpeta, **días** y **horarios** (múltiples), retención (p. ej., 15 días), *Backup ahora* y *Restaurar* con backup previo *pre-restore*.
- **Seguridad**: gateo por `_ensure_admin` y validación de numeración de tickets por sucursal (par/impar).

---

## ⚙️ Configuración esencial

### Ubicación de datos recomendada (Windows)
Para sobrevivir reinstalaciones/actualizaciones:
- Config: `%APPDATA%/CompraventasV2/app_config.json`
- Base de datos: `%APPDATA%/CompraventasV2/data.db`
- Backups: `%APPDATA%/CompraventasV2/backups/`

> La aplicación crea por defecto la carpeta de backups si no existe.

### Backups (pestaña **Backups**)
1. **Activar automáticos** y elegir **carpeta destino**.
2. Elegir **días** (L–D) y **al menos 2 horarios**.
3. Definir **retención** (p. ej., 15 días) → la limpieza elimina ZIPs más antiguos.
4. Guardar programación → el scheduler muestra en consola el **próximo disparo**.
5. *Hacer backup ahora* para generar un ZIP inmediato.
6. *Restaurar desde backup*: realiza *pre-restore*, restaura la DB desde ZIP y solicita reinicio de la app.

> Si existe el esquema nuevo (`days` + `times`), el scheduler **ignora** campos legacy (`daily_times`/`weekly`).

### Reportes & Envíos
- Definir **frecuencia** (diaria/semanal/mensual) y **horarios**.
- Configurar **SMTP** (host, puerto, TLS/SSL, usuario/clave) y **destinatarios**.
- **Guardar programación** rearma el scheduler inmediatamente (independiente de *Aplicar cambios* global).

### Tema, impresoras y plantilla
- *Configuración → General*: modo oscuro y variantes (aplican al instante), impresoras (ticket/A4), plantilla de ticket, tz, etc.

---

## 🧪 Notas de uso y soporte
- **Devoluciones**: el cálculo de caja muestra *Total anterior* vs *Total actual* y asienta `vuelto` cuando corresponde.
- **Trazas**: el scheduler de Backups imprime *Próximo (…)*, ejecución y limpieza.
- **Reinicio tras restaurar**: en desarrollo puede requerir relanzar manualmente; en empaquetado `.exe` se relanza automáticamente.

---

## 📦 Empaquetado y actualizaciones (resumen)

### Empaquetar a `.exe`
- Usar **PyInstaller** y añadir plugins Qt (`platforms`, `printsupport`, `imageformats`) e icono.
- Instalar binarios en `Program Files/CompraventasV2` y **no** tocar `%APPDATA%`.

### Actualizaciones sin reinstalar manualmente
- Flujo simple asistido: la app consulta última versión, descarga el instalador y lo lanza en modo silencioso; los datos en `%APPDATA%` **no** se tocan.
- Mantener versionado semántico, migraciones de DB cuando cambie el esquema y defaults robustos de config.

---

## 🛡️ Requisitos (mínimos sugeridos)
- Windows 10/11
- Python 3.10+ (solo en desarrollo)
- Impresora compatible para tickets (opcional)

---

## 📄 Licencia
Indica aquí la licencia de tu proyecto (por ejemplo, MIT) o una nota de uso interno.

---

## 🙌 Créditos
Equipo de desarrollo de **Compraventas V2**.



---

# CHANGELOG.md

# Compraventas V2 — Changelog

## 2.0.0-rc1 — 2025-10-16

### Añadido
- **Backups (pestaña dedicada)**
  - Activar/desactivar, **carpeta destino** y **retención** (p. ej., diarios 15 días).
  - Selección de **días** (L–D) y **múltiples horarios** (mín. 2).
  - **Hacer backup ahora** y **Restaurar** desde ZIP (con *pre-restore*).
- **Scheduler de Backups** renovado
  - Prioridad a `backup.days` + `backup.times`.
  - Ignora `daily_times/weekly` si existe el esquema nuevo.
  - Logs claros en consola: próximo disparo, ejecución, limpieza.
- **Scheduler de Reportes** independiente (programación y SMTP desde UI).
- **Tema oscuro** y **variante** aplicados **al instante**.
- **Botón “Guardar programación” (Reportes)** rearmando scheduler sin *Aplicar cambios* global.

### Corregido
- **Devoluciones**: cálculo y aviso de caja → *Se debe regresar = Total anterior − Total actual*.
- **Scroll** en Configuración (Reportes & Envíos y Ticket) mediante `QScrollArea`.
- **Persistencia** de retención y carpeta de backups centralizada en Backups.
- Eliminados **horarios legacy** fantasma al limpiar/ignorar en presencia de `days+times`.

### Mejorado
- Re-armado de schedulers al guardar (desde pestaña o botón global).
- Trazas en consola más útiles (programación, ejecución, limpieza, errores).

### Existente (resumen de capacidades previas)
- **Ventas** con escaneo, descuentos por ítem/global, interés y cálculo de vuelto; impresión de ticket.
- **Productos**: CRUD, búsqueda en vivo, import/export Excel/CSV, edición masiva, códigos de barras y etiquetas.
- **Proveedores**: CRUD básico.
- **Usuarios**: login/roles, gestión, flag admin.
- **Historial**: filtros y exportación a Excel.
- **Validaciones**: numeración por sucursal (par/impar), gateo por `_ensure_admin`.

---

> Para cambios menores posteriores a RC1, registrar aquí con **Added/Changed/Fixed/Removed** y fecha.

