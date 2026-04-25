# Tu local 2025 — Catálogo de funciones por archivo

> Referencia rápida de las funciones/métodos públicos relevantes.
> Versión: **6.5.1** · Complemento de [CLAUDE.md](CLAUDE.md) y [SECCIONES.md](SECCIONES.md).
>
> Convención: `nombre(args)` — descripción en una línea.
> Solo se listan funciones públicas/principales. Helpers internos triviales (`__repr__`, getters obvios) se omiten.

---

## Núcleo de la aplicación

### `version.py`
- `get_version_tuple()` — Retorna la versión como tupla `(major, minor, patch)` para comparaciones.

### `main.py`
- `_install_global_excepthook()` — Captura excepciones no controladas en Qt y muestra ventanas de error con contexto.
- `main()` — Entry point: inicializa logging, abre `LoginDialog`, instancia `MainWindow`.

### `app/config.py`
- `load()` — Carga `app_config.json` y completa con `DEFAULTS` (merge profundo, no pisa lo existente).
- `save(cfg)` — Persiste el dict de config a disco como JSON indentado.
- `get_images_dir()` — Devuelve ruta persistente para imágenes de tickets (logos, QRs).
- `get_log_dir()` — Devuelve ruta persistente para logs.
- `get_backup_path()` — Devuelve la ruta del backup de configuración creado por el instalador.
- `has_pending_backup()` — `True` si hay un backup de config esperando ser restaurado tras update.
- `restore_from_backup()` — Restaura la config desde el backup pendiente.
- `restore_from_path(src_path)` — Restaura config desde un archivo JSON arbitrario.
- `delete_backup()` — Borra la carpeta y el archivo de backup pendiente.

### `app/database.py`
- `init_db()` — Crea engine SQLite, configura PRAGMAs (WAL, busy_timeout, synchronous), llama a `_run_migrations()`.
- `_run_migrations()` — Ejecuta migraciones idempotentes (chequea con `PRAGMA table_info` antes de `ALTER TABLE`).

### `app/models.py` (modelos SQLAlchemy)
- `Usuario` — Cuenta de login (username, password hash, es_admin).
- `Producto` — Catálogo: código, nombre, precio, categoría, stock, version (lock optimista).
- `Venta` — Cabecera de venta: ticket, fecha, sucursal, totales, CAE, vto, modo_pago, nota_credito_cae.
- `VentaItem` — Línea de venta: producto, cantidad, precio_unitario, descuento.
- `Proveedor` — Datos de proveedor: nombre, teléfono, cuenta, CBU.
- `Comprador` — Cliente fiscal: CUIT, nombre, domicilio, condición AFIP.
- `PagoProveedor` — Pago a proveedor: proveedor, monto, método, fecha, **incluye_iva** (v6.5.0), nota.
- `VentaLog` — Auditoría de cambios sobre ventas.
- `VentaBorrador` + `VentaBorradorItem` — Cesta guardada para retomar.

### `app/repository.py`
**`UsuarioRepo`:**
- `crear(username, password, es_admin)` — Crea usuario con password hasheada.
- `obtener_por_username(username)` — Busca por nombre de login.
- `listar()` — Lista todos los usuarios.
- `verificar(username, password)` — Valida credenciales.
- `actualizar(usuario_id, username, password, es_admin)` — Modifica usuario.
- `eliminar(usuario_id)` — Borra usuario.

**`prod_repo` (productos):**
- `buscar_por_codigo(codigo)` — Lookup exacto por código de barras.
- `crear(codigo, nombre, precio, categoria)` — Inserta producto.
- `listar_todos()` — Devuelve todos los productos.
- `buscar(texto, limit)` — Búsqueda multi-campo (código/nombre/categoría/precio) con LIKE.
- `actualizar_nombre(prod_id, nuevo, expected_version)` — Update con lock optimista por `version`.
- `actualizar_precio(prod_id, nuevo, expected_version)` — Idem para precio.
- `actualizar_categoria(prod_id, nuevo)` — Update categoría.
- `eliminar(prod_id)` — Borra producto.

