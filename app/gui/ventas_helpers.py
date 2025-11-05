# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt, QRect, QSizeF, QStringListModel, QSize
from PyQt5.QtGui import QFont, QFontMetrics, QPainter
from PyQt5.QtWidgets import QCompleter
from PyQt5.QtPrintSupport import QPrinter, QPrinterInfo, QPrintPreviewDialog, QPrintDialog

from app.config import load as load_config

# ---------------------------------------------------------------------
# Autocompletado de productos en buscadores
# ---------------------------------------------------------------------
def build_product_completer(session, parent=None):
    from app.repository import prod_repo
    repo = prod_repo(session)
    pares = repo.listar_codigos_nombres()
    items = [f"{c or ''} - {n or ''}" for (c, n) in pares]

    model = QStringListModel(items, parent)
    comp = QCompleter(model, parent)
    comp.setCaseSensitivity(Qt.CaseInsensitive)
    comp.setFilterMode(Qt.MatchContains)          # permite buscar por cualquier parte
    comp.setCompletionMode(QCompleter.PopupCompletion)
    return comp, model

# ---------------------------------------------------------------------
# Utilidad: obtener impresora configurada
# kind = 'ticket' | 'barcode'
## === Textos de plantilla del ticket (Config) ===


# ---------------------------------------------------------------------
def _get_configured_printer(kind='ticket'):
    cfg = load_config()
    name = (cfg.get('printers', {}) or {}).get(
        'ticket_printer' if kind == 'ticket' else 'barcode_printer'
    )
    pr = QPrinter(QPrinter.HighResolution)
    pr.setOrientation(QPrinter.Portrait)
    try:
        if name:
            for p in QPrinterInfo.availablePrinters():
                if p.printerName() == name:
                    pr.setPrinterName(name)
                    break
    except Exception:
        pass
    return pr

# ---------------------------------------------------------------------
# Impresión de ticket de venta
#   - Usa impresora configurada en Configuración
#   - preview=False -> imprime directo
#   - Dibuja Subtotal / Interés (si se pasaron en la venta)
#   - Agrega plantilla desde Configuración
# ---------------------------------------------------------------------
def imprimir_ticket(venta, sucursal, direcciones: dict, parent=None, preview=False, template_override: str = None):
    from PyQt5.QtGui import QPageLayout
    from PyQt5.QtCore import QMarginsF
    pr = _get_configured_printer(kind='ticket')

    # Márgenes del driver
    pr.setFullPage(False)
    try:
        pr.setPageMargins(QMarginsF(2, 2, 2, 2), QPageLayout.Millimeter)
    except Exception:
        pass

    # Ancho real de rollo y alto dinámico según contenido
    width_mm = 75.0
    height_mm = _compute_ticket_height_mm(venta, pr, width_mm=width_mm, template_override=template_override)
    pr.setPaperSize(QSizeF(width_mm, height_mm + 10.0), QPrinter.Millimeter)  # +1 cm de resguardo

    if preview:
        dlg = QPrintPreviewDialog(pr, parent)
        def _paint(prn):
            p = QPainter(prn)
            try:
                _draw_ticket(p, prn.pageRect(), prn, venta, sucursal, direcciones, width_mm=width_mm, template_override=template_override)
            finally:
                p.end()
        dlg.paintRequested.connect(_paint)
        dlg.exec_()
        return True

    # Respetar “preguntar al imprimir” si corresponde
    from PyQt5.QtPrintSupport import QPrintDialog, QPrinterInfo
    cfg = load_config()
    ask = bool((cfg.get('printers') or {}).get('ask_each_time', False))
    need_dialog = ask
    try:
        fixed = (cfg.get('printers') or {}).get('ticket_printer')
        if fixed:
            names = [p.printerName() for p in QPrinterInfo.availablePrinters()]
            if fixed not in names:
                need_dialog = True
    except Exception:
        pass

    if need_dialog:
        dlg = QPrintDialog(pr, parent)
        if dlg.exec_() != QPrintDialog.Accepted:
            return False

    p = QPainter(pr)
    try:
        _draw_ticket(p, pr.pageRect(), pr, venta, sucursal, direcciones, width_mm=width_mm, template_override=template_override)
    finally:
        p.end()
    return True






