# -*- coding: utf-8 -*-
import logging
from PyQt5.QtCore import Qt, QRect, QSizeF, QStringListModel, QSize
from PyQt5.QtGui import QFont, QFontMetrics, QPainter, QPixmap
from PyQt5.QtWidgets import QCompleter
from PyQt5.QtPrintSupport import QPrinter, QPrinterInfo, QPrintPreviewDialog, QPrintDialog

from app.config import load as load_config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------
# Autocompletado de productos en buscadores
# ---------------------------------------------------------------------
def build_product_completer(session, parent=None):
    from app.repository import prod_repo
    from app.gui.main_window.filters import LimitedFilterProxy

    repo = prod_repo(session)
    pares = repo.listar_codigos_nombres()
    items = [f"{c or ''} - {n or ''}" for (c, n) in pares]

    model = QStringListModel(items, parent)

    # Usar proxy con limite para evitar lag con 13K+ items
    proxy = LimitedFilterProxy(limit=50, parent=parent)
    proxy.setSourceModel(model)
    proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)

    comp = QCompleter(proxy, parent)
    comp.setCaseSensitivity(Qt.CaseInsensitive)
    comp.setCompletionMode(QCompleter.UnfilteredPopupCompletion)
    comp.setMaxVisibleItems(15)

    # Guardar refs para actualizar el proxy/modelo despues
    comp._src_model = model
    comp._proxy = proxy

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
    """
    Imprime o previsualiza un ticket de venta.

    Compatible con todos los drivers de Windows (térmicas, convencionales, PDF, etc.)
    gracias al uso de QPrinter que abstrae la comunicación con el driver.

    Args:
        venta: Objeto Venta con datos del ticket
        sucursal: Nombre de la sucursal
        direcciones: Dict con direcciones por sucursal
        parent: Widget padre para diálogos
        preview: Si True, muestra vista previa en lugar de imprimir
        template_override: Plantilla personalizada a usar

    Returns:
        True si imprimió/mostró correctamente, False si canceló o error
    """
    from PyQt5.QtGui import QPageLayout
    from PyQt5.QtCore import QMarginsF
    from PyQt5.QtWidgets import QMessageBox
    from PyQt5.QtPrintSupport import QPrintDialog, QPrinterInfo

    # Si no hay template_override, seleccionar automáticamente según tipo de operación
    if template_override is None:
        cfg = load_config()
        tk = (cfg.get("ticket") or {})
        slots = tk.get("slots", {})

        # Detectar datos de la venta
        forma_raw = (getattr(venta, "forma_pago", "") or getattr(venta, "modo_pago", "") or getattr(venta, "modo", "")).lower()
        is_tarjeta = ("tarj" in forma_raw)
        has_cae = bool(getattr(venta, "afip_cae", None))
        tipo_cbte = (getattr(venta, "tipo_comprobante", "") or "").upper()

        # Resolver template con prioridad específica → genérica
        slot_key = ""
        if "FACTURA_A" in tipo_cbte and tk.get("template_factura_a"):
            slot_key = tk["template_factura_a"]
        elif "FACTURA_B" in tipo_cbte and tk.get("template_factura_b"):
            slot_key = tk["template_factura_b"]
        elif has_cae and is_tarjeta and tk.get("template_cae_tarjeta"):
            slot_key = tk["template_cae_tarjeta"]
        elif has_cae and not is_tarjeta and tk.get("template_cae_efectivo"):
            slot_key = tk["template_cae_efectivo"]
        elif tk.get("template_consumidor_final") and not has_cae and not tipo_cbte:
            slot_key = tk["template_consumidor_final"]

        # Fallback genérico por forma de pago
        if not slot_key:
            slot_key = tk.get("template_tarjeta", "slot3") if is_tarjeta else tk.get("template_efectivo", "slot1")

        template_override = slots.get(slot_key, "")

    try:
        pr = _get_configured_printer(kind='ticket')
    except Exception as e:
        if parent:
            QMessageBox.warning(
                parent,
                "Error de impresora",
                f"No se pudo inicializar la impresora:\n{e}\n\nVerifique que haya al menos una impresora instalada."
            )
        return False

    # Márgenes del driver
    pr.setFullPage(False)
    try:
        pr.setPageMargins(QMarginsF(2, 2, 2, 2), QPageLayout.Millimeter)
    except Exception:
        pass

    # Ancho real de rollo y alto dinámico según contenido
    width_mm = 75.0
    try:
        height_mm = _compute_ticket_height_mm(venta, pr, width_mm=width_mm, template_override=template_override)
    except Exception as e:
        if parent:
            QMessageBox.warning(
                parent,
                "Error al calcular ticket",
                f"No se pudo calcular el tamaño del ticket:\n{e}"
            )
        return False

    pr.setPaperSize(QSizeF(width_mm, height_mm + 10.0), QPrinter.Millimeter)  # +1 cm de resguardo

    if preview:
        try:
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
        except Exception as e:
            if parent:
                QMessageBox.warning(
                    parent,
                    "Error en vista previa",
                    f"No se pudo mostrar la vista previa:\n{e}"
                )
            return False

    # Respetar "preguntar al imprimir" si corresponde
    cfg = load_config()
    ask = bool((cfg.get('printers') or {}).get('ask_each_time', False))
    need_dialog = ask

    try:
        fixed = (cfg.get('printers') or {}).get('ticket_printer')
        if fixed:
            names = [p.printerName() for p in QPrinterInfo.availablePrinters()]
            if fixed not in names:
                # Impresora configurada no encontrada
                if parent:
                    resp = QMessageBox.question(
                        parent,
                        "Impresora no encontrada",
                        f"La impresora configurada '{fixed}' no está disponible.\n\n"
                        "¿Desea seleccionar otra impresora?",
                        QMessageBox.Yes | QMessageBox.No
                    )
                    if resp == QMessageBox.Yes:
                        need_dialog = True
                    else:
                        return False
                else:
                    need_dialog = True
    except Exception:
        pass

    if need_dialog:
        dlg = QPrintDialog(pr, parent)
        if dlg.exec_() != QPrintDialog.Accepted:
            return False

    # Verificar que la impresora esté lista antes de imprimir
    try:
        printer_state = pr.printerState()
        if printer_state == QPrinter.Error:
            if parent:
                QMessageBox.warning(
                    parent,
                    "Error de impresora",
                    "La impresora reporta un error. Verifique que esté encendida,\n"
                    "tenga papel y no haya atascos."
                )
            return False
    except Exception:
        pass  # Algunos drivers no soportan verificar estado

    # Imprimir
    try:
        p = QPainter(pr)
        try:
            _draw_ticket(p, pr.pageRect(), pr, venta, sucursal, direcciones, width_mm=width_mm, template_override=template_override)
        finally:
            p.end()
        return True
    except Exception as e:
        if parent:
            QMessageBox.critical(
                parent,
                "Error al imprimir",
                f"No se pudo completar la impresión:\n{e}\n\n"
                "Verifique que la impresora esté encendida y tenga papel."
            )
        return False