**`VentaRepo`:**
- `listar_por_rango(dt_min, dt_max, sucursal=None)` — Ventas en un rango (con filtro opcional de sucursal).
- `listar_por_fecha(dia, sucursal=None)` — Fallback día a día.
- `listar_items(venta_id)` — Items de una venta.
- `crear_venta(...)` — Persiste cabecera + items en transacción.
- `marcar_nota_credito(venta_id, nc_cae)` — Asocia NC a venta original.

**`PagoProveedorRepo`:**
- `listar_por_rango(dt_min, dt_max, sucursal=None)` — Pagos en un rango.
- `crear_pago(proveedor, monto, metodo, incluye_iva=False, ...)` — Inserta pago (v6.5.0 agregó `incluye_iva`).
- `eliminar(pago_id)` — Borra pago.

### `app/afip_integration.py`
- `AfipConfig` — Dataclass con `api_key`, `cuit`, `mode` (test/prod), `punto_venta`.
- `crear_factura(tipo, total, comprador, items, ...)` — POST a AfipSDK, devuelve `(cae, vto, nro)` o lanza error.
- `nota_credito(venta_original, ...)` — Emite NC asociada a una factura previa.
- `ultimo_comprobante(tipo, punto_venta)` — Consulta el último Nº emitido para sincronizar numeración.

### `app/firebase_sync.py`
**`FirebaseSyncManager`:**
- `__init__(session, sucursal_local)` — Crea el manager con sesión SQLAlchemy + nombre de sucursal.
- `_firebase_get(path, params)` — GET REST a Firebase.
- `_firebase_post(path, data)` — POST REST.
- `push_cambio(tipo, data)` — Empuja un cambio (con `sucursal_origen` y timestamp).
- `pull_cambios()` — Trae cambios remotos y aplica los que no son del propio origen. Tipos: `productos`, `ventas`, `proveedores`, `pagos_proveedores`.
- `_apply_venta(data)` — Aplica una venta remota a la BD local.
- `_apply_producto(data)` — Idem productos.
- `_apply_proveedor(data)` — Idem proveedores.
- `_apply_pago_proveedor(data)` — Idem pagos a proveedor (v6.5.0).
- `start()` / `stop()` — Arranca/detiene el thread de sync periódico.

### `app/alert_manager.py`
- `AlertManager.get_instance()` — Singleton.
- `AlertManager.send_alert(error_type, message, details, force=False)` — Manda email crítico (con throttling, salvo `force=True`).

### `app/email_helper.py`
- `send_mail_with_attachments(subject, body, recipients, attachments)` — Wrapper SMTP con fallback de puertos 587 / 465.
- `SmtpWorker` — `QThread` que envía emails sin bloquear la UI.

### `app/login.py`
- `LoginDialog` — Diálogo de login con validación.
  - `handle_login()` — Verifica usuario y emite `accept()` o muestra error.
- `CreateAdminDialog` — Diálogo inicial cuando no hay usuarios; crea el primer admin.

---

## GUI base

### `app/gui/common.py`
- `icon(name)` — Carga `QIcon` desde `icons/<name>.svg` o `assets/`.
- `BASE_ICONS_PATH`, `MIN_BTN_HEIGHT` — Constantes de estilos.
- `FullCellCheckFilter` — Event filter: permite togglear checkboxes en celdas con click en cualquier parte de la celda + Shift.

### `app/gui/dialogs.py`
- `PagoEfectivoDialog` — Pago en efectivo: monto, vuelto, descuento, comprobante AFIP.
- `PagoTarjetaDialog` — Pago con tarjeta: cuotas, interés, comprobante.
- `PagoProveedorDialog` — Registrar pago a proveedor (v6.5.0: con checkbox "Incluye IVA").
- `DevolucionDialog` — Buscar venta y emitir Nota de Crédito.
- `ProductosDialog` — Selector de producto (poco usado, fallback).
- `_draw_barcode_label(painter, width_px, code, name, ...)` — Dibuja una etiqueta de código de barras.
- `_barcode_qimage_from_code128(code_str)` — Genera `QImage` con código CODE-128.