def _draw_ticket(p, page_rect, prn, venta, sucursal, direcciones, width_mm=75.0, template_override: str = None):
    from PyQt5.QtCore import Qt, QRect
    from PyQt5.QtGui  import QFont

    # Conversión mm -> px
    dpi_x = (getattr(prn, "logicalDpiX", lambda: 300)() or 300) if prn else 300
    def px(mm): return int(round(mm * dpi_x / 25.4))

    # Márgenes simétricos (centrado real del contenido dentro de la “hoja”)
    MARGIN_MM = 4.0
    GAP_MM    = 1.4
    SEP_MM    = 0.9
    RIGHT_PAD_PX = px(0.6)

    # Área útil centrada
    x = page_rect.left() + px(MARGIN_MM)
    y = page_rect.top()  + px(MARGIN_MM)
    w = page_rect.width() - px(MARGIN_MM*2)

    # Fuentes
    f_title = QFont("Arial"); f_title.setPointSize(12); f_title.setBold(True)
    f_head  = QFont("Arial"); f_head.setPointSize(9);  f_head.setBold(True)
    f_norm  = QFont("Arial"); f_norm.setPointSize(9)

    def gap(mm=GAP_MM):
        nonlocal y
        y += px(mm)

    def line():
        nonlocal y
        p.drawLine(x, y, x + w, y)
        y += px(SEP_MM)

    def draw_text(text, font, align=Qt.AlignLeft):
        nonlocal y
        p.setFont(font)
        h = p.fontMetrics().height()
        p.drawText(QRect(x, y, w, h), align, str(text))
        y += h

    def draw_lr(left, right, font):
        nonlocal y
        p.setFont(font)
        h = p.fontMetrics().height()
        left_w = int(w * 0.55)
        right_x = x + left_w
        right_w = w - left_w - RIGHT_PAD_PX
        p.drawText(QRect(x,       y, left_w,  h), Qt.AlignLeft  | Qt.AlignVCenter,  str(left))
        p.drawText(QRect(right_x, y, right_w, h), Qt.AlignRight | Qt.AlignVCenter, str(right))
        y += h

    def money(x):
        try:
            if x is None: x = 0.0
            if not isinstance(x, (int, float)):
                x = float(str(x).replace("$","").replace(",","").strip() or 0)
        except Exception:
            x = 0.0
        return f"${x:,.2f}".replace(",", "X").replace(".", ",").replace("X",".")

    # ---------- NUEVO: si hay plantilla (en override o en config), dibujar SOLO la plantilla ----------
    from app.config import load as load_config
    cfg = load_config()
    tk  = (cfg.get("ticket") or {})
    template_text = (template_override if template_override is not None else tk.get("template") or "").strip()

    if template_text:
        # usa el motor de plantilla y salí (sin encabezado/ítems/totales predefinidos)
        _tpl_draw_block(p, px, draw_text, line, gap, f_norm, f_head, venta, sucursal, direcciones, template_override=template_text)
        return


    # ===== Encabezado =====
    draw_text((_ticket_strings().get("business") or _ticket_strings().get("title", "TICKET")), f_title, Qt.AlignCenter)

    datos = []
    try:
        if getattr(venta, "fecha", None):
            datos.append(venta.fecha.strftime("%d/%m/%Y %H:%M"))
    except Exception:
        pass
    num = getattr(venta, "numero_ticket", None) or getattr(venta, "id", None)
    if num: datos.append(f"Nº {num}")
    if datos:
        draw_text("   ".join(datos), f_norm, Qt.AlignCenter)

    dir_txt = (direcciones or {}).get(sucursal, "") or _ticket_strings().get("address", "")
    if dir_txt: draw_text(dir_txt, f_norm, Qt.AlignCenter)
    if _ticket_strings().get("branch_lbl") or sucursal:
        draw_text(_ticket_strings().get("branch_lbl") or str(sucursal), f_norm, Qt.AlignCenter)

    line()

    # ===== Ítems =====
    # Preferimos una lista de dicts en venta._ticket_items; si no está, intentamos
    # derivarla de otros atributos comunes (venta.items, venta.productos, etc.).
    items = getattr(venta, "_ticket_items", None)

    if not items:
        raw = getattr(venta, "items", None) or getattr(venta, "productos", None) or []
        items = []
        for it in raw:
            if isinstance(it, dict):
                d = {
                    "codigo": it.get("codigo") or it.get("cod") or "",
                    "nombre": it.get("nombre") or it.get("desc") or "",
                    "precio_unitario": float(it.get("precio_unitario") or it.get("precio") or 0.0),
                    "cantidad": float(it.get("cantidad") or it.get("cant") or 1),
                }
            else:
                d = {
                    "codigo": getattr(it, "codigo", "") or getattr(it, "cod", ""),
                    "nombre": getattr(it, "nombre", "") or getattr(it, "desc", ""),
                    "precio_unitario": float(getattr(it, "precio_unitario", getattr(it, "precio", 0.0)) or 0.0),
                    "cantidad": float(getattr(it, "cantidad", getattr(it, "cant", 1)) or 1),
                }
            if d["nombre"]:
                items.append(d)

    for it in items:
        codigo = it.get("codigo") or ""
        nombre = it.get("nombre") or ""
        # recorte de seguridad para nombres largos
        if len(nombre) > 28:
            nombre = nombre[:28] + "…"
        precio_u = float(it.get("precio_unitario") or 0.0)
        cant    = float(it.get("cantidad") or 1)
        importe = precio_u * cant

        # línea 1: código + nombre
        draw_text(f"{codigo} — {nombre}".strip(" —"), f_norm, Qt.AlignLeft)
        # línea 2: cantidad × precio_u … importe (alineado izq/der)
        draw_lr(f"{int(cant)} × {money(precio_u)}", money(importe), f_norm)
        gap(0.4)


    # ===== Totales =====
    if getattr(venta, "subtotal_base", None) is not None:
        draw_lr("Subtotal", money(getattr(venta, "subtotal_base", 0.0)), f_norm)
    if getattr(venta, "descuento_monto", None):
        draw_lr("Descuento", money(getattr(venta, "descuento_monto", 0.0)), f_norm)
    if getattr(venta, "interes_monto", None):
        draw_lr("Interés",  money(getattr(venta, "interes_monto", 0.0)), f_norm)
    # TOTAL: preferir el total dado; si no, recomputar base - desc + interés
    if getattr(venta, "total", None) is None:
        try:
            items = getattr(venta, "_ticket_items", None) or []
            subtotal_auto = sum(float(i.get("cantidad",0))*float(i.get("precio_unitario",0)) for i in items)
        except Exception:
            subtotal_auto = 0.0
        subtotal_base = float(getattr(venta, "subtotal_base", subtotal_auto) or subtotal_auto)
        interes   = float(getattr(venta, "interes_monto", 0.0) or 0.0)
        descuento = float(getattr(venta, "descuento_monto", 0.0) or 0.0)
        tot = subtotal_base - descuento + interes
    else:
        tot = float(getattr(venta, "total", 0.0) or 0.0)

    draw_lr("TOTAL", money(tot), f_head)
    line()

    # ===== Forma de pago =====
    forma_raw = (getattr(venta, "forma_pago", "") or getattr(venta, "modo_pago", "") or getattr(venta, "modo", "")).lower()
    is_card   = ("tarj" in forma_raw)
    draw_lr("Forma de pago", "Tarjeta" if is_card else "Efectivo", f_norm)

    if is_card:
        cuotas  = int(getattr(venta, "cuotas", 0) or 0)
        if cuotas > 0:
            monto_cuota = (tot / cuotas)
            draw_lr("Cuotas", f"{cuotas} × {money(monto_cuota)}", f_norm)
    else:
        if getattr(venta, "pagado", None) is not None:
            draw_lr("Abonado", money(getattr(venta, "pagado", 0.0)), f_norm)
            draw_lr("Vuelto",  money(getattr(venta, "vuelto", 0.0)),  f_norm)

    # ===== Plantilla 100% editable (sin “footer” automático) =====
    _tpl_draw_block(p, px, draw_text, line, gap, f_norm, f_head, venta, sucursal, direcciones, template_override=template_override)


    
    
    