def _draw_ticket(p, page_rect, prn, venta, sucursal, direcciones, width_mm=75.0, template_override: str = None):
    from PyQt5.QtCore import Qt, QRect
    from PyQt5.QtGui  import QFont

    # Conversión mm -> px
    dpi_x = (getattr(prn, "logicalDpiX", lambda: 300)() or 300) if prn else 300
    def px(mm): return int(round(mm * dpi_x / 25.4))

    # Márgenes configurables desde app_config.json
    from app.config import load as _load_cfg
    _tk_cfg = _load_cfg().get("ticket", {})
    MARGIN_LEFT_MM  = float(_tk_cfg.get("margin_left_mm", 2.0))
    MARGIN_RIGHT_MM = float(_tk_cfg.get("margin_right_mm", 2.0))
    GAP_MM    = 1.4
    SEP_MM    = 0.9
    RIGHT_PAD_PX = px(0.6)

    # Área útil con márgenes independientes
    x = page_rect.left() + px(MARGIN_LEFT_MM)
    y = page_rect.top()  + px(MARGIN_LEFT_MM)
    w = page_rect.width() - px(MARGIN_LEFT_MM) - px(MARGIN_RIGHT_MM)

    # Fuentes H1-H5 configurables
    _fonts = _tk_cfg.get("fonts") or {}
    _h1 = int(_fonts.get("h1_pt") or _fonts.get("title_pt", 14))
    _h2 = int(_fonts.get("h2_pt", 12))
    _h3 = int(_fonts.get("h3_pt") or _fonts.get("head_pt", 10))
    _h4 = int(_fonts.get("h4_pt") or _fonts.get("text_pt", 9))
    _h5 = int(_fonts.get("h5_pt", 7))
    f_title = QFont("Arial"); f_title.setPointSize(_h1); f_title.setBold(True)   # H1
    f_head  = QFont("Arial"); f_head.setPointSize(_h3);  f_head.setBold(True)    # H3
    f_norm  = QFont("Arial"); f_norm.setPointSize(_h4)                            # H4
    f_h2    = QFont("Arial"); f_h2.setPointSize(_h2);    f_h2.setBold(True)      # H2
    f_h5    = QFont("Arial"); f_h5.setPointSize(_h5)                              # H5

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

    def draw_cols(cols, font, widths=None):
        """Draw multiple columns in a single row."""
        nonlocal y
        p.setFont(font)
        h = p.fontMetrics().height()
        if not widths:
            col_w = w // len(cols)
            widths = [col_w] * len(cols)
        cx = x
        for i, (text, align) in enumerate(cols):
            cw = widths[i] if i < len(widths) else widths[-1]
            p.drawText(QRect(cx, y, cw, h), align, str(text))
            cx += cw
        y += h

    def money(x):
        try:
            if x is None: x = 0.0
            if not isinstance(x, (int, float)):
                x = float(str(x).replace("$","").replace(",","").strip() or 0)
        except Exception:
            x = 0.0
        return f"${x:,.2f}".replace(",", "X").replace(".", ",").replace("X",".")

    def draw_image(pixmap, size_mm=20.0, smooth=True):
        """Dibuja un QPixmap cuadrado (size_mm x size_mm) centrado y avanza y.
        smooth=False usa FastTransformation (ideal para QR codes)."""
        nonlocal y
        if pixmap is None or pixmap.isNull():
            return
        side = px(size_mm)
        transform = Qt.SmoothTransformation if smooth else Qt.FastTransformation
        scaled = pixmap.scaled(side, side, Qt.KeepAspectRatio, transform)
        img_x = x + (w - scaled.width()) // 2
        p.drawPixmap(img_x, y, scaled)
        y += scaled.height() + px(1.0)

    # ---------- NUEVO: si hay plantilla (en override o en config), dibujar SOLO la plantilla ----------
    from app.config import load as load_config
    cfg = load_config()
    tk  = (cfg.get("ticket") or {})
    template_text = (template_override if template_override is not None else tk.get("template") or "").strip()

    if template_text:
        # usa el motor de plantilla y salí (sin encabezado/ítems/totales predefinidos)
        _tpl_draw_block(p, px, draw_text, draw_image, line, gap, f_norm, f_head, venta, sucursal, direcciones, template_override=template_text)
        return


    # ===== Encabezado profesional =====
    S = _ticket_strings()
    draw_text("=" * 33, f_norm, Qt.AlignCenter)
    draw_text((S.get("business") or S.get("title", "TICKET")), f_title, Qt.AlignCenter)

    dir_txt = (direcciones or {}).get(sucursal, "") or S.get("address", "")
    if dir_txt:
        draw_text(dir_txt, f_norm, Qt.AlignCenter)

    cuit_txt = cfg.get("fiscal", {}).get("cuit", "")
    if cuit_txt:
        draw_text(f"CUIT: {cuit_txt}", f_norm, Qt.AlignCenter)

    draw_text("=" * 33, f_norm, Qt.AlignCenter)
    gap()

    # Ticket number and date
    num = getattr(venta, "numero_ticket", None) or getattr(venta, "id", None)
    if num:
        draw_text(f"Ticket Nº: {num}", f_norm, Qt.AlignLeft)
    try:
        if getattr(venta, "fecha", None):
            draw_text(f"Fecha: {venta.fecha.strftime('%d/%m/%Y %H:%M')}", f_norm, Qt.AlignLeft)
    except Exception:
        pass
    if S.get("branch_lbl") or sucursal:
        draw_text(f"Sucursal: {S.get('branch_lbl') or str(sucursal)}", f_norm, Qt.AlignLeft)
    gap()

    # ===== Ítems =====
    line()
    # Column widths: N.(10%) | Artículos(45%) | Prec.(22%) | Total(23%)
    col_w = [int(w * 0.10), int(w * 0.45), int(w * 0.22), int(w * 0.23)]

    # Header row
    draw_cols([
        ("N.", Qt.AlignLeft),
        ("Artículos", Qt.AlignLeft),
        ("Prec.", Qt.AlignRight),
        ("Total", Qt.AlignRight),
    ], f_head, col_w)
    line()

    # Build items list
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
                prod_obj = getattr(it, "producto", None)
                if prod_obj:
                    nombre = getattr(prod_obj, "nombre", "") or ""
                    codigo = getattr(prod_obj, "codigo", "") or getattr(prod_obj, "codigo_barra", "") or ""
                else:
                    nombre = getattr(it, "nombre", "") or getattr(it, "desc", "") or ""
                    codigo = getattr(it, "codigo", "") or getattr(it, "cod", "") or ""

                d = {
                    "codigo": codigo,
                    "nombre": nombre,
                    "precio_unitario": float(getattr(it, "precio_unitario", getattr(it, "precio", 0.0)) or 0.0),
                    "cantidad": float(getattr(it, "cantidad", getattr(it, "cant", 1)) or 1),
                }
            if d["nombre"]:
                items.append(d)

    for it in items:
        nombre = it.get("nombre") or ""
        precio_u = float(it.get("precio_unitario") or 0.0)
        cant = float(it.get("cantidad") or 1)
        importe = precio_u * cant

        # Truncate name for first line (max ~18 chars fits in column)
        if len(nombre) > 18:
            first_line = nombre[:18]
            remaining = nombre[18:]
        else:
            first_line = nombre
            remaining = ""

        # Row: qty | name | unit price | total
        draw_cols([
            (str(int(cant)), Qt.AlignLeft),
            (first_line, Qt.AlignLeft),
            (money(precio_u), Qt.AlignRight),
            (money(importe), Qt.AlignRight),
        ], f_norm, col_w)

        # Continuation line for long names
        if remaining:
            draw_cols([
                ("", Qt.AlignLeft),
                (remaining[:22], Qt.AlignLeft),
                ("", Qt.AlignRight),
                ("", Qt.AlignRight),
            ], f_norm, col_w)

    line()
    gap()

    # ===== Totales =====
    # Compute total
    if getattr(venta, "total", None) is None:
        try:
            items_for_sum = getattr(venta, "_ticket_items", None) or []
            subtotal_auto = sum(float(i.get("cantidad", 0)) * float(i.get("precio_unitario", 0)) for i in items_for_sum)
        except Exception:
            subtotal_auto = 0.0
        subtotal_base = float(getattr(venta, "subtotal_base", subtotal_auto) or subtotal_auto)
        interes = float(getattr(venta, "interes_monto", 0.0) or 0.0)
        descuento = float(getattr(venta, "descuento_monto", 0.0) or 0.0)
        tot = subtotal_base - descuento + interes
    else:
        tot = float(getattr(venta, "total", 0.0) or 0.0)

    if getattr(venta, "subtotal_base", None) is not None:
        draw_lr("Subtotal", money(getattr(venta, "subtotal_base", 0.0)), f_norm)
    descuento_monto = float(getattr(venta, "descuento_monto", 0.0) or 0.0)
    if descuento_monto:
        draw_lr("Descuento", money(descuento_monto), f_norm)
    if getattr(venta, "interes_monto", None):
        draw_lr("Interés", money(getattr(venta, "interes_monto", 0.0)), f_norm)
    draw_lr("TOTAL", money(tot), f_h2)
    gap()

    # ===== Forma de pago =====
    forma_raw = (getattr(venta, "forma_pago", "") or getattr(venta, "modo_pago", "") or getattr(venta, "modo", "")).lower()
    is_card = ("tarj" in forma_raw)
    pago_label = "tarjeta" if is_card else "efectivo"

    if is_card:
        cuotas = int(getattr(venta, "cuotas", 0) or 0)
        if cuotas > 0:
            monto_cuota = tot / cuotas
            draw_cols([
                ("Pago", Qt.AlignLeft),
                ("Total", Qt.AlignRight),
                ("Cuotas", Qt.AlignRight),
            ], f_head, [int(w * 0.25), int(w * 0.38), int(w * 0.37)])
            draw_cols([
                (pago_label, Qt.AlignLeft),
                (money(tot), Qt.AlignRight),
                (f"{cuotas} x {money(monto_cuota)}", Qt.AlignRight),
            ], f_norm, [int(w * 0.25), int(w * 0.38), int(w * 0.37)])
        else:
            draw_lr("Forma de pago", "Tarjeta", f_norm)
            draw_lr("Total", money(tot), f_norm)
    else:
        pagado = float(getattr(venta, "pagado", 0.0) or 0.0)
        vuelto_val = float(getattr(venta, "vuelto", 0.0) or 0.0)
        pago_col_w = [int(w * 0.22), int(w * 0.26), int(w * 0.26), int(w * 0.26)]
        draw_cols([
            ("Pago", Qt.AlignLeft),
            ("Total", Qt.AlignRight),
            ("Entregado", Qt.AlignRight),
            ("Devuelto", Qt.AlignRight),
        ], f_head, pago_col_w)
        draw_cols([
            (pago_label, Qt.AlignLeft),
            (money(tot), Qt.AlignRight),
            (money(pagado), Qt.AlignRight),
            (money(vuelto_val), Qt.AlignRight),
        ], f_norm, pago_col_w)

    gap()

    # ===== AFIP / CAE (si existe) =====
    afip_cae = getattr(venta, "afip_cae", None)
    afip_cae_venc = getattr(venta, "afip_cae_vencimiento", None)
    afip_num_cbte = getattr(venta, "afip_numero_comprobante", None)

    if afip_cae:
        gap(1.0)
        line()
        draw_text("COMPROBANTE ELECTRÓNICO AFIP", f_head, Qt.AlignCenter)
        gap(0.5)
        if afip_num_cbte:
            draw_lr("Nº Comprobante", str(afip_num_cbte), f_h5)
        draw_lr("CAE", str(afip_cae), f_h5)
        if afip_cae_venc:
            draw_lr("Vencimiento CAE", str(afip_cae_venc), f_h5)

    # ===== Plantilla 100% editable (sin "footer" automático) =====
    _tpl_draw_block(p, px, draw_text, draw_image, line, gap, f_norm, f_head, venta, sucursal, direcciones, template_override=template_override)


    
    
    