### `app/gui/compradores.py` — `CompradorService`
- `buscar_por_cuit(cuit)` — Lookup por CUIT.
- `guardar_o_actualizar(cuit, nombre, domicilio, ...)` — Upsert por CUIT.
- `listar_todos()` — Todos los clientes ordenados por nombre.
- `actualizar(comprador_id, **campos)` — Update parcial.
- `eliminar(comprador_id)` — Borra cliente.

### `app/gui/proveedores.py` — `ProveedorService`
- `crear_o_actualizar_por_nombre(nombre, telefono, cuenta, cbu)` — Upsert por nombre.
- `listar_todos()` — Todos los proveedores.
- `buscar_por_nombre(texto)` — Búsqueda con `ILIKE`.
- `actualizar(proveedor_id, **campos)` — Update parcial.
- `eliminar(proveedor_id)` — Borra.
- `existe_nombre(nombre)` — Chequeo de unicidad.

### `app/gui/historialventas.py` — `HistorialVentasWidget`
- `__init__(...)` — Construye barra de filtros, tabs (Listado + Estadísticas), tabla y resumen.
- `refrescar()` — Recarga ventas según filtros (CAE / Pago / fecha / sucursal / texto).
- `_pintar_tabla()` — Pinta la tabla y calcula el `lbl_resumen` (totales + CAE + IVAs + NC restada).
- `_actualizar_estadisticas()` — Calcula KPIs y dispara los gráficos (v6.5.1: usa filtros CAE+Pago).
- `_generar_grafico_ventas(ventas, dt_min, dt_max)` — Barras por día.
- `_generar_grafico_formas_pago(ventas)` — Torta Efectivo vs Tarjeta.
- `_generar_comparativa_sucursales(dt_min, dt_max, pago_txt)` — Comparativa multi-sucursal.
- `_calcular_top_productos(ventas)` — Top 10 productos por monto.
- `_ver_detalle_venta(row, col)` — Diálogo con items de una venta.
- `_export_excel()` — Exporta el listado actual a `.xlsx`.
- `_make_writer(path)` — Helper: crea `ExcelWriter` con engine fallback.
- `_autofit_sheet(ws, df, engine_name)` — Ajusta ancho de columnas.

### `app/gui/shortcuts.py`
- `_cfg_shortcuts()` — Lee atajos desde `config["shortcuts"]`.
- `ShortcutManager` — Registra `QShortcut`s sobre la `MainWindow` y los reasigna al cambiar config.

### `app/gui/smart_template_editor.py`
- `SmartTemplateEditor` — `QWidget` con `QTextEdit` + autocompletado `{{...}}` + syntax highlighting.
  - `update_preview()` — Re-renderiza el preview en tiempo real.
  - `insert_block(name)` — Inserta bloque pre-armado (cae, items, totales, etc.).
  - `validate()` — Marca placeholders inválidos en rojo.

### `app/gui/ventas_helpers.py`
- `build_product_completer(session, parent)` — Crea `QCompleter` con productos (limita 50 ítems).
- `_get_configured_printer(kind)` — Resuelve impresora `ticket` o `barcode` desde config.
- `imprimir_ticket(venta, preview, sucursal, ...)` — Render + impresión del ticket usando la plantilla correcta.

---

## Main Window y Mixins

### `app/gui/main_window/core.py` — `MainWindow`
- `__init__(es_admin, username)` — Inicializa tabs, mixins, sync, backups, atajos, bandeja.
- `_on_cesta_item_changed(item)` — Handler de `itemChanged` en cesta (v6.5.0: ignora updates programáticos vía flag `_cesta_updating` y formato `→` del descuento).
- `closeEvent(event)` — Limpieza al cerrar (detiene threads, guarda config).
- `_cleanup_resources()` — Detiene threads de sync, backups, scheduler de reportes.
- `nueva_venta()` — Limpia cesta y pone foco en buscador de productos.
- `_ensure_admin(reason)` — Pide password de admin antes de operaciones sensibles.
- `_setup_help_menu()` — Construye menú "Ayuda" con atajos.
- `_show_shortcuts_help()` — Diálogo modal con la tabla de atajos actuales.
- `_goto_tab(nombre)` — Navega a una pestaña por nombre lógico.
- `eventFilter(obj, event)` — Captura eventos globales (atajos, autocompletado en cesta).