def _compute_ticket_height_mm(venta, prn, width_mm=75.0, template_override: str = None):
    # Calcula el alto requerido en milímetros según lo que se va a imprimir
    from PyQt5.QtGui import QFont, QFontMetrics

    dpi_x = (getattr(prn, "logicalDpiX", lambda: 300)() or 300) if prn else 300
    mm_per_px = 25.4 / dpi_x

    f_title = QFont("Arial"); f_title.setPointSize(12); f_title.setBold(True)
    f_head  = QFont("Arial"); f_head.setPointSize(9);  f_head.setBold(True)
    f_norm  = QFont("Arial"); f_norm.setPointSize(9)

    fm_t = QFontMetrics(f_title, prn) if prn else QFontMetrics(f_title)
    fm_h = QFontMetrics(f_head,  prn) if prn else QFontMetrics(f_head)
    fm_n = QFontMetrics(f_norm,  prn) if prn else QFontMetrics(f_norm)

    h_t = fm_t.height() * mm_per_px
    h_h = fm_h.height() * mm_per_px
    h_n = fm_n.height() * mm_per_px

    MARGIN_MM, GAP_MM, SEP_MM = 3.0, 1.2, 0.8
    total = MARGIN_MM

    # Encabezado (título + línea info + dirección/sucursal)
    total += h_t + GAP_MM
    info_lines = 0
    try:
        if getattr(venta, "fecha", None): info_lines += 1
    except Exception:
        pass
    if getattr(venta, "numero_ticket", None) or getattr(venta, "id", None): info_lines += 1
    if info_lines: total += h_n
    total += h_n       # dirección/sucursal
    total += SEP_MM

    # Ítems (dos líneas por ítem)
    items = getattr(venta, "_ticket_items", None) or []
    for _ in items:
        total += h_n
        total += h_n
        total += SEP_MM
    total += SEP_MM

    # Totales / interés / total
    if getattr(venta, "subtotal_base", None) is not None: total += h_n
    if getattr(venta, "descuento_monto", None):           total += h_n
    if getattr(venta, "interes_monto", None):             total += h_n
    total += h_h + SEP_MM
    total += SEP_MM

    # Forma/efectivo (abonado y vuelto si aplica)
    total += h_n
    forma_raw = (getattr(venta, "forma_pago", "") or getattr(venta, "modo_pago", "") or getattr(venta, "modo", "")).lower()
    if "tarj" not in forma_raw and getattr(venta, "pagado", None) is not None:
        total += h_n
        total += h_n

    # Comentario (envuelto)
    com = getattr(venta, "comentario", None) or getattr(venta, "motivo", None) or getattr(venta, "nota", None)
    if com:
        total += GAP_MM + h_h
        avg_char_px = max(1, fm_n.averageCharWidth())
        avail_px = int(round((width_mm - 2*MARGIN_MM) / mm_per_px))
        chars_per_line = max(8, int(avail_px / avg_char_px))
        import textwrap
        wrapped = []
        for line in str(com).splitlines():
            wrapped += textwrap.wrap(line, width=chars_per_line) or [""]
        total += min(6, len(wrapped)) * h_n
     # ===== Altura extra por Plantilla =====
    try:
        from app.config import load as load_config
        cfg = load_config()
        tk  = (cfg.get("ticket") or {})

        # Usa el override si llegó desde la vista previa; si no, lo de Config
        template_text = (template_override if template_override is not None else (tk.get("template") or "")).strip()
        if template_text:
            lines = template_text.splitlines()
            line_count = 0
            for raw in lines:
                if raw.strip() in ("{{hr}}", "{{line}}"):
                    total += GAP_MM + SEP_MM
                elif "{{items}}" in raw:
                    items = getattr(venta, "_ticket_items", None) or []
                    line_count += max(0, len(items) * 2)
                else:
                    line_count += 1
            total += line_count * h_n

    except Exception:
        pass
   

   # Footer (contemplar saltos de línea y envoltura)
    S = _ticket_strings()
    footer_texts = [S.get(k, "") for k in ("footer_1", "footer_2", "footer_3")]

    avg_char_px = max(1, fm_n.averageCharWidth())
    avail_px = int(round((width_mm - 2*MARGIN_MM) / mm_per_px))
    chars_per_line = max(8, int(avail_px / avg_char_px))

    import textwrap
    footer_lines = 0
    for txt in footer_texts:
        if not txt:
            continue
        for line in str(txt).splitlines():
            wrapped = textwrap.wrap(line, width=chars_per_line) or [""]
            footer_lines += len(wrapped)

    if footer_lines:
        total += GAP_MM + footer_lines * h_n
    
    total += 3.0
    return max(float(total), 60.0)
    
    #EDICION DE TICKET 