def _compute_ticket_height_mm(venta, prn, width_mm=75.0, template_override: str = None):
    # Calcula el alto requerido en milímetros según lo que se va a imprimir
    from PyQt5.QtGui import QFont, QFontMetrics

    dpi_x = (getattr(prn, "logicalDpiX", lambda: 300)() or 300) if prn else 300
    mm_per_px = 25.4 / dpi_x

    # Fuentes H1-H5 configurables
    from app.config import load as _load_cfg_h
    _tk_cfg_h = _load_cfg_h().get("ticket", {})
    _fonts_h = _tk_cfg_h.get("fonts") or {}
    _h1 = int(_fonts_h.get("h1_pt") or _fonts_h.get("title_pt", 14))
    _h3 = int(_fonts_h.get("h3_pt") or _fonts_h.get("head_pt", 10))
    _h4 = int(_fonts_h.get("h4_pt") or _fonts_h.get("text_pt", 9))
    f_title = QFont("Arial"); f_title.setPointSize(_h1); f_title.setBold(True)
    f_head  = QFont("Arial"); f_head.setPointSize(_h3);  f_head.setBold(True)
    f_norm  = QFont("Arial"); f_norm.setPointSize(_h4)

    fm_t = QFontMetrics(f_title, prn) if prn else QFontMetrics(f_title)
    fm_h = QFontMetrics(f_head,  prn) if prn else QFontMetrics(f_head)
    fm_n = QFontMetrics(f_norm,  prn) if prn else QFontMetrics(f_norm)

    h_t = fm_t.height() * mm_per_px
    h_h = fm_h.height() * mm_per_px
    h_n = fm_n.height() * mm_per_px

    from app.config import load as _load_cfg_h
    _tk_cfg_h = _load_cfg_h().get("ticket", {})
    MARGIN_MM = float(_tk_cfg_h.get("margin_left_mm", 2.0))
    MARGIN_RIGHT_MM = float(_tk_cfg_h.get("margin_right_mm", 2.0))
    GAP_MM, SEP_MM = 1.2, 0.8
    total = MARGIN_MM

    # Encabezado profesional (separator + título + dirección + CUIT + separator + ticket/fecha/sucursal)
    total += h_n  # separator "===="
    total += h_t + GAP_MM  # business name
    total += h_n  # dirección
    total += h_n  # CUIT
    total += h_n  # separator "===="
    total += GAP_MM

    # Ticket number, fecha, sucursal
    if getattr(venta, "numero_ticket", None) or getattr(venta, "id", None):
        total += h_n
    try:
        if getattr(venta, "fecha", None):
            total += h_n
    except Exception:
        pass
    total += h_n  # sucursal
    total += GAP_MM

    # Ítems (tabla con encabezado: N. | Artículos | Prec. | Total)
    total += SEP_MM  # line separator
    total += h_h  # header row
    total += SEP_MM  # line separator
    items = getattr(venta, "_ticket_items", None) or []
    for it in items:
        total += h_n  # main row (qty + name + price + total)
        nombre = it.get("nombre", "") if isinstance(it, dict) else ""
        if len(nombre) > 18:
            total += h_n  # continuation line for long names
    total += SEP_MM  # line separator
    total += GAP_MM

    # Totales (subtotal + descuento + interés + TOTAL)
    if getattr(venta, "subtotal_base", None) is not None:
        total += h_n  # subtotal
    descuento_m = float(getattr(venta, "descuento_monto", 0.0) or 0.0)
    if descuento_m:
        total += h_n  # descuento
    if getattr(venta, "interes_monto", None):
        total += h_n  # interés
    total += h_h  # TOTAL - bold
    total += GAP_MM

    # Forma de pago (tabla: header + values row)
    total += h_h  # payment header row
    total += h_n  # payment values row
    forma_raw = (getattr(venta, "forma_pago", "") or getattr(venta, "modo_pago", "") or getattr(venta, "modo", "")).lower()
    is_card = ("tarj" in forma_raw)
    if is_card:
        cuotas = int(getattr(venta, "cuotas", 0) or 0)
        if cuotas <= 0:
            total += h_n  # extra line for non-cuota card
    total += GAP_MM

    # AFIP / CAE (si existe)
    afip_cae = getattr(venta, "afip_cae", None)
    if afip_cae:
        total += GAP_MM + SEP_MM  # gap + line
        total += h_h  # título "COMPROBANTE ELECTRÓNICO AFIP"
        total += GAP_MM * 0.5
        afip_num_cbte = getattr(venta, "afip_numero_comprobante", None)
        if afip_num_cbte:
            total += h_n  # Nº Comprobante
        total += h_n  # CAE
        afip_cae_venc = getattr(venta, "afip_cae_vencimiento", None)
        if afip_cae_venc:
            total += h_n  # Vencimiento CAE

    # Comentario (envuelto)
    com = getattr(venta, "comentario", None) or getattr(venta, "motivo", None) or getattr(venta, "nota", None)
    if com:
        total += GAP_MM + h_h
        avg_char_px = max(1, fm_n.averageCharWidth())
        avail_px = int(round((width_mm - MARGIN_MM - MARGIN_RIGHT_MM) / mm_per_px))
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
            import re
            _img_re_h = re.compile(r"^\s*\{\{img:\w+\}\}\s*$")
            lines = template_text.splitlines()
            line_count = 0
            for raw in lines:
                if raw.strip() in ("{{hr}}", "{{line}}"):
                    total += GAP_MM + SEP_MM
                elif "{{items}}" in raw:
                    items = getattr(venta, "_ticket_items", None) or []
                    line_count += max(0, len(items) * 2)
                elif _img_re_h.match(raw):
                    _isz = float((tk.get("images") or {}).get("size_mm", 20))
                    total += _isz + 1.0  # imagen + 1mm gap
                else:
                    line_count += 1
            total += line_count * h_n

            # Agregar espacio para CAE si existe (se dibuja automáticamente)
            afip_cae = getattr(venta, "afip_cae", None)
            if afip_cae:
                total += GAP_MM + SEP_MM  # gap + line
                total += h_h  # título "COMPROBANTE ELECTRÓNICO AFIP"
                total += GAP_MM * 0.5
                afip_num_cbte = getattr(venta, "afip_numero_comprobante", None)
                if afip_num_cbte:
                    total += h_n  # Nº Comprobante
                total += h_n  # CAE
                afip_cae_venc = getattr(venta, "afip_cae_vencimiento", None)
                if afip_cae_venc:
                    total += h_n  # Vencimiento CAE

    except Exception:
        pass
   

   # Footer (contemplar saltos de línea y envoltura)
    S = _ticket_strings()
    footer_texts = [S.get(k, "") for k in ("footer_1", "footer_2", "footer_3")]

    avg_char_px = max(1, fm_n.averageCharWidth())
    avail_px = int(round((width_mm - MARGIN_MM - MARGIN_RIGHT_MM) / mm_per_px))
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
        "footer_1":   tk.get("footer_msg", ""),
        "footer_2":   tk.get("google_review", "No olvide dejar una reseña en Google."),
        "footer_3":   tk.get("instagram", "Síganos en Instagram: PERFUMERIASU"),
    }
    


