# app/gui/smart_template_editor.py
"""
SmartTemplateEditor — Editor de plantillas de ticket con:
1. Autocompletado al escribir '{{' con QCompleter
2. Validacion inline con QSyntaxHighlighter (verde=valido, rojo=invalido, azul=formato)
3. Barra de insercion con dropdowns categorizados
4. Insertar bloques pre-armados
"""
import re
import logging

from PyQt5.QtCore import Qt, QStringListModel, QRect
from PyQt5.QtGui import (
    QSyntaxHighlighter, QTextCharFormat, QColor, QFont, QTextCursor,
)
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QCompleter,
    QToolBar, QAction, QMenu, QPushButton, QLabel,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
#  Definiciones de placeholders conocidos
# ──────────────────────────────────────────────────────────────────────

PLACEHOLDER_CATEGORIES = {
    "Empresa": {
        "business": "Nombre del negocio",
        "business.cuit": "CUIT del comercio",
        "business.direccion": "Direccion de la sucursal",
    },
    "Ticket": {
        "ticket.numero": "Numero de ticket (ventas sin CAE)",
        "ticket.numero_cae": "Numero de ticket (ventas con CAE)",
        "ticket.fecha_hora": "Fecha y hora de la venta",
        "sucursal": "Nombre de la sucursal",
        "vendedor": "Nombre del vendedor",
        "title": "Titulo del ticket (config)",
    },
    "Pago": {
        "pago.modo": "Metodo de pago (Efectivo/Tarjeta)",
        "pago.cuotas": "Cantidad de cuotas",
        "pago.monto_cuota": "Monto por cuota",
        "abonado": "Monto abonado por el cliente",
        "vuelto": "Vuelto entregado",
    },
    "Totales": {
        "totales.subtotal": "Subtotal (sin descuento/interes)",
        "totales.descuento": "Descuento aplicado",
        "totales.interes": "Interes por financiacion",
        "totales.total": "Total final a pagar",
    },
    "Fiscal / IVA": {
        "iva.base": "Base imponible (neto)",
        "iva.cuota": "Monto IVA",
        "iva.porcentaje": "Porcentaje IVA (21%)",
        "afip.cae": "Numero de CAE",
        "afip.vencimiento": "Vencimiento del CAE",
        "afip.comprobante": "Numero de comprobante AFIP",
        "comprobante.numero": "N de comprobante (solo CAE)",
        "comprobante.tipo": "Tipo de comprobante (Factura A/B, NC, etc.)",
    },
    "Comprador": {
        "comprador.nombre": "Nombre y Apellido del comprador",
        "comprador.cuit": "CUIT/CUIL del comprador",
        "comprador.domicilio": "Domicilio del comprador",
        "comprador.localidad": "Localidad del comprador",
    },
    "Contenido": {
        "items": "Lista de articulos vendidos",
        "cae": "Bloque completo CAE (titulo + datos)",
        "qrcae": "QR de factura electronica AFIP",
        "iva.discriminado": "Bloque IVA discriminado",
        "items_sin_iva": "Articulos con precio sin IVA (neto)",
        "hr": "Linea separadora horizontal",
    },
    "Imagenes": {
        "img:logo": "Logo del negocio",
        "img:instagram": "Icono de Instagram",
        "img:whatsapp": "Icono de WhatsApp",
        "img:qr": "Codigo QR personalizado",
    },
    "Formato": {
        "center: ": "Centrar texto",
        "right: ": "Alinear a la derecha",
        "left: ": "Alinear a la izquierda",
        "b: ": "Texto en negrita",
        "i: ": "Texto en cursiva",
        "centerb: ": "Centrar + negrita",
        "h1: ": "Tamano titulo grande",
        "h2: ": "Tamano seccion",
        "h3: ": "Tamano encabezado",
        "h4: ": "Tamano texto normal",
        "h5: ": "Tamano pie/legal pequeno",
    },
    "Expresiones": {
        "= ": "Expresion matematica (ej: totales.total - iva.cuota)",
    },
}

# Set plano de todos los placeholders validos (sin los {{ }})
ALL_PLACEHOLDERS = set()
FORMAT_TAGS = set()
for cat, items in PLACEHOLDER_CATEGORIES.items():
    for key in items:
        ALL_PLACEHOLDERS.add(key)
        if cat == "Formato" or cat == "Expresiones":
            FORMAT_TAGS.add(key.rstrip(": ").rstrip(" "))

