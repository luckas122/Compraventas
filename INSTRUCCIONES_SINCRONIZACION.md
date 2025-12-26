# Instrucciones de Integración - Sistema de Sincronización v1.0

## Resumen

Se ha implementado un sistema de sincronización automática entre sucursales usando Gmail (SMTP + IMAP). El sistema permite:

- ✅ Sincronización automática de ventas entre sucursales
- ✅ Tres modos: Intervalo fijo, Detección de cambios, Manual
- ✅ Configuración completa en pestaña "Sincronización" dentro de Configuraciones
- ✅ Detección de duplicados usando hashes MD5
- ✅ Log completo de sincronizaciones en tabla `sync_log`

---

## Archivos Creados/Modificados

### Nuevos archivos:
1. **app/sync_manager.py** - Lógica de sincronización (SMTP/IMAP)
2. **app/gui/sync_config.py** - Pestaña de configuración en UI

### Archivos modificados:
1. **app/models.py** - Agregado modelo `SyncLog`
2. **app/app_config.json** - Agregada sección `"sync"`
3. **app/gui/main_window/configuracion_mixin.py** - Agregada pestaña "Sincronización"

---

## Pasos de Integración en MainWindow

Necesitas integrar el scheduler de sincronización en el archivo principal de la ventana (probablemente `app/gui/main_window/core.py` o similar).

### 1. Importar módulos necesarios

```python
from PyQt5.QtCore import QTimer
from app.sync_manager import SyncManager
from app.config import load as load_config
```

### 2. Agregar atributos en `__init__` de MainWindow

```python
def __init__(self):
    # ... código existente ...

    # Sincronización
    self._sync_manager = None
    self._sync_timer = QTimer(self)
    self._sync_timer.timeout.connect(self._ejecutar_sincronizacion)
    self._last_sync_time = None

    # Inicializar sincronización
    self._setup_sync_scheduler()
```

### 3. Crear método `_setup_sync_scheduler()`

```python
def _setup_sync_scheduler(self):
    """Configura el scheduler de sincronización desde app_config.json"""
    cfg = load_config()
    sync_cfg = cfg.get("sync", {})

    enabled = sync_cfg.get("enabled", False)
    mode = sync_cfg.get("mode", "interval")
    interval_min = sync_cfg.get("interval_minutes", 5)

    # Detener timer si ya está corriendo
    self._sync_timer.stop()

    if not enabled:
        return

    # Crear SyncManager
    from app.database import SessionLocal
    session = SessionLocal()

    # Obtener sucursal actual
    sucursal_actual = getattr(self, 'sucursal_actual', 'Sarmiento')
    self._sync_manager = SyncManager(session, sucursal_actual)

    # Configurar según modo
    if mode == "interval":
        # Sincronizar cada X minutos
        self._sync_timer.setInterval(interval_min * 60 * 1000)  # Convertir a ms
        self._sync_timer.start()
    elif mode == "on_change":
        # Revisar cada 30 segundos si hay cambios
        self._sync_timer.setInterval(30 * 1000)
        self._sync_timer.start()
    # Si mode == "manual", no iniciar timer

def _reiniciar_sync_scheduler(self):
    """Reinicia el scheduler cuando se guarda la configuración"""
    self._setup_sync_scheduler()
```

### 4. Crear método `_ejecutar_sincronizacion()`

```python
def _ejecutar_sincronizacion(self):
    """Ejecuta un ciclo de sincronización"""
    if not self._sync_manager:
        return

    cfg = load_config()
    sync_cfg = cfg.get("sync", {})
    mode = sync_cfg.get("mode", "interval")

    # Si es modo "on_change", verificar si hay cambios
    if mode == "on_change":
        if not self._sync_manager.detectar_cambios_pendientes():
            # No hay cambios, actualizar indicador y salir
            self._actualizar_indicador_sync(pendiente=False)
            return

    # Ejecutar sincronización
    try:
        resultado = self._sync_manager.ejecutar_sincronizacion_completa()

        # Actualizar indicador
        self._last_sync_time = datetime.now()
        self._actualizar_indicador_sync(
            enviados=resultado["enviados"],
            recibidos=resultado["recibidos"],
            errores=resultado["errores"]
        )

        # Guardar timestamp
        cfg = load_config()
        cfg["sync"]["last_sync"] = self._last_sync_time.isoformat()
        from app.config import save as save_config
        save_config(cfg)

    except Exception as e:
        print(f"[SYNC] Error: {e}")
        self._actualizar_indicador_sync(error=str(e))
```

### 5. Crear método para indicador visual en status bar

