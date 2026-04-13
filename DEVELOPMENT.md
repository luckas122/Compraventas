# Tu Local 2025 — Guía de Desarrollo

> Documentación técnica para mantener y extender la aplicación.
> Versión actual: **6.0.0** | Python 3.14 + PyQt5 + SQLAlchemy + SQLite

---

## Índice

1. [Arquitectura General](#1-arquitectura-general)
2. [Estructura de Archivos](#2-estructura-de-archivos)
3. [Patrón Mixin (MainWindow)](#3-patrón-mixin-mainwindow)
4. [Base de Datos y Migraciones](#4-base-de-datos-y-migraciones)
5. [Sistema de Configuración](#5-sistema-de-configuración)
6. [Guías de Cambios Comunes](#6-guías-de-cambios-comunes)
   - 6.1 [Agregar una sucursal](#61-agregar-una-sucursal)
   - 6.2 [Agregar una pestaña/mixin](#62-agregar-una-pestañamixin)
   - 6.3 [Agregar un modelo de BD + migración](#63-agregar-un-modelo-de-bd--migración)
   - 6.4 [Agregar un placeholder de ticket](#64-agregar-un-placeholder-de-ticket)
   - 6.5 [Modificar diálogos de pago](#65-modificar-diálogos-de-pago)
   - 6.6 [Agregar un atajo de teclado](#66-agregar-un-atajo-de-teclado)
7. [Facturación AFIP](#7-facturación-afip)
8. [Sincronización Firebase](#8-sincronización-firebase)
9. [Sistema de Tickets](#9-sistema-de-tickets)
10. [Build y Deploy](#10-build-y-deploy)
11. [Versionado](#11-versionado)

---

## 1. Arquitectura General

```
Usuario → main.py (login) → MainWindow (12 mixins) → SQLite local
                                    ↕                      ↕
                              app_config.json         Firebase (sync)
                                                         ↕
                                                    AfipSDK REST API
```

**Stack:**
- **Frontend:** PyQt5 (widgets, diálogos, temas)
- **ORM:** SQLAlchemy + SQLite (`appcomprasventas.db`)
- **Config:** JSON (`app_config.json`) en `%APPDATA%\CompraventasV2\`
- **AFIP:** AfipSDK REST API (facturación electrónica)
- **Sync:** Firebase Realtime Database (REST, sin SDK)
- **Build:** PyInstaller (`.exe`) + Inno Setup 6 (`.Setup.exe`)

---

## 2. Estructura de Archivos

```
Compraventas/
├── main.py                     # Entry point: login, init DB, crea MainWindow
├── version.py                  # __version__ y __app_name__
├── build.bat                   # Pipeline de build automatizado
├── build.spec                  # Config PyInstaller
├── installer.iss               # Config Inno Setup 6
│
├── app/
│   ├── __main__.py
│   ├── config.py               # load(), save(), DEFAULTS, merge, backup/restore
│   ├── database.py             # Engine, SessionLocal, init_db(), _run_migrations()
│   ├── models.py               # 10 modelos SQLAlchemy (Usuario, Producto, Venta, etc.)
│   ├── repository.py           # Repos: prod_repo, VentaRepo, UsuarioRepo, PagoProveedorRepo
│   ├── afip_integration.py     # wsfe: crear_factura(), nota_credito(), último_comprobante()
│   ├── firebase_sync.py        # FirebaseSyncManager: push/pull productos, ventas, proveedores
│   ├── alert_manager.py        # Alertas por email ante errores críticos
│   ├── email_helper.py         # Envío de reportes por SMTP
│   ├── login.py                # LoginDialog, CreateAdminDialog
│   │
│   └── gui/
│       ├── common.py           # Constantes UI (BASE_ICONS_PATH, MIN_BTN_HEIGHT, icon())
│       ├── dialogs.py          # PagoEfectivoDialog, PagoTarjetaDialog, DevolucionDialog
│       ├── compradores.py      # CompradorService (CRUD clientes locales)
│       ├── proveedores.py      # ProveedorService
│       ├── historialventas.py  # HistorialVentasWidget (tab flotante)
│       ├── shortcuts.py        # ShortcutManager (atajos de teclado)
│       ├── smart_template_editor.py  # Editor de plantillas de ticket
│       ├── ventas_helpers.py   # build_product_completer(), imprimir_ticket()
│       │
│       └── main_window/
│           ├── core.py                      # MainWindow (hereda 12 mixins)
│           ├── productos.py                 # ProductosMixin
│           ├── ventas.py                    # VentasMixin
│           ├── ventas_finalizacion_mixin.py # Flujo de finalización de venta
│           ├── ventas_ticket_mixin.py       # Render e impresión de tickets
│           ├── proveedores_mixin.py         # Tab Proveedores
│           ├── compradores_mixin.py         # Tab Clientes
│           ├── usuarios_mixin.py            # Tab Usuarios
│           ├── configuracion_mixin.py       # Tab Configuración
│           ├── ticket_templates_mixin.py    # Gestión de plantillas ticket
│           ├── reportes_mixin.py            # Reportes por email
│           ├── backups_mixin.py             # Backup automático
│           ├── sync_mixin.py               # Notificaciones de sync
│           ├── stats_mixin.py              # Estadísticas
│           └── filters.py                  # LimitedFilterProxy
│
├── assets/                     # Iconos (.ico), fuente Roboto.ttf
├── icons/                      # SVGs para tabs (productos.svg, clientes.svg, etc.)
└── dashboard/                  # Dashboard HTML standalone
```

---

## 3. Patrón Mixin (MainWindow)

`MainWindow` hereda de **12 mixins** + `QMainWindow`. Cada mixin aporta una pestaña o funcionalidad:

```python
# app/gui/main_window/core.py
class MainWindow(
    ProductosMixin,           # tab_productos()
    VentasMixin,              # tab_ventas()
    VentasTicketMixin,        # render/impresión tickets
    VentasFinalizacionMixin,  # flujo finalizar venta
    ProveedoresMixin,         # tab_proveedores()
    CompradoresMixin,         # tab_compradores() → "Clientes"
    UsuariosMixin,            # tab_usuarios()
    ConfiguracionMixin,       # tab_configuracion()
    TicketTemplatesMixin,     # gestión plantillas
    ReportesMixin,            # reportes email
    BackupsMixin,             # backup automático
    SyncNotificationsMixin,   # sync Firebase
    StatsMixin,               # estadísticas
    QMainWindow
):
```

**Orden de tabs** (definido en `core.py.__init__`):
| Índice | Tab | Mixin |
|--------|-----|-------|
| 0 | Productos | `ProductosMixin` |
| 1 | Proveedores | `ProveedoresMixin` |
| 2 | Clientes | `CompradoresMixin` |
| 3 | Ventas | `VentasMixin` |
| dinámico | Historial | `HistorialVentasWidget` (widget separado) |
| dinámico | Configuración | `ConfiguracionMixin` |

---

## 4. Base de Datos y Migraciones

**Ubicación de la BD:**
- Desarrollo: `./appcomprasventas.db` (raíz del proyecto)
- Producción (frozen): `%LOCALAPPDATA%\Compraventas\app\appcomprasventas.db`

**Modelos** (`app/models.py`): `Usuario`, `Comprador`, `Producto`, `Venta`, `VentaItem`, `Proveedor`, `VentaLog`, `VentaBorrador`, `VentaBorradorItem`, `PagoProveedor`

**Sistema de migraciones** (`app/database.py → _run_migrations()`):
- Se ejecuta en cada `init_db()` (al arrancar la app)
- Usa `sqlalchemy.inspect()` para detectar columnas/tablas faltantes
- Patrón: verificar existencia → `ALTER TABLE ADD COLUMN` o `Table.create()`

```python
# Ejemplo: agregar nueva columna
if "mi_columna" not in cols:
    conn.execute(text("ALTER TABLE ventas ADD COLUMN mi_columna VARCHAR"))
```

**SQLite PRAGMAs** configurados: `journal_mode=WAL`, `busy_timeout=15000`, `synchronous=NORMAL`

---

## 5. Sistema de Configuración

**Archivo:** `app_config.json` en `%APPDATA%\CompraventasV2\`

**API:** `app/config.py`
- `load()` → lee JSON + merge profundo con `DEFAULTS`
- `save(cfg)` → escribe JSON a disco
- Las claves faltantes se completan automáticamente sin pisar valores existentes

**Secciones principales de `DEFAULTS`:**

| Sección | Propósito |
|---------|-----------|
| `business` | Nombre, CUIT, IVA, teléfono, sucursales |
| `general` | Timezone, minimize to tray |
| `shortcuts` | Atajos de teclado (globales y por sección) |
| `theme` | Dark mode, colores, fuentes |
| `printers` | Impresora de tickets y códigos de barras |
| `ticket` | Papel, fuentes, 10 slots de plantilla, imágenes, placeholders |
| `barcode` | Dimensiones de etiquetas |
| `backup` | Horarios, retención, compresión |
| `fiscal` | AFIP: modo test/prod, CUIT, punto de venta, AfipSDK keys |
| `startup` | Sucursal por defecto |
| `reports` | Filtros por defecto, auto-envío |
| `sync` | Firebase: URL, token, intervalo |
| `dashboard` | Cards visibles, columnas, estilos |

**Para agregar una nueva config:**
1. Agregar valor default en `DEFAULTS` en `app/config.py`
2. Leerla con `cfg.get("seccion", {}).get("clave")` donde se necesite
3. Si es editable por el usuario, agregar control en `configuracion_mixin.py`

---

## 6. Guías de Cambios Comunes

### 6.1 Agregar una sucursal

Las sucursales se leen dinámicamente de la config. **No hay que tocar código.**

1. Abrir `app_config.json` (en `%APPDATA%\CompraventasV2\`)
2. En `business.sucursales`, agregar la nueva entrada:
```json
{
  "business": {
    "sucursales": {
      "Sarmiento": "Pte. Sarmiento 1695, Gerli",
      "Salta": "Salta 1694, Gerli",
      "NuevaSucursal": "Dirección de la nueva sucursal"
    }
  }
}
```
3. Reiniciar la app → aparecerá en:
   - Selector de inicio
   - Configuración → "Sucursal por defecto"
   - Historial → filtro por sucursal

**Archivos que leen sucursales dinámicamente:**
- `app/gui/main_window/core.py` → selector de inicio
- `app/gui/main_window/configuracion_mixin.py` → combo sucursal por defecto
- `app/gui/historialventas.py` → filtro de historial

### 6.2 Agregar una pestaña/mixin

1. **Crear el mixin** en `app/gui/main_window/nuevo_mixin.py`:
```python
class NuevoMixin:
    def tab_nuevo(self):
        """Retorna el QWidget de la pestaña."""
        w = QWidget()
        layout = QVBoxLayout(w)
        # ... construir UI ...
        return w
```

2. **Registrar en `core.py`**:
   - Agregar import: `from app.gui.main_window.nuevo_mixin import NuevoMixin`
   - Agregar a la herencia de `MainWindow`: `class MainWindow(... NuevoMixin, ... QMainWindow):`
   - En `__init__`, agregar tab: `tabs.addTab(self.tab_nuevo(), icon('icono.svg'), 'Nombre')`
   - Actualizar el mapping de `_goto_tab()` si es necesario

3. **Ícono**: colocar SVG en `icons/` (raíz del proyecto)

4. **Actualizar índices**: si insertas antes de Ventas, ajustar el fallback mapping en `_goto_tab()`

### 6.3 Agregar un modelo de BD + migración

1. **Definir modelo** en `app/models.py`:
```python
class NuevoModelo(Base):
    __tablename__ = 'nuevo_tabla'
    id = Column(Integer, primary_key=True)
    # ... columnas ...
```

2. **Agregar migración** en `app/database.py → _run_migrations()`:
```python
# Crear tabla nuevo_tabla si no existe (vX.Y.Z)
if "nuevo_tabla" not in inspector.get_table_names():
    from app.models import NuevoModelo
    NuevoModelo.__table__.create(bind=engine)
```

3. **Para agregar columnas a tabla existente:**
```python
if "ventas" in inspector.get_table_names():
    _pragma_cols = conn.execute(text("PRAGMA table_info(ventas)")).fetchall()
    cols = [row[1] for row in _pragma_cols]
    if "nueva_columna" not in cols:
        conn.execute(text("ALTER TABLE ventas ADD COLUMN nueva_columna VARCHAR"))
```

> **Nota:** Usar `PRAGMA table_info()` en lugar de `inspector.get_columns()` cuando se necesita información fresca (el inspector puede cachear).

### 6.4 Agregar un placeholder de ticket

Los placeholders se resuelven en `app/gui/main_window/ventas_ticket_mixin.py`.

1. **Registrar en DEFAULTS** (`app/config.py`):
   - Agregar `"{{nuevo.placeholder}}"` a la lista `ticket.placeholders`

2. **Resolver en el render** (`ventas_ticket_mixin.py`):
   - Buscar el dict `placeholders = { ... }` en el método de render
   - Agregar: `"nuevo.placeholder": valor_calculado`

3. **Placeholders existentes principales:**
   - `{{ticket.numero}}`, `{{ticket.fecha_hora}}`, `{{sucursal}}`
   - `{{totales.subtotal}}`, `{{totales.descuento}}`, `{{totales.interes}}`, `{{totales.total}}`
   - `{{iva.base}}` (total sin IVA), `{{iva.cuota}}`, `{{iva.porcentaje}}`
   - `{{pago.modo}}`, `{{pago.cuotas}}`, `{{pago.monto_cuota}}`
   - `{{abonado}}`, `{{vuelto}}`, `{{vendedor}}`
   - `{{business}}`, `{{business.cuit}}`, `{{business.direccion}}`
   - `{{comprador.cuit}}`, `{{comprador.nombre}}`, etc.
   - `{{afip.cae}}`, `{{afip.vencimiento}}`, `{{afip.comprobante}}`
   - `{{hr}}` (línea), `{{items}}` (tabla de productos), `{{cae}}` (bloque CAE completo)
   - `{{img:logo}}`, `{{img:qr}}`, `{{qrcae}}` (QR de AFIP)

4. **Expresiones matemáticas:** se soportan con `{{= expr }}`, ej: `{{= totales.total - iva.cuota }}`

5. **Formato directives:** `{{center: texto}}`, `{{b: texto}}`, `{{centerb: texto}}`, `{{right: texto}}`, `{{rightb: texto}}`

### 6.5 Modificar diálogos de pago

Los diálogos están en `app/gui/dialogs.py`:
- `PagoEfectivoDialog` — pagos en efectivo (con opciones de factura)
- `PagoTarjetaDialog` — pagos con tarjeta (cuotas, interés)

**Para agregar un campo nuevo:**

1. En el `__init__` del diálogo, crear el widget:
```python
self.edt_nuevo = QLineEdit()
form.addRow("Nuevo campo:", self.edt_nuevo)
```

2. En `_aceptar()`, incluirlo en `self._result`:
```python
self._result["nuevo_campo"] = self.edt_nuevo.text().strip()
```

3. En `ventas_finalizacion_mixin.py`, leer el resultado:
```python
datos = dlg.result()
nuevo = datos.get("nuevo_campo", "")
```

4. Si depende del tipo de comprobante, actualizar `_on_tipo_cbte_changed()` para mostrar/ocultar.

**Campos de comprador (CUIT, nombre, domicilio, etc.):**
- Se auto-completan al presionar "Cargar" → busca en BD local via `CompradorService`
- Se auto-guardan en la BD al confirmar la venta (en `ventas_finalizacion_mixin.py`)

### 6.6 Agregar un atajo de teclado

Los atajos se definen en `app_config.json → shortcuts`:

```json
{
  "shortcuts": {
    "global": {
      "productos": "F1",
      "proveedores": "F2",
      "ventas": "F3",
      "nuevo": "F7"
    },
    "section": {
      "nuevo": {
        "accion1": "A",
        "accion2": "E"
      }
    }
  }
}
```

El `ShortcutManager` (`app/gui/shortcuts.py`) lee esta config y registra los atajos.

---

## 7. Facturación AFIP

**Archivo:** `app/afip_integration.py`
**API:** AfipSDK REST API (no SDK local)

**Config** (`fiscal` en `app_config.json`):
```json
{
  "fiscal": {
    "enabled": true,
    "mode": "prod",           // "test" o "prod"
    "cuit": "20123456789",
    "punto_venta": 1,
    "puntos_venta_por_sucursal": {"Sarmiento": 1, "Salta": 2},
    "tipo_cbte": "FACTURA_B",
    "afipsdk": {
      "api_key": "...",
      "base_url_test": "https://...",
      "base_url_prod": "https://..."
    }
  }
}
```

**Tipos de comprobante soportados:**
- `FACTURA_A` — Responsable Inscripto a Responsable Inscripto (IVA discriminado)
- `FACTURA_B` — Responsable Inscripto a Consumidor Final
- `FACTURA_B_MONO` — Monotributista
- `NOTA_CREDITO_A` / `NOTA_CREDITO_B` — Notas de crédito

**Flujo:**
1. Usuario finaliza venta → elige tipo de comprobante en el diálogo de pago
2. `ventas_finalizacion_mixin.py` llama a `afip_integration.crear_factura()`
3. AfipSDK devuelve CAE + nº comprobante → se guarda en `Venta`
4. QR AFIP se genera con los datos del CAE para el ticket

**Puntos de venta por sucursal:** se configuran en `fiscal.puntos_venta_por_sucursal`. Si no hay entrada para la sucursal, usa `fiscal.punto_venta` como fallback global.

---

## 8. Sincronización Firebase

**Archivo:** `app/firebase_sync.py`
**Clase:** `FirebaseSyncManager`

**Características:**
- Bidireccional: push (local→nube) y pull (nube→local)
- Last-write-wins (basado en timestamps)
- Cola offline: si no hay conexión, encola y reintenta
- REST API directo (no usa SDK de Firebase)
- Sincroniza: productos, ventas, proveedores

**Config** (`sync` en `app_config.json`):
```json
{
  "sync": {
    "enabled": true,
    "mode": "interval",
    "interval_minutes": 5,
    "firebase": {
      "database_url": "https://tu-proyecto.firebaseio.com",
      "auth_token": "tu-token"
    },
    "sync_productos": true,
    "sync_proveedores": true
  }
}
```

**Multi-computadora:** Funciona en varias PCs por sucursal. Cada PC sincroniza contra Firebase independientemente. Conflictos se resuelven por timestamp (último cambio gana).

---

## 9. Sistema de Tickets

**10 slots de plantillas** configurables en `ticket.slots.slot1` a `slot10`.

**Prioridad de selección de plantilla:**
1. Asignación específica por tipo de comprobante (ej: `template_efectivo_factura_a`)
2. Asignación genérica por modo de pago (`template_efectivo`, `template_tarjeta`)
3. Slot 1 como fallback absoluto

**Render** (`ventas_ticket_mixin.py`):
- Se dibuja en un canvas QPainter oversized (3x alto estimado)
- Se escanea de abajo hacia arriba buscando el último pixel no-blanco
- Se recorta con 8mm de margen → imagen final exacta

**Fuentes del ticket** (en `ticket.fonts`): H1 (14pt) a H5 (7pt)

**Imágenes en tickets:**
- `{{img:logo}}`, `{{img:instagram}}`, `{{img:whatsapp}}`, `{{img:qr}}`
- Se configuran en `ticket.images` con rutas a archivos
- `{{qrcae}}` genera QR dinámico con datos AFIP del CAE

---

## 10. Build y Deploy

### Pipeline completo

```bash
# Ejecutar desde la raíz del proyecto:
build.bat
```

**Pasos del build:**
1. Crear/activar `.venv`
2. Resetear config a estado limpio (`reset_config_for_build.py`)
3. Instalar dependencias (`requirements.txt` + `requirements-dev.txt`)
4. Limpiar builds anteriores
5. Generar archivo de versión (`create_version_file.py`)
6. PyInstaller (`build.spec`) → `dist/Tu local 2025/`
7. Inno Setup 6 (`installer.iss`) → `installer_output/Tu.local.2025.vX.Y.Z.Setup.exe`

### Requisitos
- Python 3.14 con `.venv`
- PyInstaller (en `requirements-dev.txt`)
- Inno Setup 6 instalado en el sistema

### Estructura del instalador
- Instala en `%LOCALAPPDATA%\Compraventas\app\` (sin admin)
- Config vive en `%APPDATA%\CompraventasV2\` (separada, no se toca en actualizaciones)
- BD vive junto al ejecutable en modo frozen

### Release en GitHub
```bash
git add . && git commit -m "build: vX.Y.Z"
git tag vX.Y.Z
git push origin main --tags
# GitHub > Releases > Create Release > subir el .Setup.exe
```

---

## 11. Versionado

**Archivos a actualizar al cambiar de versión:**

| Archivo | Campo |
|---------|-------|
| `version.py` | `__version__ = "X.Y.Z"` |
| `installer.iss` | `#define MyAppVersion "X.Y.Z"` |

Ambos deben coincidir. El `build.bat` lee la versión de `version.py` automáticamente.

**Convención:** SemVer — `MAJOR.MINOR.PATCH`
- MAJOR: cambios incompatibles o reestructuración grande
- MINOR: nuevas funcionalidades
- PATCH: correcciones de bugs