def _ticket_strings():
    from app.config import load as load_config
    cfg = load_config()
    tk = (cfg.get('ticket') or {})
    return {
        "title":      tk.get("title", "TICKET"),
        "business":   tk.get("business_name", "PERFUMERIA SUSI"),
        "address":    tk.get("address", ""),
        "branch_lbl": tk.get("branch_label", ""),   # p.ej. "Sucursal Gerli"
        "footer_1":   tk.get("footer_msg", ),
        "footer_2":   tk.get("google_review", "No olvide dejar una reseña en Google."),
        "footer_3":   tk.get("instagram", "Síganos en Instagram: PERFUMERIASU"),
    }
    


# ======= Plantilla: helpers =======

def _money(x):
    try:
        return f"${float(x):.2f}"
    except Exception:
        return "$0.00"

def _tpl_context(venta, sucursal, direcciones):
    import datetime
    # Textos fijos del ticket (nombre negocio, etc.)
    S = _ticket_strings()
    # Totales
    items = getattr(venta, "_ticket_items", None) or []
    subtotal = 0.0
    for it in items:
        try:
            cant = float(getattr(it, "cantidad", 1) or 1)
            pu   = float(getattr(it, "precio_unit", None) or getattr(it, "precio_unitario", None) or getattr(it, "precio", 0.0) or 0.0)
            subtotal += cant * pu
        except Exception:
            pass
    subtotal_base = getattr(venta, "subtotal_base", None)
    if subtotal_base is not None:
        subtotal = float(subtotal_base)

    descuento = float(getattr(venta, "descuento_monto", 0.0) or 0.0)
    interes = float(getattr(venta, "interes_monto", 0.0) or 0.0)
    total   = float(getattr(venta, "total", subtotal + interes) or (subtotal + interes))

    # Pago/efectivo
    forma_raw = (getattr(venta, "forma_pago", "") or getattr(venta, "modo_pago", "") or getattr(venta, "modo", "") or "").lower()
    pago_modo = "Tarjeta" if "tarj" in forma_raw else "Efectivo"
    cuotas = int(getattr(venta, "cuotas", 0) or 0)
    monto_cuota = (total / cuotas) if (pago_modo == "Tarjeta" and cuotas) else 0.0

    abonado = getattr(venta, "pagado", None)
    vuelto  = getattr(venta, "vuelto", None)

    # Encabezado
    num = getattr(venta, "numero_ticket", None) or getattr(venta, "id", None)
    fch = getattr(venta, "fecha", None)
    if fch:
        try:
            dtxt = fch.strftime("%Y-%m-%d %H:%M")
        except Exception:
            dtxt = str(fch)
    else:
        dtxt = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    # Sucursal/dirección
    dir_txt = (direcciones or {}).get(sucursal, "") or ""

    ctx = {
        "ticket.numero":     str(num or ""),
        "ticket.fecha_hora": dtxt,
        "sucursal":          str(sucursal or ""),
        "direccion":         dir_txt,
        "pago.modo":         pago_modo,
        "pago.cuotas":       (str(cuotas) if cuotas else "-"),
        "pago.monto_cuota":  (_money(monto_cuota) if monto_cuota else "-"),
        "totales.subtotal":  _money(subtotal),
        "totales.interes":   _money(interes) if interes else "-",
        "totales.total":     _money(total),
        "abonado":           (_money(abonado) if abonado is not None else "-"),
        "vuelto":            (_money(vuelto)  if vuelto  is not None else "-"),
        "business":          S.get("business", ""),   # ← NUEVO
        "title":             S.get("title", "TICKET"),
        "totales.descuento": (_money(descuento) if descuento else "-")
    }
    return ctx, items

