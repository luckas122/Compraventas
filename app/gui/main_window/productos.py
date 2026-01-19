from PyQt5.QtCore import Qt,QRect
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QComboBox,
    QTableWidget, QTableWidgetItem, QMessageBox, QTabWidget,
    QRadioButton, QButtonGroup, QSpinBox, QInputDialog, QMenu, QFileDialog,
    QCheckBox, QStyle, QHeaderView, QDialog, QDoubleSpinBox,QCompleter
)
from app.gui.dialogs import _draw_barcode_label,ProductosDialog
from barcode.writer import ImageWriter
from PyQt5.QtPrintSupport import QPrinter, QPrintDialog
from app.utils_timing import measure
from PyQt5.QtGui import QPainter, QPixmap, QIcon, QMouseEvent, QFont, QFontMetrics
from app.gui.common import BASE_ICONS_PATH, MIN_BTN_HEIGHT, ICON_SIZE, icon, _safe_viewport, _mouse_release_event_type, _checked_states, FullCellCheckFilter

import pandas as pd
import barcode
import os
import re
from io import BytesIO

PRODUCTOS_POR_PAGINA = 25


# Dependencias del dominio / helpers que usan tus métodos de productos:
from app.models import Producto
from app.repository import prod_repo
from app.gui.qt_helpers import freeze_table
# Si al ejecutar obtienes NameError: Icon -> descomenta la siguiente línea:
# from app.gui.qt_helpers import Icon

