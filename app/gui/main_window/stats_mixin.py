# app/gui/main_window/stats_mixin.py
# -*- coding: utf-8 -*-

from PyQt5.QtWidgets import QLabel
from PyQt5.QtCore import Qt


class StatsMixin:
    """
    Mixin para el tab de historial de ventas y estadísticas.
    - Expone: tab_historial(), _create_stats_tab(), _create_kpi_card(),
              _actualizar_estadisticas(), _generar_grafico_ventas(),
              _calcular_top_productos(), _generar_comparativa_sucursales(),
              _build_tpl_placeholder_panel()
    - Requiere:
        * self.venta_repo
        * self.direcciones
        * self.hist_desde, self.hist_hasta, self.hist_sucursal, self.hist_forma
        * self.recargar_historial(), self._hist_hoy(), self.exportar_historial_csv()
        * self._tpl_insert(s)
    """

    # ---------------- Historial de ventas ----------------
    def tab_historial(self):
        from PyQt5.QtWidgets import (
            QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
            QTableWidget, QHeaderView, QDateEdit, QComboBox, QTabWidget
        )
        from PyQt5.QtCore import Qt, QDate

        w = QWidget()
        main_lay = QVBoxLayout(w)

        # Tabs: Listado y Estadísticas
        tabs = QTabWidget()
        main_lay.addWidget(tabs)

        # TAB 1: LISTADO
        tab_listado = QWidget()
        lay = QVBoxLayout(tab_listado)

        # ----------------- Filtros -----------------
        row = QHBoxLayout()
        row.addWidget(QLabel("Desde:"))
        self.hist_desde = QDateEdit()
        self.hist_desde.setCalendarPopup(True)
        self.hist_desde.setDate(QDate.currentDate())
        row.addWidget(self.hist_desde)

        row.addWidget(QLabel("Hasta:"))
        self.hist_hasta = QDateEdit()
        self.hist_hasta.setCalendarPopup(True)
        self.hist_hasta.setDate(QDate.currentDate())
        row.addWidget(self.hist_hasta)

        row.addWidget(QLabel("Sucursal:"))
        self.hist_sucursal = QComboBox()
        self.hist_sucursal.addItem("Todas", None)
        for s in getattr(self, "direcciones", {}).keys():
            self.hist_sucursal.addItem(s, s)
        row.addWidget(self.hist_sucursal)

        row.addWidget(QLabel("Forma:"))
        self.hist_forma = QComboBox()
        self.hist_forma.addItem("Todas", None)
        self.hist_forma.addItem("Efectivo", "efectivo")
        self.hist_forma.addItem("Tarjeta", "tarjeta")
        row.addWidget(self.hist_forma)

        self.hist_buscar = QLineEdit()
        self.hist_buscar.setPlaceholderText("Nº de ticket o texto (producto)")
        row.addWidget(self.hist_buscar, stretch=1)

        btn_hoy = QPushButton("Hoy")
        btn_buscar = QPushButton("Buscar")
        btn_export = QPushButton("Exportar CSV")
        btn_hoy.clicked.connect(self._hist_hoy)
        btn_buscar.clicked.connect(self.recargar_historial)
        btn_export.clicked.connect(self.exportar_historial_csv)
        row.addWidget(btn_hoy)
        row.addWidget(btn_buscar)
        row.addWidget(btn_export)

        lay.addLayout(row)

        # ----------------- Tabla -----------------
        self.table_historial = QTableWidget(0, 11)
        self.table_historial.setHorizontalHeaderLabels([
            "Nº Ticket", "Fecha", "Sucursal", "Forma", "Cuotas",
            "Total", "Interés","Descuento", "Pagado", "Vuelto", "Acciones"
        ])
        self.table_historial.verticalHeader().setVisible(False)

        f = self.table_historial.font(); f.setPointSize(f.pointSize()+1)
        self.table_historial.setFont(f)

        hdr = self.table_historial.horizontalHeader()
        hf = hdr.font(); hf.setBold(True); hdr.setFont(hf)
        hdr.setSectionResizeMode(QHeaderView.Stretch)
        hdr.setSectionResizeMode(10, QHeaderView.ResizeToContents)  # acciones al ancho del contenido
        lay.addWidget(self.table_historial)

        # ----------------- Resumen -----------------
        self.lbl_hist_resumen = QLabel("0 ventas  |  Total: $0.00  |  Interés: $0.00  |  Efectivo: $0.00  |  Tarjeta: $0.00")
        lay.addWidget(self.lbl_hist_resumen)

        # Agregar tab de listado
        tabs.addTab(tab_listado, "Listado")

        # TAB 2: ESTADÍSTICAS
        try:
            tab_stats = self._create_stats_tab()
            tabs.addTab(tab_stats, "Estadísticas")
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error creando tab de estadísticas: {e}", exc_info=True)
            # Crear un tab de error simple
            error_widget = QWidget()
            error_layout = QVBoxLayout(error_widget)
            error_label = QLabel(f"Error al cargar estadísticas: {str(e)}")
            error_label.setStyleSheet("color: red; padding: 20px;")
            error_layout.addWidget(error_label)
            tabs.addTab(error_widget, "Estadísticas (Error)")

        # Cargar al abrir
        self.recargar_historial()
        return w

    def _create_stats_tab(self):
        """Crea el tab de estadísticas con gráficos y KPIs"""
        from PyQt5.QtWidgets import (
            QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox,
            QGridLayout, QPushButton, QScrollArea, QFrame
        )
        from PyQt5.QtCore import Qt

        container = QWidget()
        scroll = QScrollArea()
        scroll.setWidget(container)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        main_layout = QVBoxLayout(container)
        main_layout.setSpacing(16)

        # Banner de filtros activos
        self.stats_filtros_banner = QLabel()
        self.stats_filtros_banner.setStyleSheet("""
            QLabel {
                background-color: #e3f2fd;
                border: 1px solid #90caf9;
                border-radius: 4px;
                padding: 12px;
                font-size: 13px;
                color: #1565c0;
            }
        """)
        self.stats_filtros_banner.setWordWrap(True)
        main_layout.addWidget(self.stats_filtros_banner)

        # Botón para actualizar estadísticas
        btn_actualizar = QPushButton(" Actualizar Estadísticas")
        from app.gui.common import icon, ICON_SIZE
        btn_actualizar.setIcon(icon('refresh.svg'))
        btn_actualizar.setIconSize(ICON_SIZE)
        btn_actualizar.clicked.connect(self._actualizar_estadisticas)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(btn_actualizar)
        main_layout.addLayout(btn_layout)

        # KPIs principales (tarjetas)
        kpi_group = QGroupBox("Resumen del Período")
        kpi_layout = QGridLayout(kpi_group)
        kpi_layout.setSpacing(16)

        # Creamos labels para los KPIs
        self.kpi_total_ventas = self._create_kpi_card("Total Ventas", "$0.00", "#2e7d32")
        self.kpi_cant_ventas = self._create_kpi_card("Cantidad", "0", "#1976d2")
        self.kpi_promedio = self._create_kpi_card("Promedio", "$0.00", "#f57c00")
        self.kpi_interes_total = self._create_kpi_card("Interés Total", "$0.00", "#c62828")

        kpi_layout.addWidget(self.kpi_total_ventas, 0, 0)
        kpi_layout.addWidget(self.kpi_cant_ventas, 0, 1)
        kpi_layout.addWidget(self.kpi_promedio, 0, 2)
        kpi_layout.addWidget(self.kpi_interes_total, 0, 3)

        main_layout.addWidget(kpi_group)

        # Área para gráfico de ventas
        chart_group = QGroupBox("Ventas por Día")
        chart_layout = QVBoxLayout(chart_group)

        # Placeholder para el canvas de matplotlib
        self.stats_chart_container = QWidget()
        self.stats_chart_layout = QVBoxLayout(self.stats_chart_container)
        self.stats_chart_layout.setContentsMargins(0, 0, 0, 0)
        chart_layout.addWidget(self.stats_chart_container)

        main_layout.addWidget(chart_group)

        # Comparativa de sucursales (solo visible cuando se elige "Todas")
        self.stats_comparativa_group = QGroupBox("Comparativa por Sucursal")
        comparativa_layout = QVBoxLayout(self.stats_comparativa_group)

        self.stats_comparativa_container = QWidget()
        self.stats_comparativa_layout = QVBoxLayout(self.stats_comparativa_container)
        self.stats_comparativa_layout.setContentsMargins(0, 0, 0, 0)
        comparativa_layout.addWidget(self.stats_comparativa_container)

        main_layout.addWidget(self.stats_comparativa_group)
        self.stats_comparativa_group.setVisible(False)  # Oculto por defecto

        # Top productos
        top_group = QGroupBox("Productos Más Vendidos (Top 10)")
        top_layout = QVBoxLayout(top_group)

        from PyQt5.QtWidgets import QTableWidget, QHeaderView
        self.table_top_productos = QTableWidget(0, 4)
        self.table_top_productos.setHorizontalHeaderLabels([
            "Producto", "Código", "Cantidad Vendida", "Total Facturado"
        ])
        self.table_top_productos.verticalHeader().setVisible(False)

        hdr = self.table_top_productos.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)  # Nombre
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Código
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Cantidad
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Total

        self.table_top_productos.setMaximumHeight(350)
        top_layout.addWidget(self.table_top_productos)

        main_layout.addWidget(top_group)
        main_layout.addStretch()

        # Retornamos el scroll
        wrapper = QWidget()
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.addWidget(scroll)

        return wrapper

    def _create_kpi_card(self, title, value, color):
        """Crea una tarjeta KPI con estilo"""
        from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel
        from PyQt5.QtCore import Qt

        card = QWidget()
        card.setStyleSheet(f"""
            QWidget {{
                background-color: white;
                border: 2px solid {color};
                border-radius: 8px;
                padding: 16px;
            }}
        """)

        layout = QVBoxLayout(card)
        layout.setSpacing(8)

        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("font-size: 12px; color: #666; font-weight: normal;")
        lbl_title.setAlignment(Qt.AlignCenter)

        lbl_value = QLabel(value)
        lbl_value.setStyleSheet(f"font-size: 24px; color: {color}; font-weight: bold;")
        lbl_value.setAlignment(Qt.AlignCenter)
        lbl_value.setObjectName("kpi_value")  # Para poder actualizarlo después

        layout.addWidget(lbl_title)
        layout.addWidget(lbl_value)

        return card

    def _actualizar_estadisticas(self):
        """Actualiza las estadísticas y gráficos"""
        from datetime import datetime
        from collections import defaultdict

        # Obtener filtros del tab de listado
        try:
            desde_date = self.hist_desde.date().toPyDate()
            hasta_date = self.hist_hasta.date().toPyDate()
            sucursal = self.hist_sucursal.currentData()
            forma = self.hist_forma.currentData()
            sucursal_nombre = self.hist_sucursal.currentText()
            forma_nombre = self.hist_forma.currentText()
        except Exception:
            desde_date = datetime.now().date()
            hasta_date = datetime.now().date()
            sucursal = None
            forma = None
            sucursal_nombre = "Todas"
            forma_nombre = "Todas"

        # Actualizar banner de filtros
        filtros_texto = f"\U0001f4ca Mostrando estadísticas: {desde_date.strftime('%d/%m/%Y')} - {hasta_date.strftime('%d/%m/%Y')}"
        filtros_texto += f"  |  Sucursal: {sucursal_nombre}"
        filtros_texto += f"  |  Forma de pago: {forma_nombre}"
        self.stats_filtros_banner.setText(filtros_texto)

        # Obtener ventas del repositorio
        desde_dt = datetime.combine(desde_date, datetime.min.time())
        hasta_dt = datetime.combine(hasta_date, datetime.max.time())

        ventas = self.venta_repo.listar_por_rango(desde_dt, hasta_dt, sucursal)

        # Filtrar por forma de pago si es necesario
        if forma:
            ventas = [v for v in ventas if v.modo_pago.lower().startswith(forma[:3])]

        # Calcular KPIs
        total_ventas = sum(v.total for v in ventas)
        cant_ventas = len(ventas)
        promedio = total_ventas / cant_ventas if cant_ventas > 0 else 0
        interes_total = sum(getattr(v, 'interes_monto', 0) or 0 for v in ventas)

        # Actualizar labels de KPIs
        self.kpi_total_ventas.findChild(QLabel, "kpi_value").setText(f"${total_ventas:,.2f}")
        self.kpi_cant_ventas.findChild(QLabel, "kpi_value").setText(f"{cant_ventas}")
        self.kpi_promedio.findChild(QLabel, "kpi_value").setText(f"${promedio:,.2f}")
        self.kpi_interes_total.findChild(QLabel, "kpi_value").setText(f"${interes_total:,.2f}")

        # Preparar datos para gráfico de ventas por día
        ventas_por_dia = defaultdict(float)
        for v in ventas:
            fecha = v.fecha.date() if hasattr(v.fecha, 'date') else v.fecha
            ventas_por_dia[fecha] += v.total

        # Generar gráfico
        self._generar_grafico_ventas(ventas_por_dia, desde_date, hasta_date)

        # Si se eligió "Todas las sucursales", mostrar comparativa
        if sucursal is None and hasattr(self, 'direcciones') and len(self.direcciones) > 1:
            self.stats_comparativa_group.setVisible(True)
            self._generar_comparativa_sucursales(desde_dt, hasta_dt, forma)
        else:
            self.stats_comparativa_group.setVisible(False)

        # Calcular top productos
        self._calcular_top_productos(ventas)

    def _generar_grafico_ventas(self, ventas_por_dia, desde, hasta):
        """Genera el gráfico de ventas por día usando matplotlib"""
        try:
            import matplotlib
            matplotlib.use('Qt5Agg')
            from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
            from matplotlib.figure import Figure
            import matplotlib.dates as mdates
            from datetime import datetime, timedelta

            # Limpiar canvas anterior
            for i in reversed(range(self.stats_chart_layout.count())):
                self.stats_chart_layout.itemAt(i).widget().setParent(None)

            # Crear figura
            fig = Figure(figsize=(10, 4), dpi=100)
            ax = fig.add_subplot(111)

            # Preparar datos
            if not ventas_por_dia:
                ax.text(0.5, 0.5, 'No hay datos para mostrar',
                       ha='center', va='center', fontsize=14, color='gray')
                ax.set_xlim(0, 1)
                ax.set_ylim(0, 1)
                ax.axis('off')
            else:
                # Ordenar por fecha
                fechas = sorted(ventas_por_dia.keys())
                valores = [ventas_por_dia[f] for f in fechas]

                # Crear gráfico de barras
                ax.bar(fechas, valores, color='#2e7d32', alpha=0.7, edgecolor='#1b5e20')

                # Configurar ejes
                ax.set_xlabel('Fecha', fontsize=10)
                ax.set_ylabel('Total Ventas ($)', fontsize=10)
                ax.set_title(f'Ventas desde {desde} hasta {hasta}', fontsize=12, fontweight='bold')

                # Formato de fechas en eje X
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m'))
                if len(fechas) > 10:
                    ax.xaxis.set_major_locator(mdates.DayLocator(interval=max(1, len(fechas)//10)))

                # Rotar labels
                fig.autofmt_xdate()

                # Grid
                ax.grid(True, alpha=0.3, axis='y')
                ax.set_axisbelow(True)

            fig.tight_layout()

            # Crear canvas y agregarlo
            canvas = FigureCanvasQTAgg(fig)
            self.stats_chart_layout.addWidget(canvas)

        except Exception as e:
            from PyQt5.QtWidgets import QLabel
            error_label = QLabel(f"Error al generar gráfico: {str(e)}")
            error_label.setStyleSheet("color: red; padding: 20px;")
            self.stats_chart_layout.addWidget(error_label)

    def _calcular_top_productos(self, ventas):
        """Calcula y muestra los productos más vendidos (optimizado: 1 query en vez de N)"""
        from collections import defaultdict
        from PyQt5.QtWidgets import QTableWidgetItem
        from sqlalchemy.orm import joinedload
        from app.models import VentaItem, Producto

        # Acumular por producto
        productos_stats = defaultdict(lambda: {'cantidad': 0, 'total': 0, 'nombre': '', 'codigo': ''})

        if not ventas:
            self.table_top_productos.setRowCount(0)
            return

        # Una sola query para TODOS los items de todas las ventas
        venta_ids = [v.id for v in ventas]
        all_items = (
            self.session.query(VentaItem)
            .filter(VentaItem.venta_id.in_(venta_ids))
            .options(joinedload(VentaItem.producto))
            .all()
        )

        for item in all_items:
            if hasattr(item, 'producto') and item.producto:
                prod_id = item.producto.id
                nombre = item.producto.nombre
                codigo = item.producto.codigo_barra
            else:
                prod_id = f"item_{item.id}"
                nombre = getattr(item, 'nombre', 'Producto desconocido')
                codigo = getattr(item, 'codigo', 'N/A')

            cantidad = getattr(item, 'cantidad', 1)
            precio = getattr(item, 'precio_unit', 0)

            productos_stats[prod_id]['cantidad'] += cantidad
            productos_stats[prod_id]['total'] += cantidad * precio
            productos_stats[prod_id]['nombre'] = nombre
            productos_stats[prod_id]['codigo'] = codigo

        # Ordenar por cantidad vendida
        top_productos = sorted(productos_stats.items(),
                              key=lambda x: x[1]['cantidad'],
                              reverse=True)[:10]

        # Actualizar tabla
        self.table_top_productos.setRowCount(0)
        for i, (prod_id, stats) in enumerate(top_productos):
            self.table_top_productos.insertRow(i)
            self.table_top_productos.setItem(i, 0, QTableWidgetItem(stats['nombre']))
            self.table_top_productos.setItem(i, 1, QTableWidgetItem(stats['codigo']))
            self.table_top_productos.setItem(i, 2, QTableWidgetItem(str(int(stats['cantidad']))))
            self.table_top_productos.setItem(i, 3, QTableWidgetItem(f"${stats['total']:,.2f}"))

    def _generar_comparativa_sucursales(self, desde_dt, hasta_dt, forma):
        """Genera un gráfico comparativo entre sucursales"""
        try:
            import matplotlib
            matplotlib.use('Qt5Agg')
            from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
            from matplotlib.figure import Figure
            from collections import defaultdict

            # Limpiar canvas anterior
            for i in reversed(range(self.stats_comparativa_layout.count())):
                self.stats_comparativa_layout.itemAt(i).widget().setParent(None)

            # Obtener ventas de cada sucursal
            sucursales_data = {}
            for sucursal_nombre in self.direcciones.keys():
                ventas = self.venta_repo.listar_por_rango(desde_dt, hasta_dt, sucursal_nombre)

                # Filtrar por forma de pago si es necesario
                if forma:
                    ventas = [v for v in ventas if v.modo_pago.lower().startswith(forma[:3])]

                total = sum(v.total for v in ventas)
                cantidad = len(ventas)
                sucursales_data[sucursal_nombre] = {
                    'total': total,
                    'cantidad': cantidad,
                    'promedio': total / cantidad if cantidad > 0 else 0
                }

            if not sucursales_data:
                return

            # Crear figura con 2 subplots
            fig = Figure(figsize=(12, 4), dpi=100)

            # Subplot 1: Total facturado por sucursal
            ax1 = fig.add_subplot(121)
            sucursales = list(sucursales_data.keys())
            totales = [sucursales_data[s]['total'] for s in sucursales]

            bars1 = ax1.bar(sucursales, totales, color=['#2e7d32', '#1976d2'], alpha=0.7)
            ax1.set_ylabel('Total Facturado ($)', fontsize=10)
            ax1.set_title('Total Facturado por Sucursal', fontsize=12, fontweight='bold')
            ax1.grid(True, alpha=0.3, axis='y')
            ax1.set_axisbelow(True)

            # Agregar valores sobre las barras
            for bar, total in zip(bars1, totales):
                height = bar.get_height()
                ax1.text(bar.get_x() + bar.get_width()/2., height,
                        f'${total:,.0f}',
                        ha='center', va='bottom', fontsize=9, fontweight='bold')

            # Subplot 2: Cantidad de ventas por sucursal
            ax2 = fig.add_subplot(122)
            cantidades = [sucursales_data[s]['cantidad'] for s in sucursales]

            bars2 = ax2.bar(sucursales, cantidades, color=['#f57c00', '#c62828'], alpha=0.7)
            ax2.set_ylabel('Cantidad de Ventas', fontsize=10)
            ax2.set_title('Cantidad de Ventas por Sucursal', fontsize=12, fontweight='bold')
            ax2.grid(True, alpha=0.3, axis='y')
            ax2.set_axisbelow(True)

            # Agregar valores sobre las barras
            for bar, cant in zip(bars2, cantidades):
                height = bar.get_height()
                ax2.text(bar.get_x() + bar.get_width()/2., height,
                        f'{int(cant)}',
                        ha='center', va='bottom', fontsize=9, fontweight='bold')

            fig.tight_layout()

            # Crear canvas y agregarlo
            canvas = FigureCanvasQTAgg(fig)
            self.stats_comparativa_layout.addWidget(canvas)

            # Agregar tabla resumen debajo
            from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
            table = QTableWidget(len(sucursales), 4)
            table.setHorizontalHeaderLabels(['Sucursal', 'Total Facturado', 'Cantidad', 'Promedio'])
            table.verticalHeader().setVisible(False)

            for i, suc in enumerate(sucursales):
                data = sucursales_data[suc]
                table.setItem(i, 0, QTableWidgetItem(suc))
                table.setItem(i, 1, QTableWidgetItem(f"${data['total']:,.2f}"))
                table.setItem(i, 2, QTableWidgetItem(str(data['cantidad'])))
                table.setItem(i, 3, QTableWidgetItem(f"${data['promedio']:,.2f}"))

            hdr = table.horizontalHeader()
            hdr.setSectionResizeMode(0, QHeaderView.Stretch)
            hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
            hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
            hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)

            table.setMaximumHeight(150)
            self.stats_comparativa_layout.addWidget(table)

        except Exception as e:
            from PyQt5.QtWidgets import QLabel
            error_label = QLabel(f"Error al generar comparativa: {str(e)}")
            error_label.setStyleSheet("color: red; padding: 20px;")
            self.stats_comparativa_layout.addWidget(error_label)

 #-------------------------------------------------------------------------------------------------------


    # --- Cargar/Guardar slots de plantilla en config ---

    def _build_tpl_placeholder_panel(self):
        from PyQt5.QtWidgets import QWidget, QVBoxLayout, QGroupBox, QGridLayout, QPushButton

        def make_section(title, buttons):
            box = QGroupBox(title)
            grid = QGridLayout(box)
            grid.setHorizontalSpacing(10)
            grid.setVerticalSpacing(8)
            grid.setContentsMargins(8, 8, 8, 8)
            for i, (text, ins) in enumerate(buttons):
                b = QPushButton(text)
                b.setProperty("role", "inline")
                b.setMinimumHeight(28)
                b.setMinimumWidth(0)          # no se estiran
                b.clicked.connect(lambda _=None, s=ins: self._tpl_insert(s))
                grid.addWidget(b, i // 2, i % 2, alignment=Qt.AlignLeft)  # 2 columnas, pegado a la izquierda
            return box

        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)

        v.addWidget(make_section("Encabezado / Sucursal", [
            ("Nº ticket", "{{ticket.numero}}"),
            ("Fecha/hora", "{{ticket.fecha_hora}}"),
            ("Sucursal", "{{sucursal}}"),
            ("Dirección", "{{direccion}}"),
            ("Nombre comercio", "{{business}}"),
        ]))

        v.addWidget(make_section("Pago", [
            ("Modo pago", "{{pago.modo}}"),
            ("Cuotas", "{{pago.cuotas}}"),
            ("Monto cuota", "{{pago.monto_cuota}}"),
            ("Abonado", "{{abonado}}"),
            ("Vuelto", "{{vuelto}}"),
        ]))

        v.addWidget(make_section("Totales", [
            ("Subtotal", "{{totales.subtotal}}"),
            ("Interés", "{{totales.interes}}"),
            ("Descuento", "{{totales.descuento}}"),   # <-- nuevo
            ("TOTAL", "{{totales.total}}"),
        ]))

        v.addWidget(make_section("Ítems / Separadores", [
            ("Ítems", "{{items}}"),
            ("Línea ({{hr}})", "{{hr}}"),
        ]))

        v.addWidget(make_section("Formato por línea", [
            ("Centrar", "{{center: TU TEXTO}}"),
            ("Derecha", "{{right: TU TEXTO}}"),
            ("Negrita", "{{b: TU TEXTO}}"),
            ("Centrar+Negrita", "{{centerb: TU TEXTO}}"),
            ("Derecha+Negrita", "{{rightb: TU TEXTO}}"),
        ]))

        v.addStretch(1)
        return w