### `app/gui/main_window/productos.py` — `ProductosMixin`
- `tab_productos()` — Construye y devuelve el `QWidget` de la pestaña.
- `_do_buscar_productos()` — Ejecuta búsqueda con filtros activos.
- `_on_buscar_text_changed()` — Debounce 250 ms para refrescar resultados.
- `agregar_o_actualizar_producto()` — Upsert desde el formulario.
- `eliminar_productos()` — Borra los seleccionados.
- `editar_masivamente()` — Aplica un cambio (precio/nombre/categoría) a todos los seleccionados.
- `importar_excel()` — Lee `.xlsx` y crea/actualiza productos.
- `exportar_excel()` — Genera `.xlsx` del listado actual.
- `imprimir_codigos_barras()` — Vista previa + impresión de etiquetas.
- `mostrar_cambios_recientes()` — Diálogo con el log de cambios masivos.
- `productos_sin_ventas_90_dias()` — Reporte de inactivos.

### `app/gui/main_window/ventas.py` — `VentasMixin`
- `tab_ventas()` — Construye la pestaña: buscador, cesta, totales, botones de pago/finalizar.
- `agregar_a_cesta(producto, cantidad=1)` — Agrega línea (suma si ya existe).
- `actualizar_total()` — Recalcula totales (v6.5.0: con `_cesta_updating` + `QSignalBlocker`).
- `_descuento_en_fila(row, tipo)` — Aplica descuento `%` o `$` a una línea.
- `vaciar_cesta()` — Limpia tabla y reset de totales.
- `guardar_borrador()` / `cargar_borrador()` — Persiste/recupera la cesta.
- `_beep_ok()` — Reproduce `assets/sounds/pip.wav` al agregar (definido en `sync_mixin.py`).

### `app/gui/main_window/ventas_finalizacion_mixin.py` — `VentasFinalizacionMixin`
- `finalizar_venta()` — Punto de entrada: abre diálogo de pago, llama AFIP, persiste, imprime.
- `_abrir_dialogo_efectivo()` / `_abrir_dialogo_tarjeta()` — Lanzan los diálogos respectivos.
- `_emitir_factura_afip(payload)` — Llama a `afip_integration.crear_factura()` con manejo de errores.
- `_persistir_venta(...)` — Crea `Venta` + `VentaItem`s en transacción y empuja a Firebase.
- `_on_pago_method_changed(checked)` — Actualiza UI al cambiar entre Efectivo/Tarjeta (legacy).

### `app/gui/main_window/ventas_ticket_mixin.py` — `VentasTicketMixin`
- `_seleccionar_plantilla(modo, comprobante)` — Resuelve qué slot usar.
- `_render_ticket_image(slot, contexto)` — Dibuja en `QPainter` y recorta.
- `_items_para_ticket()` — Normaliza items desde la cesta o desde la BD (con fallbacks).
- `imprimir_ticket(venta, preview=False)` — Manda a `QPrinter` o muestra preview.
- `_enviar_whatsapp(venta)` — Genera link `wa.me` con el mensaje pre-armado.

### `app/gui/main_window/proveedores_mixin.py` — `ProveedoresMixin`
- `tab_proveedores()` — Construye la pestaña.
- `cargar_lista_proveedores()` — Recarga la tabla.
- `agregar_o_actualizar_proveedor()` — Upsert desde el formulario.
- `eliminar_proveedores()` — Borra seleccionados.
- `abrir_dialogo_pago_proveedor()` — Lanza `PagoProveedorDialog`.

### `app/gui/main_window/compradores_mixin.py` — `CompradoresMixin`
- `tab_compradores()` — Construye pestaña Clientes.
- `cargar_lista_compradores()` — Recarga tabla.
- `agregar_comprador()` — Upsert con validación de CUIT (11 dígitos).
- `eliminar_compradores()` — Borra seleccionados.

