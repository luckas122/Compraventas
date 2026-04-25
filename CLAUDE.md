# Tu local 2025 — Guía maestra para retomar el proyecto

> **Versión actual:** 6.5.1
> **Stack:** Python 3.14 · PyQt5 · SQLAlchemy · SQLite · AfipSDK REST · Firebase REST · PyInstaller · Inno Setup 6
> **Repositorio raíz:** `C:\Users\Lucas\Desktop\aplicaciones\Compraventas`

Este documento es el **punto de entrada** para retomar el desarrollo. Para detalle, abrir:

- 📋 [SECCIONES.md](SECCIONES.md) — qué hace cada pestaña/sección desde el lado del usuario.
- 🧩 [FUNCIONES.md](FUNCIONES.md) — catálogo de funciones/métodos por archivo.
- 🛠️ [DEVELOPMENT.md](DEVELOPMENT.md) — guías de cambios comunes (sucursales, mixins, migraciones, placeholders, AFIP, build).

---

## 1. ¿Qué es la app?

**"Tu local 2025"** es un punto de venta de escritorio (Windows) para comercios con varias sucursales. Hace:

- **Catálogo de productos** con códigos de barras, búsqueda live, importación/exportación Excel.
- **Cesta de venta** con scanner, descuentos, cuotas, intereses, devoluciones.
- **Facturación electrónica AFIP** (Factura A/B/Mono, Notas de Crédito) vía AfipSDK REST con CAE + QR.
- **Tickets imprimibles** con plantillas (10 slots) y editor visual con autocompletado de placeholders.
- **Historial de ventas** filtrable por CAE/forma de pago/fecha/sucursal/texto + estadísticas.
- **Proveedores y pagos** (con flag IVA 21%).
- **Clientes** con datos fiscales (CUIT, condición AFIP).
- **Usuarios** con login + permisos admin.
- **Sincronización Firebase** bidireccional multi-sucursal (productos, ventas, proveedores, pagos a proveedores).
- **Backups** automáticos (daily/weekly) con restore.
- **Reportes por email** programados (daily/weekly/monthly).
- **Dashboard HTML** standalone con cards CAE, gestión de proveedores y precios.

---

## 2. Arquitectura en 30 segundos

```
main.py (login)
    ↓
MainWindow (core.py: 13 mixins)
    ↓
SQLAlchemy → SQLite (appcomprasventas.db)
    ↕
FirebaseSyncManager → Firebase Realtime DB (REST, sin SDK)
    ↕
AfipIntegration → AfipSDK REST API (CAE + QR)
    ↕
QPrinter → Tickets / Códigos de barras
```

**Patrón mixin:** `MainWindow` hereda de ~13 mixins, cada uno aporta una pestaña o capacidad transversal (productos, ventas, ventas-finalización, ventas-ticket, proveedores, compradores, usuarios, configuración, ticket-templates, reportes, backups, sync, stats).

**Datos:** todo persiste en SQLite local (`appcomprasventas.db`). Firebase es solo capa de sync entre PCs/sucursales (last-write-wins por timestamp).

