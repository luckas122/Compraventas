from datetime import datetime, timedelta
import os
import sys
import tempfile
import webbrowser
import urllib.parse
import subprocess
import logging
from pathlib import Path

logger = logging.getLogger(__name__)
from PyQt5.QtCore import Qt, QSize, QTimer, QRect, QSizeF, QMarginsF
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFormLayout, QRadioButton, QButtonGroup, QSpinBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QInputDialog, QFileDialog,
    QDialog,
)
from PyQt5.QtPrintSupport import QPrinter
from PyQt5.QtGui import QPdfWriter, QPainter, QFont

from app.gui.common import (
    ICON_SIZE, MIN_BTN_HEIGHT, LIVE_SEARCH_INPUT_HEIGHT, icon,LIVE_SEARCH_MIN_WIDTH
)


from app.models import Producto, Venta, VentaItem
from app.repository import prod_repo

# helpers de impresión/completer
from app.gui.ventas_helpers import build_product_completer, imprimir_ticket, _draw_ticket, _compute_ticket_height_mm


class VentasMixin:
    #Construcción de la pestaña VENTAS
    
    def tab_ventas(self):
        from PyQt5.QtWidgets import (
            QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
            QFormLayout, QRadioButton, QButtonGroup, QSpinBox, QTableWidget,
            QHeaderView
        )
        from PyQt5.QtCore import Qt, QSize, QTimer
        from PyQt5.QtGui import QFontDatabase

        w = QWidget()
        layout = QVBoxLayout()

        # ----------------- Búsqueda / Agregar -----------------
        h1 = QHBoxLayout()
        self.input_venta_buscar = QLineEdit()
        self.input_venta_buscar.setPlaceholderText('Código o nombre de producto')
        self.input_venta_buscar.returnPressed.connect(self.agregar_a_cesta)
        h1.addWidget(self.input_venta_buscar)
        from app.gui.common import LIVE_SEARCH_INPUT_HEIGHT
        self.input_venta_buscar.setMinimumHeight(LIVE_SEARCH_INPUT_HEIGHT)
        self.input_venta_buscar.setStyleSheet("font-size: 16px;")

        btn_add = QPushButton()
        btn_add.setIcon(icon('add.svg'))
        btn_add.setIconSize(ICON_SIZE)
        btn_add.setToolTip('Agregar')
        btn_add.clicked.connect(self.agregar_a_cesta)
        h1.addWidget(btn_add)

        # Botón "Vaciar Cesta"
        btn_vaciar = QPushButton(' Vaciar Cesta')
        btn_vaciar.setIcon(icon('delete.svg'))
        btn_vaciar.setIconSize(ICON_SIZE)
        btn_vaciar.setToolTip('Vaciar toda la cesta')
        btn_vaciar.clicked.connect(self._vaciar_cesta)
        h1.addWidget(btn_vaciar)

        # Botón "Guardar Borrador"
        btn_guardar_borr = QPushButton(' Guardar')
        btn_guardar_borr.setIcon(icon('save.svg'))  # o 'draft.svg' si existe
        btn_guardar_borr.setIconSize(ICON_SIZE)
        btn_guardar_borr.setToolTip('Guardar cesta como borrador')
        btn_guardar_borr.clicked.connect(self._guardar_borrador)
        h1.addWidget(btn_guardar_borr)

        # Botón "Cargar Borradores"
        btn_cargar_borr = QPushButton(' Borradores')
        btn_cargar_borr.setIcon(icon('folder.svg'))  # o 'drafts.svg'
        btn_cargar_borr.setIconSize(ICON_SIZE)
        btn_cargar_borr.setToolTip('Cargar borrador guardado')
        btn_cargar_borr.clicked.connect(self._abrir_borradores)
        h1.addWidget(btn_cargar_borr)

        layout.addLayout(h1)
        self.input_venta_buscar.setMinimumWidth(360)  # ajusta a gusto
        self.input_venta_buscar.setStyleSheet("""
        QLineEdit {
            padding: 6px 10px;
            border: 1px solid #b8b8c0;
            border-radius: 8px;
        }
        QLineEdit::placeholder {
            font-weight: bold;
        }
        """)

        # Anti-reentrancia para evitar doble alta por Enter/completer
        self._agregando_guard = False

        # Completer (usa el centralizado para no duplicar lógica)
        try:
            self._setup_completer()
            if getattr(self, "_completer", None) is not None:
                self.input_venta_buscar.setCompleter(self._completer)
        except Exception:
            pass

        # ----------------- Cesta -----------------
        self.table_cesta = QTableWidget(0, 6)
        self.table_cesta.setHorizontalHeaderLabels([
            'Código', 'Nombre', 'Cantidad', 'Precio Unit.', 'Total', 'Acciones'
        ])

        f = self.table_cesta.font()
        f.setPointSize(f.pointSize() + 2)
        self.table_cesta.setFont(f)

        hdr = self.table_cesta.horizontalHeader()
        hf = hdr.font(); hf.setBold(True); hdr.setFont(hf)
        # Código/Nombre visibles y cómodos; el resto a contenido
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # Código
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)           # Nombre
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Cant
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # P.Unit
        hdr.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Total
        hdr.setSectionResizeMode(5, QHeaderView.ResizeToContents)  # Acciones
        
        self.table_cesta.verticalHeader().setVisible(False)
        self.table_cesta.verticalHeader().setDefaultSectionSize(40)  # alto de fila suficiente
        self.table_cesta.setIconSize(QSize(18, 18))
        self.table_cesta.itemChanged.connect(self._on_cesta_item_changed)

        # Doble click para editar cantidad
        self.table_cesta.itemDoubleClicked.connect(self._on_cesta_doble_click)

        layout.addWidget(self.table_cesta)

        # ----------------- Pago -----------------
        
        form = QFormLayout()

        # Radios
        self.rb_efectivo = QRadioButton('Efectivo')
        self.rb_tarjeta  = QRadioButton('Tarjeta')
        self.rb_efectivo.setChecked(True)
        bg = QButtonGroup(self)
        bg.addButton(self.rb_efectivo)
        bg.addButton(self.rb_tarjeta)

        # Controles (crearlos ANTES de usarlos)
        self.spin_cuotas = QSpinBox()
        self.spin_cuotas.setRange(1, 12)
        self.spin_cuotas.setEnabled(False)

        self.cuota_label = QLabel('')
        from PyQt5.QtWidgets import QAbstractSpinBox
        self.spin_cuotas.setButtonSymbols(QAbstractSpinBox.UpDownArrows)
        self.btn_interes = QPushButton(' Interés')
        self.btn_interes.setVisible(False)
        self.btn_interes.setIcon(icon('interes.svg'))
        self.btn_interes.setIconSize(QSize(18, 18))
        self.btn_interes.setFixedHeight(28)
        self.btn_interes.setToolTip('Aplicar interés (%)')
        self.btn_interes.setAutoDefault(False)
        self.btn_interes.setDefault(False)
        self.btn_interes.setFocusPolicy(Qt.NoFocus)
        self.btn_interes.clicked.connect(self._aplicar_interes_dialog)
        self.btn_interes.setProperty("role", "inline")

        self.btn_descuento = QPushButton(' Descuento')
        self.btn_descuento.setIcon(icon('discount.svg'))
        self.btn_descuento.setIconSize(QSize(18, 18))
        self.btn_descuento.setFixedHeight(28)
        self.btn_descuento.setToolTip('Aplicar descuento (%)')
        self.btn_descuento.setAutoDefault(False)
        self.btn_descuento.setDefault(False)
        self.btn_descuento.setFocusPolicy(Qt.NoFocus)
        self.btn_descuento.clicked.connect(self._aplicar_descuento_dialog)
        self.btn_descuento.setProperty("role", "inline")

        # Fila compacta: pago + cuotas + interés + descuento
        row_pago = QHBoxLayout()
        row_pago.addWidget(self.rb_efectivo)
        row_pago.addWidget(self.rb_tarjeta)
        row_pago.addSpacing(10)
        row_pago.addWidget(QLabel("Cuotas:"))
        row_pago.addWidget(self.spin_cuotas)
        row_pago.addSpacing(10)
        row_pago.addWidget(self.btn_interes)
        row_pago.addWidget(self.btn_descuento)
        row_pago.addStretch(1)
        row_pago.addSpacing(10)
        row_pago.addWidget(QLabel("Monto x cuota:"))
        row_pago.addWidget(self.cuota_label)

        row_pago.setAlignment(Qt.AlignVCenter)      # centra verticalmente todo
        self.spin_cuotas.setFixedHeight(28)      # iguala alturas con los botones
        form.addRow('Pago / Cuotas:', row_pago)

        

        # señales
        self.rb_tarjeta.toggled.connect(self._on_pago_method_changed)
        self.spin_cuotas.valueChanged.connect(self._update_cuota_label)

        layout.addLayout(form)

        # ----------------- Total / Acciones -----------------
        
        h3 = QHBoxLayout()
        h3.setSpacing(24)                       # separa un poco más
        h3.setContentsMargins(0, 8, 0, 8)

        self.lbl_total = QLabel('Total: $0.00')
        kpi_font = self.font()
        kpi_font.setPointSize(kpi_font.pointSize() + 8)  # mismo tamaño grande
        kpi_font.setBold(True)
        self.lbl_total.setFont(kpi_font)
        self.lbl_total.setStyleSheet("color:#2e7d32;")

        self.lbl_interes = QLabel('Interés: $0.00')
        self.lbl_interes.setFont(QFont(kpi_font))        # MISMO tamaño que Total
        self.lbl_interes.setStyleSheet("color:#c62828;")

        self.lbl_descuento = QLabel('Descuento: $0.00')
        self.lbl_descuento.setFont(QFont(kpi_font))      # MISMO tamaño que Total
        self.lbl_descuento.setStyleSheet("color:#1565c0;")

        h3.addWidget(self.lbl_total)
        h3.addSpacing(12)                                 # un poco más de aire
        h3.addWidget(self.lbl_interes)
        h3.addSpacing(12)
        h3.addWidget(self.lbl_descuento)
        h3.addStretch()
        
        
        btn_fin = QPushButton()
        btn_fin.setIcon(icon('ticket.svg'))
        btn_fin.setIconSize(ICON_SIZE)
        btn_fin.setToolTip('Finalizar Venta')
        btn_fin.setAutoDefault(True)
        btn_fin.setDefault(True)
        btn_fin.clicked.connect(self._shortcut_finalizar_venta_dialog)


        btn_dev = QPushButton()
        btn_dev.setIcon(icon('return.svg'))
        btn_dev.setIconSize(ICON_SIZE)
        btn_dev.setToolTip('Devolución')
        btn_dev.clicked.connect(self._on_devolucion)

        # Exportar PDF (80 mm)
        btn_pdf = QPushButton('PDF')
        btn_pdf.setToolTip('Exportar ticket como PDF (80 mm)')
        btn_pdf.setIcon(icon('export.svg'))
        btn_pdf.setIconSize(ICON_SIZE)
        btn_pdf.clicked.connect(self.exportar_ticket_pdf)

        # WhatsApp Web
        btn_wa = QPushButton('WhatsApp Web')
        btn_wa.setToolTip('Enviar ticket por WhatsApp Web')
        btn_wa.setIcon(icon('wtsp.svg'))  # icono que agregaste
        btn_wa.setIconSize(ICON_SIZE)
        btn_wa.clicked.connect(self.enviar_ticket_whatsapp)

    
        h3.addWidget(btn_fin)
        h3.addWidget(btn_dev)
        h3.addWidget(btn_pdf)
        h3.addWidget(btn_wa)
        layout.addLayout(h3)

        # ----------------- Ventas del día -----------------
        layout.addWidget(QLabel('Ventas Realizadas Hoy'))
        self.table_ventas_dia = QTableWidget(0, 11)
        self.table_ventas_dia.setHorizontalHeaderLabels([
            'Nº Ticket', 'Hora', 'Total', 'Forma Pago',
            'Cuotas','interes','Descuento', 'Monto x cuota', 'Pagado', 'Vuelto', 'Acciones'
        ])
        self.table_ventas_dia.verticalHeader().setVisible(False)

        fvd = self.table_ventas_dia.font()
        fvd.setPointSize(fvd.pointSize() + 2)
        self.table_ventas_dia.setFont(fvd)

        hdr2 = self.table_ventas_dia.horizontalHeader()
        hdr2.setSectionResizeMode(QHeaderView.Stretch)
        hdr2.setStretchLastSection(False)
        hdr2.setSectionResizeMode(10, QHeaderView.ResizeToContents)  # Acciones
        self.table_ventas_dia.setColumnWidth(10, 180)
        self.table_ventas_dia.setIconSize(QSize(20, 20))
        self.table_ventas_dia.verticalHeader().setDefaultSectionSize(28)

        layout.addWidget(self.table_ventas_dia)

        # Final
        w.setLayout(layout)

        # Los atajos de teclado G y B se manejan centralizadamente
        # en el ShortcutManager (core.py), no aquí

        self.recargar_ventas_dia()
        self._reset_ajustes_globales()
        self.actualizar_total()
        return w
    
    