# Lista para el completer (placeholder -> descripcion)
COMPLETER_ITEMS = []
for cat, items in PLACEHOLDER_CATEGORIES.items():
    for key, desc in items.items():
        COMPLETER_ITEMS.append(f"{{{{{key}}}}}  — {desc}")

# Solo las keys para validacion rapida
VALID_KEYS = set()
for cat, items in PLACEHOLDER_CATEGORIES.items():
    for key in items:
        VALID_KEYS.add(key)


# ──────────────────────────────────────────────────────────────────────
#  Syntax Highlighter
# ──────────────────────────────────────────────────────────────────────

class TemplateHighlighter(QSyntaxHighlighter):
    """Colorea placeholders en la plantilla del ticket."""

    def __init__(self, parent=None):
        super().__init__(parent)

        # Formato para placeholders validos (verde)
        self.fmt_valid = QTextCharFormat()
        self.fmt_valid.setForeground(QColor("#2e7d32"))
        self.fmt_valid.setFontWeight(QFont.Bold)

        # Formato para placeholders invalidos (rojo subrayado)
        self.fmt_invalid = QTextCharFormat()
        self.fmt_invalid.setForeground(QColor("#c62828"))
        self.fmt_invalid.setFontWeight(QFont.Bold)
        self.fmt_invalid.setFontUnderline(True)

        # Formato para tags de formato (azul)
        self.fmt_format = QTextCharFormat()
        self.fmt_format.setForeground(QColor("#1565c0"))
        self.fmt_format.setFontWeight(QFont.Bold)

        # Formato para expresiones (purpura)
        self.fmt_expr = QTextCharFormat()
        self.fmt_expr.setForeground(QColor("#7b1fa2"))
        self.fmt_expr.setFontWeight(QFont.Bold)

        # Regex para encontrar placeholders {{ ... }}
        self._re_placeholder = re.compile(r'\{\{(.+?)\}\}')

        # Tags de formato conocidos (inicio de la key)
        self._format_prefixes = {
            "center:", "right:", "left:", "b:", "i:",
            "centerb:", "rightb:", "leftb:",
            "h1:", "h2:", "h3:", "h4:", "h5:",
        }

        # Placeholders de datos conocidos
        self._data_keys = set()
        for cat, items in PLACEHOLDER_CATEGORIES.items():
            if cat not in ("Formato", "Expresiones"):
                for key in items:
                    self._data_keys.add(key)

    def highlightBlock(self, text):
        for match in self._re_placeholder.finditer(text):
            start = match.start()
            length = match.end() - match.start()
            inner = match.group(1).strip()

            # Expresion matematica
            if inner.startswith("="):
                self.setFormat(start, length, self.fmt_expr)
                continue

            # Tag de formato
            is_format = False
            for prefix in self._format_prefixes:
                if inner.startswith(prefix):
                    self.setFormat(start, length, self.fmt_format)
                    is_format = True
                    break
            if is_format:
                continue

            # Placeholder de datos
            if inner in self._data_keys:
                self.setFormat(start, length, self.fmt_valid)
            else:
                # Desconocido -> rojo
                self.setFormat(start, length, self.fmt_invalid)


# ──────────────────────────────────────────────────────────────────────
#  Smart Template Editor Widget
# ──────────────────────────────────────────────────────────────────────