```python
def _actualizar_indicador_sync(self, enviados=0, recibidos=0, errores=None, pendiente=False, error=None):
    """Actualiza el indicador de sincronización en la barra de estado"""
    if not hasattr(self, 'lbl_sync_status'):
        # Crear label si no existe
        self.lbl_sync_status = QLabel()
        self.statusBar().addPermanentWidget(self.lbl_sync_status)

    cfg = load_config()
    sync_enabled = cfg.get("sync", {}).get("enabled", False)

    if not sync_enabled:
        self.lbl_sync_status.setText("")
        return

    if error:
        self.lbl_sync_status.setText(f"🔴 Sync error: {error[:30]}")
        self.lbl_sync_status.setStyleSheet("color: #E74C3C;")
    elif errores:
        self.lbl_sync_status.setText(f"⚠️ Sync: {len(errores)} errores")
        self.lbl_sync_status.setStyleSheet("color: #F39C12;")
    elif pendiente:
        self.lbl_sync_status.setText("⏳ Cambios pendientes")
        self.lbl_sync_status.setStyleSheet("color: #3498DB;")
    else:
        if self._last_sync_time:
            # Calcular tiempo desde última sync
            delta = datetime.now() - self._last_sync_time
            if delta.seconds < 60:
                tiempo_str = "hace un momento"
            elif delta.seconds < 3600:
                tiempo_str = f"hace {delta.seconds // 60} min"
            else:
                tiempo_str = f"hace {delta.seconds // 3600}h"

            msg = f"✓ Sync: {tiempo_str}"
            if enviados > 0 or recibidos > 0:
                msg += f" ({enviados}↑ {recibidos}↓)"

            self.lbl_sync_status.setText(msg)
            self.lbl_sync_status.setStyleSheet("color: #27AE60;")
        else:
            self.lbl_sync_status.setText("🔄 Sync activa")
            self.lbl_sync_status.setStyleSheet("color: #95A5A6;")
```

### 6. (Opcional) Botón manual en status bar para modo manual

```python
def _crear_boton_sync_manual(self):
    """Crea un botón en la status bar para sincronización manual"""
    btn_sync = QPushButton("🔄 Sincronizar")
    btn_sync.setFlat(True)
    btn_sync.clicked.connect(self._ejecutar_sincronizacion)
    self.statusBar().addPermanentWidget(btn_sync)

    # Mostrar solo si modo es "manual"
    cfg = load_config()
    mode = cfg.get("sync", {}).get("mode", "interval")
    btn_sync.setVisible(mode == "manual")
```

---

## Configuración de Gmail

### Generar Contraseña de Aplicación

1. Ir a: https://myaccount.google.com/security
2. Activar "Verificación en dos pasos" (si no está activada)
3. Ir a: https://myaccount.google.com/apppasswords
4. Generar nueva contraseña para "Otra aplicación (nombre personalizado)"
5. Usar esta contraseña en la configuración de SMTP/IMAP

### Habilitar IMAP en Gmail

1. Abrir Gmail → Configuración (engranaje) → Ver toda la configuración
2. Pestaña "Reenvío y correo POP/IMAP"
3. En "Acceso IMAP" seleccionar "Habilitar IMAP"
4. Guardar cambios

---

## Migración de Base de Datos

Al iniciar la aplicación por primera vez después de integrar estos cambios, necesitas crear la nueva tabla `sync_log`:

```python
# En tu archivo de inicialización de BD (ej: app/database.py)
from app.database import init_db

init_db()  # Esto creará automáticamente la tabla sync_log
```

---

## Pruebas

### Prueba 1: Configuración básica
1. Ir a Configuración → Sincronización
2. Activar sincronización
3. Configurar Gmail (misma cuenta en SMTP e IMAP)
4. Probar conexión (botón "Probar conexión")
5. Guardar

### Prueba 2: Sincronización en intervalo fijo
1. Seleccionar modo "Automática (intervalo fijo)"
2. Configurar intervalo de 1 minuto (para pruebas)
3. Guardar
4. Hacer una venta en Sucursal A
5. Esperar 1 minuto
6. Verificar en status bar que aparece "✓ Sync: hace un momento (1↑ 0↓)"
7. En Sucursal B, esperar 1 minuto y verificar que aparece "(0↑ 1↓)"

### Prueba 3: Detección de cambios
1. Cambiar modo a "Solo cuando hay cambios detectados"
2. Hacer venta
3. El indicador debe mostrar "⏳ Cambios pendientes"
4. Esperar 30 segundos
5. Debe sincronizarse automáticamente

### Prueba 4: Modo manual
1. Cambiar a modo "Manual"
2. Hacer venta
3. Click en botón "🔄 Sincronizar" en status bar
4. Verificar sincronización inmediata

---

## Logs y Debugging

Para ver logs detallados de sincronización:

```python
# En sync_manager.py, agregar prints:
print(f"[SYNC] Enviados: {resultado['enviados']}, Recibidos: {resultado['recibidos']}")
print(f"[SYNC] Errores: {resultado['errores']}")
```

Consultar tabla sync_log en BD:

```sql
SELECT * FROM sync_log ORDER BY timestamp DESC LIMIT 10;
```

---

## Fase 2 (Futuro)

Características planificadas para implementar después:

- [ ] Sincronización de productos (create/update/delete)
- [ ] Sincronización de proveedores
- [ ] Resolución de conflictos (última escritura gana vs merge)
- [ ] Compresión de paquetes JSON grandes
- [ ] Reintentos automáticos en caso de fallo
- [ ] Panel de historial de sincronizaciones en UI
- [ ] Notificaciones push cuando llegan cambios

---

## Soporte

Si encuentras problemas:

1. Verificar credenciales de Gmail (contraseña de aplicación)
2. Verificar que IMAP esté habilitado en Gmail
3. Revisar logs de la aplicación
4. Consultar tabla `sync_log` para ver qué se sincronizó
5. Verificar firewall/antivirus (puertos 587 y 993)

---

**Autor:** Claude Code
**Versión:** 1.0
**Fecha:** 2025-12-26