class ProductosMixin:
  
    #Métodos de la pestaña Productos extraídos de MainWindow.
    def tab_productos(self):
        w = QWidget()
        layout = QVBoxLayout()

        # Live search
        self.input_buscar = QLineEdit()
        self.input_buscar.setPlaceholderText('Buscar por código, nombre o categoría...')
        self.input_buscar.textChanged.connect(self.buscar_productos)
        layout.addWidget(self.input_buscar)

        # —— Estilos para el Live Search —— 
        font = self.input_buscar.font()
        font.setPointSize(12)
        font.setBold(True)
        self.input_buscar.setFont(font)
        self.input_buscar.setMinimumHeight(30)
        self.input_buscar.setStyleSheet("padding: 4px;")

        # Formulario
        form = QFormLayout()
        self.input_codigo    = QLineEdit()
        self.input_nombre    = QLineEdit()
        self.input_precio    = QLineEdit()
        self.input_categoria = QLineEdit()
        form.addRow('Código de Barra:',     self.input_codigo)
        form.addRow('Nombre:',              self.input_nombre)
        form.addRow('Precio:',              self.input_precio)
        form.addRow('Categoría (opcional):',self.input_categoria)

        for fld in (self.input_codigo, self.input_nombre,
                    self.input_precio, self.input_categoria):
            fld.returnPressed.connect(self.agregar_producto)

        # —— Botones —— 
        btn_a   = QPushButton('Agregar/Actualizar'); btn_a.setIcon(icon('add.svg'));    btn_a.setToolTip('Agregar/Actualizar');    btn_a.clicked.connect(self.agregar_producto)
        btn_d   = QPushButton('Eliminar seleccionados'); btn_d.setIcon(icon('delete.svg')); btn_d.setToolTip('Eliminar seleccionados'); btn_d.clicked.connect(self.eliminar_productos)
        btn_u   = QPushButton('Deshacer'); btn_u.setIcon(icon('undo.svg'));   btn_u.setToolTip('Deshacer');               btn_u.clicked.connect(self.deshacer)
        btn_p   = QPushButton('Imprimir códigos'); btn_p.setIcon(icon('print.svg'));  btn_p.setToolTip('Imprimir códigos');       btn_p.clicked.connect(self.imprimir_codigos)
        btn_m   = QPushButton('Editar precios masivos'); btn_m.setIcon(icon('edit.svg'));   btn_m.setToolTip('Editar precios masivos'); btn_m.clicked.connect(self.editar_precios_masivos)
        btn_imp = QPushButton('Importar desde Excel'); btn_imp.setIcon(icon('import.svg'));btn_imp.setToolTip('Importar desde Excel'); btn_imp.clicked.connect(self.importar_productos)
        btn_exp = QPushButton('Exportar a Excel'); btn_exp.setIcon(icon('export.svg'));btn_exp.setToolTip('Exportar a Excel');      btn_exp.clicked.connect(self.exportar_productos)
        btn_list = QPushButton('Ver listado con filtros'); btn_list.setIcon(icon('list.svg'));btn_list.setToolTip('Ver listado con filtros');btn_list.setMinimumHeight(MIN_BTN_HEIGHT);btn_list.setIconSize(ICON_SIZE);btn_list.clicked.connect(self.abrir_listado_productos)
        self.btn_anterior = QPushButton("← Anterior")
        self.btn_siguiente = QPushButton("Siguiente →")
        self.lbl_paginacion = QLabel("Página 1")
        self.btn_export_png = QPushButton("Exportar PNG")

        hb = QHBoxLayout()
        for btn in (btn_a, btn_d, btn_u, btn_m, btn_imp, btn_exp, btn_p, btn_list):
            btn.setMinimumHeight(MIN_BTN_HEIGHT)
            btn.setIconSize(ICON_SIZE)
            hb.addWidget(btn)

        form.addRow(hb)
        layout.addLayout(form)

        # Tabla de productos (sin ID visible)
        self.table_productos = QTableWidget()
        self.table_productos.setColumnCount(6)
        self.table_productos.setHorizontalHeaderLabels(
            ['Sel','ID','Código', 'Nombre', 'Precio', 'Categoría']
        )
        
        self.table_productos.setFont(QFont("Arial", 11))
        self.table_productos.setSortingEnabled(True)
        self.table_productos.setSelectionMode(QTableWidget.MultiSelection)
        self.table_productos.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table_productos.customContextMenuRequested.connect(self.menu_contexto_productos)
        self.table_productos.verticalHeader().setVisible(False)

        # Ajustar ancho columnas: checkbox fijo, resto estiran
        hdr = self.table_productos.horizontalHeader()

        # Columna 0: Checkbox (fijo, angosto)
        hdr.setSectionResizeMode(0, QHeaderView.Fixed)
        self.table_productos.setColumnWidth(0, 28)

        # Columna 1: ID (fijo, chico)
        hdr.setSectionResizeMode(1, QHeaderView.Fixed)
        self.table_productos.setColumnWidth(1, 48)

        # Columna 2: Código (ajuste por contenido, o fijo si querés)
        hdr.setSectionResizeMode(2, QHeaderView.Fixed)
        self.table_productos.setColumnWidth(2, 200)  # solo si querés un mínimo

        # Columna 3: Nombre (expansiva)
        hdr.setSectionResizeMode(3, QHeaderView.Stretch)
        
        # Columna 4: Precio (fijo, chico)
        hdr.setSectionResizeMode(4, QHeaderView.Fixed)
        self.table_productos.setColumnWidth(4, 100)

        # Columna 5: Categoría (expansiva)
        hdr.setSectionResizeMode(5, QHeaderView.Fixed)
        self.table_productos.setColumnWidth(5, 200)

        layout.addWidget(self.table_productos)
        nav_layout = QHBoxLayout()
        nav_layout.addWidget(self.btn_anterior)
        nav_layout.addWidget(self.lbl_paginacion)
        nav_layout.addWidget(self.btn_siguiente)
        layout.addWidget(self.btn_export_png)
        layout.addLayout(nav_layout)

        self.table_productos.itemChanged.connect(self._on_producto_item_changed)
        self.table_productos.cellClicked.connect(self.cargar_producto)
        self.table_productos.cellDoubleClicked.connect(self.cargar_producto)
        self.btn_anterior.clicked.connect(self.ir_pagina_anterior)
        self.btn_siguiente.clicked.connect(self.ir_pagina_siguiente)
        self.btn_export_png.clicked.connect(self.exportar_codigos_png)

        w.setLayout(layout)

        # ---- Instalar filtro seguro ----
        try:
            vp = self.table_productos.viewport()
            if vp is not None:
                vp.installEventFilter(self)
        except Exception as e:
            print("Error instalando filtro en Productos:", e)

        def _safe_remove_filter():
            try:
                tbl = getattr(self, "table_productos", None)
                if tbl is not None:
                    vp = getattr(tbl, 'viewport', lambda: None)()
                    if vp is not None:
                        vp.removeEventFilter(self)
            except Exception:
                pass
        self.table_productos.destroyed.connect(_safe_remove_filter)

        self._chk_main = FullCellCheckFilter(self.table_productos, 0, self)
        self.refrescar_productos()
        return w

        
    def _on_productos_cell_clicked(self, row, col):
        if col != 0:
            return
        it = self.table_productos.item(row, 0)
        if it is None:
            return
        it.setCheckState(Qt.Unchecked if it.checkState() == Qt.Checked else Qt.Checked)
    def menu_contexto_productos(self, pos):
        menu   = QMenu()
        act_del= menu.addAction('Eliminar seleccionado')
        action = menu.exec_(self.table_productos.viewport().mapToGlobal(pos))
        if action == act_del:
            idx = self.table_productos.indexAt(pos)
            if idx.isValid():
                pid = int(self.table_productos.item(idx.row(),1).text())
                p   = self.session.query(Producto).get(pid)
                if p:
                    datos = {'codigo_barra':p.codigo_barra,'nombre':p.nombre,
                            'precio':p.precio,'categoria':p.categoria}
                    self.history.append(('del',[datos]))
                    self.session.delete(p); self.session.commit()
                    self.statusBar().showMessage('Producto eliminado',3000)
                    self.refrescar_productos()
    def agregar_producto(self):
        with measure("actualizar_total"):
            c  = self.input_codigo.text().strip()
            n  = self.input_nombre.text().strip()
            try: pr = float(self.input_precio.text())
            except: return QMessageBox.warning(self,'Error','Precio inválido')
            ca = self.input_categoria.text().strip() or None

            existe = self.session.query(Producto).filter_by(codigo_barra=c).first()
            if existe:
                QMessageBox.information(self,'Ya existe',
                    f'Código "{c}" ya existe:\nNombre: {existe.nombre}\nPrecio: ${existe.precio:.2f}'
                    + (f'\nCategoría: {existe.categoria}' if existe.categoria else '')
                )
                self.input_nombre.setText(existe.nombre)
                self.input_precio.setText(str(existe.precio))
                self.input_categoria.setText(existe.categoria or '')
                return

            nuevo = Producto(codigo_barra=c,nombre=n,precio=pr,categoria=ca)
            self.session.add(nuevo); 
            self.session.commit()
            

            datos = {'codigo_barra':c,'nombre':n,'precio':pr,'categoria':ca}
            self.history.append(('add',datos))
            self.statusBar().showMessage('Producto creado',3000)
            self._beep_ok()
            self.limpiar_inputs_producto(); self.refrescar_productos()
            self.refrescar_completer()
    def eliminar_productos(self):
        if QMessageBox.question(self,'Confirmar','¿Eliminar productos seleccionados?',
                                QMessageBox.Yes|QMessageBox.No) != QMessageBox.Yes:
            return

        deleted = []
        for r in range(self.table_productos.rowCount()):
            if self._is_row_checked(r, self.table_productos):
                pid = int(self.table_productos.item(r, 1).text())
                p   = self.session.query(Producto).get(pid)
                if p:
                    deleted.append({ 
                    'codigo_barra': p.codigo_barra,
                    'nombre': p.nombre,
                    'precio': p.precio,
                    'categoria': p.categoria
                    })
                    self.session.delete(p)

        if deleted:
            self.session.commit()
            self.history.append(('del', deleted))
            self.statusBar().showMessage(f'{len(deleted)} productos eliminados', 3000)
            self.refrescar_productos()
            self.refrescar_completer()
            
            
    def imprimir_codigos(self):
        # Filas marcadas con el checkbox de la columna 0
        filas = [r for r in range(self.table_productos.rowCount())
                if self._is_row_checked(r, self.table_productos)]
        if not filas:
            QMessageBox.information(self, 'Imprimir', 'No hay productos seleccionados.')
            return

        # Datos a imprimir (código + nombre)
        items = []
        for r in filas:
            code = self.table_productos.item(r, 2).text()  # 'Código'
            name = self.table_productos.item(r, 3).text()  # 'Nombre'
            items.append((code, name))

        # Diálogo de impresión
        printer = QPrinter(QPrinter.HighResolution)
        dlg = QPrintDialog(printer, self)
        if dlg.exec_() != QPrintDialog.Accepted:
            return

        painter = QPainter(printer)
        try:
            page = printer.pageRect()
            margin = 24
            label_w = page.width() - 2 * margin

            from PyQt5.QtGui import QFont, QFontMetrics

            # Fuente a 12 px como pediste
            font_code = QFont("Arial"); font_code.setPixelSize(12); font_code.setBold(False)
            fm_code   = QFontMetrics(font_code)
            font_name = QFont("Arial"); font_name.setPixelSize(12); font_name.setBold(False)
            fm_name   = QFontMetrics(font_name)

            h_bar  = 120
            y = margin  # ← INICIALIZAR AQUÍ

            for code, name in items:
                # Generar el código de barras sin texto embebido
                bc = barcode.get('code128', code, writer=ImageWriter())
                buf = BytesIO()
                bc.write(buf, options={"module_height": 18.0, "write_text": False})
                pix = QPixmap(); pix.loadFromData(buf.getvalue())

                # ¿cabe en la página actual?
                block_h = h_bar + 6 + fm_code.height() + 2 + fm_name.height() + 16
                if y + block_h > page.height() - margin:
                    printer.newPage()
                    y = margin

                # 1) Barra centrada
                scaled   = pix.scaled(label_w, h_bar, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                scaled_w = scaled.width()
                x = margin + (label_w - scaled_w) // 2
                painter.drawPixmap(x, y, scaled)
                y += scaled.height() + 6

                # 2) Número (12 px, centrado con ancho de la barra)
                painter.setFont(font_code)
                rect_code = QRect(x, y, scaled_w, fm_code.height())
                painter.drawText(rect_code, Qt.AlignHCenter | Qt.AlignVCenter, code)
                y += fm_code.height() + 2

                # 3) Nombre (12 px, elide)
                painter.setFont(font_name)
                name_short = (name or '').strip()
                elided = fm_name.elidedText(name_short, Qt.ElideRight, scaled_w)
                rect_name = QRect(x, y, scaled_w, fm_name.height())
                painter.drawText(rect_name, Qt.AlignHCenter | Qt.AlignVCenter, elided)
                y += fm_name.height() + 16
        finally:
            painter.end()
            
    def importar_productos(self):
        """Carga productos desde un archivo Excel con columnas: codigo_barra,nombre,precio,categoria."""
        path, _ = QFileDialog.getOpenFileName(self, 'Importar Excel', '', 'Excel Files (*.xlsx *.xls)')
        if not path:
            return
        try:
            df = pd.read_excel(path)
        except Exception as e:
            QMessageBox.warning(self, 'Error', f'No se pudo leer el archivo:\n{e}')
            return

        cont_tot, cont_nuevos = 0, 0
        for _, row in df.iterrows():
            codigo = str(row.get('codigo_barra','')).strip()
            nombre = str(row.get('nombre','')).strip()
            try:
                precio = float(row.get('precio',0))
            except:
                precio = 0.0
            categoria = str(row.get('categoria','')).strip() or None
            if not codigo or not nombre:
                continue
            prod = self.session.query(Producto).filter_by(codigo_barra=codigo).first()
            if prod:
                # Actualizar
                prod.nombre    = nombre
                prod.precio    = precio
                prod.categoria = categoria
            else:
                # Nuevo
                prod = Producto(codigo_barra=codigo, nombre=nombre,
                                precio=precio, categoria=categoria)
                self.session.add(prod)
                cont_nuevos += 1
            cont_tot += 1

        self.session.commit()
        self.refrescar_productos()
        QMessageBox.information(
            self, 'Importación completada',
            f'Total filas procesadas: {cont_tot}\n'
            f'Productos nuevos: {cont_nuevos}'
        )
        self.refrescar_completer()
        
    def _autofit_openpyxl(ws, df, min_width=8, max_width=50, padding=2):
        """
        Ajusta el ancho de columnas de una hoja openpyxl en base a los contenidos de df.
        ws: hoja openpyxl (workbook.active o writer.sheets['Productos'])
        df: pandas.DataFrame exportado
        """
        from openpyxl.utils import get_column_letter

        for col_idx, col_name in enumerate(df.columns, start=1):
            max_len = len(str(col_name))
            for cell in ws.iter_cols(min_col=col_idx, max_col=col_idx, min_row=2, values_only=True):
                for val in cell:
                    if val is None:
                        continue
                    max_len = max(max_len, len(str(val)))
            width = max(min_width, min(max_len + padding, max_width))
            ws.column_dimensions[get_column_letter(col_idx)].width = width


    def exportar_productos(self):
        """Exporta todos los productos a un Excel con columnas autoajustadas (o CSV si faltan libs)."""
        from PyQt5.QtWidgets import QMessageBox, QFileDialog
        import pandas as pd, os

        path, _ = QFileDialog.getSaveFileName(self, 'Exportar Excel', 'productos.xlsx', 'Excel Files (*.xlsx)')
        if not path:
            return

    # 1) DataFrame con todos los productos
        productos = self.session.query(Producto).all()
        data = [{
            'codigo_barra': p.codigo_barra,
            'nombre':       p.nombre,
            'precio':       p.precio,
            'categoria':    p.categoria or ''
        } for p in productos]
        df = pd.DataFrame(data)

        # 2) Guardado con openpyxl y auto-fit (si está disponible)
        try:
            from openpyxl import load_workbook
            with pd.ExcelWriter(path, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Productos')
                ws = writer.sheets['Productos']
                try:
                    # usa tu helper local
                    self._autofit_openpyxl(ws, df, min_width=8, max_width=50, padding=2)
                except Exception:
                    pass
            QMessageBox.information(self, 'Exportar Excel', f'Guardado: {path}')
        except Exception as e:
            # Fallback a CSV si openpyxl no está disponible
            try:
                base, _ = os.path.splitext(path)
                csv_path = base + '.csv'
                df.to_csv(csv_path, index=False, encoding='utf-8')
                QMessageBox.information(
                    self, 'Exportar CSV',
                    f'No se pudo escribir Excel ({e}).\nGuardado CSV: {csv_path}'
                )
            except Exception as e2:
                QMessageBox.warning(self, 'Exportar', f'No se pudo guardar:\n{e2}')

        
    def buscar_productos(self, txt):
            self.productos_pagina_actual = 0
            self.refrescar_productos()

            # Autoseleccionar primer resultado y cargarlo al formulario
            tbl = self.table_productos
            if tbl.rowCount() > 0:
                tbl.selectRow(0)
                # col 3 = Nombre; el slot no usa 'col' realmente para cargar
                self.cargar_producto(0, 3)    

    def cargar_producto(self,row,col):
        tbl = self.table_productos
        
            # 1) Intentar leer el ID de la columna 1 (si está visible)
        pid = None
        try:
            it_id = tbl.item(row, 1)
            if it_id:
                txt = (it_id.text() or "").strip()
                if txt.isdigit():
                    pid = int(txt)
        except Exception:
            pid = None

        # 2) Si no hay ID visible, recuperar el ID guardado en UserRole de Código/Nombre
        if pid is None:
            # primero columna Código (2), si no, Nombre (3)
            for c in (2, 3):
                it = tbl.item(row, c)
                if it is not None:
                    pid = it.data(Qt.UserRole)
                    if pid:
                        break

        if not pid:
            return  # no podemos cargar

        # 3) Traer el producto y poblar el formulario
        try:
            p = self.session.query(Producto).get(pid)  # si usás SQLAlchemy 2.x, usa Session.get(Producto, pid)
        except Exception:
            p = None

        if not p:
            return

        self.input_codigo.setText(p.codigo_barra or '')
        self.input_nombre.setText(p.nombre or '')
        self.input_precio.setText(f'{(p.precio or 0.0):.2f}')
        self.input_categoria.setText(p.categoria or '')
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(0, lambda: self.table_productos.clearSelection())

    def limpiar_inputs_producto(self):
        for fld in (self.input_codigo,self.input_nombre,
                    self.input_precio,self.input_categoria):
            fld.clear()
            
    def _find_row_by_codigo(self, codigo: str):
        for r in range(self.table_cesta.rowCount()):
            it = self.table_cesta.item(r, 0)
            if it and it.text() == codigo:
                return r
        return None
    
    
        
    def _on_producto_item_changed(self, item):
        row, col = item.row(), item.column()
        if col not in (3, 4, 5):
            return
        tbl = self.table_productos

        try:
            prod_id = int(tbl.item(row, 1).text())
        except Exception:
            return

        from PyQt5.QtCore import QSignalBlocker
        blocker = QSignalBlocker(tbl)
        try:
            if col == 4:
                try:
                    nuevo_precio = float(item.text().replace(',', '.'))
                except Exception:
                    viejo = self.prod_repo.obtener(prod_id).precio or 0.0
                    item.setText(f"{viejo:.2f}")
                    return
                self.prod_repo.actualizar_precio(prod_id, nuevo_precio)
                item.setText(f"{nuevo_precio:.2f}")
            elif col == 3:
                self.prod_repo.actualizar_nombre(prod_id, item.text().strip())
            elif col == 5:
                self.prod_repo.actualizar_categoria(prod_id, item.text().strip())
        finally:
            del blocker
            
            
    def refrescar_productos(self):
        from app.utils_timing import measure
        with measure("refrescar_productos"):
            # 1) Filtro
            texto_busqueda = self.input_buscar.text().strip().lower()
            self.productos_filtro = texto_busqueda

            todos = self.prod_repo.listar_todos()
            if texto_busqueda:
                productos = [
                    p for p in todos
                    if texto_busqueda in (p.nombre or "").lower()
                    or texto_busqueda in (p.codigo_barra or "").lower()
                    or texto_busqueda in (p.categoria or "").lower()
                ]
            else:
                productos = todos

            # 2) Página
            total = len(productos)
            por_pagina = PRODUCTOS_POR_PAGINA
            pagina_actual = getattr(self, "productos_pagina_actual", 0)
            max_pag = max(0, (total - 1) // por_pagina)
            if pagina_actual > max_pag:
                pagina_actual = max_pag
                self.productos_pagina_actual = pagina_actual

            ini = pagina_actual * por_pagina
            fin = ini + por_pagina
            paginados = productos[ini:fin]

            # 3) Pintar tabla: 0=Sel, 1=ID, 2=Código, 3=Nombre, 4=Precio, 5=Categoría
            tbl = self.table_productos

            # --- Si el header vertical está oculto, asegurate de que el ID es visible en columna 1 ---
            tbl.setColumnCount(6)
            tbl.setHorizontalHeaderLabels(
                ['Sel','ID','Código','Nombre','Precio','Categoría']
            )

            from app.gui.qt_helpers import freeze_table
            with freeze_table(tbl):
                tbl.setRowCount(0)
                tbl.setRowCount(len(paginados))
                for r, p in enumerate(paginados):
                    # Col 0: checkbox
                    chk = QTableWidgetItem()
                    chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                    chk.setCheckState(Qt.Unchecked)
                    tbl.setItem(r, 0, chk)

                    # Cols 1..5: ID, Código, Nombre, Precio, Categoría
                    vals = [p.id, p.codigo_barra, p.nombre, f'{p.precio:.2f}', p.categoria or '']
                    for c, val in enumerate(vals, start=1):
                        it = QTableWidgetItem(str(val))
                        it.setFont(QFont("Arial", 11))
                        if c in (3, 4, 5):  # Nombre, Precio, Categoría editables
                            it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
                        else:
                            it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                        tbl.setItem(r, c, it)

            # 4) Footer
            self.lbl_paginacion.setText(
                f"Página {pagina_actual+1} de {max_pag+1}  (Mostrando {ini+1}-{min(fin,total)} de {total})"
            )
            self.btn_anterior.setEnabled(pagina_actual > 0)
            self.btn_siguiente.setEnabled(pagina_actual < max_pag)
            
    def exportar_codigos_png(self):
        from PyQt5.QtWidgets import QFileDialog, QMessageBox
        from PyQt5.QtGui import QPainter, QImage
        from PyQt5.QtCore import Qt

        # 0) Pedir ruta de guardado
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar etiquetas de códigos",
            "codigos.png",
            "PNG (*.png)"
        )
        if not path:
            return

        # 1) Filtrar filas seleccionadas
        rows = []
        for r in range(self.table_productos.rowCount()):
            it = self.table_productos.item(r, 0)  # 0 = checkbox
            if it and it.checkState() == Qt.Checked:
                rows.append(r)

        if not rows:
            QMessageBox.information(self, "Exportar PNG", "Marcá al menos un producto.")
            return

        # 2) Armar lista (code, name)
        items = []
        for r in rows:
            id_it   = self.table_productos.item(r, 1)  # 1 = ID
            code_it = self.table_productos.item(r, 2)  # 2 = Código
            name_it = self.table_productos.item(r, 3)  # 3 = Nombre

            pid  = int(id_it.text()) if id_it and id_it.text().strip().isdigit() else 0
            code = code_it.text().strip() if code_it else ""
            name = name_it.text().strip() if name_it else ""

            if not code:
                code = f"ID{pid:08d}"

            items.append((code, name))

        # 3) Render de la imagen
        #    (usa tu helper _draw_barcode_label importado desde app.gui.dialogs)
        w_px, h_px = 945, 2362

        tmp = QImage(w_px, 100, QImage.Format_ARGB32)
        tmp.fill(0xffffffff)
        tp = QPainter(tmp)
        from app.gui.dialogs import _draw_barcode_label  # por si no estaba en el scope
        y_test = _draw_barcode_label(tp, w_px, "0000000000000", "preview")
        tp.end()
        block_h = max(120, y_test)

        total_h = 48 + len(items) * block_h
        img = QImage(w_px, total_h, QImage.Format_ARGB32)
        img.fill(0xffffffff)
        p = QPainter(img)
        try:
            y = 24
            for code, name in items:
                y = _draw_barcode_label(p, w_px, code, name, margin=24)
        finally:
            p.end()

        if img.save(path, "PNG"):
            QMessageBox.information(self, "Exportar PNG", f"Guardado: {path}")
        else:
            QMessageBox.warning(self, "Exportar PNG", "No se pudo guardar la imagen.")

            
    def abrir_listado_productos(self):
        dlg = ProductosDialog(self.session, self)
        dlg.data_changed.connect(self.refrescar_completer) 
        if  dlg.exec_() == QDialog.Accepted:
        # si en el futuro querés recuperar lo marcado, iterás las filas y leés cada checkbox
            pass

