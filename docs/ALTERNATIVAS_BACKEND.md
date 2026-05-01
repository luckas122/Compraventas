# Migración a Supabase — Plan completo

> **Estado:** documento de migración (no solo evaluación). Todo el trabajo
> técnico lo hago yo (Claude). Vos solo hacés un par de clicks que requieren tu
> cuenta personal — están marcados con ⚠️ **TAREA TUYA** abajo.
>
> **Última actualización:** v6.7.1.

---

## 1. ¿Por qué migrar? — los problemas concretos que sufrimos hoy

Después de v6.7.0/v6.7.1 quedan estos síntomas que son **del modelo de Firebase
Realtime Database**, no de la implementación:

| Problema observado | Causa raíz Firebase | Cómo lo resuelve Supabase |
|---|---|---|
| Borrados de venta no se propagan (fix manual en v6.7.1) | RTDB no tiene UPSERT real, todo son eventos append-only | Postgres tiene `delete from ventas where id=N` real |
| "Bus de cambios/" se llena y hay que limpiar | Eventos infinitos que viven en `cambios/` | No existe el concepto: el estado vive en las tablas |
| `diagnose_full` cuesta cuota y es lento | Recorrer todo el árbol con shallow | `select count(*)` es instantáneo |
| Sync cada 2-5 min | Pull manual con paginación de keys | WebSocket realtime: cambios aparecen en <1s |
| NCs huérfanas si se borra el bus | Los eventos se pierden si cleanup borra antes que la otra sucursal pulle | Tabla `ventas` tiene la NC como columna; no se pierde |
| Dashboard tiene que reconstruir estado mergeando creates+updates | RTDB es un log de eventos | Dashboard hace `select * from ventas` y listo |
| Ventas viejas tarjeta sin CAE/comprobante en el dashboard | Datos antiguos sin esos campos en el push | Misma data, pero más fácil de "reparar" con UPDATE en SQL |
| Latencia desde Argentina (~300ms) | Servidor en us-central1 | Servidor en sa-east-1 São Paulo (~80ms) |

**Conclusión:** Firebase RTDB no es el modelo correcto para sync de bases de
datos relacionales con borrados. Está pensado para chats / feeds / notificaciones,
no para "espejar el estado de una tabla". Supabase (Postgres) es el modelo correcto.

---

## 2. Comparativa rápida (referencia)

| Aspecto | Firebase RTDB (actual) | Supabase (recomendado) |
|---|---|---|
| Modelo | Árbol JSON, key-value, append-only | Postgres + REST + Realtime |
| Free tier | 1 GB stored, 10 GB egress/mes | 500 MB DB, 5 GB egress/mes |
| Latencia AR | us-central1 (~300ms) | sa-east-1 São Paulo (~80ms) |
| Backups | Manual (export JSON) | Automáticos diarios |
| Borrados reales | No (workaround manual) | Sí (`delete` SQL) |
| Diff local↔backend | Caro (recorrer todo) | `select count` instantáneo |
| Dashboard estático | ✅ REST con auth token | ✅ REST con `anon key` |
| Realtime push | Polling 2-5 min | WebSocket <1s |
| Filtros / queries | Limitadísimos | SQL completo |
| Cuello de botella | Cola serializada | Bulk insert nativo |
| Pause si inactivo | No | 7 días sin actividad → pausa (no aplica con sync 5 min) |

Otras opciones evaluadas y descartadas: PocketBase (requiere VPS),
Cloudflare D1 + Workers (requiere escribir Worker proxy),
Appwrite Cloud (latencia AR peor), Neon Postgres (sin REST nativo).

---

## 3. Schema final propuesto en Supabase

Cada tabla tiene 3 columnas extra para sync (`sucursal_origen`, `updated_at`,
`deleted_at`). El `deleted_at` permite soft-delete: en lugar de borrar la fila,
se marca como borrada — así el pull de las otras sucursales recoge la baja.