**Config:** `app_config.json` en `%APPDATA%\CompraventasV2\` (separado del binario para sobrevivir actualizaciones).

---

## 3. Estructura de archivos esencial

```
Compraventas/
├── main.py                       # Entry point
├── version.py                    # __version__ = "6.5.1"
├── build.bat                     # Pipeline de build (Py + PyInstaller + Inno Setup)
├── build.spec                    # Config PyInstaller (auto-bundlea assets/)
├── installer.iss                 # Config Inno Setup 6
│
├── app/
│   ├── config.py                 # load(), save(), DEFAULTS, restore desde backup
│   ├── database.py               # init_db() + _run_migrations()
│   ├── models.py                 # 10 modelos SQLAlchemy
│   ├── repository.py             # UsuarioRepo, prod_repo, VentaRepo, PagoProveedorRepo, etc.
│   ├── afip_integration.py       # crear_factura(), nota_credito() vía AfipSDK
│   ├── firebase_sync.py          # FirebaseSyncManager (push/pull)
│   ├── alert_manager.py          # Alertas críticas por email
│   ├── email_helper.py           # SMTP wrapper
│   ├── login.py                  # LoginDialog, CreateAdminDialog
│   │
│   └── gui/
│       ├── common.py             # icon(), constantes UI
│       ├── dialogs.py            # PagoEfectivoDialog, PagoTarjetaDialog, PagoProveedorDialog,
│       │                         #   DevolucionDialog, ProductosDialog
│       ├── compradores.py        # CompradorService
│       ├── proveedores.py        # ProveedorService
│       ├── historialventas.py    # HistorialVentasWidget (filtros + tabla + stats)
│       ├── shortcuts.py          # ShortcutManager (atajos globales/por sección)
│       ├── smart_template_editor.py  # Editor de plantillas con autocompletado
│       ├── ventas_helpers.py     # build_product_completer(), imprimir_ticket()
│       │
│       └── main_window/
│           ├── core.py           # class MainWindow(*mixins, QMainWindow)
│           ├── productos.py      # ProductosMixin → tab Productos
│           ├── ventas.py         # VentasMixin → tab Ventas
│           ├── ventas_finalizacion_mixin.py  # Flujo finalizar venta + AFIP
│           ├── ventas_ticket_mixin.py        # Render e impresión de ticket
│           ├── proveedores_mixin.py
│           ├── compradores_mixin.py
│           ├── usuarios_mixin.py
│           ├── configuracion_mixin.py
│           ├── ticket_templates_mixin.py
│           ├── reportes_mixin.py
│           ├── backups_mixin.py
│           ├── sync_mixin.py     # Bandeja, sync UI, sonidos (_beep_ok)
│           ├── stats_mixin.py    # Estadísticas
│           └── filters.py        # LimitedFilterProxy
│
├── assets/                       # Iconos .ico, sounds/pip.wav, fuentes
├── icons/                        # SVGs por tab
├── dashboard/                    # Dashboard HTML standalone (SPA)
├── installer_output/             # Salida de Inno Setup (NO se borra entre builds)
└── dist/                         # Salida de PyInstaller (se regenera)
```

---

## 4. Estado actual (v6.5.1)

### Cambios recientes (changelog corto)

**v6.5.1 (último)** — Historial: filtro principal **CAE: Todas / Sin CAE / Con CAE** + subfiltro **Pago: Todos / Efectivo / Tarjeta**, ambos siempre visibles y combinados en AND. Reemplaza el viejo combo `Forma:` que confundía comprobante fiscal con medio de pago. Aplica también al tab Estadísticas.

**v6.5.0** — Fix RuntimeError `wrapped C/C++ object of type QTableWidgetItem has been deleted` al aplicar descuento (causa: `setItem` en handler de `itemChanged` destruía el item en uso). Solucionado con flag `_cesta_updating` + `QSignalBlocker`. Agregadas columnas Total CAE / IVA Ventas / IVA Compras al label resumen del Historial. Notas de Crédito se restan correctamente. Nueva columna `incluye_iva` en `PagoProveedor` con migración + checkbox en diálogo. Dashboard: cards CAE (monto + cantidad con sub-totales Efectivo/Tarjeta) + nueva pestaña Proveedores con form para registrar pagos y replicarlos a la app vía Firebase. `build.bat`: ya no borra `installer_output/`, preserva versiones anteriores.

**v6.2.4** — Fix dummy de descuento (precursor del v6.5.0).

### Estado de los instaladores

`installer_output/` contiene:
- `Tu.local.2025.v6.2.2.Setup.exe`
- `Tu.local.2025.v6.2.4.Setup.exe`
- `Tu.local.2025.v6.5.0.Setup.exe`
- **`Tu.local.2025.v6.5.1.Setup.exe`** ← actual

---

## 5. Flujos críticos a entender

### 5.1 Venta + AFIP + Ticket

1. Usuario escanea/busca producto → `VentasMixin.agregar_a_cesta()` (en `ventas.py`).
2. Cesta editable: cantidad/precio (doble clic). Recálculo en `actualizar_total()` con `QSignalBlocker` + flag `_cesta_updating` para evitar el bug del descuento (ver v6.5.0).
3. Click "Finalizar" → `VentasFinalizacionMixin` abre `PagoEfectivoDialog` o `PagoTarjetaDialog`.
4. Si el diálogo pide AFIP (Factura A/B/Mono/NC), `afip_integration.crear_factura()` llama a AfipSDK REST → devuelve CAE + Nº comprobante.
5. Se persiste `Venta` + `VentaItem`s + datos AFIP en SQLite.
6. `VentasTicketMixin` renderiza el ticket con `imprimir_ticket()` (en `ventas_helpers.py`): elige plantilla (slot1..slot10) según método de pago + tipo de comprobante, sustituye placeholders (`{{totales.total}}`, `{{cae}}`, `{{qrcae}}`, `{{img:logo}}`, etc.), dibuja en QPainter oversized, recorta y manda a QPrinter.
7. `_sync_push("venta", ...)` empuja a Firebase para que otras sucursales/dashboard lo vean.

### 5.2 Sincronización Firebase

- `FirebaseSyncManager` (en `firebase_sync.py`) hace push y pull cada `sync.interval_minutes` (default ~2-5 min).
- Tipos sincronizados: `productos`, `ventas`, `proveedores`, **`pagos_proveedores`** (agregado en v6.5.0).
- Anti-eco: cada cambio lleva `sucursal_origen`. Al hacer pull, si `sucursal_origen == self.sucursal_local`, se descarta.
- Resolución de conflictos: last-write-wins por `timestamp`.

### 5.3 Historial — resumen al pie

Label `lbl_resumen` en `historialventas.py` muestra (sobre la lista filtrada):
```
N ventas — Efectivo $X — Tarjeta $Y — Total $Z — Total CAE $C — IVA Ventas $IV — IVA Compras $IC
```
- **Notas de Crédito** se restan de Efectivo/Tarjeta/Total/Total CAE (v6.5.0).
- **IVA Ventas:** `total_cae * 21/121`.
- **IVA Compras:** `monto * 21/121` solo sobre `PagoProveedor.incluye_iva == True`.

### 5.4 Build pipeline

```bash
build.bat
```
Pasos: venv → reset config → instalar deps → limpiar `build/` y `dist/` (no `installer_output/`) → leer `version.py` → PyInstaller (`build.spec`) → Inno Setup (`installer.iss`) → `installer_output/Tu.local.2025.vX.Y.Z.Setup.exe`.

Runner alternativo (PowerShell con redirects para que no quede colgado): `C:\tmp\run_build.ps1`.

---

## 6. Convenciones y gotchas

- **Versión:** SemVer 3 dígitos. Bumpear `version.py`, `installer.iss` y `version_info.txt` juntos.
- **Migraciones:** siempre por `PRAGMA table_info` en `_run_migrations()` de `database.py`. Idempotentes (chequear antes de `ALTER`).
- **Mixins:** un mixin por pestaña; el método `tab_<nombre>()` retorna el `QWidget`. Registro en `core.py` (herencia + `addTab`).
- **PyQt5 + tablas:** **nunca** hacer `setItem` desde un handler de `itemChanged` (destruye el QTableWidgetItem y deja referencias Python wrapping objetos C++ muertos → `RuntimeError`). Usar `setText` sobre el item existente, o `QSignalBlocker` + flag para updates programáticos.
- **Firebase anti-eco:** todo push lleva `sucursal_origen`. Todo pull descarta si origen == local.
- **`installer_output/`:** **no borrar** al rebuild. Solo borrar el `.exe` de la versión actual antes de recompilar (idempotencia).
- **Config separada:** `%APPDATA%\CompraventasV2\app_config.json` no se toca en updates. La app pregunta al iniciar si hay un backup pendiente.

---

## 7. Para resumir el trabajo

Al retomar:

1. Leer este archivo completo.
2. Si necesitás detalle UX por pestaña → [SECCIONES.md](SECCIONES.md).
3. Si necesitás encontrar una función específica → [FUNCIONES.md](FUNCIONES.md).
4. Si vas a hacer un cambio estructural (mixin nuevo, migración, placeholder de ticket) → [DEVELOPMENT.md](DEVELOPMENT.md) sección 6 (guías).
5. `git log --oneline -20` para ver actividad reciente.
6. `python version.py` para confirmar versión.
