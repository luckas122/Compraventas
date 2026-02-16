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
        lay.setContentsMargins(2, 0, 2, 0)
        lay.setSpacing(3)
        lay.setAlignment(Qt.AlignCenter)

        # Botón - (decrementar cantidad)
        btn_minus = QPushButton("−")
        btn_minus.setToolTip('Quitar 1 unidad')
        btn_minus.setFixedSize(24, 24)
        btn_minus.setFocusPolicy(Qt.NoFocus)
        btn_minus.clicked.connect(lambda _, row=r: self._cambiar_cantidad(row, -1))
        lay.addWidget(btn_minus)

        # Botón + (incrementar cantidad)
        btn_plus = QPushButton("+")
        btn_plus.setToolTip('Agregar 1 unidad')
        btn_plus.setFixedSize(24, 24)
        btn_plus.setFocusPolicy(Qt.NoFocus)
        btn_plus.clicked.connect(lambda _, row=r: self._cambiar_cantidad(row, +1))
        lay.addWidget(btn_plus)

        # Botón Editar cantidad
        btn_edit = QPushButton()
        btn_edit.setIcon(icon('edit.svg'))
        btn_edit.setToolTip('Editar cantidad')
        btn_edit.setFixedSize(24, 24)
        btn_edit.setFocusPolicy(Qt.NoFocus)
        btn_edit.clicked.connect(lambda _, row=r: self.editar_cantidad(row))
        lay.addWidget(btn_edit)

        # Botón Descuento (% por ítem)
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
        btn_del.setFocusPolicy(Qt.NoFocus)
        btn_del.clicked.connect(lambda _, row=r: self.quitar_producto(row))
        lay.addWidget(btn_del)

        row_h = self.table_cesta.verticalHeader().defaultSectionSize()
        btn_sz = max(28, row_h - 8)
    ##########
    # #garantiza que los botones no queden cortados
        self.table_cesta.setRowHeight(r, max(self.table_cesta.rowHeight(r), btn_sz + 8))
    ##########
        for b in (btn_minus, btn_plus, btn_edit, btn_desc, btn_del):
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
        
        
        
    def _cambiar_cantidad(self, row: int, delta: int):
        """Incrementa o decrementa la cantidad en la fila."""
        tbl = self.table_cesta
        if row >= tbl.rowCount():
            return

        try:
            cant_actual = float(tbl.item(row, 2).text())
        except Exception:
            cant_actual = 1.0

        nueva = cant_actual + delta
        if nueva < 1:
            # Si llega a 0, preguntar si quiere eliminar
            from PyQt5.QtWidgets import QMessageBox
            resp = QMessageBox.question(
                self, "Eliminar producto",
                "¿Quitar este producto de la cesta?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if resp == QMessageBox.Yes:
                self.quitar_producto(row)
            return

        tbl.item(row, 2).setText(str(int(nueva)))

        # Recalcular total de fila
        try:
            pu = float(str(tbl.item(row, 3).text()).replace("$", "").strip())
        except Exception:
            pu = 0.0
        total_fila = int(nueva) * pu

        it_total = tbl.item(row, 4)
        if it_total is None:
            it_total = QTableWidgetItem()
            tbl.setItem(row, 4, it_total)
        it_total.setText(f"{total_fila:.2f}")

        # Alinear
        for c in (2, 3, 4):
            it = tbl.item(row, c)
            if it:
                it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.actualizar_total()

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

        # Pedir nueva cantidad (unificado con getDouble para consistencia)
        nueva_cantidad, ok = QInputDialog.getDouble(
            self,
            "Editar Cantidad",
            "Nueva cantidad:",
            cantidad_actual,
            0.01,
            999999.0,
            2
        )

        if ok and nueva_cantidad > 0:
            # Actualizar cantidad
            self.table_cesta.item(row, 2).setText(f"{nueva_cantidad:.2f}")

            # Recalcular total de la fila
            try:
                precio_unit = float(self.table_cesta.item(row, 3).text())
                total_fila = nueva_cantidad * precio_unit
                self.table_cesta.item(row, 4).setText(f"{total_fila:.2f}")
            except Exception:
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
            # Si hay descuento por ítem, mostrar precio tachado + precio final
            try:
                if pct_item > 0:
                    pu_item.setText(f"{base:.2f} → {eff:.2f}")
                    pu_item.setToolTip(f"Precio base: ${base:.2f}\nDescuento: {pct_item:.1f}%\nPrecio final: ${eff:.2f}")
                else:
                    pu_item.setText(f"{base:.2f}")
                    pu_item.setToolTip("")
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
            
            
    # -----------------------------------------------------------------------
    # Atajos de cesta (invocados por ShortcutManager)
    # -----------------------------------------------------------------------

    def _shortcut_sumar_cesta(self):
        """Atajo +: incrementa cantidad del producto seleccionado en la cesta."""
        tbl = self.table_cesta
        row = tbl.currentRow()
        if row < 0:
            if tbl.rowCount() > 0:
                row = tbl.rowCount() - 1  # último producto
            else:
                return
        self._cambiar_cantidad(row, +1)

    def _shortcut_restar_cesta(self):
        """Atajo -: decrementa cantidad del producto seleccionado en la cesta."""
        tbl = self.table_cesta
        row = tbl.currentRow()
        if row < 0:
            if tbl.rowCount() > 0:
                row = tbl.rowCount() - 1
            else:
                return
        self._cambiar_cantidad(row, -1)

    def _shortcut_editar_cantidad_cesta(self):
        """Atajo C: editar cantidad del producto seleccionado en la cesta."""
        tbl = self.table_cesta
        row = tbl.currentRow()
        if row < 0:
            if tbl.rowCount() > 0:
                row = tbl.rowCount() - 1
            else:
                return
        self.editar_cantidad(row)

    def _shortcut_descuento_item_cesta(self):
        """Atajo X: aplicar descuento al producto seleccionado en la cesta."""
        tbl = self.table_cesta
        row = tbl.currentRow()
        if row < 0:
            if tbl.rowCount() > 0:
                row = tbl.rowCount() - 1
            else:
                return
        self._descuento_en_fila(row)

    # -----------------------------------------------------------------------
    # Metodos extraidos a mixins separados (se combinan via MainWindow):
    #
    #   ventas_ticket_mixin.py      -> VentasTicketMixin
    #     _items_para_ticket, imprimir_ticket, _write_ticket_pdf,
    #     exportar_ticket_pdf, enviar_ticket_whatsapp, recargar_ventas_dia,
    #     _reimprimir_venta_seleccionada, _enviar_ticket_whatsapp_by_id,
    #     _reimprimir_ticket_by_id, _eliminar_venta_by_id,
    #     _setup_completer, refrescar_completer, _force_complete
    #
    #   ventas_finalizacion_mixin.py -> VentasFinalizacionMixin
    #     _on_pago_method_changed, _abrir_dialogo_tarjeta,
    #     _update_cuota_label, finalizar_venta, _afip_emitir_si_corresponde
    # -----------------------------------------------------------------------
    