```sql
-- ═══════════════════════════════════════════════════════════════════════
-- SCHEMA SUPABASE — TU LOCAL 2025
-- ═══════════════════════════════════════════════════════════════════════

-- ═══ PRODUCTOS ═══
create table public.productos (
  id              bigserial primary key,
  codigo_barra    text not null unique,
  nombre          text not null,
  precio          numeric not null,
  categoria       text,
  telefono        text,
  numero_cuenta   text,
  cbu             text,
  -- columnas de sync
  sucursal_origen text not null,
  updated_at      timestamptz not null default now(),
  deleted_at      timestamptz                                   -- soft-delete
);
create index idx_productos_updated on public.productos(updated_at);
create index idx_productos_codigo  on public.productos(codigo_barra);

-- ═══ PROVEEDORES ═══
create table public.proveedores (
  id              bigserial primary key,
  nombre          text not null unique,
  telefono        text,
  numero_cuenta   text,
  cbu             text,
  sucursal_origen text not null,
  updated_at      timestamptz not null default now(),
  deleted_at      timestamptz
);
create index idx_proveedores_updated on public.proveedores(updated_at);

-- ═══ COMPRADORES (clientes) ═══
create table public.compradores (
  id              bigserial primary key,
  cuit            text not null unique,
  nombre          text,
  domicilio       text,
  localidad       text,
  codigo_postal   text,
  condicion       text,
  sucursal_origen text not null,
  updated_at      timestamptz not null default now(),
  deleted_at      timestamptz
);
create index idx_compradores_updated on public.compradores(updated_at);

-- ═══ VENTAS ═══
create table public.ventas (
  id                       bigserial primary key,
  -- Identificadores propios
  sucursal                 text not null,
  numero_ticket            integer,
  numero_ticket_cae        integer,
  -- Datos de venta
  fecha                    timestamptz not null,
  modo_pago                text not null,
  cuotas                   integer,
  total                    numeric not null,
  subtotal_base            numeric default 0,
  interes_pct              numeric default 0,
  interes_monto            numeric default 0,
  descuento_pct            numeric default 0,
  descuento_monto          numeric default 0,
  pagado                   numeric,
  vuelto                   numeric,
  -- AFIP
  afip_cae                 text,
  afip_cae_vencimiento     text,
  afip_numero_comprobante  bigint,
  tipo_comprobante         text,
  punto_venta              integer,
  -- Notas de Crédito
  nota_credito_cae         text,
  nota_credito_numero      bigint,
  -- Datos del comprador (snapshot)
  cuit_cliente             text,
  nombre_cliente           text,
  domicilio_cliente        text,
  localidad_cliente        text,
  codigo_postal_cliente    text,
  condicion_cliente        text,
  -- Sync
  sucursal_origen          text not null,
  updated_at               timestamptz not null default now(),
  deleted_at               timestamptz,
  -- Restricción única por sucursal+ticket: evita duplicados al sincronizar
  unique (sucursal, numero_ticket),
  unique (sucursal, numero_ticket_cae)
);
create index idx_ventas_updated  on public.ventas(updated_at);
create index idx_ventas_fecha    on public.ventas(fecha);
create index idx_ventas_sucursal on public.ventas(sucursal);

-- ═══ VENTA_ITEMS ═══
create table public.venta_items (
  id           bigserial primary key,
  venta_id     bigint not null references public.ventas(id) on delete cascade,
  codigo_barra text,
  nombre       text,
  cantidad     integer not null,
  precio_unit  numeric not null
);
create index idx_venta_items_venta on public.venta_items(venta_id);

-- ═══ PAGOS A PROVEEDORES ═══
create table public.pagos_proveedores (
  id                bigserial primary key,
  sucursal          text not null,
  numero_ticket     integer,
  fecha             timestamptz not null,
  proveedor_nombre  text not null,
  monto             numeric not null,
  metodo_pago       text default 'Efectivo',
  pago_de_caja      boolean default false,
  incluye_iva       boolean default false,
  nota              text,
  sucursal_origen   text not null,
  updated_at        timestamptz not null default now(),
  deleted_at        timestamptz,
  unique (sucursal, numero_ticket)
);
create index idx_pagos_updated on public.pagos_proveedores(updated_at);

-- ═══ TRIGGER: actualizar updated_at en cada UPDATE ═══
create or replace function public.touch_updated_at() returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

create trigger trg_productos_touch         before update on public.productos
  for each row execute function public.touch_updated_at();
create trigger trg_proveedores_touch       before update on public.proveedores
  for each row execute function public.touch_updated_at();
create trigger trg_compradores_touch       before update on public.compradores
  for each row execute function public.touch_updated_at();
create trigger trg_ventas_touch            before update on public.ventas
  for each row execute function public.touch_updated_at();
create trigger trg_pagos_touch             before update on public.pagos_proveedores
  for each row execute function public.touch_updated_at();
```

### Row Level Security (RLS)

