# Tu local 2025 — Guía maestra para retomar el proyecto

> **Versión actual:** 6.6.4
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

## 4. Estado actual (v6.6.4)

### Cambios recientes (changelog corto)

**v6.6.4 (último)** — Patch de performance + apply de tarjeta. (1) **Bug crítico**: `_apply_venta` skipeaba ventas con `numero_ticket=null` (caso v6.5.1 con tarjeta/CAE) → Salta nunca recibía esas ventas. Ahora usa `numero_ticket_cae` o `afip_numero_comprobante` como identidad fallback. (2) **Velocidad force_pull 10x**: thread session usa `PRAGMA synchronous=NORMAL` (commits ~1ms vs ~10ms), retry timeout reducido de 5×(3,6,12,24,48s)=93s → 3×(1,2,4s)=7s, progress callback cada 25 items. (3) Antes de force_pull, se commitea la sesión principal y se pausa el `_sync_timer` para liberar locks SQLite (la mitad del tiempo se perdía esperando que la BD se libere). (4) Cancelación de force_pull es ahora más rápida (chequea entre cada item, no solo entre páginas).

**v6.6.3** — Patch crítico post-v6.6.2. (1) **Dashboard merge key fix**: ventas con `numero_ticket=null` (publicadas por v6.5.1 con tarjeta/CAE) colisionaban en `?|sucursal` y solo aparecía 1 — ahora usa `K:fbKey` como fallback de identidad, así cada venta aparece independientemente. (2) Dashboard "Detalle de ventas" ahora muestra `Fecha / Hora` (DD/MM HH:MM) en lugar de solo HH:MM. (3) **Force pull con progress real**: QThread + QProgressDialog cancelable que muestra "Procesando productos pagina 4/30 (1500 aplicados)". (4) **Diagnose comparativo**: nuevo `diagnose_full()` cuenta filas locales (BD) y entradas Firebase (con `shallow=true`, gratis en cuota), muestra diff real local vs Firebase. (5) Audit log defensivo: providers usan `getattr` y `_ctx` loguea tipo de excepción una vez. (6) `cleanup.safe_window_days` default subido de 7 → 30 días para que el dashboard mantenga histórico.

**v6.6.2** — Patch crítico de sync. (1) Fix `diagnose_pending` que usaba `getattr(self, "last_processed_keys", {})` (atributo inexistente) → contaba todo como pendiente. Ahora usa el método real `_get_last_processed_keys()`. (2) **Skip-on-fail**: si un cambio de Firebase falla 3 veces seguidas en aplicarse, se avanza cursor y se registra en `sync_skipped.log` para inspección — antes el cursor quedaba atascado y nunca avanzaba. (3) Botón **"Forzar descarga completa desde Firebase"** que resetea `last_processed_keys` + fail counter y dispara `pull_changes()` desde cero. (4) Botón **"Ver items con error (skipeados)"** muestra el log de items skipeados. (5) Dashboard fix: ticket "#-" ya no aparece (renderiza `-` cuando no hay número), y el merge create+update prioriza `numero_ticket_cae` para ventas con tarjeta. (6) Audit log: formato cambiado de `[user@sucursal]` a `user=X suc=Y` (más legible).

**v6.6.1** — Patch de bugs reportados sobre v6.6.0. (1) Fix botón "Verificar pendientes": atributo equivocado en `sync_config.py` (`_sync_manager` → `_firebase_sync`). (2) Audit log ahora captura **F1-F12, Ctrl+letra/dígito y cambios de pestaña** (antes solo clicks de botón y diálogos), loguea `INIT file=...` al arrancar para confirmar la ruta. (3) Carpeta del log de auditoría configurable desde Configuración → General → Auditoría (botón "Cambiar..."). (4) Expuestas en UI: `sync.cleanup.{enabled, safe_window_days}` (pestaña Sincronización) y `ui.autocomplete_limit_productos/clientes` (pestaña General → Rendimiento de búsquedas).