### `app/gui/main_window/usuarios_mixin.py` — `UsuariosMixin`
- `tab_usuarios()` — Pestaña de gestión (solo admin).
- `cargar_usuarios()` — Recarga tabla.
- `agregar_usuario()` — Crea usuario nuevo (password hasheada).
- `actualizar_usuario()` — Edita el usuario seleccionado.
- `eliminar_usuario()` — Borra (con protección: no permite borrar el último admin).

### `app/gui/main_window/configuracion_mixin.py` — `ConfiguracionMixin`
- `tab_configuracion()` — Construye la pestaña con sub-tabs.
- `_apply_config_from_ui()` — Lee widgets y persiste a `app_config.json`.
- `_apply_theme_stylesheet()` — Aplica el tema (claro / suave / medio / negro) a la app.
- `_wire_reportes_guardar_programacion(page)` — Configura el scheduler de reportes desde la UI.
- `_save_alert_config()` — Persiste config de alertas SMTP.
- `_test_alert_email()` — Envía email de prueba.
- `_browse_image(field)` — File dialog para seleccionar imagen del ticket (logo, IG, WhatsApp).
- `_pick_color(field)` — Color picker para hover de botones, etc.

### `app/gui/main_window/ticket_templates_mixin.py` — `TicketTemplatesMixin`
- `tab_ticket_templates()` — Editor de los 10 slots de plantilla.
- `_save_slot(slot_n)` — Guarda el contenido del slot.
- `_preview_slot(slot_n)` — Renderiza el slot con datos dummy.
- `_assign_template(modo, comprobante, slot_n)` — Asigna un slot a una combinación pago+comprobante.

### `app/gui/main_window/reportes_mixin.py` — `ReportesMixin`
- `_init_reportes_scheduler()` — Crea `QTimer` 60s que dispara envíos automáticos.
- `_enviar_reporte_historial()` — Genera Excel del Historial y lo manda por SMTP.
- `_should_send_now(now, freq, time_str, weekday, monthday)` — Lógica de scheduling DAILY/WEEKLY/MONTHLY.

### `app/gui/main_window/backups_mixin.py` — `BackupsMixin`
- `_init_backups()` — Inicializa scheduler.
- `_setup_backups()` — Configura horarios desde config.
- `_run_backup(tag, dest_override=None)` — Ejecuta backup ZIP (BD + config).
- `_cleanup_old_backups(dest_dir, tag)` — Borra backups antiguos según retención.
- `_restore_from_zip()` — Diálogo para restaurar desde ZIP (con confirmación).
- `_verify_backup_integrity(zip_path, db_name)` — Chequea que el ZIP esté completo y la BD sea válida.

### `app/gui/main_window/sync_mixin.py` — `SyncNotificationsMixin`
- `_setup_sync_manager()` — Instancia `FirebaseSyncManager` y arranca el thread.
- `_sync_push(tipo, data)` — Helper para empujar un cambio a Firebase.
- `_setup_tray_icon()` — Crea ícono en bandeja con menú (Mostrar / Backup / Salir).
- `_beep_ok()` — Reproduce `pip.wav` (usado al agregar a cesta).
- `_on_sync_status(estado)` — Actualiza indicador visual de sync.

### `app/gui/main_window/stats_mixin.py` — `StatsMixin`
- (Ver `historialventas.py._actualizar_estadisticas()` — la implementación real vive ahí; el mixin orquesta los hooks).

### `app/gui/main_window/filters.py`
- `LimitedFilterProxy(limit, parent)` — `QSortFilterProxyModel` que limita filas (evita lag en listas grandes).
  - `rowCount(parent)` — Devuelve `min(filas_originales, limit)`.

---

## Notas de uso

- **Para encontrar dónde se hace X:** buscar primero en este catálogo. Si no aparece, `Grep` por nombre del método o palabra clave.
- **Para entender el flujo de un click de UI:** localizar el handler en el mixin correspondiente, seguir hasta `repository.py` (BD) y `firebase_sync.py` (replicación).
- **Para agregar funcionalidad nueva:** ver [DEVELOPMENT.md](DEVELOPMENT.md) §6 con guías paso a paso (sucursal, mixin, modelo, placeholder, atajo).