```sql
-- ═══ POLICIES ═══
-- Lectura: pública con anon key (el dashboard la usa)
-- Escritura: solo con service_role key (que vive en la app de escritorio)
alter table public.productos          enable row level security;
alter table public.proveedores        enable row level security;
alter table public.compradores        enable row level security;
alter table public.ventas             enable row level security;
alter table public.venta_items        enable row level security;
alter table public.pagos_proveedores  enable row level security;

-- Read all (anon + authenticated)
create policy "Allow read"   on public.productos          for select using (true);
create policy "Allow read"   on public.proveedores        for select using (true);
create policy "Allow read"   on public.compradores        for select using (true);
create policy "Allow read"   on public.ventas             for select using (true);
create policy "Allow read"   on public.venta_items        for select using (true);
create policy "Allow read"   on public.pagos_proveedores  for select using (true);

-- service_role bypassa RLS por default — la app usa esa key.
```

---

## 4. Plan de migración paso a paso

### Fase 0 — Pre-requisitos (⚠️ TAREA TUYA, ~10 min)

Necesito que hagas esto **una sola vez** y me pases las credenciales:

1. **Crear cuenta en Supabase** — https://supabase.com
   - Botón "Start your project". Loggeate con GitHub o email.
2. **Crear un proyecto nuevo:**
   - Nombre: `tu-local-2025`
   - **Region: South America (São Paulo)** — IMPORTANTE para latencia AR.
   - Database password: anotala (yo no la voy a usar, pero la necesitás vos para
     entrar al panel después).
   - Plan: Free.
   - Esperá ~2 min a que diga "Project is healthy".
3. **Pasarme estos 3 datos** (los buscás en `Project Settings > API`):
   - **Project URL** (algo como `https://xxxxx.supabase.co`)
   - **anon / public key** (token largo que empieza con `eyJ...`)
   - **service_role key** (otro token largo, **mantenelo en secreto**, no lo
     pegues en chats públicos)

Eso es **todo** lo que vos hacés. El resto lo hago yo.

### Fase 1 — Setup técnico en la rama `migracion-bbdd` (yo, ~3 días)

1. Crear el schema en Supabase ejecutando el SQL del punto 3
   (Database > SQL Editor > New query → pegar → Run).
2. Configurar las RLS policies.
3. Crear `app/supabase_sync.py` con la misma API que `firebase_sync.py`:
   - `push_producto`, `push_proveedor`, `push_comprador`, `push_venta`,
     `push_venta_eliminada`, `push_pago_proveedor`, etc.
   - Pero usando `requests.post/.patch` contra `https://xxxxx.supabase.co/rest/v1/{tabla}`
     con header `apikey: <service_role>` y `Prefer: resolution=merge-duplicates`
     (UPSERT real).
   - `pull_changes` usa `GET /rest/v1/{tabla}?updated_at=gt.{cursor}&order=updated_at.asc`.
   - El cursor pasa de "Firebase push key" a "timestamp del último update visto" — más simple.
4. Agregar columna `deleted_at` al modelo SQLite local (migración idempotente
   en `database._run_migrations`). Esto permite que el delete local también
   pueda hacerse "soft" si algún día queremos.
5. Toggle en `app_config.json`: `sync.backend = "firebase" | "supabase"`. Por
   default queda `firebase`. Al activar `supabase`, el `MainWindow` instancia
   `SupabaseSyncManager` en lugar de `FirebaseSyncManager`. Las llamadas
   `_sync_push("venta", venta)` etc. siguen funcionando porque la API es
   idéntica.
6. Dashboard: nuevo `dashboard/dashboard-supabase.html` que en vez de pegarle a
   Firebase pega a Supabase REST. Mismo HTML / CSS / lógica de cards y tabla,
   solo cambia la capa de carga (1 función `cargarDatos()`).

### Fase 2 — Bulk migration de datos existentes (yo, ~1 día)

1. Script `scripts/migrate_firebase_to_supabase.py` que:
   - Lee SQLite local (la sucursal "madre" Sarmiento).
   - Bulk-inserta cada tabla a Supabase con UPSERT.
   - Verifica conteos al final (local count == Supabase count).
2. Otra sucursal (Salta) NO migra datos — los recibe haciendo "force pull"
   contra Supabase como hoy hace contra Firebase.

### Fase 3 — Doble-sync paralelo (~1 semana)

1. Activar `sync.backend = "supabase"` en Sarmiento.
2. Mantener Firebase también activo en paralelo (push a ambos, pull desde
   Supabase). Esto valida que no se pierde data.
3. Comparar cada día: cantidad de ventas en Firebase vs. cantidad en Supabase.
   Si coinciden 7 días seguidos, listo.

### Fase 4 — Cutover (yo, ~1 día)

1. Activar `sync.backend = "supabase"` en Salta.
2. Dejar de pushear a Firebase (1 line change).
3. Reemplazar `dashboard/dashboard.html` por la versión Supabase.
4. Build v7.0.0 con backend Supabase como default.

