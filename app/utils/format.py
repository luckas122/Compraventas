# app/utils/format.py
# -*- coding: utf-8 -*-
"""
Helpers de formato para moneda y cantidades en formato Argentina.

Convenciones Argentina:
    - Separador de miles: punto      "1.234.567"
    - Separador decimal: coma        "1.234,56"
    - Símbolo: "$" pegado al número  "$1.234,56"

Funciones:
    parse_money(s)  -> float           # "$1.234,56" o "1234,56" o "1234.56" -> 1234.56
    fmt_money(v)    -> str             # 1234.56 -> "$1.234,56"
    parse_qty(s)    -> float           # "1,5" -> 1.5

Todas son tolerantes a entrada vacía/inválida (devuelven 0.0 o "" en lugar de excepción).
"""
from __future__ import annotations

from typing import Union

Numeric = Union[int, float, str, None]


def parse_money(s: Numeric) -> float:
    """
    Parsea un string de moneda (formato AR o US) a float.

    Acepta:
        "$1.234,56"  -> 1234.56  (formato AR)
        "$1,234.56"  -> 1234.56  (formato US)
        "1234,56"    -> 1234.56
        "1234.56"    -> 1234.56
        "1.234,56"   -> 1234.56
        ""           -> 0.0
        None         -> 0.0
        " $ 100 "    -> 100.0   (tolera espacios)

    Si la entrada es ambigua (ej. "1.234" sin coma), asume formato AR (1.234 = 1234)
    SOLO si hay punto y NO hay coma. Si hay un único punto seguido de exactamente
    2 dígitos al final ("1234.56"), se trata como decimal US.

    Para totales financieros usar siempre con strings que vienen de UI argentina.
    """
    if s is None:
        return 0.0
    if isinstance(s, (int, float)):
        return float(s)

    txt = str(s).strip()
    if not txt:
        return 0.0

    # Quitar símbolo $ y espacios
    txt = txt.replace("$", "").replace(" ", "").strip()
    if not txt:
        return 0.0

    has_comma = "," in txt
    has_dot = "." in txt

    if has_comma and has_dot:
        # Si están ambos: el último que aparezca es el decimal
        if txt.rfind(",") > txt.rfind("."):
            # Formato AR: "1.234,56"
            txt = txt.replace(".", "").replace(",", ".")
        else:
            # Formato US: "1,234.56"
            txt = txt.replace(",", "")
    elif has_comma:
        # Solo coma → formato AR decimal: "1234,56"
        txt = txt.replace(",", ".")
    elif has_dot:
        # Solo punto: ambiguo. Si tiene exactamente 1 punto y la parte
        # después tiene 1-2 dígitos, asumir decimal ("1234.56"). Si tiene
        # múltiples puntos o la parte tras el punto tiene 3 dígitos
        # (probable separador de miles AR), tratarlo como miles.
        parts = txt.split(".")
        if len(parts) == 2 and 1 <= len(parts[1]) <= 2:
            pass  # ya está en formato US: float() lo parsea
        else:
            # 1.234 o 1.234.567 -> miles AR
            txt = txt.replace(".", "")
    # else: solo dígitos, float() los parsea OK

    try:
        return float(txt)
    except (ValueError, TypeError):
        return 0.0


def fmt_money(v: Numeric, with_symbol: bool = True) -> str:
    """
    Formatea un número como moneda en formato AR.

    Args:
        v: número (int/float) o string parseable. Si es None o vacío, devuelve "$0,00".
        with_symbol: si False, omite el "$" prefijo.

    Returns:
        "$1.234,56" (default)
        "1.234,56"  (with_symbol=False)
    """
    if v is None or v == "":
        v = 0.0
    if isinstance(v, str):
        v = parse_money(v)

    try:
        # Formato US como pivote: "1,234.56"
        us = f"{float(v):,.2f}"
    except (ValueError, TypeError):
        us = "0.00"

    # US -> AR: swap coma y punto
    ar = us.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"${ar}" if with_symbol else ar


def parse_qty(s: Numeric) -> float:
    """
    Parsea una cantidad ("1,5", "2.5", "3", " 4 ") a float.
    Acepta coma o punto como decimal. Tolera vacíos -> 0.0.
    """
    if s is None:
        return 0.0
    if isinstance(s, (int, float)):
        return float(s)

    txt = str(s).strip().replace(" ", "")
    if not txt:
        return 0.0

    # Para cantidades, asumir siempre decimal AR (coma)
    txt = txt.replace(",", ".")

    try:
        return float(txt)
    except (ValueError, TypeError):
        return 0.0