**v6.6.0** — Auditoría de actividad (eventFilter global con retención configurable), single-instance (QSharedMemory + QLocalServer; popup + restore al lanzar 2da instancia), botón "Verificar pendientes" con diff Local↔Firebase, auto-cleanup de Firebase tras pull con `safe_window_days=7`, columna "Nº Comprobante" en Historial, dashboard espejo correcto: NCs descontadas + badge con hover, fix tickets de tarjeta `#-`, columna Nº Comprobante AFIP. Backup default `%APPDATA%/CompraventasV2/backups` con validación al arrancar.

**v6.5.2** — Bug fix reportes semanales (3 frecuencias paralelas DAILY/WEEKLY/MONTHLY con auto-migración), logging crítico en bloques except, build.bat con auto-versionado vía `sync_version_files.py`, GitHub Actions CI, `app/utils/format.py` para formato de moneda AR, `error_messages.py`, `confirm_dialogs.py`, `progress_helpers.py`, RotatingFileHandler centralizado, índice navegable en `configuracion_mixin.py`.

**v6.5.1** — Historial: filtro principal **CAE: Todas / Sin CAE / Con CAE** + subfiltro **Pago: Todos / Efectivo / Tarjeta**, ambos siempre visibles y combinados en AND.

**v6.5.0** — Fix RuntimeError `wrapped C/C++ object of type QTableWidgetItem has been deleted` al aplicar descuento. Columnas Total CAE / IVA Ventas / IVA Compras en Historial. Dashboard: cards CAE + pestaña Proveedores. `build.bat` preserva `installer_output/`.

### Estado de los instaladores

`installer_output/` contiene:
- `Tu.local.2025.v6.2.2.Setup.exe`
- `Tu.local.2025.v6.2.4.Setup.exe`
- `Tu.local.2025.v6.5.0.Setup.exe`
- `Tu.local.2025.v6.5.1.Setup.exe`
- `Tu.local.2025.v6.5.2.Setup.exe`
- `Tu.local.2025.v6.6.0.Setup.exe`
- `Tu.local.2025.v6.6.1.Setup.exe`
- `Tu.local.2025.v6.6.2.Setup.exe`
- `Tu.local.2025.v6.6.3.Setup.exe`
- **`Tu.local.2025.v6.6.4.Setup.exe`** ← actual

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
- **`backup.dir` (v6.6.0):** la ubicación de backup persiste en `app_config.json → backup.dir` y sobrevive a updates. Si la ruta queda inválida (USB desconectado, etc.) se cae al default `%APPDATA%\CompraventasV2\backups` con un warning en el log.
- **Auto-cleanup de Firebase (`sync.cleanup`, v6.6.0):** borra registros viejos del nodo `cambios/{tipo}/` en Firebase Realtime DB para no llenar la cuota gratuita. **NO afecta los productos/ventas/proveedores en SQLite local de ninguna sucursal.** Una vez que un cambio se replicó, el dato vive permanentemente en la base local; el registro en `cambios/` es solo un buzón de tránsito. El borrado solo procede si el cambio tiene más de `safe_window_days` (default 7), para dar margen a sucursales que estuvieron offline. Configurable desde Configuración → Sincronización (v6.6.1).
- **Audit log (`audit.log_dir`, v6.6.1):** ubicación del log de auditoría configurable desde UI. Si la carpeta no es escribible, cae al default `%APPDATA%\CompraventasV2\logs\activity.log`. Captura clicks, F1-F12, Ctrl+letra, cambios de pestaña, apertura/cierre de diálogos. **NO captura passwords ni texto de campos sensibles** (skip de QLineEdit con `echoMode=Password` o objectName "pass"/"clave"/"secret"/"token").

---

## 7. Para resumir el trabajo

Al retomar:

1. Leer este archivo completo.
2. Si necesitás detalle UX por pestaña → [SECCIONES.md](SECCIONES.md).
3. Si necesitás encontrar una función específica → [FUNCIONES.md](FUNCIONES.md).
4. Si vas a hacer un cambio estructural (mixin nuevo, migración, placeholder de ticket) → [DEVELOPMENT.md](DEVELOPMENT.md) sección 6 (guías).
5. `git log --oneline -20` para ver actividad reciente.
6. `python version.py` para confirmar versión.