# ======= Plantilla: helpers =======

def _money(x):
    """Formatea un valor numérico como moneda argentina: $1.234,56"""
    try:
        v = float(x)
        formatted = f"${v:,.2f}"
        # Convertir formato US (1,234.56) a argentino (1.234,56)
        return formatted.replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "$0,00"

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

    # Obtener CUIT y dirección de config fiscal
    from app.config import load as load_config
    cfg = load_config()
    cuit_txt = cfg.get("fiscal", {}).get("cuit", "")
    business_dir = (direcciones or {}).get(sucursal, "") or S.get("address", "")

    # IVA breakdown
    iva_base = round(total / 1.21, 2) if total else 0.0
    iva_cuota = round(total - total / 1.21, 2) if total else 0.0

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
        "business":          S.get("business", ""),
        "title":             S.get("title", "TICKET"),
        "totales.descuento": (_money(descuento) if descuento else "-"),
        # Nuevos placeholders profesionales
        "business.cuit":     cuit_txt,
        "business.direccion": business_dir,
        "iva.base":          _money(iva_base),
        "iva.cuota":         _money(iva_cuota),
        "iva.porcentaje":    "21%",
        "vendedor":          "",
        # Datos AFIP individuales
        "afip.cae":          str(getattr(venta, "afip_cae", "") or ""),
        "afip.vencimiento":  str(getattr(venta, "afip_cae_vencimiento", "") or ""),
        "afip.comprobante":  str(getattr(venta, "afip_numero_comprobante", "") or ""),
    }

    # Valores numéricos para expresiones {{= ... }}
    ctx_numeric = {
        "totales.subtotal": subtotal,
        "totales.total":    total,
        "totales.descuento": descuento,
        "totales.interes":  interes,
        "iva.base":         iva_base,
        "iva.cuota":        iva_cuota,
        "abonado":          float(abonado or 0),
        "vuelto":           float(vuelto or 0),
        "pago.cuotas":      float(cuotas),
        "pago.monto_cuota": monto_cuota,
    }

    return ctx, ctx_numeric, items