class SmartTemplateEditor(QWidget):
    """
    Editor de plantillas de ticket con autocompletado,
    validacion visual y barra de insercion.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # ── Barra de insercion (una fila, botones expandidos) ──
        from PyQt5.QtWidgets import QGridLayout
        tb_widget = QWidget()
        tb_widget.setStyleSheet("background: #f5f5f5; border-radius: 4px;")
        grid = QGridLayout(tb_widget)
        grid.setContentsMargins(4, 4, 4, 4)
        grid.setSpacing(4)

        _btn_style = (
            "QPushButton { background: #e8eaf6; color: #1a237e; "
            "border: 1px solid #c5cae9; border-radius: 3px; "
            "padding: 4px 2px; font-size: 11px; font-weight: 500; }"
            "QPushButton:hover { background: #c5cae9; }"
        )
        _menu_style = (
            "QMenu { font-size: 13px; background: white; }"
            "QMenu::item { padding: 6px 18px; }"
            "QMenu::item:selected { background: #c5cae9; color: #1a237e; }"
        )
        _cats = list(PLACEHOLDER_CATEGORIES.items())
        cols = 6  # 6 columnas por fila
        for idx, (cat_name, items) in enumerate(_cats):
            btn = QPushButton(f"{cat_name} \u25be")
            btn.setStyleSheet(_btn_style)
            menu = QMenu(self)
            menu.setStyleSheet(_menu_style)
            for key, desc in items.items():
                action = menu.addAction(f"{{{{{key}}}}}  \u2014  {desc}")
                action.setData(key)
                action.triggered.connect(lambda checked, k=key: self._insert_placeholder(k))
            btn.setMenu(menu)
            grid.addWidget(btn, idx // cols, idx % cols)

        # Bloques
        btn_blocks = QPushButton("Bloques \u25be")
        btn_blocks.setStyleSheet(
            "QPushButton { background: #fff3e0; color: #e65100; "
            "border: 1px solid #ffcc80; border-radius: 3px; "
            "padding: 4px 2px; font-size: 11px; font-weight: 600; }"
            "QPushButton:hover { background: #ffe0b2; }"
        )
        blocks_menu = QMenu(self)
        blocks_menu.setStyleSheet(
            "QMenu { font-size: 13px; background: white; }"
            "QMenu::item { padding: 6px 18px; }"
            "QMenu::item:selected { background: #ffe0b2; color: #e65100; }"
        )
        for block_name, block_text in self._get_blocks().items():
            action = blocks_menu.addAction(block_name)
            action.setData(block_text)
            action.triggered.connect(lambda checked, t=block_text: self._insert_text(t))
        btn_blocks.setMenu(blocks_menu)
        idx_next = len(_cats)
        grid.addWidget(btn_blocks, idx_next // cols, idx_next % cols)

        layout.addWidget(tb_widget)

        # ── Editor de texto ──
        self.editor = QTextEdit()
        self.editor.setAcceptRichText(False)
        self.editor.setLineWrapMode(QTextEdit.NoWrap)
        self.editor.setStyleSheet("""
            QTextEdit {
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 14px;
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        layout.addWidget(self.editor)

        # ── Syntax Highlighter ──
        self._highlighter = TemplateHighlighter(self.editor.document())

        # ── Completer ──
        completer_keys = []
        for cat, items in PLACEHOLDER_CATEGORIES.items():
            for key, desc in items.items():
                completer_keys.append(f"{{{{{key}}}}}")

        self._completer_model = QStringListModel(completer_keys)
        self._completer = QCompleter(self._completer_model, self)
        self._completer.setWidget(self.editor)
        self._completer.setCompletionMode(QCompleter.PopupCompletion)
        self._completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._completer.setFilterMode(Qt.MatchContains)
        self._completer.activated.connect(self._on_completer_activated)

        # Conectar key press para trigger autocompletado
        self.editor.textChanged.connect(self._check_autocomplete)

        # ── Leyenda de colores ──
        legend = QHBoxLayout()
        legend.setSpacing(12)
        for color, label in [
            ("#2e7d32", "Placeholder valido"),
            ("#c62828", "Placeholder desconocido"),
            ("#1565c0", "Tag de formato"),
            ("#7b1fa2", "Expresion matematica"),
        ]:
            lbl = QLabel(f"● {label}")
            lbl.setStyleSheet(f"color: {color}; font-size: 10px;")
            legend.addWidget(lbl)
        legend.addStretch(1)
        layout.addLayout(legend)

    # ------------------------------------------------------------------
    #  Bloques pre-armados
    # ------------------------------------------------------------------
    def _get_blocks(self):
        return {
            "Encabezado comercio": (
                "{{center: {{h2: {{business}} }} }}\n"
                "{{center: {{business.direccion}} }}\n"
                "{{center: CUIT: {{business.cuit}} }}\n"
                "{{hr}}\n"
            ),
            "Bloque totales": (
                "{{hr}}\n"
                "{{b: Subtotal:}}  {{totales.subtotal}}\n"
                "{{b: Descuento:}} {{totales.descuento}}\n"
                "{{h2: {{b: TOTAL: {{totales.total}} }} }}\n"
            ),
            "Bloque pago": (
                "Pago: {{pago.modo}}\n"
                "Cuotas: {{pago.cuotas}} x {{pago.monto_cuota}}\n"
                "Abonado: {{abonado}}\n"
                "Vuelto: {{vuelto}}\n"
            ),
            "Bloque CAE + QR": (
                "{{hr}}\n"
                "{{cae}}\n"
                "{{qrcae}}\n"
            ),
            "Bloque IVA discriminado": (
                "{{hr}}\n"
                "{{iva.discriminado}}\n"
            ),
            "Pie de ticket": (
                "{{hr}}\n"
                "{{center: {{h5: Gracias por su compra! }} }}\n"
                "{{center: {{h5: {{ticket.fecha_hora}} }} }}\n"
            ),
            "Imagenes redes sociales": (
                "{{center: {{img:instagram}} }}\n"
                "{{center: {{img:whatsapp}} }}\n"
            ),
        }

    # ------------------------------------------------------------------
    #  Insertar placeholder / texto
    # ------------------------------------------------------------------
    def _insert_placeholder(self, key):
        """Inserta un placeholder en la posicion del cursor."""
        text = f"{{{{{key}}}}}"
        cursor = self.editor.textCursor()
        cursor.insertText(text)
        self.editor.setTextCursor(cursor)
        self.editor.setFocus()

    def _insert_text(self, text):
        """Inserta un bloque de texto en la posicion del cursor."""
        cursor = self.editor.textCursor()
        cursor.insertText(text)
        self.editor.setTextCursor(cursor)
        self.editor.setFocus()

    # ------------------------------------------------------------------
    #  Autocompletado
    # ------------------------------------------------------------------
    def _check_autocomplete(self):
        """Verifica si debe mostrar el popup de autocompletado."""
        cursor = self.editor.textCursor()
        cursor.movePosition(QTextCursor.StartOfBlock, QTextCursor.KeepAnchor)
        line_before = cursor.selectedText()

        # Buscar si hay '{{' sin cerrar
        last_open = line_before.rfind("{{")
        if last_open == -1:
            self._completer.popup().hide()
            return

        last_close = line_before.rfind("}}")
        if last_close > last_open:
            # El placeholder ya esta cerrado
            self._completer.popup().hide()
            return

        # Hay un '{{' abierto — obtener el texto parcial despues de '{{'
        partial = line_before[last_open + 2:]

        if not partial and last_open == len(line_before) - 2:
            # Acaba de escribir '{{', mostrar todo
            self._completer.setCompletionPrefix("{{")
            self._show_completer()
        elif partial:
            # Filtrar por texto parcial
            prefix = "{{" + partial
            self._completer.setCompletionPrefix(prefix)
            if self._completer.completionCount() > 0:
                self._show_completer()
            else:
                self._completer.popup().hide()
        else:
            self._completer.popup().hide()

    def _show_completer(self):
        """Muestra el popup del completer en la posicion del cursor."""
        cr = self.editor.cursorRect()
        cr.setWidth(
            self._completer.popup().sizeHintForColumn(0)
            + self._completer.popup().verticalScrollBar().sizeHint().width()
            + 20
        )
        cr.setWidth(min(cr.width(), 400))
        self._completer.complete(cr)

    def _on_completer_activated(self, text):
        """Cuando se selecciona un item del autocompletado."""
        cursor = self.editor.textCursor()

        # Encontrar el inicio del placeholder incompleto
        cursor.movePosition(QTextCursor.StartOfBlock, QTextCursor.KeepAnchor)
        line_before = cursor.selectedText()
        last_open = line_before.rfind("{{")

        if last_open >= 0:
            # Posicionar cursor al inicio del '{{'
            cursor = self.editor.textCursor()
            block_pos = cursor.block().position()

            cursor.setPosition(block_pos + last_open)
            cursor.setPosition(cursor.position() + (len(line_before) - last_open),
                             QTextCursor.KeepAnchor)
            cursor.insertText(text)
            self.editor.setTextCursor(cursor)

    # ------------------------------------------------------------------
    #  API publica — compatibilidad con QTextEdit
    # ------------------------------------------------------------------
    @property
    def textChanged(self):
        """Proxy de la signal textChanged del editor interno."""
        return self.editor.textChanged

    def toPlainText(self):
        """Retorna el texto plano del editor."""
        return self.editor.toPlainText()

    def setPlainText(self, text):
        """Establece el texto del editor."""
        self.editor.setPlainText(text)

    def textCursor(self):
        """Retorna el cursor de texto del editor."""
        return self.editor.textCursor()

    def setTextCursor(self, cursor):
        """Establece el cursor de texto del editor."""
        self.editor.setTextCursor(cursor)

    def document(self):
        """Retorna el QDocument del editor."""
        return self.editor.document()

    def setMinimumHeight(self, h):
        """Override para aplicar al editor interno."""
        self.editor.setMinimumHeight(h)

    def setToolTip(self, tip):
        """Override para aplicar al editor interno."""
        self.editor.setToolTip(tip)

    def setFocus(self):
        """Da foco al editor interno."""
        self.editor.setFocus()