#----Cesta (agregar/editar/quitar y totales)---

    def agregar_a_cesta(self):
            # Si la cesta está vacía, asegurá iniciar con ajustes globales en cero

            if self.table_cesta.rowCount() == 0:
                self._reset_ajustes_globales()
            
            """Añade el producto buscado por código o nombre a la cesta.
            Si ya está, incrementa la cantidad (evita el 'doble alta' por Enter/completer)."""
            # Guard anti-reentrancia
            if getattr(self, "_agregando_guard", False):
                return
            self._agregando_guard = True
            try:
                term = (self.input_venta_buscar.text() or "").strip()
                if not term:
                    return

                # Normalización si viene “CODIGO - NOMBRE”
                code = None
                name_hint = None
                if " - " in term:
                    code, name_hint = term.split(" - ", 1)
                    code = (code or "").strip()
                    name_hint = (name_hint or "").strip()

                prod = None

                # 1) Buscar por código explícito (si se separó)
                if code:
                    prod = self.prod_repo.buscar_por_codigo(code)

                # 2) Si no encontró, intentar código si term es numérico "largo"
                if not prod and term.isdigit():
                    prod = self.prod_repo.buscar_por_codigo(term)

                # 3) Si aún no, buscar por nombre con fuzzy matching
                if not prod:
                    qtxt = name_hint or term
                    prod = self._buscar_producto_fuzzy(qtxt)

                if not prod:
                    QMessageBox.warning(self, 'No encontrado', f'Producto "{term}" no hallado.')
                    return

                # --- Fusionar si el producto ya está en la tabla (mismo código) ---
                existing_row = None
                for r in range(self.table_cesta.rowCount()):
                    it_code = self.table_cesta.item(r, 0)
                    if it_code and it_code.text() == prod.codigo_barra:
                        existing_row = r
                        break

                if existing_row is not None:
                    # Sumar cantidad
                    it_cant = self.table_cesta.item(existing_row, 2)
                    try:
                        cant = int((it_cant.text() if it_cant else "0")) + 1
                    except Exception:
                        cant = 1
                    self.table_cesta.setItem(existing_row, 2, QTableWidgetItem(str(cant)))

                    # Recalcular total de fila
                    it_pu = self.table_cesta.item(existing_row, 3)
                    try:
                        pu = float(str(it_pu.text()).replace("$", "").strip())
                    except Exception:
                        pu = float(getattr(prod, "precio", 0.0))

                    total_fila = cant * pu
                    it_total = QTableWidgetItem(f"{total_fila:.2f}")
                    it_total.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    self.table_cesta.setItem(existing_row, 4, it_total)

                    # Actualizar totales y anchos
                    self.actualizar_total()
                    if hasattr(self, "_ajustar_anchos_cesta"):
                        self._ajustar_anchos_cesta()
                    self._beep_ok()

                    # 🔹 limpiar buscador y cerrar popup
                    self.input_venta_buscar.clear()
                    try:
                        self._completer.popup().hide()
                    except Exception:
                        pass
                    self.input_venta_buscar.setFocus()
                    return

                # --- Si no estaba: agregar nueva fila ---
                self._add_row_to_cesta(prod)
                if hasattr(self, "_ajustar_anchos_cesta"):
                    self._ajustar_anchos_cesta()
                self.actualizar_total()
                self._beep_ok()

                # 🔹 limpiar buscador y cerrar popup
                self.input_venta_buscar.clear()
                try:
                    self._completer.popup().hide()
                except Exception:
                    pass
                self.input_venta_buscar.setFocus()

            finally:
                # Liberar el guard en el siguiente ciclo de eventos (evita dobles por Enter/completer)
                QTimer.singleShot(0, lambda: setattr(self, "_agregando_guard", False))

    def _buscar_producto_fuzzy(self, query):
        """
        Busca productos usando fuzzy matching (tolerante a errores de tipeo).
        Retorna el mejor match si supera el umbral de similitud.
        """
        try:
            from rapidfuzz import fuzz, process
        except ImportError:
            # Si no está instalado rapidfuzz, usar búsqueda tradicional
            return (self.session.query(Producto)
                    .filter(Producto.nombre.ilike(f'%{query}%'))
                    .first())

        # Obtener todos los productos
        productos = self.session.query(Producto).all()

        if not productos:
            return None

        # Crear diccionario de productos por nombre y código (lowercase para comparar)
        productos_dict = {p.nombre.lower(): p for p in productos}
        productos_dict_codigo = {p.codigo_barra.lower(): p for p in productos}

        query_lower = query.lower()

        # 1. Primero intentar match exacto (case insensitive)
        if query_lower in productos_dict:
            return productos_dict[query_lower]
        if query_lower in productos_dict_codigo:
            return productos_dict_codigo[query_lower]

        # 2. Buscar substring (contiene)
        for nombre, prod in productos_dict.items():
            if query_lower in nombre or nombre in query_lower:
                return prod

        # 3. Fuzzy matching con umbral adaptativo según longitud de la query
        # Queries cortas: umbral más bajo
        if len(query) <= 4:
            threshold = 50  # Muy permisivo para búsquedas cortas como "prva"
        elif len(query) <= 7:
            threshold = 60
        else:
            threshold = 70

        # Buscar el mejor match en nombres usando partial_ratio (mejor para substrings)
        result_nombre = process.extractOne(
            query_lower,
            productos_dict.keys(),
            scorer=fuzz.partial_ratio,  # Mejor para búsquedas parciales
            score_cutoff=threshold
        )

        # Buscar el mejor match en códigos de barras
        result_codigo = process.extractOne(
            query_lower,
            productos_dict_codigo.keys(),
            scorer=fuzz.partial_ratio,
            score_cutoff=threshold + 10  # Un poco más estricto para códigos
        )

        # Decidir cuál usar (priorizar el de mayor score)
        best_match = None
        best_score = 0

        if result_nombre:
            match_nombre, score_nombre, _ = result_nombre
            if score_nombre > best_score:
                best_match = productos_dict[match_nombre]
                best_score = score_nombre

        if result_codigo:
            match_codigo, score_codigo, _ = result_codigo
            if score_codigo > best_score:
                best_match = productos_dict_codigo[match_codigo]
                best_score = score_codigo

        return best_match



    def _add_row_to_cesta(self, prod):
        r = self.table_cesta.rowCount()
        self.table_cesta.insertRow(r)
        # Columnas 0–4 con el producto
        for c, val in enumerate([
            prod.codigo_barra,
            prod.nombre,
            '1',
            f'{prod.precio:.2f}',
            f'{prod.precio:.2f}'
        ]):
            self.table_cesta.setItem(r, c, QTableWidgetItem(val))
            # Guardar "precio base" en UserRole para cálculos de interés
        pu_item = self.table_cesta.item(r, 3)
        try:
            pu_item.setData(Qt.UserRole, float(pu_item.text()))
        except Exception:
            pass

        # Columna 5: widget con iconos y conexión directa
        widget = QWidget()
        lay = QHBoxLayout(widget)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setAlignment(Qt.AlignCenter)

        # Botón Editar
        btn_edit = QPushButton()
        btn_edit.setIcon(icon('edit.svg'))
        btn_edit.setToolTip('Editar')
        btn_edit.setFixedSize(24, 24)
        # Conectamos pasando el índice de fila
        btn_edit.clicked.connect(lambda _, row=r: self.editar_cantidad(row))
        lay.addWidget(btn_edit)
        
        # Botón Descuento (% por ítem)
        btn_desc = QPushButton()
        btn_desc.setIcon(icon('discount.svg'))  # si no lo tenés, podés dejar texto con setText("Desc.")
        btn_desc.setToolTip('Descuento (%) solo a este producto')
        btn_desc.setFixedSize(24, 24)
        btn_desc.setFocusPolicy(Qt.NoFocus)
        btn_desc.clicked.connect(lambda _, row=r: self._descuento_en_fila(row))
        lay.addWidget(btn_desc)

        # Botón Borrar
        btn_del = QPushButton()
        btn_del.setIcon(icon('delete.svg'))
        btn_del.setToolTip('Borrar')
        btn_del.setFixedSize(24, 24)
        btn_del.clicked.connect(lambda _, row=r: self.quitar_producto(row))
        lay.addWidget(btn_del)

        row_h = self.table_cesta.verticalHeader().defaultSectionSize()
        btn_sz = max(28, row_h - 8)
    ##########
    # #garantiza que los botones no queden cortados
        self.table_cesta.setRowHeight(r, max(self.table_cesta.rowHeight(r), btn_sz + 8))
    ##########
        for b in (btn_edit, btn_desc, btn_del):
            b.setProperty("role", "cell")                 # usa el CSS global de common.py
            b.setFixedSize(btn_sz, btn_sz)                # cuadrado, no se corta
            b.setIconSize(QSize(btn_sz - 12, btn_sz - 12))
        
        self.table_cesta.setCellWidget(r, 5, widget)
        self.actualizar_total()
        
        # Alinear numéricos de la fila recién agregada
        for col in (2, 3, 4):
            it = self.table_cesta.item(r, col)
            if it:
                it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self._ajustar_anchos_cesta()
        
        
        
        #BOTON EDITAR
        
    def editar_cantidad(self, row=None):
        """Edita la cantidad (y recalcula totales) de la fila de la cesta."""
        from PyQt5.QtWidgets import QInputDialog, QTableWidgetItem
        tbl = self.table_cesta
        if row is None:
            it = tbl.selectedItems()
            if not it:
                return
            row = it[0].row()

        # Cantidad actual
        try:
            cant_actual = float(tbl.item(row, 2).text())
        except Exception:
            cant_actual = 1.0

        nueva, ok = QInputDialog.getDouble(
            self, 'Editar cantidad', 'Cantidad:', cant_actual, 0.0, 999999.0, 2
        )
        if not ok:
            return

        # Actualizar cantidad
        tbl.item(row, 2).setText(f"{float(nueva):.2f}")

        # Recalcular total de la fila
        try:
            pu = float(str(tbl.item(row, 3).text()).replace("$","").strip())
        except Exception:
            pu = 0.0
        total = float(nueva) * pu

        it_total = tbl.item(row, 4)
        if it_total is None:
            it_total = QTableWidgetItem()
            tbl.setItem(row, 4, it_total)
        it_total.setText(f"{total:.2f}")

        # Alinear numéricos
        for c in (2, 3, 4):
            it = tbl.item(row, c)
            if it:
                it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

        # Totales generales
        self.actualizar_total()     
        
    
    def _descuento_en_fila(self, row: int):
        from PyQt5.QtWidgets import QInputDialog, QTableWidgetItem
        # 1) pedir porcentaje
        pct, ok = QInputDialog.getDouble(
            self, 'Descuento por producto', 'Porcentaje (0–100):', 0.0, 0.0, 100.0, 2
        )
        if not ok:
            return

        # 2) cantidad
        try:
            cant = float(self.table_cesta.item(row, 2).text())
        except Exception:
            cant = 1.0

        # 3) precio base guardado en UserRole de la col 3
        pu_item = self.table_cesta.item(row, 3)
        if pu_item is None:
            return
        base = pu_item.data(Qt.UserRole)
        if base is None:
            try:
                base = float(str(pu_item.text()).replace("$","").strip())
            except Exception:
                base = 0.0
            pu_item.setData(Qt.UserRole, base)

        # 4) guardar % por-ítem en UserRole+1 (NO tocamos el texto de la celda)
        pu_item.setData(Qt.UserRole + 1, float(pct))
        # opcional: señalizar en tooltip
        pu_item.setToolTip(f"Precio base: ${base:.2f}\nDescuento ítem: {pct:.2f}%")

        # 5) total de la fila con descuento por-ítem aplicado
        eff = round(base * (1.0 - float(pct)/100.0), 2)
        it_total = self.table_cesta.item(row, 4)
        if it_total is None:
            it_total = QTableWidgetItem()
            self.table_cesta.setItem(row, 4, it_total)
        it_total.setText(f"{eff * cant:.2f}")
        for c in (3, 4):
            it = self.table_cesta.item(row, c)
            if it:
                it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

        # 6) actualizar totales generales/cuotas
        self.actualizar_total()
        try:
            if self.rb_tarjeta.isChecked() and int(self.spin_cuotas.value() or 0) > 0:
                self._update_cuota_label(int(self.spin_cuotas.value()))
        except Exception:
            pass
        
    def quitar_producto(self, row=None):
        if row is None:
            items = self.table_cesta.selectedItems()
            if not items:
                return
            row = items[0].row()
        self.table_cesta.removeRow(row)
        self.actualizar_total()
        # Si quedó vacía, reiniciar ajustes globales y UI
        if self.table_cesta.rowCount() == 0:
            self._reset_ajustes_globales()
        self._ajustar_anchos_cesta()

    def _on_cesta_doble_click(self, item):
        """Maneja doble click en la cesta para editar cantidad"""
        if item is None:
            return

        row = item.row()
        col = item.column()

        # Solo permitir editar la columna de Cantidad (columna 2)
        if col != 2:
            return

        # Obtener cantidad actual
        try:
            cantidad_actual = float(self.table_cesta.item(row, 2).text())
        except:
            cantidad_actual = 1.0

        # Pedir nueva cantidad
        nueva_cantidad, ok = QInputDialog.getInt(
            self,
            "Editar Cantidad",
            "Nueva cantidad:",
            value=int(cantidad_actual),
            min=1,
            max=9999,
            step=1
        )

        if ok and nueva_cantidad > 0:
            # Actualizar cantidad
            self.table_cesta.item(row, 2).setText(str(nueva_cantidad))

            # Recalcular total de la fila
            try:
                precio_unit = float(self.table_cesta.item(row, 3).text())
                total_fila = nueva_cantidad * precio_unit
                self.table_cesta.item(row, 4).setText(f"{total_fila:.2f}")
            except:
                pass

            # Actualizar totales generales
            self.actualizar_total()

    #---------- BORRADORES ----------

    def _guardar_borrador(self):
        """Guarda la cesta actual como borrador"""
        from app.models import VentaBorrador, VentaBorradorItem

        # Verificar que hay items en la cesta
        if self.table_cesta.rowCount() == 0:
            QMessageBox.information(self, "Cesta vacía", "No hay items para guardar como borrador.")
            return

        try:
            # Contar borradores existentes para asignar número
            count = self.session.query(VentaBorrador).filter_by(sucursal=self.sucursal).count()

            # Si hay 5, eliminar el más antiguo
            if count >= 5:
                oldest = (self.session.query(VentaBorrador)
                         .filter_by(sucursal=self.sucursal)
                         .order_by(VentaBorrador.fecha_creacion.asc())
                         .first())
                if oldest:
                    self.session.delete(oldest)
                    count = 4  # Ahora hay 4

            # Nombre automático: Borrador 1, 2, 3, 4, 5
            numero_borrador = count + 1
            nombre = f"Borrador {numero_borrador}"

            # Crear borrador
            borrador = VentaBorrador(
                nombre=nombre,
                sucursal=self.sucursal,
                modo_pago='Tarjeta' if self.rb_tarjeta.isChecked() else 'Efectivo',
                cuotas=self.spin_cuotas.value() if self.rb_tarjeta.isChecked() else None,
                total=self._total_actual,
                subtotal_base=self._subtotal_base,
                interes_pct=self._interes_pct,
                interes_monto=self._interes_monto,
                descuento_pct=self._descuento_pct,
                descuento_monto=self._descuento_monto
            )

            # Guardar items
            for r in range(self.table_cesta.rowCount()):
                # Validar que las celdas existan
                item_codigo = self.table_cesta.item(r, 0)
                item_nombre = self.table_cesta.item(r, 1)
                item_cant = self.table_cesta.item(r, 2)
                item_precio = self.table_cesta.item(r, 3)

                if not item_codigo or not item_cant or not item_precio:
                    continue

                codigo = item_codigo.text().strip()
                nombre_prod = item_nombre.text().strip() if item_nombre else ""

                # Conversiones seguras
                try:
                    cantidad = int(float(item_cant.text().replace(",", ".").strip() or "0"))
                    precio_unit = float(item_precio.text().replace("$", "").replace(",", ".").strip() or "0")
                except (ValueError, AttributeError):
                    continue

                if not codigo or cantidad <= 0:
                    continue

                # Buscar producto_id si existe
                from app.models import Producto
                prod = self.session.query(Producto).filter_by(codigo_barra=codigo).first()

                item = VentaBorradorItem(
                    producto_id=prod.id if prod else None,
                    codigo_barra=codigo,
                    nombre=nombre_prod,
                    cantidad=cantidad,
                    precio_unit=precio_unit
                )
                borrador.items.append(item)

            self.session.add(borrador)
            self.session.commit()

            QMessageBox.information(self, "Borrador Guardado", f"'{nombre}' guardado correctamente.")

        except Exception as e:
            self.session.rollback()
            QMessageBox.critical(self, "Error", f"No se pudo guardar el borrador:\n{str(e)}")

    def _abrir_borradores(self):
        """Abre diálogo para cargar o eliminar borradores"""
        from app.models import VentaBorrador
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QListWidget, QHBoxLayout, QLabel

        # Obtener borradores de esta sucursal
        borradores = (self.session.query(VentaBorrador)
                     .filter_by(sucursal=self.sucursal)
                     .order_by(VentaBorrador.fecha_creacion.desc())
                     .all())

        if not borradores:
            QMessageBox.information(self, "Sin Borradores", "No hay borradores guardados.")
            return

        # Crear diálogo
        dialog = QDialog(self)
        dialog.setWindowTitle("Borradores Guardados")
        dialog.setMinimumWidth(400)
        dialog.setMinimumHeight(300)

        layout = QVBoxLayout(dialog)

        # Label info
        layout.addWidget(QLabel(f"Borradores en {self.sucursal} (máximo 5):"))

        # Lista de borradores
        list_widget = QListWidget()
        for b in borradores:
            list_widget.addItem(f"{b.nombre} - ${b.total:.2f} ({len(b.items)} items)")

        layout.addWidget(list_widget)

        # Botones
        btn_layout = QHBoxLayout()

        btn_cargar = QPushButton("Cargar")
        btn_cargar.clicked.connect(lambda: self._cargar_borrador_seleccionado(borradores, list_widget, dialog))
        btn_layout.addWidget(btn_cargar)

        btn_eliminar = QPushButton("Eliminar")
        btn_eliminar.clicked.connect(lambda: self._eliminar_borrador_seleccionado(borradores, list_widget))
        btn_layout.addWidget(btn_eliminar)

        btn_cancelar = QPushButton("Cancelar")
        btn_cancelar.clicked.connect(dialog.reject)
        btn_layout.addWidget(btn_cancelar)

        layout.addLayout(btn_layout)

        dialog.exec_()

    def _cargar_borrador_seleccionado(self, borradores, list_widget, dialog):
        """Carga el borrador seleccionado en la cesta"""
        selected = list_widget.currentRow()
        if selected < 0:
            QMessageBox.warning(self, "Selección requerida", "Por favor selecciona un borrador.")
            return

        borrador = borradores[selected]

        # Confirmar si hay items en la cesta
        if self.table_cesta.rowCount() > 0:
            reply = QMessageBox.question(
                self,
                "Reemplazar Cesta",
                "¿Deseas reemplazar la cesta actual con el borrador?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

        # Limpiar cesta actual
        self.table_cesta.setRowCount(0)
        self._reset_ajustes_globales()

        # Cargar items del borrador
        from app.models import Producto
        for item in borrador.items:
            # Buscar producto actual (puede haber cambiado de precio)
            prod = self.session.query(Producto).filter_by(codigo_barra=item.codigo_barra).first()

            if prod:
                # Usar datos actuales del producto
                self._add_row_to_cesta_custom(
                    codigo=prod.codigo_barra,
                    nombre=prod.nombre,
                    cantidad=item.cantidad,
                    precio=item.precio_unit  # Usar precio del borrador
                )
            else:
                # Producto eliminado, usar datos guardados
                self._add_row_to_cesta_custom(
                    codigo=item.codigo_barra,
                    nombre=item.nombre + " (eliminado)",
                    cantidad=item.cantidad,
                    precio=item.precio_unit
                )

        # Restaurar configuración
        if borrador.modo_pago == 'Tarjeta':
            self.rb_tarjeta.setChecked(True)
            if borrador.cuotas:
                self.spin_cuotas.setValue(borrador.cuotas)
        else:
            self.rb_efectivo.setChecked(True)

        # Restaurar ajustes
        self._interes_pct = borrador.interes_pct
        self._interes_monto = borrador.interes_monto
        self._descuento_pct = borrador.descuento_pct
        self._descuento_monto = borrador.descuento_monto

        self.actualizar_total()
        dialog.accept()

        QMessageBox.information(self, "Borrador Cargado", f"Borrador '{borrador.nombre}' cargado correctamente.")

    def _eliminar_borrador_seleccionado(self, borradores, list_widget):
        """Elimina el borrador seleccionado"""
        from app.models import VentaBorrador

        selected = list_widget.currentRow()
        if selected < 0:
            QMessageBox.warning(self, "Selección requerida", "Por favor selecciona un borrador.")
            return

        borrador = borradores[selected]

        reply = QMessageBox.question(
            self,
            "Eliminar Borrador",
            f"¿Estás seguro de eliminar '{borrador.nombre}'?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            try:
                self.session.delete(borrador)
                self.session.commit()
                list_widget.takeItem(selected)
                borradores.pop(selected)
                QMessageBox.information(self, "Eliminado", "Borrador eliminado correctamente.")
            except Exception as e:
                self.session.rollback()
                QMessageBox.critical(self, "Error", f"No se pudo eliminar:\n{str(e)}")

    def _add_row_to_cesta_custom(self, codigo, nombre, cantidad, precio):
        """Agrega un item custom a la cesta (para cargar borradores)"""
        r = self.table_cesta.rowCount()
        self.table_cesta.insertRow(r)

        self.table_cesta.setItem(r, 0, QTableWidgetItem(codigo))
        self.table_cesta.setItem(r, 1, QTableWidgetItem(nombre))
        self.table_cesta.setItem(r, 2, QTableWidgetItem(str(cantidad)))
        self.table_cesta.setItem(r, 3, QTableWidgetItem(f"{precio:.2f}"))
        self.table_cesta.setItem(r, 4, QTableWidgetItem(f"{cantidad * precio:.2f}"))

        # Agregar botones de acciones (copiado de _add_row_to_cesta)
        self._add_action_buttons_to_row(r)

    def _add_action_buttons_to_row(self, r):
        """Agrega los botones de acciones a una fila (helper para borradores)"""
        from PyQt5.QtWidgets import QWidget, QHBoxLayout
        from PyQt5.QtCore import QSize, Qt

        widget = QWidget()
        lay = QHBoxLayout(widget)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(2)

        # Botón Editar Precio
        btn_edit = QPushButton()
        btn_edit.setIcon(icon('edit.svg'))
        btn_edit.setToolTip('Editar precio')
        btn_edit.setFixedSize(24, 24)
        btn_edit.setFocusPolicy(Qt.NoFocus)
        btn_edit.clicked.connect(lambda _, row=r: self._editar_precio_en_fila(row))
        lay.addWidget(btn_edit)

        # Botón Descuento
        btn_desc = QPushButton()
        btn_desc.setIcon(icon('discount.svg'))
        btn_desc.setToolTip('Descuento (%) solo a este producto')
        btn_desc.setFixedSize(24, 24)
        btn_desc.setFocusPolicy(Qt.NoFocus)
        btn_desc.clicked.connect(lambda _, row=r: self._descuento_en_fila(row))
        lay.addWidget(btn_desc)

        # Botón Borrar
        btn_del = QPushButton()
        btn_del.setIcon(icon('delete.svg'))
        btn_del.setToolTip('Borrar')
        btn_del.setFixedSize(24, 24)
        btn_del.clicked.connect(lambda _, row=r: self.quitar_producto(row))
        lay.addWidget(btn_del)

        self.table_cesta.setCellWidget(r, 5, widget)


    def actualizar_total(self):
        subtotal_base = 0.0
        descuento_items_monto = 0.0   # ← NUEVO

        # Sumar SIEMPRE con precio base guardado en UserRole
        for r in range(self.table_cesta.rowCount()):
            # cantidad
            try:
                cant = float(self.table_cesta.item(r, 2).text())
            except Exception:
                cant = 0.0

            # precio base (UserRole en col 3)
            pu_item = self.table_cesta.item(r, 3)
            base = 0.0
            if pu_item is not None:
                try:
                    base = float(pu_item.data(Qt.UserRole))
                except Exception:
                    try:
                        base = float(str(pu_item.text()).replace("$","").strip() or "0")
                    except Exception:
                        base = 0.0

            subtotal_base += cant * base

            # ↓↓↓ NUEVO: descuento % por-ítem (UserRole+1)
            try:
                pct_item = float(pu_item.data(Qt.UserRole + 1) or 0.0)
            except Exception:
                pct_item = 0.0
            eff = base * (1.0 - pct_item/100.0)
            descuento_items_monto += (base - eff) * cant

            # mantener visible el base en la tabla (P.Unit.)
            try:
                pu_item.setText(f"{base:.2f}")
            except Exception:
                pass
            try:
                tot_item = self.table_cesta.item(r, 4)
                if tot_item is None:
                    tot_item = QTableWidgetItem()
                    self.table_cesta.setItem(r, 4, tot_item)
                # ↓↓↓ usar el precio efectivo (base - %item) para el total por fila
                tot_item.setText(f"{eff * cant:.2f}")
                tot_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            except Exception:
                pass

        # Ajustes globales
        interes_monto    = round(subtotal_base * (float(getattr(self, "_interes_pct", 0.0))   / 100.0), 2)
        descuento_global = round(subtotal_base * (float(getattr(self, "_descuento_pct", 0.0)) / 100.0), 2)
        descuento_total  = round(descuento_global + descuento_items_monto, 2)   # ← NUEVO
        total_final      = round(subtotal_base - descuento_total + interes_monto, 2)  # ← NUEVO

        # UI
        self.lbl_total.setText(f"Total: ${total_final:.2f}")
        if hasattr(self, 'lbl_interes') and self.lbl_interes:
            self.lbl_interes.setText(f"Interés: ${interes_monto:.2f}")
        if hasattr(self, 'lbl_descuento') and self.lbl_descuento:
            self.lbl_descuento.setText(f"Descuento: ${descuento_total:.2f}")     # ← NUEVO (muestra global + ítem)

        # Estado
        self._subtotal_base   = subtotal_base
        self._interes_monto   = interes_monto
        self._descuento_monto = descuento_total    # ← NUEVO (ticket verá el total de descuentos)
        self._total_actual    = total_final

        # Tarjeta: actualizar monto x cuota
        try:
            if hasattr(self, 'rb_tarjeta') and self.rb_tarjeta.isChecked():
                c = int(self.spin_cuotas.value() or 0)
                if c > 0:
                    self._update_cuota_label(c)
        except Exception:
            pass
        
        
    def _ajustar_anchos_cesta(self):
        """Ajusta ancho de 'Código' al código más largo y alinea numéricos."""
        if not hasattr(self, 'table_cesta') or self.table_cesta is None:
            return
        fm = self.table_cesta.fontMetrics()
        maxw = 0
        for r in range(self.table_cesta.rowCount()):
            it = self.table_cesta.item(r, 0)
            if it:
                maxw = max(maxw, fm.horizontalAdvance(it.text()))
            # Alinear numéricos (Cantidad, Precio Unit., Total)
            for c in (2, 3, 4):
                itn = self.table_cesta.item(r, c)
                if itn:
                    itn.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        if maxw:
            self.table_cesta.horizontalHeader().resizeSection(0, maxw + 24)
            
            
    #RESET GLOBALES DE VENTA 
    def _vaciar_cesta(self):
        """Vacía todos los items de la cesta con confirmación"""
        if self.table_cesta.rowCount() == 0:
            QMessageBox.information(self, "Cesta vacía", "No hay items en la cesta para eliminar.")
            return

        respuesta = QMessageBox.question(
            self,
            "Vaciar Cesta",
            f"¿Estás seguro de eliminar todos los {self.table_cesta.rowCount()} items de la cesta?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if respuesta == QMessageBox.Yes:
            self.table_cesta.setRowCount(0)
            self._reset_ajustes_globales()

    def _reset_ajustes_globales(self):
        # porcentajes
        self._interes_pct = 0.0
        self._descuento_pct = 0.0
        # montos y cache
        self._subtotal_base = 0.0
        self._interes_monto = 0.0
        self._descuento_monto = 0.0
        self._total_actual = 0.0

        # labels (si existen)
        try:
            if hasattr(self, 'lbl_interes') and self.lbl_interes:
                self.lbl_interes.setText("Interés: $0.00")
            if hasattr(self, 'lbl_descuento') and self.lbl_descuento:
                self.lbl_descuento.setText("Descuento: $0.00")
            if hasattr(self, 'lbl_total') and self.lbl_total:
                self.lbl_total.setText("Total: $0.00")
        except Exception:
            pass

        # forma de pago por defecto (opcional)
        try:
            if hasattr(self, 'rb_efectivo'):
                self.rb_efectivo.setChecked(True)
            if hasattr(self, 'spin_cuotas'):
                self.spin_cuotas.setValue(1)
            if hasattr(self, '_update_cuota_label'):
                self._update_cuota_label(0)
            # Limpiar datos del diálogo de tarjeta
            if hasattr(self, '_datos_tarjeta'):
                self._datos_tarjeta = None
        except Exception:
            pass
        
        
#-----Interés / Descuento / Método de pago

    def _aplicar_interes_dialog(self):
    # pide el % y aplica a la cesta
        val, ok = QInputDialog.getDouble(self, 'Interés', 'Porcentaje (+/-):', 0.0, -100.0, 1000.0, 2)
        if not ok:
            return
        self._aplicar_interes_a_cesta(val)

    def _aplicar_interes_a_cesta(self, pct: float):
        try:
            self._interes_pct = float(pct or 0.0)
        except Exception:
            self._interes_pct = 0.0
        self.actualizar_total()
        try:
            if hasattr(self, 'rb_tarjeta') and self.rb_tarjeta.isChecked() and int(self.spin_cuotas.value() or 0) > 0:
                self._update_cuota_label(int(self.spin_cuotas.value()))
        except Exception:
            pass
        
    def _aplicar_descuento_dialog(self):
        # pide el % y aplica a la cesta
        val, ok = QInputDialog.getDouble(self, 'Descuento', 'Porcentaje (0–100):', 0.0, 0.0, 100.0, 2)
        if not ok:
            return
        self._aplicar_descuento_a_cesta(val)

    def _aplicar_descuento_a_cesta(self, pct: float):
        try:
            self._descuento_pct = float(pct or 0.0)
        except Exception:
            self._descuento_pct = 0.0
        self.actualizar_total()
        try:
            if hasattr(self, 'rb_tarjeta') and self.rb_tarjeta.isChecked() and int(self.spin_cuotas.value() or 0) > 0:
                self._update_cuota_label(int(self.spin_cuotas.value()))
        except Exception:
            pass
        
            
    def _revertir_interes_en_cesta(self):
        self._interes_pct = 0.0
        self.actualizar_total()
        try:
            if hasattr(self, 'rb_tarjeta') and self.rb_tarjeta.isChecked() and int(self.spin_cuotas.value() or 0) > 0:
                self._update_cuota_label(int(self.spin_cuotas.value()))
        except Exception:
            pass
    

    def _refrescar_interes_btn(self):
    # mostrar botón "Interés %" solo si Tarjeta y cuotas > 1
        visible = self.rb_tarjeta.isChecked() and self.spin_cuotas.value() > 1
        if hasattr(self, 'btn_interes'):
            self.btn_interes.setVisible(visible)
            
            
    def _on_pago_method_changed(self, checked):
        is_tarj = bool(getattr(self, 'rb_tarjeta', None) and self.rb_tarjeta.isChecked())

        if hasattr(self, 'spin_cuotas'):
            self.spin_cuotas.setEnabled(is_tarj)
        if hasattr(self, 'cuota_label'):
            self.cuota_label.setVisible(is_tarj)

        # Si se seleccionó tarjeta, abrir diálogo configuración
        # NUEVO: Solo abrir si NO hay datos configurados ya
        if is_tarj and checked:
            # Solo abrir diálogo si no está configurado
            if not (hasattr(self, '_datos_tarjeta') and self._datos_tarjeta):
                self._abrir_dialogo_tarjeta()
        elif not is_tarj:
            # Si se deseleccionó tarjeta, limpiar datos
            if hasattr(self, 'spin_cuotas'):
                self.spin_cuotas.setValue(1)
            if hasattr(self, '_datos_tarjeta'):
                self._datos_tarjeta = None

        if is_tarj:
            try:
                self._update_cuota_label(int(self.spin_cuotas.value() or 1))
            except Exception:
                self.cuota_label.clear()
        self._refrescar_interes_btn()

    def _abrir_dialogo_tarjeta(self):
        """Abre el diálogo para configurar pago con tarjeta."""
        from app.gui.dialogs import PagoTarjetaDialog

        # Obtener total actual
        try:
            txt = (self.lbl_total.text() or "").replace("Total:", "").replace("$", "").strip()
            total = float(txt.replace(",", ""))
        except Exception:
            total = 0.0

        dlg = PagoTarjetaDialog(total_actual=total, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            datos = dlg.get_datos()
            if datos:
                # Guardar datos para usar al finalizar venta
                self._datos_tarjeta = datos

                # Actualizar UI
                self.spin_cuotas.setValue(datos["cuotas"])

                # Aplicar interés si hay
                if datos["interes_pct"] > 0:
                    self._aplicar_interes_a_cesta(datos["interes_pct"])

                logger.info(f"[Tarjeta] Configurado: {datos['cuotas']} cuotas, {datos['interes_pct']}% interés, {datos['tipo_comprobante']}")
                if datos["cuit_cliente"]:
                    logger.info(f"[Tarjeta] CUIT cliente: {datos['cuit_cliente']}")
        else:
            # Usuario canceló, volver a efectivo
            self.rb_efectivo.setChecked(True)

    def _update_cuota_label(self, cuotas):
        try:
            txt = (self.lbl_total.text() or "").replace("Total:", "").replace("$", "").strip()
            total = float(txt.replace(",", ""))
            if cuotas:
                self.cuota_label.setText(f"$ {total / float(cuotas):.2f}")
            else:
                self.cuota_label.clear()
        except Exception:
            self.cuota_label.clear()
        self._refrescar_interes_btn()
        
        
    #----Finalizar venta e impresión
    
    def finalizar_venta(self):
        # Recalcula totales / interés antes de cualquier cosa
        self.actualizar_total()

        if self.table_cesta.rowCount() == 0:
            QMessageBox.warning(self, 'Cesta vacía', 'Agrega al menos un producto.')
            return

        # ¿Efectivo o Tarjeta?
        forma_combo = (self.cb_forma_pago.currentText() if hasattr(self, 'cb_forma_pago') else '').lower()
        is_efectivo = (forma_combo.startswith('efectivo') or
                    (hasattr(self, 'rb_efectivo') and self.rb_efectivo.isChecked()))

        pagado = None
        vuelto = None
        total_actual = float(getattr(self, "_total_actual", 0.0))

        # Variables para AFIP en efectivo
        efectivo_emitir_afip = False
        efectivo_tipo_cbte = None
        efectivo_cuit_cliente = ""

        if is_efectivo:
            # Usar el nuevo diálogo de pago en efectivo
            from app.gui.dialogs import PagoEfectivoDialog

            dlg = PagoEfectivoDialog(total_actual=total_actual, parent=self)
            if dlg.exec_() != QDialog.Accepted:
                return  # cancelado

            datos_efectivo = dlg.get_datos()
            if not datos_efectivo:
                return

            pagado = datos_efectivo["abonado"]
            vuelto = datos_efectivo["vuelto"]
            efectivo_emitir_afip = datos_efectivo["emitir_afip"]
            efectivo_tipo_cbte = datos_efectivo["tipo_comprobante"]
            efectivo_cuit_cliente = datos_efectivo["cuit_cliente"]

            self._ultimo_pagado = pagado
            self._ultimo_vuelto = vuelto
            self.vuelto = vuelto
        else:
            self.vuelto = 0.0

        modo = 'Efectivo' if is_efectivo else 'Tarjeta'
        cuotas = self.spin_cuotas.value() if (hasattr(self, 'rb_tarjeta') and self.rb_tarjeta.isChecked()) else None
        
        
        # Crear venta (total=0 en BD inicialmente)
        venta = self.venta_repo.crear_venta(
            sucursal=self.sucursal,
            modo_pago=modo,
            cuotas=cuotas
        )

        # Agregar ítems
        for r in range(self.table_cesta.rowCount()):
            # Validar que las celdas existan antes de acceder
            item_codigo = self.table_cesta.item(r, 0)
            item_cant = self.table_cesta.item(r, 2)
            item_pu = self.table_cesta.item(r, 3)

            if not item_codigo or not item_cant or not item_pu:
                continue  # Saltar filas con celdas vacías

            codigo = item_codigo.text().strip()
            if not codigo:
                continue  # Saltar si no hay código

            # Conversiones seguras con try-except
            try:
                cant = int(float(item_cant.text().replace(",", ".").strip() or "0"))
                pu = float(item_pu.text().replace("$", "").replace(",", ".").strip() or "0")
            except (ValueError, AttributeError):
                continue  # Saltar filas con valores inválidos

            if cant <= 0 or pu < 0:
                continue  # Saltar cantidades inválidas

            self.venta_repo.agregar_item(venta.id, codigo, cant, pu)

        # Total en BD y commit
        total_bd = self.venta_repo.actualizar_total(venta.id)
        try:
            venta.subtotal_base   = float(getattr(self, "_subtotal_base", 0.0) or 0.0)
            venta.interes_pct     = float(getattr(self, "_interes_pct", 0.0) or 0.0)
            venta.interes_monto   = float(getattr(self, "_interes_monto", 0.0) or 0.0)
            venta.descuento_pct   = float(getattr(self, "_descuento_pct", 0.0) or 0.0)
            venta.descuento_monto = float(getattr(self, "_descuento_monto", 0.0) or 0.0)
            # El total final mostrado al usuario (subtotal - desc + interés)
            venta.total           = float(getattr(self, "_total_actual", 0.0) or 0.0)
            self.session.commit()
        except Exception:
            # si prefieres mantener el patrón del repo
            try:
                self.venta_repo.commit()
            except Exception:
                pass
        try:
            if is_efectivo and pagado is not None:
                try:
                    # Guardar directo en el modelo si soporta los campos
                    venta.pagado = float(pagado)
                    venta.vuelto = float(vuelto or 0.0)
                    self.session.commit()
                except Exception:
                    # Fallback a método del repo si existe
                    try:
                        self.venta_repo.actualizar_efectivo(venta.id, float(pagado), float(vuelto or 0.0))
                        self.venta_repo.commit()
                    except Exception:
                        pass
        except Exception:
            pass

        # Guardar Pagado/Vuelto para el resumen
        if pagado is not None:
            if not hasattr(self, "_pagos_efectivo"):
                self._pagos_efectivo = {}
            key = str(getattr(venta, 'numero_ticket', venta.id))
            self._pagos_efectivo[key] = (pagado, vuelto)

        if modo == 'Efectivo':
            QMessageBox.information(self, 'Vuelto', f'Vuelto: ${self.vuelto:.2f}')

        # Integración AFIP / ARCA (solo si está habilitada en Configuración)
        # Para efectivo con AFIP, pasar los datos específicos
        if modo == 'Efectivo' and efectivo_emitir_afip:
            self._afip_emitir_si_corresponde(
                venta, modo,
                forzar_afip=True,
                tipo_cbte=efectivo_tipo_cbte,
                cuit_cliente=efectivo_cuit_cliente
            )
        else:
            self._afip_emitir_si_corresponde(venta, modo)

        # Guardar último id para exportar a PNG
        self._last_venta_id = venta.id

        # --- ¿Enviar el ticket por WhatsApp Web en lugar de imprimir? ---
        resp = QMessageBox.question(
            self, "Ticket",
            "¿Enviar el ticket por WhatsApp Web en lugar de imprimir?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        self._last_venta_id = venta.id  # para export/share posteriores
        if resp == QMessageBox.Yes:
            # genera un PDF temporal y abre WhatsApp Web
            try:
                self.enviar_ticket_whatsapp()
            except Exception as e:
                QMessageBox.warning(self, "WhatsApp", f"No se pudo abrir WhatsApp Web:\n{e}")
        else:
            self.imprimir_ticket(venta.id)

        # Limpiar UI
        self.nueva_venta()
        self.recargar_ventas_dia()
        if hasattr(self, 'historial') and self.historial is not None:
            self.historial.recargar_historial()
    
    
    def _afip_emitir_si_corresponde(self, venta, modo_pago: str, *,
                                      forzar_afip: bool = False,
                                      tipo_cbte: str = None,
                                      cuit_cliente: str = ""):
        """
        Integra con AFIP/ARCA vía AfipSDK si:
          - está habilitado en Configuración → Facturación
          - y (por defecto) la venta es con tarjeta.
          - O si forzar_afip=True (para efectivo con factura)
        No lanza excepciones hacia afuera: cualquier error se avisa pero no rompe la venta.

        Parámetros opcionales:
          - forzar_afip: Si True, emite factura aunque sea efectivo
          - tipo_cbte: Tipo de comprobante (FACTURA_A, FACTURA_B, etc.)
          - cuit_cliente: CUIT del cliente (requerido para Factura A)
        """
        try:
            from app.config import load as _load_cfg
            cfg = _load_cfg()
        except Exception:
            # Si no se puede leer config, no hacemos nada
            return

        fisc = (cfg.get("fiscal") or {})
        if not fisc.get("enabled", False):
            return

        # Por defecto solo tarjeta; si desmarcas la opción, también facturaría efectivo
        # EXCEPCIÓN: si forzar_afip=True, siempre emitir
        only_card = bool(fisc.get("only_card", True))
        if only_card and modo_pago.lower() != "tarjeta" and not forzar_afip:
            return

        # Intentamos construir los ítems de forma normalizada
        try:
            items = self._items_para_ticket(venta.id)
        except Exception:
            items = []

        # Cliente AfipSDK
        try:
            from app.afip_integration import crear_cliente_afip
            cfg = _load_cfg()
            # CORRECCIÓN: La sección se llama "fiscal" no "afip"
            fiscal_config = cfg.get("fiscal", {}).copy()  # Copiar para no modificar original

            # Mapear access_token desde afipsdk.api_key si existe
            if "afipsdk" in fiscal_config and "api_key" in fiscal_config["afipsdk"]:
                fiscal_config["access_token"] = fiscal_config["afipsdk"]["api_key"]

            # Mapear environment desde mode (test -> dev, prod -> prod)
            mode = fiscal_config.get("mode", "test")
            if mode == "test":
                fiscal_config["environment"] = "dev"
            elif mode == "prod":
                fiscal_config["environment"] = "prod"
            else:
                fiscal_config["environment"] = "dev"  # Fallback

            # Mapear only_card_payments desde only_card
            if "only_card" in fiscal_config:
                fiscal_config["only_card_payments"] = fiscal_config["only_card"]

            client = crear_cliente_afip(fiscal_config)
            if not client:
                return  # AFIP deshabilitado
        except Exception as e:
            print(f"[AFIP] No se pudo inicializar AfipSDKClient: {e}", file=sys.stderr)
            return

        # Calcular total, subtotal e IVA para AFIP
        total = float(getattr(venta, 'total', 0.0) or 0.0)
        # Asumimos IVA 21% (puedes ajustar según tu lógica)
        iva_rate = 0.21
        subtotal = round(total / (1.0 + iva_rate), 2)
        iva = round(total - subtotal, 2)

        # Debug: Mostrar configuración que se está usando
        print(f"[AFIP DEBUG] Config: enabled={fiscal_config.get('enabled')}, "
              f"environment={fiscal_config.get('environment')}, "
              f"cuit={fiscal_config.get('cuit')}, "
              f"has_api_key={bool(fiscal_config.get('access_token'))}")

        # Determinar tipo de comprobante y CUIT cliente
        # Prioridad: parámetros explícitos > _datos_tarjeta > default
        tipo_comprobante_final = tipo_cbte
        cuit_cliente_final = cuit_cliente

        if not tipo_comprobante_final and hasattr(self, '_datos_tarjeta') and self._datos_tarjeta:
            tipo_comprobante_final = self._datos_tarjeta.get("tipo_comprobante")
            cuit_cliente_final = self._datos_tarjeta.get("cuit_cliente", "")

        print(f"[AFIP DEBUG] Tipo comprobante: {tipo_comprobante_final}, CUIT cliente: {cuit_cliente_final}")

        # Emitir factura
        try:
            # Por ahora emitimos Factura B (default)
            # TODO: Agregar soporte para Factura A cuando se necesite
            response = client.emitir_factura_b(
                items=items,
                total=total,
                subtotal=subtotal,
                iva=iva
            )
        except Exception as e:
            print(f"[AFIP] Error al emitir factura: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()

            # Mensaje de error más específico según el tipo
            error_msg = str(e)
            if "400" in error_msg or "Bad Request" in error_msg:
                error_detail = (
                    "Error 400: Bad Request\n\n"
                    "Posibles causas:\n"
                    "• API Key inválida o sin permisos\n"
                    "• CUIT no registrado con esta API Key\n"
                    "• Modo (test/prod) incorrecto\n\n"
                    f"Verifica la configuración en:\n"
                    f"Configuración → Facturación Electrónica\n\n"
                    f"CUIT actual: {fiscal_config.get('cuit')}\n"
                    f"Modo: {fiscal_config.get('mode')}\n\n"
                    f"Error técnico: {error_msg}"
                )
            elif "401" in error_msg or "Unauthorized" in error_msg:
                error_detail = (
                    "Error 401: No autorizado\n\n"
                    "La API Key es inválida o ha expirado.\n"
                    "Verifica en Configuración → Facturación Electrónica"
                )
            else:
                error_detail = f"Error al emitir comprobante electrónico:\n\n{error_msg}"

            # Guardar el error en la venta para poder reintentar después
            try:
                venta.afip_error = f"Error AFIP: {error_msg[:500]}"  # Limitar longitud
                self.session.commit()
            except Exception:
                pass

            QMessageBox.warning(
                self,
                "AFIP - Error",
                f"{error_detail}\n\n"
                "La venta fue registrada pero SIN comprobante electrónico.\n"
                "Puedes reintentar desde el historial de ventas."
            )
            return

        # Guardar CAE si fue exitoso
        if response.success:
            venta.afip_cae = response.cae
            venta.afip_cae_vencimiento = response.cae_vencimiento
            venta.afip_numero_comprobante = response.numero_comprobante
            try:
                self.session.commit()
            except Exception as e:
                print(f"[AFIP] Error al guardar CAE: {e}", file=sys.stderr)

        # Mostramos feedback al usuario
        try:
            if response.success:
                # Limpiar cualquier error previo
                venta.afip_error = None
                try:
                    self.session.commit()
                except Exception:
                    pass

                QMessageBox.information(
                    self,
                    "AFIP - Factura Electrónica",
                    "Comprobante electrónico emitido correctamente.\n\n"
                    f"CAE: {response.cae}\n"
                    f"Vencimiento: {response.cae_vencimiento}\n"
                    f"Número de comprobante: {response.numero_comprobante}"
                )
            else:
                # Guardar el error para poder reintentar después
                error_msg = response.error_message or "Error desconocido de AFIP"
                try:
                    venta.afip_error = f"AFIP rechazó: {error_msg[:500]}"
                    self.session.commit()
                except Exception:
                    pass

                QMessageBox.warning(
                    self,
                    "AFIP - Error",
                    "No se pudo emitir el comprobante electrónico.\n\n"
                    f"Detalle:\n{error_msg}\n\n"
                    "La venta fue registrada pero SIN comprobante electrónico.\n"
                    "Puedes reintentar desde el historial de ventas."
                )
        except Exception as e:
            print(f"[AFIP] Error mostrando mensaje AFIP: {e}", file=sys.stderr)
        
            
    def _items_para_ticket(self, venta_id):
        """
        Devuelve una lista de ítems normalizados con código/nombre/cantidad/precio_unitario.
        1º usa la cesta visible (si existe), 2º lee BD con múltiples "fallbacks".
        """
        items = []

        # 1) Si la cesta está visible y con filas, úsala (garantiza que haya código/nombre)
        if getattr(self, "table_cesta", None) and self.table_cesta.rowCount() > 0:
            for r in range(self.table_cesta.rowCount()):
                codigo = (self.table_cesta.item(r, 0).text() if self.table_cesta.item(r, 0) else "") or ""
                nombre = (self.table_cesta.item(r, 1).text() if self.table_cesta.item(r, 1) else "") or ""
                try:    cant = float(self.table_cesta.item(r, 2).text())
                except: cant = 1.0
                try:
                    punit = float(str(self.table_cesta.item(r, 3).text()).replace("$","").strip())
                except:
                    punit = 0.0
                items.append({"codigo": codigo, "nombre": nombre, "cantidad": cant, "precio_unitario": punit})
            return items

        # 2) Fallback BD
        try:
            rows = self.venta_repo.listar_items(venta_id)
        except Exception:
            rows = self.session.query(VentaItem).filter_by(venta_id=venta_id).all()

        for it in rows:
            # muchos nombres posibles de atributos…
            codigo = (
                getattr(it, 'codigo', None) or
                getattr(it, 'codigo_barra', None) or
                getattr(it, 'cod_barra', None) or
                getattr(it, 'codigobarra', None) or
                ""
            )
            nombre = getattr(it, 'nombre', None) or ""
            # si no hay relación cargada, intentar por producto_id
            if not (codigo and nombre):
                prod = getattr(it, 'producto', None)
                if not prod:
                    pid = getattr(it, 'producto_id', None) or getattr(it, 'id_producto', None)
                    if pid:
                        try:
                            prod = self.session.query(Producto).get(pid)
                        except Exception:
                            prod = None
                if prod:
                    if not codigo:
                        codigo = getattr(prod, 'codigo_barra', '') or codigo
                    if not nombre:
                        nombre = getattr(prod, 'nombre', '') or nombre

            try:    cant = float(getattr(it, 'cantidad', 1) or 1)
            except: cant = 1.0

            try:
                punit = float(
                    getattr(it, 'precio', getattr(it, 'precio_unit', getattr(it, 'precio_unitario', 0.0))) or 0.0
                )
            except Exception:
                punit = 0.0

            items.append({"codigo": codigo or "", "nombre": nombre or "", "cantidad": cant, "precio_unitario": punit})

        return items
    
    
    def imprimir_ticket(self, venta_id):
        v = self.venta_repo.obtener(venta_id)
        try:
            # 1) Ítems: usar helper si existe; si no, cesta visible -> BD
            items = []
            try:
                if hasattr(self, "_items_para_ticket") and callable(self._items_para_ticket):
                    items = self._items_para_ticket(venta_id)
            except Exception:
                items = []

            if not items:
                if getattr(self, "table_cesta", None) and self.table_cesta.rowCount() > 0:
                    for r in range(self.table_cesta.rowCount()):
                        codigo = (self.table_cesta.item(r, 0).text() if self.table_cesta.item(r, 0) else "") or ""
                        nombre = (self.table_cesta.item(r, 1).text() if self.table_cesta.item(r, 1) else "") or ""
                        try:    cant = float(self.table_cesta.item(r, 2).text())
                        except: cant = 1.0
                        try:    punit = float(str(self.table_cesta.item(r, 3).text()).replace("$", "").strip())
                        except: punit = 0.0
                        items.append({
                            "codigo": codigo,
                            "nombre": nombre,
                            "cantidad": cant,
                            "precio_unitario": punit,
                        })
                else:
                    # Fallback a repositorio o BD
                    try:
                        rows = self.venta_repo.listar_items(venta_id)
                    except Exception:
                        try:
                            from app.models import VentaItem  # por si no estaba importado en el módulo
                        except Exception:
                            VentaItem = None
                        rows = self.session.query(VentaItem).filter_by(venta_id=venta_id).all() if VentaItem else []
                    for it in rows:
                        # Obtener nombre: primero intentar it.nombre, luego it.producto.nombre
                        nombre = getattr(it, "nombre", "") or ""
                        if not nombre:
                            prod_obj = getattr(it, "producto", None)
                            if prod_obj:
                                nombre = getattr(prod_obj, "nombre", "") or ""

                        # Obtener código: intentar desde it o desde it.producto
                        codigo = getattr(it, "codigo", None) or getattr(it, "codigo_barra", None) or ""
                        if not codigo:
                            prod_obj = getattr(it, "producto", None)
                            if prod_obj:
                                codigo = getattr(prod_obj, "codigo", "") or getattr(prod_obj, "codigo_barra", "") or ""

                        items.append({
                            "codigo": codigo,
                            "nombre": nombre,
                            "cantidad": float(getattr(it, "cantidad", 1) or 1),
                            "precio_unitario": float(getattr(it, "precio", getattr(it, "precio_unitario", 0.0)) or 0.0),
                        })

            # 2) Datos extra para el dibujante
            v._ticket_items = items
            v.subtotal_base = getattr(self, "_subtotal_base", None)
            v.descuento_monto = getattr(self, "_descuento_monto", None)
            v.total           = getattr(self, "_total_actual", None)
            v.interes_monto = getattr(self, "_interes_monto", None)
            v.pagado        = getattr(self, "_ultimo_pagado", None)
            v.vuelto        = getattr(self, "_ultimo_vuelto", None)

            # cuotas (para tarjeta): intenta tomar de la venta, o de posibles atributos del flujo
            try:
                v.cuotas = int(
                    (getattr(v, "cuotas", None)
                    or getattr(self, "_cuotas", None)
                    or getattr(self, "cuotas", None)
                    or 0) or 0
                )
            except Exception:
                v.cuotas = getattr(v, "cuotas", 0) or 0

            # 3) Imprimir con el helper unificado
            from app.gui.ventas_helpers import imprimir_ticket as _print
            _print(v, self.sucursal, self.direcciones, parent=self, preview=False)

        except Exception as e:
            QMessageBox.warning(self, "Impresión", f"No se pudo imprimir:\n{e}")
    
    


    def _write_ticket_pdf(self, venta_id, path_pdf, *, extra_bottom_mm: float = 0.0):

        """Escribe el ticket a PDF (ancho 75 mm, alto dinámico)."""
        from PyQt5.QtGui import QPdfWriter, QPainter
        from PyQt5.QtCore import QSizeF, QMarginsF, QSize
        from app.gui.ventas_helpers import _draw_ticket, _compute_ticket_height_mm

        v = self.venta_repo.obtener(venta_id)
        v._ticket_items = self._items_para_ticket(venta_id)
        v.subtotal_base = getattr(self, "_subtotal_base", None)
        v.interes_monto = getattr(self, "_interes_monto", None)
        v.pagado        = getattr(self, "_ultimo_pagado", None)
        v.vuelto        = getattr(self, "_ultimo_vuelto", None)

        pdf = QPdfWriter(path_pdf)
        pdf.setResolution(300)

        width_mm = 75.0
        height_mm = _compute_ticket_height_mm(v, pdf, width_mm=width_mm)
        pdf.setPageSizeMM(QSizeF(width_mm, height_mm + 10.0))  # 1 cm debajo del footer

        p = QPainter(pdf)
        try:
            _draw_ticket(p, QRect(0, 0, pdf.width(), pdf.height()), None,
                        v, self.sucursal, self.direcciones, width_mm=width_mm)
        finally:
            p.end()



    def exportar_ticket_pdf(self):
        """Diálogo de guardado + escritura PDF 80 mm."""
        from PyQt5.QtWidgets import QFileDialog, QMessageBox
        vid = getattr(self, "_last_venta_id", None)
        if not vid:
            QMessageBox.information(self, "PDF", "No hay una venta reciente para exportar.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Guardar ticket como PDF", "ticket.pdf", "PDF (*.pdf)")
        if not path:
            return
        try:
            self._write_ticket_pdf(vid, path)
            self._last_ticket_pdf_path = path
            QMessageBox.information(self, "PDF", f"Guardado: {path}")
        except Exception as e:
            QMessageBox.warning(self, "PDF", f"No se pudo exportar:\n{e}")
        
    def enviar_ticket_whatsapp(self):
        """
        Abre WhatsApp Web con un texto prellenado y abre el Explorador
        con el PDF del ticket SELECCIONADO para arrastrarlo al chat.
        """
        import tempfile, os, webbrowser, urllib.parse, sys, subprocess
        from PyQt5.QtWidgets import QMessageBox

        vid = getattr(self, "_last_venta_id", None)
        if not vid:
            QMessageBox.information(self, "WhatsApp", "No hay una venta reciente.")
            return

        # 1) Generar un PDF temporal (80 mm) reutilizando el writer robusto
        fd, tmp_path = tempfile.mkstemp(prefix="ticket_", suffix=".pdf")
        os.close(fd)
        self._write_ticket_pdf(vid, tmp_path)         # <- genera el PDF
        self._last_ticket_pdf_path = tmp_path         # <- guardamos por si hace falta de nuevo

        # 2) Abrir WhatsApp Web con mensaje prellenado
        msg = urllib.parse.quote("Te envío el ticket de tu compra. Adjuntaré el PDF en el chat.")
        webbrowser.open(f"https://web.whatsapp.com/send?text={msg}")

        # 3) Abrir EXPLORER seleccionando el archivo (Windows)
        try:
            if sys.platform.startswith("win"):
                # Explorer con el archivo resaltado
                subprocess.run(['explorer', f'/select,"{tmp_path}"'], shell=True)
            else:
                # Linux/Mac: abrir carpeta
                folder = os.path.dirname(tmp_path)
                if sys.platform == "darwin":
                    subprocess.run(["open", folder])
                else:
                    subprocess.run(["xdg-open", folder])
        except Exception:
            # Fallback: al menos abrir la carpeta
            try:
                os.startfile(os.path.dirname(tmp_path))
            except Exception:
                pass

        # (Opcional) Avisar la ruta exacta por si el usuario la quiere copiar
        try:
            QMessageBox.information(self, "WhatsApp",
                f"Ticket generado en:\n{tmp_path}\n\n"
                "Se abrió el Explorador con el archivo seleccionado.")
        except Exception:
            pass
        
        
    #--- Ventas del día / Acciones por ID
    
    def recargar_ventas_dia(self):
        """
        Recarga en memoria (y si existe, en la tabla) las ventas del día.
        Tolerante a errores para no romper la app.
        """
        from datetime import datetime, timedelta
        try:
            if not hasattr(self, 'venta_repo') or self.venta_repo is None:
                self._ventas_dia = []
                return

            hoy = datetime.now().date()
            ventas = []

            # 1) Método del repositorio si existe
            if hasattr(self.venta_repo, 'listar_por_fecha'):
                try:
                    ventas = self.venta_repo.listar_por_fecha(hoy, getattr(self, 'sucursal', None))
                except Exception:
                    try:
                        ventas = self.venta_repo.listar_por_fecha(hoy)
                    except Exception:
                        ventas = []

            # 2) Fallback directo con session
            if not ventas and hasattr(self, 'session'):
                try:
                    from app.models import Venta
                    inicio = datetime.combine(hoy, datetime.min.time())
                    fin = datetime.combine(hoy + timedelta(days=1), datetime.min.time())
                    q = self.session.query(Venta).filter(Venta.fecha >= inicio, Venta.fecha < fin)
                    if getattr(self, 'sucursal', None):
                        q = q.filter(Venta.sucursal == self.sucursal)
                    ventas = q.order_by(Venta.fecha.desc()).all()
                except Exception:
                    ventas = []

            self._ventas_dia = ventas

            # 3) Poblar tabla si existe
            if not hasattr(self, 'table_ventas_dia') or self.table_ventas_dia is None:
                return

            from PyQt5.QtWidgets import QTableWidgetItem, QWidget, QHBoxLayout, QPushButton
            tbl = self.table_ventas_dia
            tbl.setUpdatesEnabled(False)                 # ← DESACTIVO repaints
            try:
                tbl.setRowCount(0)
                for v in ventas:
                    row = tbl.rowCount()
                    tbl.insertRow(row)

                    nro = str(getattr(v, 'numero_ticket', '') or getattr(v, 'id', ''))
                    fch = getattr(v, 'fecha', None)
                    hora = fch.strftime('%H:%M') if fch else ''

                    try:
                        tot = float(getattr(v, 'total', 0.0))
                    except Exception:
                        tot = 0.0
                    interes_m = float(getattr(v, 'interes_monto', 0.0) or 0.0)
                    descto_m  = float(getattr(v, 'descuento_monto', 0.0) or 0.0)
                    forma_raw = (getattr(v, 'forma_pago', None) or getattr(v, 'modo_pago', None) or getattr(v, 'modo', None) or '').lower()
                    forma = 'Tarjeta' if forma_raw.startswith('tarj') else 'Efectivo'

                    cuotas = int(getattr(v, 'cuotas', 0) or 0)
                    monto_cuota = (tot / cuotas) if (forma == 'Tarjeta' and cuotas) else 0.0

                    pagado = '-'
                    vuelto = '-'
                    if forma == 'Efectivo':
                        pv = getattr(v, 'pagado', None)
                        vv = getattr(v, 'vuelto', None)
                        if pv is not None:
                            pagado = f"${float(pv):.2f}"
                        if vv is not None:
                            vuelto = f"${float(vv):.2f}"
                        elif hasattr(self, "_pagos_efectivo") and nro in self._pagos_efectivo:
                            pv, vv = self._pagos_efectivo[nro]
                            pagado = f"${float(pv):.2f}"
                            vuelto = f"${float(vv):.2f}"

                    data = [
                        nro,
                        hora,
                        f"${tot:.2f}",
                        forma,
                        (str(cuotas) if cuotas else '-'),
                        f"${interes_m:.2f}",            # ← NUEVA COLUMNA
                        f"${descto_m:.2f}",             # ← NUEVA COLUMNA
                        (f"${monto_cuota:.2f}" if monto_cuota else '-'),
                        pagado,
                        vuelto
                    ]
                    for c, val in enumerate(data):
                        it = QTableWidgetItem(val)
                        it.setTextAlignment(Qt.AlignCenter)
                        tbl.setItem(row, c, it)

                    # --- Acciones (DENTRO del for) ---
                    vid = getattr(v, 'id', None)
                    actions = QWidget()
                    ah = QHBoxLayout(actions)
                    ah.setContentsMargins(0, 0, 0, 0)
                    ah.setSpacing(6)
                    ah.setAlignment(Qt.AlignCenter)
                    row_h = self.table_ventas_dia.verticalHeader().defaultSectionSize()
                    btn_sz = max(28, row_h - 8)
                    
                    
                    def _mk_btn(ico_name, tip, slot):
                        b = QPushButton()
                        b.setProperty("role", "cell")      # usa el CSS centralizado
                        b.setIcon(icon(ico_name))
                        b.setToolTip(tip)
                        b.setFixedSize(btn_sz, btn_sz)     # cuadrado y sin cortarse
                        b.setIconSize(QSize(btn_sz - 12, btn_sz - 12))
                        b.setFocusPolicy(Qt.NoFocus)
                        b.setStyleSheet("")  # deja el estilo al CSS global
                        b.clicked.connect(slot)
                        return b

                    btn_imp = _mk_btn('print.svg', 'Reimprimir ticket',
                                    lambda _, _vid=vid: self._reimprimir_ticket_by_id(_vid))
                    ah.addWidget(btn_imp, alignment=Qt.AlignCenter)

                    btn_wa = _mk_btn('wtsp.svg', 'Enviar por WhatsApp Web',
                                    lambda _, _vid=vid: self._enviar_ticket_whatsapp_by_id(_vid))
                    ah.addWidget(btn_wa, alignment=Qt.AlignCenter)

                    if getattr(self, 'es_admin', False):
                        btn_del = _mk_btn('delete.svg', 'Eliminar venta',
                                        lambda _, _vid=vid: self._eliminar_venta_by_id(_vid))
                        ah.addWidget(btn_del, alignment=Qt.AlignCenter)

                    tbl.setItem(row, 10, QTableWidgetItem(""))
                    tbl.setCellWidget(row, 10, actions)
            finally:
                tbl.setUpdatesEnabled(True)              # ← SIEMPRE reactivar
        except Exception as e:
            logger.warning(f"[WARN] recargar_ventas_dia: {e}")
            
            
    def _reimprimir_venta_seleccionada(self):
        itms = self.table_ventas_dia.selectedItems()
        if not itms:
            QMessageBox.information(self, "Reimprimir", "Selecciona una fila de la lista.")
            return
        row = itms[0].row()
        nro_txt = self.table_ventas_dia.item(row, 0).text().strip()  # col 0 = Nº Ticket
        if not nro_txt:
            QMessageBox.warning(self, "Reimprimir", "No se encontró el número de ticket en la fila.")
            return
        try:
            nro = int(nro_txt)
        except:
            nro = None

        venta = None
        if nro and hasattr(self.venta_repo, 'obtener_por_numero'):
            venta = self.venta_repo.obtener_por_numero(nro)
        if not venta:
            # como fallback, probar con id
            try:
                venta = self.venta_repo.obtener(int(nro_txt))
            except:
                venta = None
        if not venta:
            QMessageBox.warning(self, "Reimprimir", "No pude cargar la venta.")
            return

        # Guardar id por si quieren exportar PNG
        self._last_venta_id = venta.id
        # Imprimir
        self.imprimir_ticket(venta.id)
    
    
    
    
    def _enviar_ticket_whatsapp_by_id(self, venta_id):
        if not venta_id:
            QMessageBox.warning(self, "WhatsApp", "No se encontró la venta.")
            return
        self._last_venta_id = venta_id
        self.enviar_ticket_whatsapp()

    def _reimprimir_ticket_by_id(self, venta_id):
        if not venta_id:
            QMessageBox.warning(self, "Reimprimir", "No se encontró el ID de la venta.")
            return
        self._last_venta_id = venta_id  # útil para botón PNG
        self.imprimir_ticket(venta_id)
    
    #FUNCION ELIMINAR VENTA SOLO PARA ADMIN
    
    
    def _eliminar_venta_by_id(self, venta_id):
        if not venta_id:
            QMessageBox.warning(self, "Eliminar", "No se encontró el ID de la venta.")
            return
        if QMessageBox.question(
            self, "Eliminar venta",
            f"¿Seguro que deseas eliminar la venta #{venta_id}?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        ) != QMessageBox.Yes:
            return

        try:
            # Si el repositorio tiene helper:
            if hasattr(self.venta_repo, "eliminar"):
                self.venta_repo.eliminar(venta_id)
                self.venta_repo.commit()
            else:
                # Fallback directo
                v = self.session.query(Venta).get(venta_id)
                if v:
                    self.session.delete(v)
                    self.session.commit()
        except Exception as e:
            try:
                self.session.rollback()
            except Exception:
                pass
            QMessageBox.critical(self, "Eliminar", f"No se pudo eliminar la venta:\n{e}")
            return

        # Refrescos de UI
        try:
            self.recargar_ventas_dia()
        except Exception:
            pass
        try:
            if hasattr(self, 'historial') and self.historial is not None:
                self.historial.recargar_historial()
        except Exception:
            pass
        QMessageBox.information(self, "Eliminar", "La venta fue eliminada.")
        
    #---------Completer (autocompletar del buscador de ventas)
    
    def _setup_completer(self):
        try:
            comp, model = build_product_completer(self.session, self)
            self._completer = comp
            self._completer_model = model

            # ⬇⬇⬇ Asignar SÓLO al buscador de la pestaña Ventas
            ventas_input = getattr(self, 'input_venta_buscar', None)
            if ventas_input is not None:
                ventas_input.setCompleter(self._completer)
            from app.gui.common import LIVE_SEARCH_FONT_PT, LIVE_SEARCH_ROW_PAD, LIVE_SEARCH_MIN_WIDTH
            try:
                popup = self._completer.popup()   # QListView del completer
                # tamaño de fuente
                f = popup.font()
                f.setPointSize(LIVE_SEARCH_FONT_PT)
                popup.setFont(f)

                # padding por ítem y ancho mínimo
                popup.setStyleSheet(
                    f"QListView::item{{ padding:{LIVE_SEARCH_ROW_PAD}px {LIVE_SEARCH_ROW_PAD+2}px; }}"
                    f"QListView{{ min-width:{LIVE_SEARCH_MIN_WIDTH}px; }}"
                )
            except Exception:
                pass
            # Asegurarnos de NO poner completer en Productos
            prod_input = getattr(self, 'input_buscar', None)
            if prod_input is not None:
                prod_input.setCompleter(None)

        except Exception as e:
            logger.warning(f"[WARN] No se pudo crear el completer: {e}")

    def refrescar_completer(self):
        """Actualiza la lista del completer sólo cuando hay cambios reales en productos."""
        try:
            # Si aún no existe el completer, créalo
            if self._completer is None or self._completer_model is None:
                self._setup_completer()
                # si falló la creación, no seguimos
                if self._completer_model is None:
                    return

            # Recalcular la lista (código - nombre) desde el repo
            from app.repository import prod_repo
            repo = prod_repo(self.session)
            pares = repo.listar_codigos_nombres()  # [(codigo, nombre), ...]
            items = [f"{(c or '').strip()} - {(n or '').strip()}" for (c, n) in pares]

            # Actualizar el modelo sin reconstruir todo el completer
            self._completer_model.setStringList(items)

        except Exception as e:
            logger.warning(f"[WARN] refrescar_completer falló: {e}")
            
    def _force_complete(self, t):
    # actualiza prefijo y abre el popup
        try:
            self._comp.setCompletionPrefix(t)
            # posiciona el popup bajo el QLineEdit
            self._comp.complete()
        except Exception:
            pass
    