def _generate_afip_qr_pixmap(venta, sucursal):
    """Genera QPixmap con QR de factura electrónica AFIP/ARCA.
    URL: https://www.afip.gob.ar/fe/qr/?p={base64_json}
    Retorna None si no hay datos suficientes."""
    try:
        afip_cae = getattr(venta, 'afip_cae', None)
        if not afip_cae:
            return None

        import json, base64
        from app.config import load as _load_cfg_qr
        cfg = _load_cfg_qr()
        fiscal = cfg.get("fiscal") or {}

        # CUIT del comerciante (solo dígitos)
        cuit_str = str(fiscal.get("cuit", "") or "").replace("-", "").replace(" ", "").strip()
        if not cuit_str:
            logger.warning("[QRCAE] No hay CUIT configurado, no se genera QR")
            return None
        cuit_num = int(cuit_str)

        # Punto de venta (por sucursal o global)
        pv_map = fiscal.get("puntos_venta_por_sucursal") or {}
        pto_vta = int(pv_map.get(sucursal) or fiscal.get("punto_venta", 1))

        # Tipo comprobante AFIP
        _TIPO_MAP = {"FACTURA_A": 1, "FACTURA_B": 6, "FACTURA_C": 11}
        tipo_cbte = str(getattr(venta, 'tipo_comprobante', '') or '').upper()
        tipo_cmp = _TIPO_MAP.get(tipo_cbte, 6)  # default Factura B

        nro_cmp = int(getattr(venta, 'afip_numero_comprobante', 0) or 0)
        importe = float(getattr(venta, 'total', 0) or 0)

        # Fecha de emisión
        fecha = getattr(venta, 'fecha', None)
        if fecha:
            import datetime
            if isinstance(fecha, str):
                fecha_str = fecha[:10]
            elif isinstance(fecha, datetime.datetime):
                fecha_str = fecha.strftime("%Y-%m-%d")
            else:
                fecha_str = str(fecha)[:10]
        else:
            import datetime
            fecha_str = datetime.datetime.now().strftime("%Y-%m-%d")

        # Tipo documento receptor (99=consumidor final, 80=CUIT)
        tipo_doc_rec = 80 if tipo_cbte == "FACTURA_A" else 99
        nro_doc_rec = 0

        payload = {
            "ver": 1,
            "fecha": fecha_str,
            "cuit": cuit_num,
            "ptoVta": pto_vta,
            "tipoCmp": tipo_cmp,
            "nroCmp": nro_cmp,
            "importe": round(importe, 2),
            "moneda": "PES",
            "ctz": 1,
            "tipoDocRec": tipo_doc_rec,
            "nroDocRec": nro_doc_rec,
            "tipoCodAut": "E",
            "codAut": int(str(afip_cae).strip()),
        }

        json_bytes = json.dumps(payload, separators=(',', ':')).encode('utf-8')
        b64 = base64.b64encode(json_bytes).decode('ascii')
        url = f"https://www.afip.gob.ar/fe/qr/?p={b64}"
        logger.info("[QRCAE] URL generada: %s", url[:120])

        import qrcode
        from io import BytesIO
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_L,  # 7% — menos módulos posible
            box_size=8,       # 8px/módulo → imagen nítida ~450px, se achica poco
            border=2,
        )
        qr.add_data(url)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white")
        buf = BytesIO()
        qr_img.save(buf, format='PNG')
        buf.seek(0)

        pm = QPixmap()
        pm.loadFromData(buf.read())
        if pm.isNull():
            logger.warning("[QRCAE] QPixmap generado es null")
            return None
        return pm

    except ImportError:
        logger.warning("[QRCAE] Libreria 'qrcode' no instalada")
        return None
    except Exception as ex:
        logger.error("[QRCAE] Error generando QR AFIP: %s", ex, exc_info=True)
        return None