def _tpl_render_lines(template_text, ctx, items):
    """
    Convierte la plantilla en una lista de dicts 'línea' con campos:
    {'text': str, 'align': Qt.AlignmentFlag, 'bold': bool, 'italic': bool, 'is_rule': bool}
    Expande {{items}} en múltiples líneas.
    """
    lines = []
    if not template_text:
        return lines

    def _repl_placeholders(s):
        out = s
        for k, v in ctx.items():
            out = out.replace("{{" + k + "}}", str(v))
        return out

    # Expansión de {{items}}
    def _expand_items():
        out = []
        for it in (items or []):
            try:
                cant = float(getattr(it, "cantidad", 1) or 1)
                pu   = float(getattr(it, "precio_unit", None) or getattr(it, "precio_unitario", None) or getattr(it, "precio", 0.0) or 0.0)
                nom  = str(getattr(getattr(it, "producto", None), "nombre", "") or getattr(it, "nombre", "") or "")
                tot  = cant * pu
                out.append(f"{int(cant)} x {nom}")
                out.append(f"  { _money(pu) }   →   { _money(tot) }")
            except Exception:
                pass
        return out

    for raw in template_text.splitlines():
        raw = raw.rstrip("\n")

        # Línea horizontal
        if raw.strip() in ("{{hr}}", "{{line}}"):
            lines.append({"text": "", "align": Qt.AlignLeft, "bold": False, "italic": False, "is_rule": True})
            continue

        # Bloque items
        if "{{items}}" in raw:
            for l in _expand_items():
                lines.append({"text": l, "align": Qt.AlignLeft, "bold": False, "italic": False, "is_rule": False})
            continue

        # Alineado y estilo por prefijo
        align = Qt.AlignLeft
        bold = italic = False
        txt = raw.strip()

        for tag, a in (("{{center:", Qt.AlignHCenter), ("{{right:", Qt.AlignRight), ("{{left:", Qt.AlignLeft)):
            if txt.startswith(tag) and txt.endswith("}}"):
                txt = txt[len(tag):-2].strip()
                align = a
                break

        for tag, flag in (("{{b:", "b"), ("{{i:", "i"), ("{{centerb:", "cb"), ("{{rightb:", "rb")):
            if txt.startswith(tag) and txt.endswith("}}"):
                inner = txt[len(tag):-2].strip()
                if flag == "b":       bold = True;  txt = inner
                elif flag == "i":     italic = True; txt = inner
                elif flag == "cb":    bold = True;  align = Qt.AlignHCenter; txt = inner
                elif flag == "rb":    bold = True;  align = Qt.AlignRight;   txt = inner
                break

        txt = _repl_placeholders(txt)
        lines.append({"text": txt, "align": align, "bold": bold, "italic": italic, "is_rule": False})

    return lines

def _tpl_draw_block(p, px, draw_text, line, gap, f_norm, f_head, venta, sucursal, direcciones, template_override: str = None):
    from app.config import load as load_config
    cfg = load_config()
    tk  = (cfg.get("ticket") or {})
    template_text = (template_override if template_override is not None else tk.get("template") or "").strip()
    if not template_text:
        return

    ctx, items = _tpl_context(venta, sucursal, direcciones)
    lines = _tpl_render_lines(template_text, ctx, items)

    for ln in lines:
        if ln["is_rule"]:
            gap(); line(); continue
        f = f_norm
        if ln["bold"] or ln["italic"]:
            f = QFont(f_norm)
            if ln["bold"]:   f.setBold(True)
            if ln["italic"]: f.setItalic(True)
        draw_text(ln["text"], f, ln["align"])