### Fase 5 — Apagar Firebase (~1 día, después de 2 semanas estables)

1. Export final de Firebase (backup por si las moscas).
2. Borrar el proyecto Firebase (o dejarlo dormido — es free).
3. Documentar el cambio en CLAUDE.md.

---

## 5. ¿Qué cambia para vos como usuario final?

### Cosas que **no cambian** (van a seguir igual):
- La app de escritorio se ve igual.
- Los tickets se imprimen igual.
- AFIP / CAE / NC siguen igual.
- Los Excel de productos siguen igual.
- Backups siguen igual.

### Cosas que **mejoran**:
- Borrar una venta o producto en una sucursal **se ve en la otra en segundos**
  (no minutos).
- El dashboard carga en 2-3 segundos (vs 10-20 hoy).
- El dashboard puede tener filtros más potentes (top 10 productos, ventas por
  hora, etc.) — agregables en el futuro.
- "Verificar pendientes" muestra el diff exacto sin gastar cuota.
- Si hay un conflicto de datos lo podés resolver en SQL desde el panel web de
  Supabase (vista de tabla, edit en celda).
- No más "se trabó la sync" — Postgres no tiene esos modos raros.

### Cosas que **podrían empeorar**:
- Si pasan 7 días enteros sin que ninguna sucursal abra la app, el proyecto
  Supabase se pausa. Al reabrir tarda 30 segundos en despertar. (En la
  práctica con sync cada 5 min nunca pasa.)
- Hay un costo de aprendizaje **mío** las primeras semanas mientras me adapto
  al modelo nuevo (vos no notás nada).

---

## 6. Riesgos y plan de rollback

### Riesgos
- **R1:** Bug en `supabase_sync.py` que pierda datos. **Mitigación:**
  Fase 3 mantiene Firebase activo en paralelo durante 1 semana antes del
  cutover. Si algo falla, se vuelve a Firebase con un cambio de 1 línea.
- **R2:** Cuota Supabase excedida. **Mitigación:** monitorear el dashboard del
  proyecto Supabase la primera semana; si se acerca al límite, ajustar la
  frecuencia de sync o pasar a un plan pago (US$25/mes). Para tu volumen actual
  esto es muy improbable.
- **R3:** Algo del dashboard HTML rompe. **Mitigación:** mantener
  `dashboard.html` (Firebase) y `dashboard-supabase.html` en paralelo durante
  el cutover. Si uno falla se usa el otro.

### Rollback
- **Antes del cutover (Fase 4):** trivial — toggle `sync.backend = "firebase"`.
- **Después del cutover y antes de Fase 5:** todavía está Firebase con la data,
  toggle de vuelta + force pull desde Firebase para recuperar lo perdido.
- **Después de Fase 5:** Firebase ya no se actualiza pero la última snapshot
  está exportada en backup. Recuperación manual desde ese JSON.

---

## 7. Cronograma realista

| Fase | Duración | Quién | Bloqueante de |
|---|---|---|---|
| 0 — Pre-requisitos | 10 min | Vos | Todo lo demás |
| 1 — Setup técnico | 3 días | Yo | Fase 2 |
| 2 — Bulk migration | 1 día | Yo | Fase 3 |
| 3 — Doble-sync paralelo | 7 días | Yo (correr) + Vos (usar app normal) | Fase 4 |
| 4 — Cutover | 1 día | Yo | Fase 5 |
| 5 — Apagar Firebase | 1 día | Yo | — |

**Total: ~14 días calendario.** Trabajo activo mío: ~6 días.

---

## 8. Checkpoints visibles para vos

Cada fase termina con algo concreto que vos podés validar:

- **Fin Fase 1:** te paso una URL del dashboard nuevo y vos abrís y ves los
  primeros datos sincronizados (un par de ventas de prueba).
- **Fin Fase 2:** en el panel de Supabase ves todas las tablas pobladas con la
  data de Sarmiento.
- **Fin Fase 3:** te muestro cada día un screenshot del comparador "Firebase
  vs Supabase". Cuando 7 días seguidos el diff es 0, pasamos al cutover.
- **Fin Fase 4:** instalador v7.0.0 con backend Supabase como default.
- **Fin Fase 5:** Firebase apagado. Documentado.

---

## 9. Empezamos cuando vos quieras

Aislé el trabajo en la rama `migracion-bbdd` (creada en este commit) para que
el `main` siga estable con Firebase. Cuando tengamos los 3 datos de la Fase 0,
arranco con la Fase 1.

> _Documento mantenido en `docs/ALTERNATIVAS_BACKEND.md`. Última actualización:
> v6.7.1._