def _safe_eval_expr(expr_str, ctx_numeric):
    """Evalúa expresiones aritméticas simples de forma segura.
    Solo permite: números, +, -, *, /, paréntesis y nombres del ctx.
    Retorna el resultado como float o None si falla."""
    import ast
    import operator
    _ops = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
    }
    # Reemplazar nombres con puntos por identificadores válidos
    # Ordenar por longitud descendente para evitar reemplazos parciales
    transformed = expr_str
    ctx_safe = {}
    for key in sorted(ctx_numeric.keys(), key=len, reverse=True):
        safe_key = key.replace(".", "_")
        transformed = transformed.replace(key, safe_key)
        ctx_safe[safe_key] = ctx_numeric[key]

    def _eval_node(node):
        # Número literal
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        # Variable (nombre del contexto)
        if isinstance(node, ast.Name):
            if node.id in ctx_safe:
                return float(ctx_safe[node.id])
            raise ValueError(f"Variable desconocida: {node.id}")
        # Operación binaria (+, -, *, /)
        if isinstance(node, ast.BinOp):
            op_fn = _ops.get(type(node.op))
            if op_fn is None:
                raise ValueError("Operador no soportado")
            left = _eval_node(node.left)
            right = _eval_node(node.right)
            if isinstance(node.op, ast.Div) and right == 0:
                raise ValueError("División por cero")
            return op_fn(left, right)
        # Negación unaria
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -_eval_node(node.operand)
        raise ValueError("Expresión no soportada")

    try:
        tree = ast.parse(transformed.strip(), mode='eval')
        result = _eval_node(tree.body)
        logger.debug("[EXPR] '%s' → '%s' = %s", expr_str, transformed.strip(), result)
        return result
    except Exception as e:
        logger.warning("[EXPR] Error evaluando '%s' (transformed='%s'): %s", expr_str, transformed, e)
        return None


