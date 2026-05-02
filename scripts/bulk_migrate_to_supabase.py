# scripts/bulk_migrate_to_supabase.py
# -*- coding: utf-8 -*-
"""
Bulk migration de los datos LOCALES de SQLite a Supabase.

Lo corres UNA VEZ en la PC madre (Sarmiento) cuando ya tenes el schema Supabase
creado y la app configurada con backend en Supabase o Dual.

Idempotente: usa UPSERT por unique key (codigo_barra, nombre, cuit, etc.).
Si lo corres dos veces no rompe nada — la segunda vez sera un no-op por fila.

Uso:
    python scripts/bulk_migrate_to_supabase.py
    python scripts/bulk_migrate_to_supabase.py --tipos productos,proveedores
    python scripts/bulk_migrate_to_supabase.py --dry-run

Tipos disponibles:
    productos, proveedores, compradores, ventas, pagos_proveedores
    Si no se especifica --tipos, sube todos.
"""
from __future__ import annotations

import argparse
import os
import sys
import time

# Asegurar que la app sea importable desde la raiz del repo
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app.config import load as load_config  # noqa: E402
from app.database import SessionLocal       # noqa: E402
from app.supabase_sync import (              # noqa: E402
    SupabaseSyncManager, TIPOS_BACKEND, TABLA_DE_TIPO,
)
from app.models import (                     # noqa: E402
    Producto, Proveedor, Comprador, Venta, PagoProveedor,
)


TIPO_MODELO = {
    "productos": Producto,
    "proveedores": Proveedor,
    "compradores": Comprador,
    "ventas": Venta,
    "pagos_proveedores": PagoProveedor,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Bulk migrate SQLite local -> Supabase")
    parser.add_argument(
        "--tipos", default=",".join(TIPOS_BACKEND),
        help=f"Tipos a migrar (csv). Default: todos ({','.join(TIPOS_BACKEND)})",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Solo muestra los conteos locales y los conteos en Supabase, no sube nada.",
    )
    parser.add_argument(
        "--sucursal", default=None,
        help="Sucursal local (override). Si no, lee de app_config.json.",
    )
    args = parser.parse_args()

    tipos = [t.strip() for t in args.tipos.split(",") if t.strip()]
    invalidos = [t for t in tipos if t not in TIPOS_BACKEND]
    if invalidos:
        print(f"ERROR: tipos invalidos: {invalidos}")
        print(f"Tipos validos: {TIPOS_BACKEND}")
        return 2

    cfg = load_config()
    sync_cfg = (cfg.get("sync") or {})
    sucursal = args.sucursal or cfg.get("sucursal_actual") or "Sarmiento"
    print(f"Sucursal local: {sucursal}")
    sb_cfg = sync_cfg.get("supabase") or {}
    if not sb_cfg.get("url") or not sb_cfg.get("secret_key"):
        print("ERROR: Supabase no esta configurado. Abrir la app -> Configuracion -> "
              "Sincronizacion -> Backend = Supabase, llenar URL + secret y guardar.")
        return 2

    print(f"Supabase URL: {sb_cfg.get('url')}")
    print()

    session = SessionLocal()
    mgr = SupabaseSyncManager(session, sucursal)

    # ─── Conteos ANTES ─────────────────────────────────────────────
    print("Conteos ANTES (local vs Supabase):")
    print(f"  {'tipo':<22} {'local':>10} {'supabase':>10}")
    locales = {}
    remotos_pre = {}
    for tipo in tipos:
        modelo = TIPO_MODELO[tipo]
        n_local = session.query(modelo).count()
        locales[tipo] = n_local
        n_remoto = mgr._rest_count(TABLA_DE_TIPO[tipo])
        remotos_pre[tipo] = n_remoto
        print(f"  {tipo:<22} {n_local:>10} {n_remoto:>10}")
    print()

    if args.dry_run:
        print("--dry-run: no se sube nada. Salgo.")
        return 0

    if all(remotos_pre.get(t, 0) >= locales.get(t, 0) for t in tipos):
        confirm = input(
            "Supabase ya tiene >= que local en todos los tipos seleccionados. "
            "¿Subir igual? (s/N): "
        ).strip().lower()
        if confirm != "s":
            print("Abortado por el usuario.")
            return 0

    # ─── Bulk push ──────────────────────────────────────────────────
    print(f"Subiendo a Supabase: tipos={tipos}")
    t0 = time.time()

    def cb(current, total, t):
        sys.stdout.write(f"\r  [{t}] {current}/{total}     ")
        sys.stdout.flush()

    result = mgr.push_all_existing(callback=cb, tipos=set(tipos))
    print()  # newline despues del callback
    print(f"Subida tardo {time.time() - t0:.1f}s")
    print()

    # ─── Conteos DESPUES ──────────────────────────────────────────
    print("Conteos DESPUES (local vs Supabase, diff):")
    print(f"  {'tipo':<22} {'local':>10} {'supabase':>10} {'subidos':>10} {'diff':>8}")
    todo_ok = True
    for tipo in tipos:
        modelo = TIPO_MODELO[tipo]
        n_local = session.query(modelo).count()
        n_remoto = mgr._rest_count(TABLA_DE_TIPO[tipo])
        n_subidos = result.get(tipo, 0)
        diff = n_local - n_remoto
        flag = "OK ✓" if diff == 0 else f"⚠ {diff:+d}"
        if diff != 0:
            todo_ok = False
        print(f"  {tipo:<22} {n_local:>10} {n_remoto:>10} {n_subidos:>10} {flag:>8}")
    print()
    errs = result.get("errores", 0)
    if errs:
        print(f"⚠  {errs} errores durante el bulk push (revisa sync_supabase.log)")
    if todo_ok and not errs:
        print("✓ TODO OK — migracion completa.")
        return 0
    print("⚠ Hubo discrepancias o errores. Re-correr el script puede arreglarlas (es idempotente).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
