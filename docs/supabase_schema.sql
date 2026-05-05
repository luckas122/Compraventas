-- ═══════════════════════════════════════════════════════════════════════
-- SCHEMA SUPABASE — Tu local 2025 (migracion-bbdd)
-- ═══════════════════════════════════════════════════════════════════════
--
-- Cómo aplicarlo:
--   1. Ir a https://supabase.com/dashboard/project/puuxzrviijeiixcwsgle
--   2. Database → SQL Editor → New query
--   3. Copiar TODO este archivo, pegarlo y darle Run
--   4. Verificar en Table Editor que aparezcan las 6 tablas:
--      productos, proveedores, compradores, ventas, venta_items, pagos_proveedores
--
-- Es idempotente: se puede correr varias veces sin romper nada.
--
-- ═══════════════════════════════════════════════════════════════════════

-- ───── PRODUCTOS ─────
create table if not exists public.productos (
  id              bigserial primary key,
  codigo_barra    text not null unique,
  nombre          text not null,
  precio          numeric not null,
  categoria       text,
  telefono        text,
  numero_cuenta   text,
  cbu             text,
  sucursal_origen text not null,
  updated_at      timestamptz not null default now(),
  deleted_at      timestamptz
);
create index if not exists idx_productos_updated on public.productos(updated_at);
create index if not exists idx_productos_codigo  on public.productos(codigo_barra);

-- ───── PROVEEDORES ─────
create table if not exists public.proveedores (
  id              bigserial primary key,
  nombre          text not null unique,
  telefono        text,
  numero_cuenta   text,
  cbu             text,
  sucursal_origen text not null,
  updated_at      timestamptz not null default now(),
  deleted_at      timestamptz
);
create index if not exists idx_proveedores_updated on public.proveedores(updated_at);