def _tpl_render_lines(template_text, ctx, ctx_numeric=None, items=None, venta=None):
    """
    Convierte la plantilla en una lista de dicts 'línea' con campos:
    {'text': str, 'align': Qt.AlignmentFlag, 'bold': bool, 'italic': bool, 'is_rule': bool}
    Expande {{items}} en múltiples líneas.
    Soporta expresiones {{= expr }} con operaciones aritméticas.
    """
    if ctx_numeric is None:
        ctx_numeric = {}
    if items is None:
        items = []
    lines = []
    if not template_text:
        return lines

    import re
    _expr_re = re.compile(r"\{\{=\s*(.+?)\s*\}\}")

    def _repl_placeholders(s):
        out = s
        for k, v in ctx.items():
            out = out.replace("{{" + k + "}}", str(v))
        # Evaluar expresiones {{= ... }}
        def _eval_match(m):
            expr = m.group(1)
            logger.debug("[EXPR] Regex capturó: '%s', ctx_numeric keys=%s", expr, list((ctx_numeric or {}).keys()))
            result = _safe_eval_expr(expr, ctx_numeric or {})
            if result is not None:
                formatted = _money(result)
                logger.debug("[EXPR] Resultado formateado: %s", formatted)
                return formatted
            logger.warning("[EXPR] Expresión '%s' retornó None", expr)
            return ""
        out = _expr_re.sub(_eval_match, out)
        return out

    _img_re = re.compile(r"\{\{img:(\w+)\}\}")

    # Expansión de {{cae}} - Datos AFIP
    def _expand_cae():
        if venta is None:
            return []
        out = []
        afip_cae = getattr(venta, "afip_cae", None)
        if afip_cae:
            out.append("")  # Línea en blanco antes
            out.append("COMPROBANTE ELECTRÓNICO AFIP")
            afip_num_cbte = getattr(venta, "afip_numero_comprobante", None)
            if afip_num_cbte:
                out.append(f"Nº Comprobante: {afip_num_cbte}")
            out.append(f"CAE: {afip_cae}")
            afip_cae_venc = getattr(venta, "afip_cae_vencimiento", None)
            if afip_cae_venc:
                out.append(f"Vencimiento CAE: {afip_cae_venc}")
        return out

    # Expansión de {{items}} - FORMATO DE 3 LÍNEAS
    def _expand_items():
        out = []
        for it in (items or []):
            try:
                # Extraer cantidad
                if isinstance(it, dict):
                    cant = float(it.get("cantidad", 1) or 1)
                    pu   = float(it.get("precio_unitario") or it.get("precio_unit") or it.get("precio", 0.0) or 0.0)
                    nom  = str(it.get("nombre", "") or "")
                    cod  = str(it.get("codigo", "") or it.get("codigo_barra", "") or "")
                else:
                    cant = float(getattr(it, "cantidad", 1) or 1)
                    pu   = float(getattr(it, "precio_unit", None) or getattr(it, "precio_unitario", None) or getattr(it, "precio", 0.0) or 0.0)
                    # Intentar obtener nombre desde producto.nombre o directamente nombre
                    prod_obj = getattr(it, "producto", None)
                    if prod_obj:
                        nom = str(getattr(prod_obj, "nombre", "") or "")
                    else:
                        nom = str(getattr(it, "nombre", "") or "")
                    cod  = str(getattr(it, "codigo", "") or getattr(it, "codigo_barra", "") or "")

                tot  = cant * pu

                # Línea 1: Nombre del producto
                if len(nom) > 35:
                    nom = nom[:35] + "…"
                if nom:  # Solo agregar si hay nombre
                    out.append(nom)

                # Línea 2: Código de barras (solo si existe)
                if cod:
                    out.append(f"Código: {cod}")

                # Línea 3: Cantidad × precio → total
                out.append(f"Cant: {int(cant)} × { _money(pu) }      { _money(tot) }")
            except Exception as e:
                # Si falla, al menos mostrar algo
                pass
        return out

    # Expansión de {{iva.discriminado}} — todas las ventas con CAE (configurable)
    def _expand_iva_discriminado():
        if venta is None:
            return []
        afip_cae = getattr(venta, 'afip_cae', None)
        if not afip_cae:
            return []
        total = float(getattr(venta, 'total', 0) or 0)
        if not total:
            return []
        neto = round(total / 1.21, 2)
        iva = round(total - neto, 2)
        # Leer configuración de qué líneas mostrar
        from app.config import load as _load_cfg
        _cfg = _load_cfg()
        cfg_iva = (_cfg.get("ticket") or {}).get("iva_discriminado", {})
        lines = []
        if cfg_iva.get("mostrar_neto", True):
            lines.append(f"Subtotal Neto: {_money(neto)}")
        if cfg_iva.get("mostrar_iva", True):
            lines.append(f"IVA 21%: {_money(iva)}")
        if cfg_iva.get("mostrar_total", True):
            lines.append(f"TOTAL: {_money(total)}")
        return lines

    # Detectar si la plantilla ya incluye {{cae}}
    has_cae_placeholder = "{{cae}}" in template_text

    for raw in template_text.splitlines():
        raw = raw.rstrip("\n")

        # Línea horizontal
        if raw.strip() in ("{{hr}}", "{{line}}"):
            lines.append({"text": "", "align": Qt.AlignLeft, "bold": False, "italic": False, "is_rule": True})
            continue

        # Bloque CAE
        if "{{cae}}" in raw:
            cae_lines = _expand_cae()
            if cae_lines:
                # Agregar línea horizontal antes si no es la primera línea
                if lines:
                    lines.append({"text": "", "align": Qt.AlignLeft, "bold": False, "italic": False, "is_rule": True})
                # Primera línea (título) en negrita y centrada
                for i, l in enumerate(cae_lines):
                    if i == 0:  # línea en blanco
                        continue
                    elif i == 1:  # título "COMPROBANTE ELECTRÓNICO AFIP"
                        lines.append({"text": l, "align": Qt.AlignCenter, "bold": True, "italic": False, "is_rule": False})
                    else:  # resto de datos
                        lines.append({"text": l, "align": Qt.AlignLeft, "bold": False, "italic": False, "is_rule": False})
            continue

        # Bloque IVA discriminado (solo Factura A)
        if "{{iva.discriminado}}" in raw:
            iva_lines = _expand_iva_discriminado()
            if iva_lines:
                lines.append({"text": "", "align": Qt.AlignLeft, "bold": False, "italic": False, "is_rule": True})
                for l in iva_lines:
                    is_total = l.startswith("TOTAL")
                    lines.append({"text": l, "align": Qt.AlignRight if is_total else Qt.AlignLeft,
                                  "bold": is_total, "italic": False, "is_rule": False})
            continue

        # Bloque items
        if "{{items}}" in raw:
            for l in _expand_items():
                lines.append({"text": l, "align": Qt.AlignLeft, "bold": False, "italic": False, "is_rule": False})
            continue

        # QR CAE AFIP {{qrcae}}
        if raw.strip() == "{{qrcae}}":
            lines.append({
                "text": "", "align": Qt.AlignHCenter, "bold": False,
                "italic": False, "is_rule": False,
                "is_qrcae": True,
            })
            continue

        # Imagen {{img:xxx}}
        img_m = _img_re.search(raw.strip())
        if img_m and raw.strip() == img_m.group(0):
            # Línea que es SÓLO un placeholder de imagen
            img_key = img_m.group(1)
            lines.append({
                "text": "", "align": Qt.AlignHCenter, "bold": False,
                "italic": False, "is_rule": False,
                "is_image": True, "image_key": img_key,
            })
            continue

        # Alineado y estilo por prefijo
        align = Qt.AlignLeft
        bold = italic = False
        heading = None  # None = default (f_norm), 1-5 = H1-H5
        txt = raw.strip()

        for tag, a in (("{{center:", Qt.AlignHCenter), ("{{right:", Qt.AlignRight), ("{{left:", Qt.AlignLeft)):
            if txt.startswith(tag) and txt.endswith("}}"):
                txt = txt[len(tag):-2].strip()
                align = a
                break

        for tag, flag in (("{{b:", "b"), ("{{i:", "i"), ("{{leftb:", "lb"), ("{{centerb:", "cb"), ("{{rightb:", "rb")):
            if txt.startswith(tag) and txt.endswith("}}"):
                inner = txt[len(tag):-2].strip()
                if flag == "b":       bold = True;  txt = inner
                elif flag == "i":     italic = True; txt = inner
                elif flag == "lb":    bold = True;  align = Qt.AlignLeft;    txt = inner
                elif flag == "cb":    bold = True;  align = Qt.AlignHCenter; txt = inner
                elif flag == "rb":    bold = True;  align = Qt.AlignRight;   txt = inner
                break

        # Heading tags {{h1: texto}} ... {{h5: texto}}
        for h_tag, h_level in (("{{h1:", 1), ("{{h2:", 2), ("{{h3:", 3), ("{{h4:", 4), ("{{h5:", 5)):
            if txt.startswith(h_tag) and txt.endswith("}}"):
                txt = txt[len(h_tag):-2].strip()
                heading = h_level
                if h_level <= 3:
                    bold = True
                break

        txt = _repl_placeholders(txt)
        lines.append({"text": txt, "align": align, "bold": bold, "italic": italic, "is_rule": False, "heading": heading})

    return lines

