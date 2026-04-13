# Diálogos extraídos de gui.py original (sin cambios)
from PyQt5.QtWidgets import *
from PyQt5.QtCore import QSize,pyqtSignal, Qt, QTimer, QRectF,QSizeF,QRect
from PyQt5.QtGui import QPixmap, QPainter,QFont, QFontMetrics,QImage
from app.models import Producto  # usado en ProductosDialog.cargar()
from .common import icon, MIN_BTN_HEIGHT, ICON_SIZE
from io import BytesIO
# Fallback: si no está instalado python-barcode, no rompas el import del módulo
try:
    import barcode
    from barcode.writer import ImageWriter
except Exception:
    barcode = None
    ImageWriter = None
from PyQt5.QtPrintSupport import QPrinter, QPrintDialog, QPrinterInfo
import pandas
from app.repository import prod_repo
from app.gui.qt_helpers import FullCellCheckDelegate, NoScrollComboBox
from app.config import load as load_config
import unicodedata

PRODUCTOS_POR_PAGINA = 30



from PyQt5.QtCore import QRectF
from PyQt5.QtGui import QFont


def _px_per_mm(painter):
    # conversión robusta a pixeles por milímetro
    try:
        dpix = painter.device().logicalDpiX()
    except Exception:
        dpix = 96.0
    return dpix / 25.4


def _barcode_qimage_from_code128(code_str: str) -> QImage:
    """
    Devuelve una QImage con el código de barras CODE-128.
    Requiere 'python-barcode' (ya lo importas arriba).
    """
    try:
        import barcode
        from barcode.writer import ImageWriter
        buf = BytesIO()
        barcode.get('code128', str(code_str or ''), writer=ImageWriter()).write(
            buf,
            {
                'write_text': False,
                # Ajustes opcionales del grosor/altura:
                # 'module_width': 0.2, 'module_height': 12.0
            }
        )
        img = QImage.fromData(buf.getvalue())
        return img
    except Exception:
        return QImage()  # imagen nula -> el helper dibujará placeholder
    
    
def _draw_barcode_label(
    painter, page_width_px: int, code_text: str, name_text: str,
    *, max_width_mm=50.0, margin_mm=4.0, name_px=18, code_px=12, vgap_mm=1.5,
    barcode_height_px: int = None, text_height_px: int = None,
    barcode_img: QImage | None = None,
):
    """
    Dibuja una etiqueta: [barcode centrado] + [código] + [nombre].
    Si se pasan barcode_height_px y text_height_px, usa distribución fija (75%/25%).
    Devuelve 'y' relativo (px) que quedó al final de la etiqueta.
    """
    pxmm = _px_per_mm(painter)
    margin = int(round(margin_mm * pxmm))
    vgap = int(round(vgap_mm * pxmm))
    max_w = int(round(max_width_mm * pxmm))
    w = min(page_width_px - 2 * margin, max_w)

    x = (page_width_px - w) // 2  # centrado horizontal
    y = margin

    # Obtener fuente de la aplicación (Roboto si está disponible)
    font_family = "Roboto"
    try:
        from app.config import load as load_config
        cfg = load_config()
        font_family = cfg.get("theme", {}).get("font_family", "Roboto") or "Roboto"
    except Exception:
        pass

    # --- BARCODE (75% del espacio si se especifica) ---
    if barcode_height_px is not None:
        barcode_h = barcode_height_px - margin
    else:
        barcode_h = None

    if isinstance(barcode_img, QImage) and not barcode_img.isNull():
        bw = w
        if barcode_h:
            # Usar altura fija especificada
            bh = barcode_h
        else:
            # Calcular proporcionalmente
            bh = max(1, int(barcode_img.height() * (bw / barcode_img.width())))
        bar_rect = QRect(x, y, bw, bh)
        painter.drawImage(bar_rect, barcode_img)
        y += bh + vgap
    else:
        # fallback: rectángulo placeholder
        ph = barcode_h if barcode_h else int(12 * pxmm)
        painter.fillRect(QRect(x, y, w, ph), Qt.black)
        painter.fillRect(QRect(x + 2, y + 2, w - 4, ph - 4), Qt.white)
        y += ph + vgap

    # --- TEXTO (25% del espacio si se especifica) ---
    if text_height_px is not None:
        # Dividir el espacio de texto entre código y nombre
        available_text_h = text_height_px - margin
        code_h = int(available_text_h * 0.4)  # 40% para código
        name_h = int(available_text_h * 0.6)  # 60% para nombre

        # Calcular tamaño de fuente autoajustable
        code_font_px = max(8, min(code_h - 2, 14))
        name_font_px = max(10, min(name_h - 2, 18))
    else:
        code_font_px = code_px
        name_font_px = name_px

    # --- TEXTO: código ---
    f_code = QFont(font_family)
    f_code.setPixelSize(code_font_px)
    painter.setFont(f_code)
    fm_code = QFontMetrics(f_code)
    code_line = fm_code.elidedText(code_text or "", Qt.ElideRight, w)
    painter.drawText(QRect(x, y, w, fm_code.height()), Qt.AlignHCenter | Qt.TextSingleLine, code_line)
    y += fm_code.height() + vgap

    # --- TEXTO: nombre ---
    f_name = QFont(font_family)
    f_name.setPixelSize(name_font_px)
    painter.setFont(f_name)
    fm_name = QFontMetrics(f_name)
    name_line = fm_name.elidedText(name_text or "", Qt.ElideRight, w)
    painter.drawText(QRect(x, y, w, fm_name.height()), Qt.AlignHCenter | Qt.TextSingleLine, name_line)
    y += fm_name.height()

    return y + margin



class DevolucionDialog(QDialog):
    def __init__(self, venta, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f'Devolución Ticket {getattr(venta, "numero_ticket", venta.id)}')
        layout = QVBoxLayout(self)

        self.table_dev = QTableWidget(len(venta.items), 4)
        self.table_dev.setHorizontalHeaderLabels(['Código','Nombre','Cantidad','Precio'])

        for r, item in enumerate(venta.items):
            codigo = (
                getattr(item, 'codigo', None)
                or getattr(item, 'producto_codigo', None)
                or (getattr(item.producto, 'codigo_barra', '') if getattr(item, 'producto', None) else '')
                or ''
            )
            nombre = getattr(item.producto, 'nombre', '') if getattr(item, 'producto', None) else ''
            cantidad = getattr(item, 'cantidad', 1)
            precio_unit = (
                getattr(item, 'precio_unit', None)
                or getattr(item, 'precio_unitario', None)
                or getattr(item, 'precio', 0.0)
            )

            self.table_dev.setItem(r, 0, QTableWidgetItem(str(codigo)))
            self.table_dev.setItem(r, 1, QTableWidgetItem(str(nombre)))
            self.table_dev.setItem(r, 2, QTableWidgetItem(str(cantidad)))
            self.table_dev.setItem(r, 3, QTableWidgetItem(f'{float(precio_unit):.2f}'))

            
        layout.addWidget(self.table_dev)
        # Quitar números de la izquierda
        self.table_dev.verticalHeader().setVisible(False)

        # +2 pt legibilidad
        f = self.table_dev.font()
        f.setPointSize(f.pointSize() + 2)
        self.table_dev.setFont(f)

        # Encabezado en negrita y tamaños de columna
        hdr = self.table_dev.horizontalHeader()
        hf = hdr.font(); hf.setBold(True); hdr.setFont(hf)
        hdr.setSectionResizeMode(QHeaderView.Interactive)
        hdr.setStretchLastSection(True)
        self.table_dev.setColumnWidth(0, 120)  # Código
        self.table_dev.setColumnWidth(1, 250)  # Nombre
        self.table_dev.setColumnWidth(2, 80)   # Cantidad
        self.table_dev.resizeColumnsToContents()

        # Abrir el diálogo del tamaño del contenido
        total_w = sum(hdr.sectionSize(i) for i in range(self.table_dev.columnCount())) + 48
        rows_h = min(8, self.table_dev.rowCount()) * self.table_dev.verticalHeader().defaultSectionSize() + 160
        self.resize(max(560, total_w), max(360, rows_h))
        btn_box = QHBoxLayout()
        btn_ok = QPushButton('Guardar Cambios'); btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton('Cancelar'); btn_cancel.clicked.connect(self.reject)
        btn_box.addStretch(); btn_box.addWidget(btn_ok); btn_box.addWidget(btn_cancel)
        layout.addLayout(btn_box)
        # --- Live search ---



    def get_modified(self):
        """Devuelve lista de tuplas (codigo_barra, nueva_cantidad)."""
        mods = []
        for r in range(self.table_dev.rowCount()):
            codigo = self.table_dev.item(r,0).text()
            cant   = int(self.table_dev.item(r,2).text())
            mods.append((codigo, cant))
        return mods