-- ───── COMPRADORES (clientes) ─────
create table if not exists public.compradores (
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
create index if not exists idx_compradores_updated on public.compradores(updated_at);

-- ───── VENTAS ─────
create table if not exists public.ventas (
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
  -- Datos del comprador (snapshot al momento de la venta)
  cuit_cliente             text,
  nombre_cliente           text,
  domicilio_cliente        text,
  localidad_cliente        text,
  codigo_postal_cliente    text,
  condicion_cliente        text,
  -- Sync
  sucursal_origen          text not null,
  updated_at               timestamptz not null default now(),
  deleted_at               timestamptz
);
-- v6.9.3: ELIMINAR partial unique. PostgREST no soporta on_conflict con
-- partial indices y nuestro `push_venta` ya hace SELECT-then-PATCH-or-INSERT
-- manual (no necesita ON CONFLICT). Mantenemos solo indices para velocidad.
drop index if exists idx_ventas_uniq_ticket;
drop index if exists idx_ventas_uniq_ticket_cae;
create index if not exists idx_ventas_ticket
  on public.ventas(sucursal, numero_ticket) where numero_ticket is not null;
create index if not exists idx_ventas_ticket_cae
  on public.ventas(sucursal, numero_ticket_cae) where numero_ticket_cae is not null;
create index if not exists idx_ventas_updated  on public.ventas(updated_at);
create index if not exists idx_ventas_fecha    on public.ventas(fecha);
create index if not exists idx_ventas_sucursal on public.ventas(sucursal);

-- ───── VENTA_ITEMS ─────
create table if not exists public.venta_items (
  id           bigserial primary key,
  venta_id     bigint not null references public.ventas(id) on delete cascade,
  codigo_barra text,
  nombre       text,
  cantidad     integer not null,
  precio_unit  numeric not null
);
create index if not exists idx_venta_items_venta on public.venta_items(venta_id);

-- ───── PAGOS A PROVEEDORES ─────
create table if not exists public.pagos_proveedores (
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
  deleted_at        timestamptz
);
create unique index if not exists idx_pagos_uniq_ticket
  on public.pagos_proveedores(sucursal, numero_ticket) where numero_ticket is not null;
create index if not exists idx_pagos_updated on public.pagos_proveedores(updated_at);

-- ═══ TRIGGERS: actualizar updated_at en cada UPDATE ═══
create or replace function public.touch_updated_at() returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists trg_productos_touch          on public.productos;
drop trigger if exists trg_proveedores_touch        on public.proveedores;
drop trigger if exists trg_compradores_touch        on public.compradores;
drop trigger if exists trg_ventas_touch             on public.ventas;
drop trigger if exists trg_pagos_touch              on public.pagos_proveedores;

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

-- ═══ ROW LEVEL SECURITY ═══
alter table public.productos          enable row level security;
alter table public.proveedores        enable row level security;
alter table public.compradores        enable row level security;
alter table public.ventas             enable row level security;
alter table public.venta_items        enable row level security;
alter table public.pagos_proveedores  enable row level security;

-- Lectura: pública (anon key + service_role bypass)
drop policy if exists "Allow read all" on public.productos;
drop policy if exists "Allow read all" on public.proveedores;
drop policy if exists "Allow read all" on public.compradores;
drop policy if exists "Allow read all" on public.ventas;
drop policy if exists "Allow read all" on public.venta_items;
drop policy if exists "Allow read all" on public.pagos_proveedores;

create policy "Allow read all" on public.productos          for select using (true);
create policy "Allow read all" on public.proveedores        for select using (true);
create policy "Allow read all" on public.compradores        for select using (true);
create policy "Allow read all" on public.ventas             for select using (true);
create policy "Allow read all" on public.venta_items        for select using (true);
create policy "Allow read all" on public.pagos_proveedores  for select using (true);

-- v6.9.3: policies WRITE explicitas para service_role como defensa en profundidad.
-- Aunque service_role normalmente bypassa RLS, hacerlo explicito evita sorpresas
-- si la role mapping cambia. Anon (publishable) NO tiene policy de WRITE — eso es
-- intencional: el dashboard usa publishable y no debe poder escribir.

drop policy if exists "Service role write" on public.productos;
drop policy if exists "Service role write" on public.proveedores;
drop policy if exists "Service role write" on public.compradores;
drop policy if exists "Service role write" on public.ventas;
drop policy if exists "Service role write" on public.venta_items;
drop policy if exists "Service role write" on public.pagos_proveedores;

create policy "Service role write" on public.productos          for all to service_role using (true) with check (true);
create policy "Service role write" on public.proveedores        for all to service_role using (true) with check (true);
create policy "Service role write" on public.compradores        for all to service_role using (true) with check (true);
create policy "Service role write" on public.ventas             for all to service_role using (true) with check (true);
create policy "Service role write" on public.venta_items        for all to service_role using (true) with check (true);
create policy "Service role write" on public.pagos_proveedores  for all to service_role using (true) with check (true);

-- Tambien grant a la role
grant all on public.productos          to service_role;
grant all on public.proveedores        to service_role;
grant all on public.compradores        to service_role;
grant all on public.ventas             to service_role;
grant all on public.venta_items        to service_role;
grant all on public.pagos_proveedores  to service_role;

-- ═══ REALTIME: habilitar replication para WebSocket ═══
-- Para que start_realtime() reciba INSERT/UPDATE/DELETE en vivo.
-- Wrap en DO blocks: alter publication add table NO es idempotente y falla
-- con 42710 si la tabla ya esta en la publication. Los DO con catch lo
-- hacen seguro de re-ejecutar.
do $$ begin alter publication supabase_realtime add table public.productos;
  exception when duplicate_object then null; end $$;
do $$ begin alter publication supabase_realtime add table public.proveedores;
  exception when duplicate_object then null; end $$;
do $$ begin alter publication supabase_realtime add table public.compradores;
  exception when duplicate_object then null; end $$;
do $$ begin alter publication supabase_realtime add table public.ventas;
  exception when duplicate_object then null; end $$;
do $$ begin alter publication supabase_realtime add table public.venta_items;
  exception when duplicate_object then null; end $$;
do $$ begin alter publication supabase_realtime add table public.pagos_proveedores;
  exception when duplicate_object then null; end $$;

-- ═══ VIEWS de "solo activos" (v6.8.4) ═══
-- Cada tabla soportada con soft-delete tiene su VIEW que filtra deleted_at IS NULL.
-- Para consultas desde la app o el panel: ver `productos_activos` en lugar de `productos`.
--
-- v6.9.1: WITH (security_invoker=true) hace que la view respete las RLS policies
-- de la tabla subyacente (en lugar de correr como el creador, que bypassa RLS).
-- Esto quita el badge "UNRESTRICTED" en el panel de Supabase.

create or replace view public.productos_activos
  with (security_invoker=true) as
  select * from public.productos where deleted_at is null;

create or replace view public.proveedores_activos
  with (security_invoker=true) as
  select * from public.proveedores where deleted_at is null;

create or replace view public.compradores_activos
  with (security_invoker=true) as
  select * from public.compradores where deleted_at is null;

create or replace view public.ventas_activas
  with (security_invoker=true) as
  select * from public.ventas where deleted_at is null;

create or replace view public.pagos_proveedores_activos
  with (security_invoker=true) as
  select * from public.pagos_proveedores where deleted_at is null;

-- Permitir lectura anon de las views (la security_invoker delega a las RLS de la tabla)
grant select on public.productos_activos          to anon, authenticated;
grant select on public.proveedores_activos        to anon, authenticated;
grant select on public.compradores_activos        to anon, authenticated;
grant select on public.ventas_activas             to anon, authenticated;
grant select on public.pagos_proveedores_activos  to anon, authenticated;

-- ═══ CLEANUP AUTOMATICO de filas soft-deleted (v6.8.4) ═══
-- Funcion que hard-deletea filas con deleted_at de mas de N dias.
-- Despues de N dias todas las sucursales tuvieron tiempo de procesar la baja.

create or replace function public.cleanup_soft_deleted(days_old int default 30)
returns table(tabla text, eliminadas bigint)
language plpgsql
security definer
as $$
declare
  cutoff timestamptz := now() - (days_old || ' days')::interval;
  n bigint;
begin
  delete from public.productos          where deleted_at < cutoff; get diagnostics n = row_count;
  return query select 'productos'::text, n;

  delete from public.proveedores        where deleted_at < cutoff; get diagnostics n = row_count;
  return query select 'proveedores'::text, n;

  delete from public.compradores        where deleted_at < cutoff; get diagnostics n = row_count;
  return query select 'compradores'::text, n;

  delete from public.ventas             where deleted_at < cutoff; get diagnostics n = row_count;
  return query select 'ventas'::text, n;
  -- venta_items se borra cascade (ON DELETE CASCADE en venta_id)

  delete from public.pagos_proveedores  where deleted_at < cutoff; get diagnostics n = row_count;
  return query select 'pagos_proveedores'::text, n;
end;
$$;

-- pg_cron: schedule diario a las 03:00 UTC (00:00 hora AR)
-- Si pg_cron no esta habilitado, este bloque va a fallar — habilitalo en
-- Supabase Dashboard -> Database -> Extensions -> buscar "pg_cron" -> Enable.
do $$
begin
  -- Enable extension if posible (puede requerir permisos extra; si falla,
  -- el usuario debe habilitarla desde el dashboard)
  create extension if not exists pg_cron;
exception when others then
  raise notice 'pg_cron no disponible automaticamente. Habilitalo desde Supabase Dashboard > Database > Extensions.';
end $$;

-- Reprogramar idempotente: borrar el schedule anterior si existe, luego crear uno nuevo
do $$
begin
  if exists (select 1 from pg_extension where extname = 'pg_cron') then
    perform cron.unschedule('cleanup-soft-deleted-daily');
  end if;
exception when others then
  null;  -- ignorar "job no existe"
end $$;

do $$
begin
  if exists (select 1 from pg_extension where extname = 'pg_cron') then
    perform cron.schedule(
      'cleanup-soft-deleted-daily',
      '0 3 * * *',  -- 03:00 UTC = 00:00 AR
      $cron$select public.cleanup_soft_deleted(30)$cron$
    );
    raise notice 'Cleanup automatico programado: diariamente 03:00 UTC, retencion 30 dias.';
  else
    raise notice 'pg_cron no esta habilitado. Cleanup quedara manual (correr public.cleanup_soft_deleted(30) cuando quieras).';
  end if;
end $$;

-- ═══════════════════════════════════════════════════════════════════════
-- FIN — Si no hay errores, todo listo.
-- Verificar:
--   SELECT count(*) from public.productos;          -> total (incluye soft-deleted)
--   SELECT count(*) from public.productos_activos;  -> solo activos
--   SELECT * from public.cleanup_soft_deleted(30);  -> ejecucion manual del cleanup
-- ═══════════════════════════════════════════════════════════════════════