def _tpl_draw_block(p, px, draw_text, draw_image, line, gap, f_norm, f_head, venta, sucursal, direcciones, template_override: str = None):
    from app.config import load as load_config
    cfg = load_config()
    tk  = (cfg.get("ticket") or {})
    template_text = (template_override if template_override is not None else tk.get("template") or "").strip()
    if not template_text:
        return

    ctx, ctx_numeric, items = _tpl_context(venta, sucursal, direcciones)
    lines = _tpl_render_lines(template_text, ctx, ctx_numeric, items, venta)

    # Precargar imagenes de ticket
    _img_cache = {}
    img_cfg = tk.get("images") or {}
    img_size_mm = float(img_cfg.get("size_mm", 20))   # 20mm=2cm default, 10mm=1cm
    try:
        from app.config import get_images_dir
        import os
        logger.info("[ticket-img] config images: %s, size=%smm", img_cfg, img_size_mm)
        for key, fname in img_cfg.items():
            if fname and key not in ("qr_url", "size_mm"):
                fpath = os.path.join(get_images_dir(), fname)
                logger.info("[ticket-img] cargando '%s' -> %s (existe=%s)", key, fpath, os.path.isfile(fpath))
                if os.path.isfile(fpath):
                    pm = QPixmap(fpath)
                    if not pm.isNull():
                        _img_cache[key] = pm
                        logger.info("[ticket-img] '%s' cargada OK (%dx%d)", key, pm.width(), pm.height())
                    else:
                        logger.warning("[ticket-img] '%s' QPixmap es null - formato no soportado?", key)
    except Exception as ex:
        logger.error("[ticket-img] error cargando imagenes: %s", ex, exc_info=True)

    # Construir fuentes H1-H5 para tags {{h1:}} ... {{h5:}}
    _fonts = tk.get("fonts") or {}
    _h1_pt = int(_fonts.get("h1_pt") or _fonts.get("title_pt", 14))
    _h2_pt = int(_fonts.get("h2_pt", 12))
    _h3_pt = int(_fonts.get("h3_pt") or _fonts.get("head_pt", 10))
    _h4_pt = int(_fonts.get("h4_pt") or _fonts.get("text_pt", 9))
    _h5_pt = int(_fonts.get("h5_pt", 7))
    _heading_sizes = {1: _h1_pt, 2: _h2_pt, 3: _h3_pt, 4: _h4_pt, 5: _h5_pt}

    # Pre-generar QR AFIP si hay alguna línea {{qrcae}}
    _qrcae_pixmap = None
    if any(ln.get("is_qrcae") for ln in lines):
        _qrcae_pixmap = _generate_afip_qr_pixmap(venta, sucursal)

    for ln in lines:
        if ln["is_rule"]:
            gap(); line(); continue

        # QR CAE AFIP
        if ln.get("is_qrcae"):
            if _qrcae_pixmap is not None:
                # QR AFIP: mínimo 25mm para legibilidad, sin suavizado
                qr_size = max(img_size_mm, 35.0)
                draw_image(_qrcae_pixmap, size_mm=qr_size, smooth=True)
            continue

        # Dibujar imagen si es linea de imagen
        if ln.get("is_image"):
            img_key = ln.get("image_key", "")
            pm = _img_cache.get(img_key)
            if pm is not None:
                logger.info("[ticket-img] dibujando '%s' a %smm", img_key, img_size_mm)
                draw_image(pm, size_mm=img_size_mm)
            else:
                logger.warning("[ticket-img] '%s' no encontrada en cache (configurada?)", img_key)
            continue

        h_level = ln.get("heading")
        if h_level and h_level in _heading_sizes:
            f = QFont("Arial")
            f.setPointSize(_heading_sizes[h_level])
            if ln["bold"]:   f.setBold(True)
            if ln["italic"]: f.setItalic(True)
        elif ln["bold"] or ln["italic"]:
            f = QFont(f_norm)
            if ln["bold"]:   f.setBold(True)
            if ln["italic"]: f.setItalic(True)
        else:
            f = f_norm
        draw_text(ln["text"], f, ln["align"])

    # ===== Agregar datos del CAE automáticamente solo si NO está en la plantilla =====
    has_cae_placeholder = "{{cae}}" in template_text
    afip_cae = getattr(venta, "afip_cae", None)
    afip_cae_venc = getattr(venta, "afip_cae_vencimiento", None)
    afip_num_cbte = getattr(venta, "afip_numero_comprobante", None)

    if afip_cae and not has_cae_placeholder:
        from PyQt5.QtCore import Qt, QRect
        # Función auxiliar para draw_lr (necesaria para mostrar CAE)
        def draw_lr_local(left, right, font):
            nonlocal p, px
            p.setFont(font)
            h = p.fontMetrics().height()
            # Obtener coordenadas y ancho de página
            page_rect = p.viewport()
            from app.config import load as _lcfg_cae
            _tcae = _lcfg_cae().get("ticket", {})
            _ml = float(_tcae.get("margin_left_mm", 2.0))
            _mr = float(_tcae.get("margin_right_mm", 2.0))
            x_start = page_rect.left() + px(_ml)  # margen izquierdo
            width = page_rect.width() - px(_ml) - px(_mr)   # ancho total menos márgenes
            left_w = int(width * 0.55)
            right_x = x_start + left_w
            right_w = width - left_w - px(0.6)

            # Obtener posición Y actual del painter
            import sys
            # Como no tenemos acceso directo a 'y', usamos el viewport actual
            current_y = getattr(draw_lr_local, '_y', page_rect.top() + px(_ml))

            p.drawText(QRect(x_start, current_y, left_w, h), Qt.AlignLeft | Qt.AlignVCenter, str(left))
            p.drawText(QRect(right_x, current_y, right_w, h), Qt.AlignRight | Qt.AlignVCenter, str(right))

            # Actualizar posición Y
            draw_lr_local._y = current_y + h

        gap(1.0)
        line()
        draw_text("COMPROBANTE ELECTRÓNICO AFIP", f_head, Qt.AlignCenter)
        gap(0.5)

        if afip_num_cbte:
            draw_text(f"Nº Comprobante: {afip_num_cbte}", f_norm, Qt.AlignLeft)
        draw_text(f"CAE: {afip_cae}", f_norm, Qt.AlignLeft)
        if afip_cae_venc:
            draw_text(f"Vencimiento CAE: {afip_cae_venc}", f_norm, Qt.AlignLeft)
