import os
import sys
import tempfile
import webbrowser
import urllib.parse
import subprocess
import logging

logger = logging.getLogger(__name__)

from PyQt5.QtCore import Qt, QSize, QRect, QSizeF
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton,
    QTableWidgetItem, QMessageBox, QFileDialog, QDialog,
)
from PyQt5.QtGui import QPdfWriter, QPainter

from app.gui.common import ICON_SIZE, icon
from app.models import Producto, Venta, VentaItem
from app.gui.ventas_helpers import build_product_completer, _draw_ticket, _compute_ticket_height_mm


class VentasTicketMixin:
    """Mixin con operaciones post-venta: ticket, impresion, WhatsApp, completer, ventas del dia."""

    def _items_para_ticket(self, venta_id):
        """
        Devuelve una lista de items normalizados con codigo/nombre/cantidad/precio_unitario.
        1ro usa la cesta visible (si existe), 2do lee BD con multiples "fallbacks".
        """
        items = []

        # 1) Si la cesta esta visible y con filas, usala (garantiza que haya codigo/nombre)
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
            # muchos nombres posibles de atributos...
            codigo = (
                getattr(it, 'codigo', None) or
                getattr(it, 'codigo_barra', None) or
                getattr(it, 'cod_barra', None) or
                getattr(it, 'codigobarra', None) or
                ""
            )
            nombre = getattr(it, 'nombre', None) or ""
            # si no hay relacion cargada, intentar por producto_id
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
            # 1) Items: usar helper si existe; si no, cesta visible -> BD
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
                            from app.models import VentaItem  # por si no estaba importado en el modulo
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

                        # Obtener codigo: intentar desde it o desde it.producto
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
            QMessageBox.warning(self, "Impresion", f"No se pudo imprimir:\n{e}")


    def _write_ticket_pdf(self, venta_id, path_pdf, *, extra_bottom_mm: float = 0.0):

        """Escribe el ticket a PDF (ancho 75 mm, alto dinamico)."""
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
        """Dialogo de guardado + escritura PDF 80 mm."""
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
        msg = urllib.parse.quote("Te envio el ticket de tu compra. Adjuntare el PDF en el chat.")
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
                "Se abrio el Explorador con el archivo seleccionado.")
        except Exception:
            pass


    #--- Ventas del dia / Acciones por ID

    def recargar_ventas_dia(self):
        """
        Recarga en memoria (y si existe, en la tabla) las ventas del dia.
        Tolerante a errores para no romper la app.
        """
        from datetime import datetime, timedelta
        try:
            if not hasattr(self, 'venta_repo') or self.venta_repo is None:
                self._ventas_dia = []
                return

            hoy = datetime.now().date()
            ventas = []

            # 1) Metodo del repositorio si existe
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
            tbl.setUpdatesEnabled(False)                 # <- DESACTIVO repaints
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
                        f"${interes_m:.2f}",            # <- NUEVA COLUMNA
                        f"${descto_m:.2f}",             # <- NUEVA COLUMNA
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
                tbl.setUpdatesEnabled(True)              # <- SIEMPRE reactivar
        except Exception as e:
            logger.warning(f"[WARN] recargar_ventas_dia: {e}")


    def _reimprimir_venta_seleccionada(self):
        itms = self.table_ventas_dia.selectedItems()
        if not itms:
            QMessageBox.information(self, "Reimprimir", "Selecciona una fila de la lista.")
            return
        row = itms[0].row()
        nro_txt = self.table_ventas_dia.item(row, 0).text().strip()  # col 0 = Nro Ticket
        if not nro_txt:
            QMessageBox.warning(self, "Reimprimir", "No se encontro el numero de ticket en la fila.")
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
            QMessageBox.warning(self, "WhatsApp", "No se encontro la venta.")
            return
        self._last_venta_id = venta_id
        self.enviar_ticket_whatsapp()

    def _reimprimir_ticket_by_id(self, venta_id):
        if not venta_id:
            QMessageBox.warning(self, "Reimprimir", "No se encontro el ID de la venta.")
            return
        self._last_venta_id = venta_id  # util para boton PNG
        self.imprimir_ticket(venta_id)

    #FUNCION ELIMINAR VENTA SOLO PARA ADMIN


    def _eliminar_venta_by_id(self, venta_id):
        if not venta_id:
            QMessageBox.warning(self, "Eliminar", "No se encontro el ID de la venta.")
            return
        if QMessageBox.question(
            self, "Eliminar venta",
            f"Seguro que deseas eliminar la venta #{venta_id}?",
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

            # Asignar SOLO al buscador de la pestana Ventas
            ventas_input = getattr(self, 'input_venta_buscar', None)
            if ventas_input is not None:
                ventas_input.setCompleter(self._completer)

                # Conectar filtro del proxy al textChanged (con debounce)
                from PyQt5.QtCore import QTimer
                self._completer_debounce = QTimer(self)
                self._completer_debounce.setSingleShot(True)
                self._completer_debounce.setInterval(150)
                self._completer_debounce.timeout.connect(self._update_completer_filter)
                ventas_input.textChanged.connect(lambda t: self._completer_debounce.start())

            from app.gui.common import LIVE_SEARCH_FONT_PT, LIVE_SEARCH_ROW_PAD, LIVE_SEARCH_MIN_WIDTH
            try:
                popup = self._completer.popup()   # QListView del completer
                # tamano de fuente
                f = popup.font()
                f.setPointSize(LIVE_SEARCH_FONT_PT)
                popup.setFont(f)

                # padding por item y ancho minimo
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

    def _update_completer_filter(self):
        """Actualiza el filtro del proxy del completer tras debounce."""
        try:
            ventas_input = getattr(self, 'input_venta_buscar', None)
            if not ventas_input:
                return
            text = ventas_input.text().strip()
            if len(text) < 2:
                return
            proxy = getattr(self._completer, '_proxy', None)
            if proxy:
                proxy.setFilterWildcard(f"*{text}*")
                self._completer.setCompletionPrefix(text)
                self._completer.complete()
        except Exception:
            pass

    def refrescar_completer(self):
        """Actualiza la lista del completer solo cuando hay cambios reales en productos."""
        try:
            # Si aun no existe el completer, crealo
            if self._completer is None or self._completer_model is None:
                self._setup_completer()
                # si fallo la creacion, no seguimos
                if self._completer_model is None:
                    return

            # Recalcular la lista (codigo - nombre) desde el repo
            from app.repository import prod_repo
            repo = prod_repo(self.session)
            pares = repo.listar_codigos_nombres()  # [(codigo, nombre), ...]
            items = [f"{(c or '').strip()} - {(n or '').strip()}" for (c, n) in pares]

            # Actualizar el modelo sin reconstruir todo el completer
            self._completer_model.setStringList(items)

        except Exception as e:
            logger.warning(f"[WARN] refrescar_completer fallo: {e}")

    def _force_complete(self, t):
    # actualiza prefijo y abre el popup
        try:
            self._comp.setCompletionPrefix(t)
            # posiciona el popup bajo el QLineEdit
            self._comp.complete()
        except Exception:
            pass
