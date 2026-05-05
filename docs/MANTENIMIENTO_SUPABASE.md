# Mantenimiento Supabase — Guía operacional

> Cosas a tener en cuenta para que la sincronización siga funcionando bien
> con el free tier de Supabase. Pensado para revisar 1 vez por mes.

---

## 1. Free tier — qué hay que vigilar

Supabase Free tier (a marzo 2026):

| Recurso | Límite free | Tu uso aproximado | Cuándo preocuparte |
|---|---|---|---|
| Storage (DB) | 500 MB | ~30 MB con 15.000 productos | A los 400 MB |
| Egress (descargas) | 5 GB / mes | < 100 MB / mes | A los 4 GB |
| Realtime concurrent | 200 conexiones | 2 (una por sucursal) | Nunca |
| Database connections | 60 | < 10 (sync + dashboard) | Nunca |
| API requests | Sin límite hard, soft 500 req/seg | ~10 req/min | Nunca |
| Auth users | 50.000 | 0 | Nunca |
| **Pausa por inactividad** | 7 días sin queries → pausa proyecto | App sincroniza cada 5 min → nunca queda inactiva | Si la app no se usa por > 7 días seguidos |

**Conclusión:** con el uso actual estás muy lejos de los límites. El único
riesgo real es la pausa por inactividad si la app deja de usarse.

### Cómo monitorear

1. https://supabase.com/dashboard/project/puuxzrviijeiixcwsgle → Reports
2. Revisar al menos una vez al mes: Storage, Egress, Database connections
3. Si algo se acerca al 80% del límite, la app envía email de alerta
   `sync_quota` (ver sección Alertas).

---

## 2. Mantenimiento periódico recomendado

### Diario (automático, no requiere acción)

- **Cleanup soft-deleted**: el job `pg_cron` corre a las 03:00 UTC y borra
  filas con `deleted_at` de más de 30 días. Ya está configurado en el schema.
- **Realtime publication**: las 6 tablas están suscritas. Sin acción.

### Semanal (5 minutos)

- Verificar que el dashboard cargue sin errores. Si carga lento o tarda más
  de 10s, puede ser que la cuota de egress esté alta — revisar en el panel.
- Hacer una venta en una sucursal y confirmar que aparece en la otra en
  menos de 2s (Realtime). Si tarda más de 5s, el WebSocket se cayó y está
  usando solo polling.

### Mensual (10 minutos)

- Login en https://supabase.com/dashboard → Reports → revisar:
  - Storage usage: debería crecer ~2-5 MB por mes con uso normal
  - Egress: debería estar bien lejos del límite
- En Database → Tables → ver counts:
  - `productos`: ~15.500 (estable)
  - `ventas`: crece linealmente (~N ventas / mes)
  - `venta_items`: crece más rápido (3-10 items por venta)
- Si `ventas + venta_items` crecen mucho, considerar agregar archivado a
  un blob storage (no urgente — el free tier soporta años de operación).

### Anual (30 minutos)

- **Rotar la `sb_secret_*`**: ir a Project Settings → API → Generate new
  service_role key → actualizar en config en TODAS las sucursales.
  Por seguridad: una key vieja podría haberse filtrado en logs/screenshots.
- **Backup manual** de Supabase: Project Settings → Database → Backups →
  Download. Aunque Supabase hace backups automáticos diarios, tener uno
  propio en disco vale la pena.
- Verificar que `pg_cron` siga corriendo:
  ```sql
  select jobname, schedule, last_run_started_at, last_run_status
  from cron.job
  where jobname = 'cleanup-soft-deleted-daily';
  ```

---

## 3. Alertas configuradas

La app envía email cuando detecta problemas:

| Tipo de alerta | Cuándo se dispara | Acción recomendada |
|---|---|---|
| `sync_offline` | El pull falla 3 veces seguidas (red, Supabase down) | Revisar internet. Si Supabase está down, no se puede hacer nada — esperar. |
| `sync_write_fail` | Supabase devuelve 204 con 0 filas afectadas (typical: secret_key incorrecta) | Revisar Configuración → Sincronización. Si la secret empieza con `sb_publishable_`, está mal. |
| `sync_quota` | Reports de Supabase indica > 80% de Storage o Egress | Subir a plan pago (US$25/mes) o reducir frecuencia de sync. |
| `db_error` | Error en SQLite local | Revisar `%APPDATA%\CompraventasV2\logs\` |
| `afip_error` | Error en facturación AFIP (no relacionado con sync) | Ver log AFIP. |
| `critical` | Excepción no manejada | Ver log y reportar bug. |

Las alertas tienen cooldown de 1 hora por tipo (no spam).

Para configurar quién recibe alertas: Configuración → Alertas → email destino.

---

## 4. Si algo se rompe — runbook

### "Las ventas no se sincronizan"
1. Configuración → Sincronización → "Probar conexión".
   - Si falla con "secret_key sin permisos de escritura": pegar la
     `sb_secret_*` correcta (NO la publishable).
2. Si la prueba pasa pero sigue sin sincronizar: revisar
   `%APPDATA%\CompraventasV2\logs\sync_supabase.log`.
3. Click "Forzar descarga completa desde Supabase" para resetear cursores.

### "Faltan productos en una sucursal"
1. Configuración → Sincronización → "Refrescar contadores" (panel Estado).
2. Ver la columna "Diff": si es positiva, hay más local que en Supabase
   → click "Subir todos los datos a Supabase" en la sucursal con MÁS
   datos.
3. Si es negativa, hay más en Supabase → click "Forzar descarga completa".

### "Quiero empezar de cero"
1. Configuración → Sincronización → "⚠ Vaciar TODOS los datos en Supabase"
   (requiere password admin).
2. Una sucursal corre "Subir todos los datos a Supabase".
3. Las otras sucursales corren "Forzar descarga completa".

### "El dashboard muestra menos productos que la app"
- v6.9.3 fixeó el cap de 1000 filas con paginación. Si el dashboard sigue
  mostrando solo 1000, asegurate de tener `dashboard-supabase.html` actualizado.
- Hard refresh del browser (Ctrl+F5).

### "Veo duplicados de ventas en Supabase"
- Causa típica: `secret_key` mal configurada en alguna sucursal hizo que
  el SELECT-pre-INSERT no encontrara la fila existente.
- Limpieza: en Supabase Dashboard → Table Editor → `ventas` → ordenar por
  `numero_ticket` + filtrar por sucursal → identificar duplicados → borrar
  los más nuevos. Mantener el más viejo (por id menor).

---

## 5. Migración a Supabase pago (cuando crezca el negocio)

El plan **Pro** (US$25/mes) tiene:
- 8 GB Storage
- 50 GB Egress
- 7 días de backup automático
- Email support

No es urgente. Pasarse al Pro tiene sentido cuando:
- Storage > 400 MB en uso
- Egress mensual > 4 GB
- Necesitás backups con retención > 7 días

La migración es transparente: cambiás el plan en Dashboard → Billing →
Upgrade, no cambia nada en la app.

---

## 6. Datos sensibles y privacidad

Las tablas Supabase tienen estos datos sensibles:
- `compradores.cuit` — CUIT/CUIL de clientes
- `compradores.domicilio` — direcciones
- `ventas.cuit_cliente`, `nombre_cliente`, `domicilio_cliente` — snapshot
- `ventas.afip_cae` — números de CAE

**NO compartas** la `sb_secret_*` con nadie. Si se filtra:
1. Project Settings → API → Reset → genera una nueva.
2. Actualizar la nueva key en todas las sucursales.

La `sb_publishable_*` es pública por diseño (anon read). NO da acceso a
escribir gracias a las RLS policies del schema.

---

_Documento mantenido en `docs/MANTENIMIENTO_SUPABASE.md`. Última
actualización: v6.9.4._
