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
-- Únicos parciales: solo cuando el campo no es null (admite multiples ventas con ticket=null)
create unique index if not exists idx_ventas_uniq_ticket
  on public.ventas(sucursal, numero_ticket) where numero_ticket is not null;
create unique index if not exists idx_ventas_uniq_ticket_cae
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

-- Escritura: solo service_role (que bypassa RLS sin policies adicionales)
-- Nota: la app usa la sb_secret_* que es service_role → puede escribir todo.
-- El dashboard usa la sb_publishable_* que es anon → solo lee.

-- ═══ REALTIME: habilitar replication para WebSocket ═══
-- Para que start_realtime() reciba INSERT/UPDATE/DELETE en vivo
alter publication supabase_realtime add table public.productos;
alter publication supabase_realtime add table public.proveedores;
alter publication supabase_realtime add table public.compradores;
alter publication supabase_realtime add table public.ventas;
alter publication supabase_realtime add table public.venta_items;
alter publication supabase_realtime add table public.pagos_proveedores;

-- ═══════════════════════════════════════════════════════════════════════
-- FIN — Si no hay errores, todo listo.
-- Verificar: SELECT count(*) from public.productos;  -> debería devolver 0
-- ═══════════════════════════════════════════════════════════════════════
