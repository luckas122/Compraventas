# scripts/diff_backends.py
# -*- coding: utf-8 -*-
"""
Auditoria de paridad: cuenta filas en SQLite local, Firebase y Supabase y
muestra una tabla comparativa.

Util durante Fase 3 (modo dual) para verificar que ambos backends quedan
identicos antes del cutover.

Uso:
    python scripts/diff_backends.py
    python scripts/diff_backends.py --json     # output legible por scripts
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app.config import load as load_config             # noqa: E402
from app.database import SessionLocal                   # noqa: E402
from app.supabase_sync import TABLA_DE_TIPO             # noqa: E402
from app.models import Producto, Proveedor, Comprador, Venta, PagoProveedor  # noqa: E402

TIPO_MODELO = {
    "productos": Producto,
    "proveedores": Proveedor,
    "compradores": Comprador,
    "ventas": Venta,
    "pagos_proveedores": PagoProveedor,
}


def count_local(session) -> dict:
    return {tipo: session.query(modelo).count()
            for tipo, modelo in TIPO_MODELO.items()}


def count_firebase(cfg) -> dict:
    """Cuenta entradas en cambios/{tipo}/ con shallow=true (gratis en cuota)."""
    fb = (cfg.get("sync") or {}).get("firebase") or {}
    db_url = (fb.get("database_url") or "").rstrip("/")
    token = fb.get("auth_token") or ""
    out = {}
    for tipo in TIPO_MODELO.keys():
        if not db_url:
            out[tipo] = -1
            continue
        try:
            url = f"{db_url}/cambios/{tipo}.json?shallow=true&auth={token}"
            r = requests.get(url, timeout=15)
            if r.status_code == 200:
                data = r.json() or {}
                out[tipo] = len(data) if isinstance(data, dict) else 0
            else:
                out[tipo] = -1
        except Exception:
            out[tipo] = -1
    return out


def count_supabase(cfg) -> dict:
    """Cuenta filas activas (deleted_at IS NULL) por tabla."""
    sb = (cfg.get("sync") or {}).get("supabase") or {}
    url = (sb.get("url") or "").rstrip("/")
    secret = sb.get("secret_key") or ""
    out = {}
    for tipo in TIPO_MODELO.keys():
        if not url or not secret:
            out[tipo] = -1
            continue
        try:
            r = requests.get(
                f"{url}/rest/v1/{TABLA_DE_TIPO[tipo]}",
                params={"select": "id", "limit": "0", "deleted_at": "is.null"},
                headers={"apikey": secret, "Prefer": "count=exact"},
                timeout=15,
            )
            if r.status_code in (200, 206):
                cr = r.headers.get("Content-Range", "")
                if "/" in cr:
                    out[tipo] = int(cr.split("/")[-1])
                else:
                    out[tipo] = 0
            else:
                out[tipo] = -1
        except Exception:
            out[tipo] = -1
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Diff de conteos local / Firebase / Supabase")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    cfg = load_config()
    session = SessionLocal()

    local = count_local(session)
    firebase = count_firebase(cfg)
    supabase = count_supabase(cfg)

    if args.json:
        print(json.dumps({
            "local": local, "firebase": firebase, "supabase": supabase,
        }, indent=2))
        return 0

    print("Diff de conteos por tipo:")
    print(f"  {'tipo':<22} {'local':>10} {'firebase':>10} {'supabase':>10}   {'diff fb':>8} {'diff sb':>8}")
    print("  " + "─" * 78)
    todo_ok = True
    for tipo in TIPO_MODELO.keys():
        l, f, s = local.get(tipo, 0), firebase.get(tipo, -1), supabase.get(tipo, -1)
        df = (f - l) if f >= 0 else "?"
        ds = (s - l) if s >= 0 else "?"
        if df != 0 or ds != 0:
            todo_ok = False
        flag_f = "OK" if df == 0 else (str(df) if df != "?" else "??")
        flag_s = "OK" if ds == 0 else (str(ds) if ds != "?" else "??")
        f_disp = "??" if f < 0 else str(f)
        s_disp = "??" if s < 0 else str(s)
        print(f"  {tipo:<22} {l:>10} {f_disp:>10} {s_disp:>10}   {flag_f:>8} {flag_s:>8}")
    print()
    if todo_ok:
        print("✓ Todos los backends en paridad.")
        return 0
    print("⚠ Diferencias detectadas. Revisar push pendiente o cola offline.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