class ProductosDialog(QDialog):

    data_changed = pyqtSignal() 
    """
    Listado de productos con filtros (nombre, categoría, precio min/max),
    checkbox por fila y acciones: Seleccionar todo (filtrado), Editar precios,
    Eliminar seleccionados, Imprimir códigos, Exportar.
    """
    def __init__(self, session, parent=None):
        super().__init__(parent)

        self.session = session
        self.prod_repo = prod_repo(self.session)
        self.pagina_actual = 0  # Para la paginación
        
        self.main = parent if parent and hasattr(parent, 'history') else None        
        
        self.setWindowTitle('Listado de productos')
        self.resize(900, 600)
        
        
        root = QVBoxLayout(self)

        # Filtros
        filtros = QHBoxLayout()
        self.f_nombre = QLineEdit();  self.f_nombre.setPlaceholderText('Nombre')
        self.f_categ  = QLineEdit();  self.f_categ.setPlaceholderText('Categoría')
        self.f_min    = QLineEdit();  self.f_min.setPlaceholderText('Precio min')
        self.f_max    = QLineEdit();  self.f_max.setPlaceholderText('Precio max')

        btn_aplicar = QPushButton('Filtrar')
        btn_sel_all = QPushButton('Seleccionar (filtrado)')
        btn_cerrar  = QPushButton('Cerrar')

        filtros.addWidget(self.f_nombre)
        filtros.addWidget(self.f_categ)
        filtros.addWidget(self.f_min)
        filtros.addWidget(self.f_max)
        filtros.addWidget(btn_aplicar)
        filtros.addWidget(btn_sel_all)
        filtros.addStretch()
        filtros.addWidget(btn_cerrar)

        root.addLayout(filtros)
        # --- Live search (código/nombre/categoría) ---
        self.ed_buscar = QLineEdit(self)
        self.ed_buscar.setPlaceholderText("Buscar por código, nombre o categoría...")
        root.insertWidget(0, self.ed_buscar)  # o agrégalo donde prefieras

        # Debounce para no recargar en cada tecla
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(180)  # ms
        self.ed_buscar.textEdited.connect(lambda _=None: self._debounce.start())
        self._debounce.timeout.connect(self.cargar)
        for fld in (self.f_nombre, self.f_categ, self.f_min, self.f_max):
            fld.textEdited.connect(lambda _=None: self._debounce.start())
        # estado del filtro
        self._filtro_texto = ""
        # Tabla (¡sin ellipsis!)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(['Sel','ID','Código','Nombre','Precio','Categoría'])
        self.table.setFont(QFont("Arial", 11))                # Fuente global
        self.table.verticalHeader().setVisible(False)          # Sin números de fila

        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.Interactive)
        hdr.setStretchLastSection(True)
        self.table.setColumnWidth(0, 36)   # Sel
        self.table.setColumnWidth(1, 40)   # ID
        self.table.setColumnWidth(2, 120)  # Código
        self.table.setColumnWidth(3, 250)  # Nombre
        self.table.setColumnWidth(4, 72)   # Precio
        
        root.addWidget(self.table)
        self.table.itemChanged.connect(self._on_item_changed)


        # --- Barra de acciones (igual que pestaña Productos) ---
        acciones = QHBoxLayout()
        btn_a   = QPushButton("Agregar/Actualizar"); btn_a.setIcon(icon('add.svg'));    btn_a.clicked.connect(self.dlg_agregar)
        btn_d   = QPushButton("Eliminar");           btn_d.setIcon(icon('delete.svg')); btn_d.clicked.connect(self.dlg_eliminar)
        btn_u   = QPushButton("Restaurar");          btn_u.setIcon(icon('undo.svg'));   btn_u.clicked.connect(self.dlg_deshacer)
        btn_m   = QPushButton("Editar Precios");     btn_m.setIcon(icon('edit.svg'));   btn_m.clicked.connect(self.dlg_editar_precios)
        btn_p   = QPushButton("Imprimir");           btn_p.setIcon(icon('print.svg'));  btn_p.clicked.connect(self.dlg_imprimir_codigos)
        btn_imp = QPushButton("Importar");           btn_imp.setIcon(icon('import.svg'));btn_imp.clicked.connect(self.dlg_importar)
        btn_exp = QPushButton("Exportar");           btn_exp.setIcon(icon('export.svg'));btn_exp.clicked.connect(self.dlg_exportar)

        for b in (btn_a, btn_d, btn_u, btn_m, btn_imp, btn_exp, btn_p):
            b.setMinimumHeight(MIN_BTN_HEIGHT)
            b.setIconSize(ICON_SIZE)
            acciones.addWidget(b)

        root.addLayout(acciones)
        # Poblar al inicio
        

        # Delegate para checkbox full-cell (con soporte Shift+Click)
        self.table.setItemDelegateForColumn(0, FullCellCheckDelegate(self.table, column=0, padding=2))
        # Conexiones
        btn_aplicar.clicked.connect(self._aplicar_filtro_inputs)        
        btn_sel_all.clicked.connect(self.seleccionar_filtrado)
        btn_cerrar.clicked.connect(self.reject)

        self.pagina_actual = 0

        # Botones de navegación y label de página
        self.btn_anterior = QPushButton("← Anterior")
        self.btn_siguiente = QPushButton("Siguiente →")
        self.lbl_paginacion = QLabel("Página 1")
        self.btn_anterior.clicked.connect(self.ir_pagina_anterior)
        self.btn_siguiente.clicked.connect(self.ir_pagina_siguiente)

        # Layout de navegación (agregalo debajo de la tabla en el layout principal)
        nav_layout = QHBoxLayout()
        nav_layout.addWidget(self.btn_anterior)
        nav_layout.addWidget(self.lbl_paginacion)
        nav_layout.addWidget(self.btn_siguiente)
        root.addLayout(nav_layout)  # Donde 'root' es tu QVBoxLayout principal del dialog
        self.cargar()
    
    
    def cargar(self):
        # --- Helpers locales (sin tocar el resto de la clase) ---
        def _norm(s: str) -> str:
            if not s:
                return ""
            s = unicodedata.normalize("NFKD", s)
            s = "".join(ch for ch in s if not unicodedata.combining(ch))
            return s.lower().strip()

        def _to_float(txt):
            txt = (txt or "").strip().replace(",", ".")
            if not txt:
                return None
            try:
                return float(txt)
            except ValueError:
                return None

        # 1) Traer todos
        todos = self.prod_repo.listar_todos()

        # 2) Leer filtros (si algún campo no existe, se ignora)
        texto = _norm(getattr(self.ed_buscar, "text", lambda: "")())
        f_nom = _norm(getattr(self.f_nombre, "text", lambda: "")())
        f_cat = _norm(getattr(self.f_categ, "text",  lambda: "")())
        pmin  = _to_float(getattr(self.f_min,   "text", lambda: "")())
        pmax  = _to_float(getattr(self.f_max,   "text", lambda: "")())

        # 3) Aplicar filtros ANTES de paginar
        productos = []
        for p in todos:
            nom = _norm(getattr(p, "nombre", "") or "")
            cod = _norm(getattr(p, "codigo_barra", "") or "")
            cat = _norm(getattr(p, "categoria", "") or "")
            price = float(getattr(p, "precio", 0.0) or 0.0)

            # filtro global
            if texto and (texto not in nom and texto not in cod and texto not in cat):
                continue
            # filtro específicos
            if f_nom and f_nom not in nom:
                continue
            if f_cat and f_cat not in cat:
                continue
            if pmin is not None and price < pmin:
                continue
            if pmax is not None and price > pmax:
                continue

            productos.append(p)

        # 4) Paginación
        total = len(productos)
        por_pagina = PRODUCTOS_POR_PAGINA
        pagina = getattr(self, "pagina_actual", 0)
        max_pag = max(0, (total - 1) // por_pagina)
        if pagina > max_pag:
            pagina = max_pag
            self.pagina_actual = pagina

        ini = pagina * por_pagina
        fin = ini + por_pagina
        paginados = productos[ini:fin]

        # 5) Pintar tabla
        tbl = self.table
        sorting = tbl.isSortingEnabled()
        tbl.setSortingEnabled(False)
        self._suppress_change = True
        tbl.setUpdatesEnabled(False)

        tbl.setRowCount(0)
        tbl.setRowCount(len(paginados))
        for r, p in enumerate(paginados):
            # Col 0: checkbox
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            chk.setCheckState(Qt.Unchecked)
            chk.setFont(QFont("Arial", 11))
            tbl.setItem(r, 0, chk)

            # Cols 1..5: ID, Código, Nombre, Precio, Categoría
            vals = [p.id, p.codigo_barra, p.nombre, f"{(p.precio or 0.0):.2f}", p.categoria or ""]
            for c, val in enumerate(vals, start=1):
                it = QTableWidgetItem(str(val))
                it.setFont(QFont("Arial", 11))
                # Guarda el ID en UserRole por si ocultas la col 1
                if c in (2, 3):  # Código o Nombre
                    it.setData(Qt.UserRole, p.id)
                # Editables: Nombre(3), Precio(4), Categoría(5)
                if c in (3, 4, 5):
                    it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
                else:
                    it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                tbl.setItem(r, c, it)

        tbl.setUpdatesEnabled(True)
        self._suppress_change = False
        tbl.setSortingEnabled(sorting)

        # 6) Footer de página
        self.lbl_paginacion.setText(
            f"Página {pagina+1} de {max_pag+1} (Mostrando {ini+1}-{min(fin, total)} de {total})"
        )
        self.btn_anterior.setEnabled(pagina > 0)
        self.btn_siguiente.setEnabled(pagina < max_pag)

        # 7) Ajustar columnas si tienes helper
        if hasattr(self, "_configurar_columnas_productos"):
            self._configurar_columnas_productos()
        #Botones para navegacion
    def ir_pagina_anterior(self):
            if self.pagina_actual > 0:
                self.pagina_actual -= 1
                self.cargar()

    def ir_pagina_siguiente(self):
        # Calcula el máximo según el total actual
        prods = self.prod_repo.listar_todos()  # <-- ANTES: self.prod_repo()
        total = len(prods)
        max_pag = max(0, (total - 1) // PRODUCTOS_POR_PAGINA)
        if self.pagina_actual < max_pag:
            self.pagina_actual += 1
            self.cargar()

    def seleccionar_filtrado(self):
        # Marca todos los checkboxes visibles (filtrados) de la columna 0
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if it:
                it.setCheckState(Qt.Checked)

    def _rows_checked_dialog(self):
        rows = []
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if it and it.checkState() == Qt.Checked:
                rows.append(r)
        return rows

    def dlg_eliminar(self):
        if QMessageBox.question(self, 'Confirmar', '¿Eliminar productos seleccionados?',
                                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        # filas marcadas
        rows = [r for r in range(self.table.rowCount())
                if (self.table.item(r, 0) and self.table.item(r, 0).checkState() == Qt.Checked)]
        if not rows:
            QMessageBox.information(self, 'Eliminar', 'No hay seleccionados.')
            return

        # recolectar IDs SIN consultar a la DB uno a uno
        ids = []
        for r in rows:
            it = self.table.item(r, 1)  # Col 1 = ID
            if it:
                try:
                    ids.append(int(it.text()))
                except Exception:
                    pass

        # borrar de golpe
        try:
            self.prod_repo.eliminar_ids(ids)   # <- usa el método rápido del repo
        except Exception as e:
            QMessageBox.warning(self, 'Eliminar', f'No se pudo eliminar:\n{e}')
            return

        # refresco de UI "congelando" la tabla
        from app.gui.qt_helpers import freeze_table
        with freeze_table(self.table):
            self.cargar()  # tu método que repinta página/tabla

        # notificar a ventana principal si corresponde
        try:
            self.data_changed.emit()
        except Exception:
            pass

        QMessageBox.information(self, 'Eliminar', f'Eliminados {len(ids)} producto(s).')

    def dlg_deshacer(self):
        if getattr(self, 'main', None):
            self.main.deshacer()  # reutiliza el historial global
            self.cargar()         # refresca el listado del diálogo
        else:
            QMessageBox.information(self,'Restaurar','No hay historial global disponible.')

    def dlg_editar_precios(self):
        modos = ['Porcentaje', 'Monto fijo', 'Valor final']
        modo, ok = QInputDialog.getItem(self, 'Modo de edición', 'Seleccione modo:', modos, 0, False)
        if not ok: return
        if modo == 'Porcentaje':
            val, ok = QInputDialog.getDouble(self, 'Porcentaje', 'Introduce % (10 o -5):', decimals=2)
        elif modo == 'Valor final':
            val, ok = QInputDialog.getDouble(self, 'Valor final', 'Nuevo precio para todos:', 0, 0, 999999, 2)
        else:
            val, ok = QInputDialog.getDouble(self, 'Monto fijo', 'Introduce importe (+/-):', decimals=2)
        if not ok: return

        rows = self._rows_checked_dialog()
        if not rows:
            QMessageBox.information(self,'Editar precios','No hay seleccionados.')
            return

        for r in rows:
            pid  = int(self.table.item(r, 1).text())
            prod = self.session.query(Producto).get(pid)
            if modo == 'Porcentaje':
                prod.precio *= (1 + val/100.0)
            elif modo == 'Valor final':
                prod.precio = val
            else:
                prod.precio += val
            prod.precio = max(prod.precio, 0.0)
        self.session.commit()
        self.cargar()
        self.data_changed.emit()
        QMessageBox.information(self,'Completado',f'Actualizados {len(rows)} producto(s).')

    def dlg_imprimir_codigos(self):
        # 1) Filas marcadas
        rows = []
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if it and it.checkState() == Qt.Checked:
                rows.append(r)

        if not rows:
            QMessageBox.information(self, "Imprimir", "Marca al menos un producto.")
            return

        # 2) Preparar (código, nombre) desde columnas 2 y 3 (con fallback si falta)
        items = []
        for r in rows:
            id_it   = self.table.item(r, 1)  # ID (col 1)
            code_it = self.table.item(r, 2)  # Código (col 2)
            name_it = self.table.item(r, 3)  # Nombre (col 3)

            pid  = int(id_it.text()) if id_it and id_it.text().strip().isdigit() else 0
            code = (code_it.text().strip() if code_it else "")
            name = (name_it.text().strip() if name_it else "")

            # Fallback: si no hay código, generamos uno legible por el lector (Code128)
            if not code:
                code = f"ID{pid:08d}"  # ej: ID00001234

            items.append((code, name))

        if not items:
            QMessageBox.information(self, "Imprimir", "No hay códigos válidos.")
            return

        # 3) Obtener configuración de etiquetas
        cfg = load_config()
        barcode_cfg = cfg.get('barcode') or {}
        default_width_cm = barcode_cfg.get('width_cm', 5.0)
        default_height_cm = barcode_cfg.get('height_cm', 3.0)
        barcode_ratio = barcode_cfg.get('barcode_ratio', 0.75)
        text_ratio = barcode_cfg.get('text_ratio', 0.25)

        # Configurar impresora (usa impresora por defecto guardada, si existe)
        default_name = (cfg.get('printers', {}) or {}).get('barcode_printer')

        printer = QPrinter(QPrinter.HighResolution)
        printer.setResolution(203)  # 203 dpi típico para térmicas
        try:
            for p in QPrinterInfo.availablePrinters():
                if default_name and p.printerName() == default_name:
                    printer.setPrinterName(default_name)
                    break
        except Exception:
            pass

        # 4) Tamaño en cm (con valores de config como default, máx 8cm)
        w_cm, ok1 = QInputDialog.getDouble(
            self, 'Imprimir códigos', 'Ancho (cm):',
            default_width_cm, 1.0, 8.0, 1
        )
        if not ok1:
            return
        h_cm, ok2 = QInputDialog.getDouble(
            self, 'Imprimir códigos', 'Alto (cm):',
            default_height_cm, 1.0, 8.0, 1
        )
        if not ok2:
            return

        # Calcular tamaño de página para múltiples etiquetas
        page_height_cm = h_cm * len(items)
        if page_height_cm > 100:  # máximo razonable
            page_height_cm = 100.0

        printer.setPaperSize(QSizeF(QSize(int(w_cm*10), int(page_height_cm*10))), QPrinter.Millimeter)
        printer.setOrientation(QPrinter.Portrait)
        printer.setFullPage(True)

        # 5) Elegir impresora
        pd = QPrintDialog(printer, self)
        pd.setWindowTitle('Elegir impresora (códigos)')
        if pd.exec_() != QPrintDialog.Accepted:
            return

        # Helper local mm→px
        def mm_to_px(mm: float) -> int:
            dpi = printer.resolution() or 203
            return int(mm * (dpi / 25.4))

        # 6) Imprimir etiquetas apiladas
        painter = QPainter()
        if not painter.begin(printer):
            QMessageBox.warning(self, "Imprimir", "No se pudo iniciar la impresora.")
            return

        try:
            page = printer.pageRect()
            width = page.width()

            # Altura de cada etiqueta en px
            label_height_px = mm_to_px(h_cm * 10)
            y = 0

            for code, name in items:
                try:
                    painter.save()
                    painter.translate(0, y)
                    img = _barcode_qimage_from_code128(code)

                    # Calcular distribución 75%/25%
                    barcode_height = int(label_height_px * barcode_ratio)
                    text_height = int(label_height_px * text_ratio)

                    y_end = _draw_barcode_label(
                        painter, width, code, name_text=name,
                        max_width_mm=w_cm * 10,
                        margin_mm=2.0,
                        barcode_height_px=barcode_height,
                        text_height_px=text_height,
                        barcode_img=img,
                    )
                finally:
                    painter.restore()

                y += label_height_px

                # ¿Cabe otra etiqueta en la misma página?
                if y + label_height_px > page.height():
                    printer.newPage()
                    y = 0
        finally:
            painter.end()
    def dlg_importar(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Importar Excel', '', 'Excel Files (*.xlsx *.xls)')
        if not path: return
        try:
            df = pandas.read_excel(path, dtype={'codigo_barra': str})
        except Exception as e:
            QMessageBox.warning(self,'Error',f'No se pudo leer:\n{e}')
            return
        cont_tot, cont_nuevos = 0, 0
        for _, row in df.iterrows():
            codigo = str(row.get('codigo_barra','')).strip()
            nombre = str(row.get('nombre','')).strip()
            try: precio = float(row.get('precio',0))
            except: precio = 0.0
            categoria = str(row.get('categoria','')).strip() or None
            if not codigo or not nombre:
                continue
            prod = self.session.query(Producto).filter_by(codigo_barra=codigo).first()
            if prod:
                prod.nombre = nombre; prod.precio = precio; prod.categoria = categoria
            else:
                self.session.add(Producto(codigo_barra=codigo, nombre=nombre, precio=precio, categoria=categoria))
                cont_nuevos += 1
            cont_tot += 1
        self.session.commit(); 
        self.cargar()
        self.data_changed.emit()  
        QMessageBox.information(self,'Importación', f'Procesadas: {cont_tot}\nNuevos: {cont_nuevos}')

    def dlg_exportar(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Exportar Excel', 'productos.xlsx', 'Excel Files (*.xlsx)')
        if not path: return
        productos = self.session.query(Producto).all()
        data = [{
            'codigo_barra': p.codigo_barra,
            'nombre': p.nombre,
            'precio': p.precio,
            'categoria': p.categoria or ''
        } for p in productos]
        df = pandas.DataFrame(data)
        try:
            df.to_excel(path, index=False)
        except Exception as e:
            QMessageBox.warning(self,'Error',f'No se pudo guardar:\n{e}')
            return
        QMessageBox.information(self,'Exportación', f'Guardado en:\n{path}')

    def dlg_agregar(self):
        # Formulario rápido por diálogos
        codigo, ok = QInputDialog.getText(self,'Agregar','Código de barras:')
        if not ok or not codigo.strip(): return
        nombre, ok = QInputDialog.getText(self,'Agregar','Nombre:')
        if not ok or not nombre.strip(): return
        precio, ok = QInputDialog.getDouble(self,'Agregar','Precio:', decimals=2)
        if not ok: return
        categoria, ok = QInputDialog.getText(self,'Agregar','Categoría (opcional):')
        if not ok: categoria = None
        codigo = codigo.strip(); nombre = nombre.strip(); categoria = (categoria or '').strip() or None

        existe = self.session.query(Producto).filter_by(codigo_barra=codigo).first()
        if existe:
            existe.nombre = nombre; existe.precio = precio; existe.categoria = categoria
        else:
            self.session.add(Producto(codigo_barra=codigo, nombre=nombre, precio=precio, categoria=categoria))
            if getattr(self, 'main', None):
                self.main.history.append(('add', {
                    'codigo_barra': codigo,
                    'nombre': nombre,
                    'precio': precio,
                    'categoria': categoria
                }))

        self.session.commit()
        self.cargar()
        self.data_changed.emit()
        QMessageBox.information(self,'Guardar','Producto agregado/actualizado.')
    def _on_item_changed(self, item):
        # Evitar recursion cuando llenamos/normalizamos celdas
        if getattr(self, "_suppress_change", False):
            return

        col = item.column()
        if col not in (3, 4, 5):   # 3=Nombre, 4=Precio, 5=Categoría
            return

        row = item.row()
        pid_item = self.table.item(row, 1)  # ID en col 1
        if not pid_item:
            return
        try:
            pid = int(pid_item.text())
        except ValueError:
            return

        prod = self.session.query(Producto).get(pid)
        if not prod:
            return

        txt = (item.text() or "").strip()

        if col == 3:
            prod.nombre = txt

        elif col == 4:
            try:
                val = float(txt.replace(",", "."))
            except ValueError:
                QMessageBox.warning(self, "Precio inválido", "Introduce un número válido.")
                # revertir al valor anterior
                self._suppress_change = True
                item.setText(f"{prod.precio:.2f}")
                self._suppress_change = False
                return
            prod.precio = max(val, 0.0)
            # normalizar formato en la celda
            self._suppress_change = True
            item.setText(f"{prod.precio:.2f}")
            self._suppress_change = False

        elif col == 5:
            prod.categoria = txt or None

        # Guardar cambios
        self.session.commit()

        # Opcional: avisar al resto (si lo usas para refrescar la pestaña principal)
        if hasattr(self, "data_changed"):
            try:
                self.data_changed.emit()
            except Exception:
                pass

        # Quitar selección azul y continuar fluido
        self.table.clearSelection()

    def closeEvent(self, e):
        try:
            if hasattr(self, '_debounce'):
                self._debounce.stop()
        except Exception:
            pass
        super().closeEvent(e)   
        
        
    def exportar_codigos_png(self):
            # 1) Selección
        rows = []
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if it and it.checkState() == Qt.Checked:
                rows.append(r)
        if not rows:
            QMessageBox.information(self, "Exportar PNG", "Marcá al menos un producto.")
            return

        items = []
        for r in rows:
            code = self.table.item(r, 2).text()
            name = self.table.item(r, 3).text()
            items.append((code, name))

        # 2) Archivo destino
        path, _ = QFileDialog.getSaveFileName(self, "Guardar etiquetas como PNG",
                                            "etiquetas_codigos.png", "Imágenes PNG (*.png)")
        if not path:
            return

        # 3) “Página” de 8x20 cm a ~300 DPI aprox (945 x 2362 px)
        w_px, h_px = 945, 2362
        img = QImage(w_px, h_px, QImage.Format_ARGB32); img.fill(0xffffffff)
        p = QPainter(img)
        try:
            page_height = h_px
            margin = 24
            width = w_px
            y = margin

            for code, name in items:
                p.save()
                p.translate(0, y - margin)
                y_end = _draw_barcode_label(p, width, code, name, margin=margin)
                p.restore()

                if y_end +30 > page_height:
                    break  # (simple; si querés multi-página PNG, armamos varias imágenes)
                else:
                    y = y_end
        finally:
            p.end()

        if img.save(path, "PNG"):
            QMessageBox.information(self, "Exportar PNG", f"Guardado: {path}")
        else:
            QMessageBox.warning(self, "Exportar PNG", "No se pudo guardar la imagen.")
            
    def _norm(self, s: str) -> str:
        if not s:
            return ""
        s = unicodedata.normalize("NFKD", s)
        s = "".join(ch for ch in s if not unicodedata.combining(ch))
        return s.lower().strip()

    def _to_float(self, txt):
        """Convierte texto a float, devuelve None si no es válido."""
        txt = (txt or "").strip().replace(",", ".")
        if not txt:
            return None
        try:
            return float(txt)
        except ValueError:
            return None

    def _leer_filtros(self):
            # Campos pueden no existir; se ignoran
        texto = self._norm(getattr(self.ed_buscar, "text", lambda: "")())
        f_nom = self._norm(getattr(getattr(self, "f_nombre", None), "text", lambda: "")())
        f_cat = self._norm(getattr(getattr(self, "f_categ",  None), "text", lambda: "")())
        pmin  = self._to_float(getattr(getattr(self, "f_min",   None), "text", lambda: "")())
        pmax  = self._to_float(getattr(getattr(self, "f_max",   None), "text", lambda: "")())
        return {"texto": texto, "nombre": f_nom, "categoria": f_cat, "pmin": pmin, "pmax": pmax}
    
    def _filtrar(self, items):
        F = self._leer_filtros()
        out = []
        for p in items:
            nom = self._norm(getattr(p, "nombre", "") or "")
            cod = self._norm(getattr(p, "codigo_barra", "") or "")
            cat = self._norm(getattr(p, "categoria", "") or "")
            price = float(getattr(p, "precio", 0.0) or 0.0)

            if F["texto"] and (F["texto"] not in nom and F["texto"] not in cod and F["texto"] not in cat):
                continue
            if F["nombre"] and F["nombre"] not in nom:
                continue
            if F["categoria"] and F["categoria"] not in cat:
                continue
            if F["pmin"] is not None and price < F["pmin"]:
                continue
            if F["pmax"] is not None and price > F["pmax"]:
                continue
            out.append(p)
        return out

    def _aplicar_filtro_inputs(self):
        self.pagina_actual = 0
        self.cargar()
        
        
        # ====== DIÁLOGOS RÁPIDOS PARA PRODUCTOS (Agregar / Editar) ======
class QuickAddProductoDialog(QDialog):
    """Popup mínimo: Código / Nombre / Precio / Categoría"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Agregar producto")
        lay = QFormLayout(self)

        self.ed_codigo = QLineEdit(self);  self.ed_codigo.setPlaceholderText("Código de barras")
        self.ed_nombre = QLineEdit(self);  self.ed_nombre.setPlaceholderText("Nombre")
        self.ed_precio = QLineEdit(self);  self.ed_precio.setPlaceholderText("Precio (ej: 123.45)")
        self.ed_categoria = QLineEdit(self); self.ed_categoria.setPlaceholderText("Categoría (opcional)")

        lay.addRow("Código:", self.ed_codigo)
        lay.addRow("Nombre:", self.ed_nombre)
        lay.addRow("Precio:", self.ed_precio)
        lay.addRow("Categoría:", self.ed_categoria)

        row = QHBoxLayout()
        btn_ok = QPushButton("Guardar"); btn_cancel = QPushButton("Cancelar")
        btn_ok.clicked.connect(self._on_accept); btn_cancel.clicked.connect(self.reject)
        # Hacer que Enter dispare Guardar (Aceptar)
        btn_ok.setDefault(True)
        btn_ok.setAutoDefault(True)
        btn_cancel.setAutoDefault(False)

        # Foco inicial y Enter en los campos => Guardar
        self.ed_codigo.setFocus()
        for w in (self.ed_codigo, self.ed_nombre, self.ed_precio, self.ed_categoria):
            w.returnPressed.connect(btn_ok.click)
        row.addStretch(); row.addWidget(btn_cancel); row.addWidget(btn_ok)
        lay.addRow(row)

    def _on_accept(self):
        cod = (self.ed_codigo.text() or "").strip()
        nom = (self.ed_nombre.text() or "").strip()
        pre = (self.ed_precio.text() or "").strip().replace(",", ".")
        cat = (self.ed_categoria.text() or "").strip() or None
        # Validaciones mínimas
        if not cod or not nom:
            QMessageBox.warning(self, "Faltan datos", "Completá Código y Nombre.")
            return
        try:
            precio = float(pre)
            if precio < 0:
                raise ValueError()
        except Exception:
            QMessageBox.warning(self, "Precio inválido", "Ingresá un número válido para el precio.")
            return
        self._result = (cod, nom, precio, cat)
        self.accept()

    def datos(self):
        return getattr(self, "_result", None)


class QuickEditProductoDialog(QDialog):
    """Paso 1: pide Código. Paso 2: edita Nombre/Precio/Categoría del producto encontrado."""
    def __init__(self, producto, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Editar producto")
        self._p = producto
        lay = QFormLayout(self)

        # Solo lectura el código (se buscó antes)
        self.lbl_codigo = QLabel(str(getattr(producto, "codigo_barra", "")))
        self.ed_nombre  = QLineEdit(self); self.ed_nombre.setText(getattr(producto, "nombre", "") or "")
        self.ed_precio  = QLineEdit(self); self.ed_precio.setText(f"{float(getattr(producto,'precio',0.0) or 0.0):.2f}")
        self.ed_categoria = QLineEdit(self); self.ed_categoria.setText(getattr(producto, "categoria", "") or "")

        lay.addRow("Código:", self.lbl_codigo)
        lay.addRow("Nombre:", self.ed_nombre)
        lay.addRow("Precio:", self.ed_precio)
        lay.addRow("Categoría:", self.ed_categoria)

        row = QHBoxLayout()
        btn_ok = QPushButton("Guardar"); btn_cancel = QPushButton("Cancelar")
        btn_ok.clicked.connect(self._on_accept); btn_cancel.clicked.connect(self.reject)
        # Hacer que Enter dispare Guardar
        btn_ok.setDefault(True)
        btn_ok.setAutoDefault(True)
        btn_cancel.setAutoDefault(False)

        # Foco y Enter en campos => Guardar
        self.ed_nombre.setFocus()
        for w in (self.ed_nombre, self.ed_precio, self.ed_categoria):
            w.returnPressed.connect(btn_ok.click)
        row.addStretch(); row.addWidget(btn_cancel); row.addWidget(btn_ok)
        lay.addRow(row)

    def _on_accept(self):
        nom = (self.ed_nombre.text() or "").strip()
        pre = (self.ed_precio.text() or "").strip().replace(",", ".")
        cat = (self.ed_categoria.text() or "").strip() or None
        if not nom:
            QMessageBox.warning(self, "Faltan datos", "El nombre no puede estar vacío.")
            return
        try:
            precio = float(pre)
            if precio < 0:
                raise ValueError()
        except Exception:
            QMessageBox.warning(self, "Precio inválido", "Ingresá un número válido para el precio.")
            return
        self._result = (nom, precio, cat)
        self.accept()

    def datos(self):
        return getattr(self, "_result", None)

# Diálogo temporal para agregar a dialogs.py

from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QIntValidator


class PagoTarjetaDialog(QDialog):
    """
    Diálogo unificado para configurar pago con tarjeta.
    Incluye:
    - Número de cuotas (auto-focus)
    - Porcentaje de interés
    - Descuento (% o monto fijo)
    - Tipo de comprobante fiscal (Factura A, B, C)
    - CUIT del cliente (si es Factura A)
    Enter navega al siguiente campo.
    """

    def __init__(self, total_actual=0.0, parent=None, session=None):
        super().__init__(parent)
        self.total_actual = total_actual
        self._session = session
        self._result = None
        self._updating_discount = False
        self.setWindowTitle("Pago con Tarjeta")
        self.setMinimumWidth(450)

        layout = QVBoxLayout(self)

        # Título
        titulo = QLabel("Configuración de Pago con Tarjeta")
        titulo_font = QFont()
        titulo_font.setPointSize(12)
        titulo_font.setBold(True)
        titulo.setFont(titulo_font)
        layout.addWidget(titulo)

        # Separador
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line)

        # Formulario
        form = QFormLayout()
        form.setSpacing(12)

        # Cuotas
        self.spin_cuotas = QSpinBox()
        self.spin_cuotas.setRange(1, 12)
        self.spin_cuotas.setValue(1)
        self.spin_cuotas.setSuffix(" cuota(s)")
        self.spin_cuotas.valueChanged.connect(self._actualizar_resumen)
        form.addRow("Número de cuotas:", self.spin_cuotas)

        # Interés
        self.spin_interes = QDoubleSpinBox()
        self.spin_interes.setRange(0.0, 100.0)
        self.spin_interes.setValue(0.0)
        self.spin_interes.setSuffix(" %")
        self.spin_interes.setDecimals(2)
        self.spin_interes.setSingleStep(0.5)
        self.spin_interes.valueChanged.connect(self._actualizar_resumen)
        form.addRow("Interés por cuotas:", self.spin_interes)

        # Descuento %
        self.spin_descuento_pct = QDoubleSpinBox()
        self.spin_descuento_pct.setRange(0.0, 100.0)
        self.spin_descuento_pct.setValue(0.0)
        self.spin_descuento_pct.setSuffix(" %")
        self.spin_descuento_pct.setDecimals(2)
        self.spin_descuento_pct.setSingleStep(1.0)
        self.spin_descuento_pct.valueChanged.connect(self._on_descuento_pct_changed)
        form.addRow("Descuento (%):", self.spin_descuento_pct)

        # Descuento monto fijo
        self.spin_descuento_monto = QDoubleSpinBox()
        self.spin_descuento_monto.setRange(0.0, max(total_actual, 1.0))
        self.spin_descuento_monto.setValue(0.0)
        self.spin_descuento_monto.setPrefix("$ ")
        self.spin_descuento_monto.setDecimals(2)
        self.spin_descuento_monto.setSingleStep(10.0)
        self.spin_descuento_monto.valueChanged.connect(self._on_descuento_monto_changed)
        form.addRow("Descuento ($):", self.spin_descuento_monto)

        # Tipo de comprobante
        self.cmb_tipo_cbte = NoScrollComboBox()
        self.cmb_tipo_cbte.addItem("Factura A - Resp. Inscripto", "FACTURA_A")
        self.cmb_tipo_cbte.addItem("Factura B - Consumidor Final", "FACTURA_B")
        self.cmb_tipo_cbte.addItem("Factura B - Monotributo", "FACTURA_B_MONO")
        # Leer default de config (fiscal.tipo_cbte)
        from app.config import load as _load_cfg
        _fiscal_cfg = _load_cfg().get("fiscal", {})
        _tipo_default = (_fiscal_cfg.get("tipo_cbte", "FACTURA_B") or "FACTURA_B").strip()
        _idx_default = 1  # fallback Factura B
        for _i in range(self.cmb_tipo_cbte.count()):
            if self.cmb_tipo_cbte.itemData(_i) == _tipo_default:
                _idx_default = _i
                break
        self.cmb_tipo_cbte.setCurrentIndex(_idx_default)
        self.cmb_tipo_cbte.currentIndexChanged.connect(self._on_tipo_cbte_changed)
        form.addRow("Tipo de comprobante:", self.cmb_tipo_cbte)

        # CUIT del cliente (visible para Factura A y Factura B Monotributo)
        self.lbl_cuit = QLabel("CUIT/CUIL de cliente:")
        self.edt_cuit = QLineEdit()
        self.edt_cuit.setPlaceholderText("Ej: 20123456789 (solo números)")
        self.edt_cuit.setMaxLength(11)
        _cuit_default = (_load_cfg().get("fiscal", {}).get("cuit_predefinido", "20000000001") or "").strip()
        self.edt_cuit.setText(_cuit_default)

        from PyQt5.QtGui import QRegExpValidator
        from PyQt5.QtCore import QRegExp
        regex = QRegExp("[0-9]{0,11}")
        validator = QRegExpValidator(regex)
        self.edt_cuit.setValidator(validator)

        # Layout CUIT + botón cargar
        cuit_row = QHBoxLayout()
        cuit_row.addWidget(self.edt_cuit)
        self.btn_consultar_cuit = QPushButton("Cargar")
        self.btn_consultar_cuit.setToolTip("Cargar datos del comprador desde la base de datos local")
        self.btn_consultar_cuit.setAutoDefault(False)
        self.btn_consultar_cuit.clicked.connect(self._consultar_cuit)
        cuit_row.addWidget(self.btn_consultar_cuit)
        cuit_widget = QWidget()
        cuit_widget.setLayout(cuit_row)
        cuit_row.setContentsMargins(0, 0, 0, 0)
        form.addRow(self.lbl_cuit, cuit_widget)

        # Campos adicionales del comprador (Factura A y B Monotributo)
        self.lbl_nombre = QLabel("Nombre y Apellido:")
        self.edt_nombre = QLineEdit()
        self.edt_nombre.setPlaceholderText("Nombre y Apellido del comprador")
        form.addRow(self.lbl_nombre, self.edt_nombre)

        self.lbl_domicilio = QLabel("Domicilio:")
        self.edt_domicilio = QLineEdit()
        self.edt_domicilio.setPlaceholderText("Dirección del comprador")
        form.addRow(self.lbl_domicilio, self.edt_domicilio)

        self.lbl_localidad = QLabel("Localidad:")
        self.edt_localidad = QLineEdit()
        self.edt_localidad.setPlaceholderText("Ciudad / Localidad")
        form.addRow(self.lbl_localidad, self.edt_localidad)

        self.lbl_codigo_postal = QLabel("Código Postal:")
        self.edt_codigo_postal = QLineEdit()
        self.edt_codigo_postal.setPlaceholderText("Código postal")
        form.addRow(self.lbl_codigo_postal, self.edt_codigo_postal)

        self.lbl_condicion = QLabel("Condición Fiscal:")
        self.edt_condicion = QComboBox()
        self.edt_condicion.addItems(["", "Responsable Inscripto", "Monotributista", "Consumidor Final", "Exento"])
        form.addRow(self.lbl_condicion, self.edt_condicion)

        layout.addLayout(form)

        # Separador
        line2 = QFrame()
        line2.setFrameShape(QFrame.HLine)
        line2.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line2)

        # Resumen
        self.lbl_resumen = QLabel()
        self.lbl_resumen.setStyleSheet("QLabel { background-color: #f0f0f0; padding: 12px; border-radius: 4px; }")
        layout.addWidget(self.lbl_resumen)

        # Botones
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_cancelar = QPushButton("Cancelar")
        btn_cancelar.setAutoDefault(False)
        btn_cancelar.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancelar)

        self.btn_aceptar = QPushButton("Aceptar")
        self.btn_aceptar.setAutoDefault(True)
        self.btn_aceptar.setDefault(True)
        self.btn_aceptar.clicked.connect(self._aceptar)
        btn_layout.addWidget(self.btn_aceptar)

        layout.addLayout(btn_layout)

        # Tab order explícito: cuotas → interes → desc% → desc$ → tipo cbte → cuit → aceptar
        self.setTabOrder(self.spin_cuotas, self.spin_interes)
        self.setTabOrder(self.spin_interes, self.spin_descuento_pct)
        self.setTabOrder(self.spin_descuento_pct, self.spin_descuento_monto)
        self.setTabOrder(self.spin_descuento_monto, self.cmb_tipo_cbte)
        self.setTabOrder(self.cmb_tipo_cbte, self.edt_cuit)
        self.setTabOrder(self.edt_cuit, self.btn_aceptar)

        # Enter navega al siguiente campo (event filter)
        for w in (self.spin_cuotas, self.spin_interes, self.spin_descuento_pct,
                  self.spin_descuento_monto, self.cmb_tipo_cbte, self.edt_cuit):
            w.installEventFilter(self)

        # Inicializar
        self._on_tipo_cbte_changed()
        self._actualizar_resumen()

        # Auto-focus en cuotas
        self.spin_cuotas.setFocus()
        self.spin_cuotas.selectAll()

    def eventFilter(self, obj, event):
        """Enter/Return navega al siguiente campo en vez de aceptar el diálogo."""
        from PyQt5.QtCore import QEvent, Qt as _Qt
        if event.type() == QEvent.KeyPress and event.key() in (_Qt.Key_Return, _Qt.Key_Enter):
            self.focusNextChild()
            return True
        return super().eventFilter(obj, event)

    def _on_descuento_pct_changed(self, val):
        if self._updating_discount:
            return
        self._updating_discount = True
        monto = round(self.total_actual * (val / 100.0), 2)
        self.spin_descuento_monto.setValue(monto)
        self._actualizar_resumen()
        self._updating_discount = False

    def _on_descuento_monto_changed(self, val):
        if self._updating_discount:
            return
        self._updating_discount = True
        if self.total_actual > 0:
            pct = round((val / self.total_actual) * 100.0, 2)
        else:
            pct = 0.0
        self.spin_descuento_pct.setValue(pct)
        self._actualizar_resumen()
        self._updating_discount = False

    def _on_tipo_cbte_changed(self):
        """Muestra/oculta los campos del comprador según el tipo de comprobante."""
        tipo = self.cmb_tipo_cbte.currentData()
        necesita_cuit = tipo in ("FACTURA_A", "FACTURA_B_MONO")

        self.lbl_cuit.setVisible(necesita_cuit)
        self.edt_cuit.setVisible(necesita_cuit)
        self.btn_consultar_cuit.setVisible(necesita_cuit)
        self.lbl_nombre.setVisible(necesita_cuit)
        self.edt_nombre.setVisible(necesita_cuit)
        self.lbl_domicilio.setVisible(necesita_cuit)
        self.edt_domicilio.setVisible(necesita_cuit)
        self.lbl_localidad.setVisible(necesita_cuit)
        self.edt_localidad.setVisible(necesita_cuit)
        self.lbl_codigo_postal.setVisible(necesita_cuit)
        self.edt_codigo_postal.setVisible(necesita_cuit)
        self.lbl_condicion.setVisible(necesita_cuit)
        self.edt_condicion.setVisible(necesita_cuit)

        if necesita_cuit:
            self.edt_cuit.setFocus()
            self.edt_cuit.selectAll()

    def _consultar_cuit(self):
        """Busca datos del comprador en la base de datos local por CUIT."""
        cuit = self.edt_cuit.text().strip()
        if not cuit or len(cuit) != 11:
            QMessageBox.warning(self, "CUIT", "Ingrese un CUIT/CUIL válido de 11 dígitos.")
            return
        if not self._session:
            QMessageBox.warning(self, "Error", "No hay sesión de base de datos disponible.")
            return
        try:
            from app.gui.compradores import CompradorService
            comp = CompradorService(self._session).buscar_por_cuit(cuit)
            if comp:
                self.edt_nombre.setText(comp.nombre or "")
                self.edt_domicilio.setText(comp.domicilio or "")
                self.edt_localidad.setText(comp.localidad or "")
                self.edt_codigo_postal.setText(comp.codigo_postal or "")
                idx = self.edt_condicion.findText(comp.condicion or "")
                self.edt_condicion.setCurrentIndex(idx if idx >= 0 else 0)
            else:
                QMessageBox.information(self, "Cliente",
                    "CUIT no registrado.\nComplete los datos y se guardarán automáticamente al confirmar la venta.")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Error al buscar cliente:\n{e}")

    def _actualizar_resumen(self):
        """Actualiza el resumen de totales con interés y descuento."""
        cuotas = self.spin_cuotas.value()
        interes_pct = self.spin_interes.value()
        descuento_monto = self.spin_descuento_monto.value()

        subtotal = self.total_actual
        interes_monto = round(subtotal * (interes_pct / 100.0), 2)
        total_final = round(subtotal + interes_monto - descuento_monto, 2)
        total_final = max(0, total_final)

        if cuotas > 0:
            monto_cuota = total_final / cuotas
        else:
            monto_cuota = 0.0

        resumen = f"""<b>Resumen:</b><br>
Subtotal: ${subtotal:,.2f}<br>
Interés ({interes_pct}%): +${interes_monto:,.2f}<br>
Descuento: -${descuento_monto:,.2f}<br>
<b>Total: ${total_final:,.2f}</b><br>
<br>
<b>{cuotas} cuota(s) de ${monto_cuota:,.2f}</b>"""

        self.lbl_resumen.setText(resumen)

    def _aceptar(self):
        """Valida y acepta el diálogo."""
        tipo = self.cmb_tipo_cbte.currentData()

        if tipo in ("FACTURA_A", "FACTURA_B_MONO"):
            cuit = self.edt_cuit.text().strip()
            if not cuit or len(cuit) != 11:
                label = "Factura A" if tipo == "FACTURA_A" else "Factura B Monotributo"
                QMessageBox.warning(
                    self,
                    "CUIT requerido",
                    f"Para {label} es obligatorio ingresar el CUIT/CUIL del cliente (11 dígitos)."
                )
                self.edt_cuit.setFocus()
                return

        _es_comprador = tipo in ("FACTURA_A", "FACTURA_B_MONO")
        self._result = {
            "cuotas": self.spin_cuotas.value(),
            "interes_pct": self.spin_interes.value(),
            "descuento_pct": self.spin_descuento_pct.value(),
            "descuento_monto": self.spin_descuento_monto.value(),
            "tipo_comprobante": tipo,
            "cuit_cliente": self.edt_cuit.text().strip() if _es_comprador else "",
            "nombre_cliente": self.edt_nombre.text().strip() if _es_comprador else "",
            "domicilio_cliente": self.edt_domicilio.text().strip() if _es_comprador else "",
            "localidad_cliente": self.edt_localidad.text().strip() if _es_comprador else "",
            "codigo_postal_cliente": self.edt_codigo_postal.text().strip() if _es_comprador else "",
            "condicion_cliente": self.edt_condicion.currentText() if _es_comprador else "",
        }

        self.accept()

    def get_datos(self):
        """Retorna los datos ingresados o None si se canceló."""
        return self._result


class PagoEfectivoDialog(QDialog):
    """
    Diálogo para pago en efectivo con opción de emitir factura AFIP.
    Incluye:
    - Importe abonado (auto-focus)
    - Descuento (% o monto fijo)
    - Checkbox opcional para emitir factura AFIP
    - Tipo de comprobante (si AFIP habilitado)
    - CUIT del cliente (si es Factura A)
    Enter navega al siguiente campo.
    """

    def __init__(self, total_actual=0.0, parent=None, session=None):
        super().__init__(parent)
        self.total_actual = total_actual
        self._total_con_descuento = total_actual
        self._result = None
        self._session = session
        self._updating_discount = False  # evitar bucle entre % y $
        self.setWindowTitle("Pago en Efectivo")
        self.setMinimumWidth(450)

        layout = QVBoxLayout(self)

        # Título
        titulo = QLabel("Pago en Efectivo")
        titulo_font = QFont()
        titulo_font.setPointSize(12)
        titulo_font.setBold(True)
        titulo.setFont(titulo_font)
        layout.addWidget(titulo)

        # Separador
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line)

        # Formulario principal
        form = QFormLayout()
        form.setSpacing(12)

        # Subtotal (solo lectura)
        self.lbl_total_valor = QLabel(f"${total_actual:,.2f}")
        self.lbl_total_valor.setStyleSheet("font-weight: bold; font-size: 14px;")
        form.addRow("Subtotal:", self.lbl_total_valor)

        # Descuento %
        self.spin_descuento_pct = QDoubleSpinBox()
        self.spin_descuento_pct.setRange(0.0, 100.0)
        self.spin_descuento_pct.setValue(0.0)
        self.spin_descuento_pct.setSuffix(" %")
        self.spin_descuento_pct.setDecimals(2)
        self.spin_descuento_pct.setSingleStep(1.0)
        self.spin_descuento_pct.valueChanged.connect(self._on_descuento_pct_changed)
        form.addRow("Descuento (%):", self.spin_descuento_pct)

        # Descuento monto fijo
        self.spin_descuento_monto = QDoubleSpinBox()
        self.spin_descuento_monto.setRange(0.0, max(total_actual, 1.0))
        self.spin_descuento_monto.setValue(0.0)
        self.spin_descuento_monto.setPrefix("$ ")
        self.spin_descuento_monto.setDecimals(2)
        self.spin_descuento_monto.setSingleStep(10.0)
        self.spin_descuento_monto.valueChanged.connect(self._on_descuento_monto_changed)
        form.addRow("Descuento ($):", self.spin_descuento_monto)

        # Total con descuento
        self.lbl_total_final = QLabel(f"${total_actual:,.2f}")
        self.lbl_total_final.setStyleSheet("font-weight: bold; font-size: 16px; color: #2e7d32;")
        form.addRow("Total a pagar:", self.lbl_total_final)

        # Importe abonado
        self.spin_abonado = QDoubleSpinBox()
        self.spin_abonado.setRange(0.0, 99999999.0)
        self.spin_abonado.setValue(total_actual)
        self.spin_abonado.setPrefix("$ ")
        self.spin_abonado.setDecimals(2)
        self.spin_abonado.setSingleStep(100.0)
        self.spin_abonado.valueChanged.connect(self._actualizar_vuelto)
        form.addRow("Importe abonado:", self.spin_abonado)

        # Vuelto
        self.lbl_vuelto = QLabel("$0.00")
        self.lbl_vuelto.setStyleSheet("font-weight: bold; color: #2e7d32; font-size: 14px;")
        form.addRow("Vuelto:", self.lbl_vuelto)

        layout.addLayout(form)

        # Separador
        line2 = QFrame()
        line2.setFrameShape(QFrame.HLine)
        line2.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line2)

        # Checkbox para emitir factura AFIP
        self.chk_emitir_afip = QCheckBox("Emitir factura AFIP")
        self.chk_emitir_afip.setChecked(False)
        self.chk_emitir_afip.toggled.connect(self._on_afip_toggled)
        layout.addWidget(self.chk_emitir_afip)

        # Sección AFIP (oculta por defecto)
        self.afip_widget = QWidget()
        afip_layout = QFormLayout(self.afip_widget)
        afip_layout.setSpacing(10)

        # Tipo de comprobante
        self.cmb_tipo_cbte = NoScrollComboBox()
        self.cmb_tipo_cbte.addItem("Factura A - Resp. Inscripto", "FACTURA_A")
        self.cmb_tipo_cbte.addItem("Factura B - Consumidor Final", "FACTURA_B")
        self.cmb_tipo_cbte.addItem("Factura B - Monotributo", "FACTURA_B_MONO")
        # Leer default de config (fiscal.tipo_cbte)
        from app.config import load as _load_cfg2
        _fiscal_cfg2 = _load_cfg2().get("fiscal", {})
        _tipo_default2 = (_fiscal_cfg2.get("tipo_cbte", "FACTURA_B") or "FACTURA_B").strip()
        _idx_default2 = 1  # fallback Factura B
        for _i in range(self.cmb_tipo_cbte.count()):
            if self.cmb_tipo_cbte.itemData(_i) == _tipo_default2:
                _idx_default2 = _i
                break
        self.cmb_tipo_cbte.setCurrentIndex(_idx_default2)
        self.cmb_tipo_cbte.currentIndexChanged.connect(self._on_tipo_cbte_changed)
        afip_layout.addRow("Tipo de comprobante:", self.cmb_tipo_cbte)

        # CUIT del cliente (visible para Factura A y Factura B Monotributo)
        self.lbl_cuit = QLabel("CUIT/CUIL de cliente:")
        self.edt_cuit = QLineEdit()
        self.edt_cuit.setPlaceholderText("Ej: 20123456789 (solo números)")
        self.edt_cuit.setMaxLength(11)
        _cuit_default2 = (_fiscal_cfg2.get("cuit_predefinido", "20000000001") or "").strip()
        self.edt_cuit.setText(_cuit_default2)

        from PyQt5.QtGui import QRegExpValidator
        from PyQt5.QtCore import QRegExp
        regex = QRegExp("[0-9]{0,11}")
        validator = QRegExpValidator(regex)
        self.edt_cuit.setValidator(validator)

        # Layout CUIT + botón cargar
        cuit_row2 = QHBoxLayout()
        cuit_row2.addWidget(self.edt_cuit)
        self.btn_consultar_cuit = QPushButton("Cargar")
        self.btn_consultar_cuit.setToolTip("Cargar datos del comprador desde la base de datos local")
        self.btn_consultar_cuit.setAutoDefault(False)
        self.btn_consultar_cuit.clicked.connect(self._consultar_cuit)
        cuit_row2.addWidget(self.btn_consultar_cuit)
        cuit_widget2 = QWidget()
        cuit_widget2.setLayout(cuit_row2)
        cuit_row2.setContentsMargins(0, 0, 0, 0)
        afip_layout.addRow(self.lbl_cuit, cuit_widget2)

        # Campos adicionales del comprador (Factura A y B Monotributo)
        self.lbl_nombre = QLabel("Nombre y Apellido:")
        self.edt_nombre = QLineEdit()
        self.edt_nombre.setPlaceholderText("Nombre y Apellido del comprador")
        afip_layout.addRow(self.lbl_nombre, self.edt_nombre)

        self.lbl_domicilio = QLabel("Domicilio:")
        self.edt_domicilio = QLineEdit()
        self.edt_domicilio.setPlaceholderText("Dirección del comprador")
        afip_layout.addRow(self.lbl_domicilio, self.edt_domicilio)

        self.lbl_localidad = QLabel("Localidad:")
        self.edt_localidad = QLineEdit()
        self.edt_localidad.setPlaceholderText("Ciudad / Localidad")
        afip_layout.addRow(self.lbl_localidad, self.edt_localidad)

        self.lbl_codigo_postal = QLabel("Código Postal:")
        self.edt_codigo_postal = QLineEdit()
        self.edt_codigo_postal.setPlaceholderText("Código postal")
        afip_layout.addRow(self.lbl_codigo_postal, self.edt_codigo_postal)

        self.lbl_condicion = QLabel("Condición Fiscal:")
        self.edt_condicion = QComboBox()
        self.edt_condicion.addItems(["", "Responsable Inscripto", "Monotributista", "Consumidor Final", "Exento"])
        afip_layout.addRow(self.lbl_condicion, self.edt_condicion)

        self.afip_widget.setVisible(False)
        layout.addWidget(self.afip_widget)

        # Espacio flexible
        layout.addStretch()

        # Botones
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_cancelar = QPushButton("Cancelar")
        btn_cancelar.setAutoDefault(False)
        btn_cancelar.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancelar)

        self.btn_aceptar = QPushButton("Aceptar")
        self.btn_aceptar.setAutoDefault(True)
        self.btn_aceptar.setDefault(True)
        self.btn_aceptar.clicked.connect(self._aceptar)
        btn_layout.addWidget(self.btn_aceptar)

        layout.addLayout(btn_layout)

        # Tab order: abonado → aceptar (Enter directo para pago rápido)
        # Descuento y AFIP accesibles con click/Tab si se necesitan
        self.setTabOrder(self.spin_abonado, self.btn_aceptar)
        self.setTabOrder(self.btn_aceptar, self.spin_descuento_pct)
        self.setTabOrder(self.spin_descuento_pct, self.spin_descuento_monto)
        self.setTabOrder(self.spin_descuento_monto, self.chk_emitir_afip)
        self.setTabOrder(self.chk_emitir_afip, self.cmb_tipo_cbte)
        self.setTabOrder(self.cmb_tipo_cbte, self.edt_cuit)
        self.setTabOrder(self.edt_cuit, btn_cancelar)

        # Enter en abonado → acepta directamente (no navega a descuento)
        # Solo edt_cuit necesita eventFilter para navegar con Enter
        for w in (self.spin_descuento_pct, self.spin_descuento_monto, self.edt_cuit):
            w.installEventFilter(self)

        # Inicializar
        self._on_tipo_cbte_changed()
        self._actualizar_vuelto()

        # Auto-focus en importe abonado
        self.spin_abonado.setFocus()
        self.spin_abonado.selectAll()

    def eventFilter(self, obj, event):
        """Enter/Return navega al siguiente campo en vez de aceptar el diálogo."""
        from PyQt5.QtCore import QEvent, Qt as _Qt
        if event.type() == QEvent.KeyPress and event.key() in (_Qt.Key_Return, _Qt.Key_Enter):
            self.focusNextChild()
            return True
        return super().eventFilter(obj, event)

    def _on_descuento_pct_changed(self, val):
        """Al cambiar descuento %, actualizar monto $ correspondiente."""
        if self._updating_discount:
            return
        self._updating_discount = True
        monto = round(self.total_actual * (val / 100.0), 2)
        self.spin_descuento_monto.setValue(monto)
        self._recalcular_total_con_descuento()
        self._updating_discount = False

    def _on_descuento_monto_changed(self, val):
        """Al cambiar descuento $, actualizar % correspondiente."""
        if self._updating_discount:
            return
        self._updating_discount = True
        if self.total_actual > 0:
            pct = round((val / self.total_actual) * 100.0, 2)
        else:
            pct = 0.0
        self.spin_descuento_pct.setValue(pct)
        self._recalcular_total_con_descuento()
        self._updating_discount = False

    def _recalcular_total_con_descuento(self):
        """Recalcula total con descuento y actualiza labels."""
        desc_monto = self.spin_descuento_monto.value()
        self._total_con_descuento = max(0, round(self.total_actual - desc_monto, 2))
        self.lbl_total_final.setText(f"${self._total_con_descuento:,.2f}")
        # Actualizar abonado si estaba en el total original
        if self.spin_abonado.value() == self.total_actual or self.spin_abonado.value() == self._total_con_descuento + desc_monto:
            pass  # no forzar cambio, el usuario ya puso un valor
        self._actualizar_vuelto()

    def _actualizar_vuelto(self):
        """Actualiza el vuelto según el importe abonado y descuento."""
        abonado = self.spin_abonado.value()
        total = self._total_con_descuento
        vuelto = max(0.0, abonado - total)
        self.lbl_vuelto.setText(f"${vuelto:,.2f}")

        if abonado < total - 0.01:
            self.lbl_vuelto.setStyleSheet("font-weight: bold; color: #c62828; font-size: 14px;")
        else:
            self.lbl_vuelto.setStyleSheet("font-weight: bold; color: #2e7d32; font-size: 14px;")

    def _on_afip_toggled(self, checked):
        """Muestra/oculta la sección AFIP."""
        self.afip_widget.setVisible(checked)
        self.adjustSize()

    def _on_tipo_cbte_changed(self):
        """Muestra/oculta los campos del comprador según el tipo de comprobante."""
        tipo = self.cmb_tipo_cbte.currentData()
        necesita_cuit = tipo in ("FACTURA_A", "FACTURA_B_MONO")

        self.lbl_cuit.setVisible(necesita_cuit)
        self.edt_cuit.setVisible(necesita_cuit)
        self.btn_consultar_cuit.setVisible(necesita_cuit)
        self.lbl_nombre.setVisible(necesita_cuit)
        self.edt_nombre.setVisible(necesita_cuit)
        self.lbl_domicilio.setVisible(necesita_cuit)
        self.edt_domicilio.setVisible(necesita_cuit)
        self.lbl_localidad.setVisible(necesita_cuit)
        self.edt_localidad.setVisible(necesita_cuit)
        self.lbl_codigo_postal.setVisible(necesita_cuit)
        self.edt_codigo_postal.setVisible(necesita_cuit)
        self.lbl_condicion.setVisible(necesita_cuit)
        self.edt_condicion.setVisible(necesita_cuit)

        if necesita_cuit and self.afip_widget.isVisible():
            self.edt_cuit.setFocus()
            self.edt_cuit.selectAll()

    def _consultar_cuit(self):
        """Busca datos del comprador en la base de datos local por CUIT."""
        cuit = self.edt_cuit.text().strip()
        if not cuit or len(cuit) != 11:
            QMessageBox.warning(self, "CUIT", "Ingrese un CUIT/CUIL válido de 11 dígitos.")
            return
        if not self._session:
            QMessageBox.warning(self, "Error", "No hay sesión de base de datos disponible.")
            return
        try:
            from app.gui.compradores import CompradorService
            comp = CompradorService(self._session).buscar_por_cuit(cuit)
            if comp:
                self.edt_nombre.setText(comp.nombre or "")
                self.edt_domicilio.setText(comp.domicilio or "")
                self.edt_localidad.setText(comp.localidad or "")
                self.edt_codigo_postal.setText(comp.codigo_postal or "")
                idx = self.edt_condicion.findText(comp.condicion or "")
                self.edt_condicion.setCurrentIndex(idx if idx >= 0 else 0)
            else:
                QMessageBox.information(self, "Cliente",
                    "CUIT no registrado.\nComplete los datos y se guardarán automáticamente al confirmar la venta.")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Error al buscar cliente:\n{e}")

    def _aceptar(self):
        """Valida y acepta el diálogo."""
        abonado = self.spin_abonado.value()
        total = self._total_con_descuento

        # Validar que abonado >= total con descuento
        if abonado < total - 0.01:
            QMessageBox.warning(
                self,
                "Importe insuficiente",
                f"El importe abonado (${abonado:,.2f}) es menor al total (${total:,.2f})."
            )
            self.spin_abonado.setFocus()
            return

        vuelto = max(0.0, abonado - total)

        emitir_afip = self.chk_emitir_afip.isChecked()
        tipo_comprobante = None
        cuit_cliente = ""

        if emitir_afip:
            tipo_comprobante = self.cmb_tipo_cbte.currentData()

            if tipo_comprobante in ("FACTURA_A", "FACTURA_B_MONO"):
                cuit = self.edt_cuit.text().strip()
                if not cuit or len(cuit) != 11:
                    label = "Factura A" if tipo_comprobante == "FACTURA_A" else "Factura B Monotributo"
                    QMessageBox.warning(
                        self,
                        "CUIT requerido",
                        f"Para {label} es obligatorio ingresar el CUIT/CUIL del cliente (11 dígitos)."
                    )
                    self.edt_cuit.setFocus()
                    return
                cuit_cliente = cuit

        _es_comprador = tipo_comprobante in ("FACTURA_A", "FACTURA_B_MONO")
        self._result = {
            "abonado": abonado,
            "vuelto": vuelto,
            "descuento_pct": self.spin_descuento_pct.value(),
            "descuento_monto": self.spin_descuento_monto.value(),
            "emitir_afip": emitir_afip,
            "tipo_comprobante": tipo_comprobante,
            "cuit_cliente": cuit_cliente,
            "nombre_cliente": self.edt_nombre.text().strip() if _es_comprador else "",
            "domicilio_cliente": self.edt_domicilio.text().strip() if _es_comprador else "",
            "localidad_cliente": self.edt_localidad.text().strip() if _es_comprador else "",
            "codigo_postal_cliente": self.edt_codigo_postal.text().strip() if _es_comprador else "",
            "condicion_cliente": self.edt_condicion.currentText() if _es_comprador else "",
        }

        self.accept()

    def get_datos(self):
        """Retorna los datos ingresados o None si se canceló."""
        return self._result


class PagoProveedorDialog(QDialog):
    """Dialog para registrar un pago a proveedor."""

    def __init__(self, session, sucursal, parent=None):
        super().__init__(parent)
        self.session = session
        self.sucursal = sucursal
        self.setWindowTitle("Pago a Proveedor")
        self.setMinimumWidth(450)
        self._result = None

        layout = QVBoxLayout(self)
        form = QFormLayout()

        # Proveedor dropdown
        self.cmb_proveedor = NoScrollComboBox()
        self.cmb_proveedor.setEditable(False)
        self._cargar_proveedores()
        self.cmb_proveedor.currentIndexChanged.connect(self._on_proveedor_changed)
        form.addRow("Proveedor:", self.cmb_proveedor)

        # Formulario inline para nuevo proveedor (oculto por defecto)
        self.grp_nuevo = QGroupBox("Nuevo proveedor")
        self.grp_nuevo.setVisible(False)
        grp_form = QFormLayout(self.grp_nuevo)
        self.ed_nombre = QLineEdit()
        self.ed_nombre.setPlaceholderText("Nombre del proveedor (obligatorio)")
        self.ed_telefono = QLineEdit()
        self.ed_telefono.setPlaceholderText("Opcional")
        self.ed_cuenta = QLineEdit()
        self.ed_cuenta.setPlaceholderText("Opcional")
        self.ed_cbu = QLineEdit()
        self.ed_cbu.setPlaceholderText("Opcional")
        grp_form.addRow("Nombre:", self.ed_nombre)
        grp_form.addRow("Teléfono:", self.ed_telefono)
        grp_form.addRow("Cuenta:", self.ed_cuenta)
        grp_form.addRow("CBU:", self.ed_cbu)
        form.addRow(self.grp_nuevo)

        # Monto
        self.spin_monto = QDoubleSpinBox()
        self.spin_monto.setRange(0.01, 99999999.99)
        self.spin_monto.setDecimals(2)
        self.spin_monto.setPrefix("$ ")
        self.spin_monto.setMinimumHeight(32)
        font = self.spin_monto.font()
        font.setPointSize(font.pointSize() + 2)
        self.spin_monto.setFont(font)
        form.addRow("Monto:", self.spin_monto)

        # Metodo de pago
        self.cmb_metodo = NoScrollComboBox()
        self.cmb_metodo.addItems(["Efectivo", "Tarjeta", "Transferencia"])
        form.addRow("Método de pago:", self.cmb_metodo)

        # Pago de caja
        self.chk_caja = QCheckBox("Pago de caja (descontar del efectivo)")
        form.addRow("", self.chk_caja)

        # Nota
        self.ed_nota = QLineEdit()
        self.ed_nota.setPlaceholderText("Nota opcional...")
        form.addRow("Nota:", self.ed_nota)

        layout.addLayout(form)

        # Botones
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("Registrar Pago")
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _cargar_proveedores(self):
        from app.gui.proveedores import ProveedorService
        svc = ProveedorService(self.session)
        provs = svc.listar_todos()
        for p in provs:
            self.cmb_proveedor.addItem(p.nombre, p.id)
        self.cmb_proveedor.addItem("-- Otro (nuevo) --", -1)

    def _on_proveedor_changed(self, idx):
        data = self.cmb_proveedor.currentData()
        self.grp_nuevo.setVisible(data == -1)

    def _on_accept(self):
        data = self.cmb_proveedor.currentData()
        if data == -1:
            nombre = self.ed_nombre.text().strip()
            if not nombre:
                QMessageBox.warning(self, "Pago", "Ingresá el nombre del proveedor.")
                return
            # Crear nuevo proveedor
            from app.gui.proveedores import ProveedorService
            svc = ProveedorService(self.session)
            prov = svc.crear_o_actualizar_por_nombre(
                nombre,
                telefono=self.ed_telefono.text().strip() or None,
                numero_cuenta=self.ed_cuenta.text().strip() or None,
                cbu=self.ed_cbu.text().strip() or None
            )
            prov_id = prov.id if prov else None
            prov_nombre = nombre
        else:
            prov_id = data
            prov_nombre = self.cmb_proveedor.currentText()

        monto = self.spin_monto.value()
        if monto <= 0:
            QMessageBox.warning(self, "Pago", "El monto debe ser mayor a 0.")
            return

        self._result = {
            'proveedor_id': prov_id,
            'proveedor_nombre': prov_nombre,
            'monto': monto,
            'metodo_pago': self.cmb_metodo.currentText(),
            'pago_de_caja': self.chk_caja.isChecked(),
            'nota': self.ed_nota.text().strip() or None
        }
        self.accept()

    def get_datos(self):
        return self._result


# ───────────────────────────────────────────────
# Función compartida: agregar producto rápido
# ───────────────────────────────────────────────

def agregar_producto_rapido_dialog(session, parent, term="",
                                   sync_push_fn=None,
                                   completer_refresh_fn=None):
    """Diálogo para agregar un producto nuevo al vuelo.

    Usado desde Ventas y Productos.
    Retorna el Producto creado, uno existente, o None si cancela.
    """
    from PyQt5.QtWidgets import (QDialog, QFormLayout, QLineEdit,
                                 QDoubleSpinBox, QPushButton, QHBoxLayout,
                                 QVBoxLayout, QMessageBox as _QMB)
    from app.models import Producto

    dlg = QDialog(parent)
    dlg.setWindowTitle("Agregar producto nuevo")
    dlg.setMinimumWidth(380)
    lay = QVBoxLayout(dlg)

    form = QFormLayout()
    edt_codigo = QLineEdit(term if term.replace("-", "").isdigit() else "")
    edt_codigo.setPlaceholderText("Codigo de barras")
    edt_nombre = QLineEdit("" if term.replace("-", "").isdigit() else term.upper())
    edt_nombre.setPlaceholderText("Nombre del producto")
    spin_precio = QDoubleSpinBox()
    spin_precio.setRange(0, 99999999)
    spin_precio.setDecimals(2)
    spin_precio.setPrefix("$ ")
    spin_precio.setValue(0)
    edt_categoria = QLineEdit()
    edt_categoria.setPlaceholderText("(Opcional)")

    form.addRow("Codigo:", edt_codigo)
    form.addRow("Nombre:", edt_nombre)
    form.addRow("Precio:", spin_precio)
    form.addRow("Categoria:", edt_categoria)
    lay.addLayout(form)

    btns = QHBoxLayout()
    btn_cancel = QPushButton("Cancelar")
    btn_cancel.setAutoDefault(False)
    btn_ok = QPushButton("Guardar")
    btn_ok.setDefault(True)
    btn_ok.setAutoDefault(True)
    btn_ok.setStyleSheet("font-weight:bold;")
    btns.addWidget(btn_cancel)
    btns.addWidget(btn_ok)
    lay.addLayout(btns)

    btn_cancel.clicked.connect(dlg.reject)
    btn_ok.clicked.connect(dlg.accept)

    if edt_codigo.text():
        edt_nombre.setFocus()
    else:
        edt_codigo.setFocus()

    if dlg.exec_() != QDialog.Accepted:
        return None

    codigo = edt_codigo.text().strip()
    nombre = edt_nombre.text().strip().upper()
    precio = spin_precio.value()
    categoria = edt_categoria.text().strip().upper() or None

    if not codigo or not nombre:
        _QMB.warning(parent, "Datos incompletos", "Codigo y nombre son obligatorios.")
        return None
    if precio <= 0:
        _QMB.warning(parent, "Precio invalido", "El precio debe ser mayor a 0.")
        return None

    from app.repository import prod_repo
    repo = prod_repo(session)
    existe = repo.buscar_por_codigo(codigo)
    if existe:
        _QMB.information(parent, "Ya existe",
            f'Producto con codigo "{codigo}" ya existe:\n{existe.nombre} - ${existe.precio:.2f}')
        return existe

    try:
        nuevo = Producto(codigo_barra=codigo, nombre=nombre, precio=precio, categoria=categoria)
        session.add(nuevo)
        session.commit()
        if sync_push_fn:
            sync_push_fn("producto", nuevo)
        if completer_refresh_fn:
            completer_refresh_fn()
        return nuevo
    except Exception as e:
        session.rollback()
        _QMB.critical(parent, "Error", f"No se pudo crear el producto:\n{e}")
        return None
