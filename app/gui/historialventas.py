# app/gui/historialventas.py
# -*- coding: utf-8 -*-
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, time as dtime
from typing import List, Optional


import os
import tempfile

import pandas as pd
from PyQt5.QtCore import Qt, QTimer, QDate,QTime

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QDateEdit, QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox,
    QFileDialog, QMessageBox, QDialog, QTableWidgetSelectionRange,QTimeEdit, QSpinBox
)

from app.config import load as load_config, save as save_config   # ← config existente :contentReference[oaicite:1]{index=1}
from app.models import Venta, VentaItem
from app.repository import VentaRepo                               # ← repo existente (listar_por_rango, listar_items) :contentReference[oaicite:2]{index=2}



# === Helpers Excel (definidos a nivel de módulo) ===
def _make_writer(path):
    import pandas as pd
    # El caller ya asegura .xlsx, acá solo probamos engines
    for engine in ("openpyxl", "xlsxwriter"):
        try:
            return pd.ExcelWriter(path, engine=engine)
        except Exception:
            continue
    return None


def _autofit_sheet(ws, df, engine_name: str):
    def _maxlen(series):
        try:
            return max([len(str(series.name))] + [len(str(x)) for x in series.astype(str).tolist()])
        except Exception:
            return 12

    if "openpyxl" in (engine_name or "").lower():
        from openpyxl.utils import get_column_letter
        for i, col in enumerate(df.columns, start=1):
            width = min(max(10, _maxlen(df[col]) + 2), 60)
            ws.column_dimensions[get_column_letter(i)].width = width
    else:  # xlsxwriter
        for i, col in enumerate(df.columns):
            width = min(max(10, _maxlen(df[col]) + 2), 60)
            try:
                ws.set_column(i, i, width)
            except Exception:
                pass

def _get_any(obj, names, default=None):
    for n in names:
        try:
            v = getattr(obj, n, None)
        except Exception:
            v = None
        if v not in (None, ""):
            return v
    return default

def _norm_item_fields(it):
    # Códigos posibles en VentaItem
    codigo = _get_any(it, ['codigo', 'codigo_barra', 'cod_barra', 'codigobarra', 'cod'], "") or ""
    # Nombre directo o a través de la relación producto
    nombre = _get_any(it, ['nombre'], "")
    if not nombre:
        prod = getattr(it, 'producto', None)
        if prod:
            nombre = _get_any(prod, ['nombre', 'descripcion', 'desc'], "") or ""
    # Cantidad / precio unitario con alias típicos
    try:
        cant = float(_get_any(it, ['cantidad', 'cant', 'unidades'], 1) or 1)
    except Exception:
        cant = 1.0
    try:
        pu = float(_get_any(it, ['precio', 'precio_unit', 'precio_unitario', 'p_unit', 'precioU'], 0.0) or 0.0)
    except Exception:
        pu = 0.0
    return codigo, nombre, cant, pu
# ---------------------- Email helper (SMTP simple) ----------------------
def _send_mail_with_attachments(subject: str, body: str,
                                recipients: List[str], attachments: List[str] = None):
    import smtplib
    from email.message import EmailMessage

    cfg = load_config()
    e = (cfg.get("email") or {})
    smtp = (e.get("smtp") or {})

    host = smtp.get("host")
    port = int(smtp.get("port") or 587)
    use_tls = bool(smtp.get("use_tls", True))
    user = smtp.get("username")
    pwd  = smtp.get("password")
    from_addr = e.get("sender") or user

    if not host or not user or not pwd or not from_addr:
        raise RuntimeError("Falta configurar SMTP en Configuración → Email.")

    msg = EmailMessage()
    msg["Subject"] = subject or "Reporte"
    msg["From"] = from_addr
    msg["To"] = ", ".join(recipients or [])
    if e.get("bcc"):
        msg["Bcc"] = ", ".join(e.get("bcc"))

    msg.set_content(body or "")

    for path in (attachments or []):
        try:
            with open(path, "rb") as f:
                data = f.read()
            filename = os.path.basename(path)
            msg.add_attachment(data, maintype="application",
                               subtype="octet-stream", filename=filename)
        except Exception as ex:
            print("Adjunto falló:", ex)

    if use_tls:
        server = smtplib.SMTP(host, port)
        server.starttls()
    else:
        server = smtplib.SMTP_SSL(host, port)

    server.login(user, pwd)
    server.send_message(msg)
    server.quit()
    return True


# ---------------------- UI principal ----------------------
class HistorialVentasWidget(QWidget):
    """
    Pestaña Historial de ventas:
    - Filtros por fecha (desde/hasta), sucursal, forma pago, texto.
    - Tabla con ventas del rango.
    - Botón Enviar a correo (Excel con filtros aplicados).
    - Programación de envíos (diario/semanal/mensual a hora fija).
    - Doble clic en una venta => dialog con items vendidos.
    """
    def __init__(self, session, sucursal_actual: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.session = session
        self.repo = VentaRepo(self.session)  # :contentReference[oaicite:4]{index=4}
        self.sucursal_actual = sucursal_actual

        self._ventas_cache: List[Venta] = []

        root = QVBoxLayout(self)

        # --- Filtros ---
        filtros = QFormLayout()
        row1 = QHBoxLayout()
        self.dt_desde = QDateEdit()
        self.dt_hasta = QDateEdit()
        for d in (self.dt_desde, self.dt_hasta):
            d.setDisplayFormat("yyyy-MM-dd")
            d.setCalendarPopup(True)
        hoy = QDate.currentDate()
        self.dt_desde.setDate(hoy)  # por defecto hoy
        self.dt_hasta.setDate(hoy)

        self.cmb_sucursal = QComboBox()
        self.cmb_sucursal.addItem("Todas", None)
        for s in ("Sarmiento", "Salta"):
            self.cmb_sucursal.addItem(s, s)
        if self.sucursal_actual and self.sucursal_actual in ("Sarmiento", "Salta"):
            self.cmb_sucursal.setCurrentText(self.sucursal_actual)

        self.cmb_forma = QComboBox()
        self.cmb_forma.addItems(["Todas", "Efectivo", "Tarjeta"])

        self.txt_buscar = QLineEdit()
        self.txt_buscar.setPlaceholderText("Buscar por Nº ticket o texto...")

        row1.addWidget(QLabel("Desde:")); row1.addWidget(self.dt_desde)
        row1.addWidget(QLabel("Hasta:")); row1.addWidget(self.dt_hasta)
        row1.addWidget(QLabel("Sucursal:")); row1.addWidget(self.cmb_sucursal)
        row1.addWidget(QLabel("Forma:")); row1.addWidget(self.cmb_forma)
        row1.addWidget(self.txt_buscar)

        btn_filtrar = QPushButton("Aplicar filtros")
        btn_filtrar.clicked.connect(self.refrescar)
        row1.addWidget(btn_filtrar)
        root.addLayout(row1)

        # refrescar con Enter en el texto
        self.txt_buscar.returnPressed.connect(self.refrescar)
        # refrescar al cambiar fechas/combos
        self.dt_desde.dateChanged.connect(lambda *_: self.refrescar())
        self.dt_hasta.dateChanged.connect(lambda *_: self.refrescar())
        self.cmb_sucursal.currentIndexChanged.connect(lambda *_: self.refrescar())
        self.cmb_forma.currentIndexChanged.connect(lambda *_: self.refrescar())
        
        # --- Tabla ---
        self.tbl = QTableWidget(0, 13)
        self.tbl.setHorizontalHeaderLabels([
            "Nº Ticket", "Fecha/Hora", "Sucursal", "Forma Pago",
            "Cuotas","Interés", "Descuento", "Monto x cuota", "Total", "Pagado", "Vuelto", "Comentario", "ID"
        ])
        hdr = self.tbl.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.Stretch)
        for col in (5, 6, 7):  # Interés, Descuento, Monto x cuota
            hdr.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setSelectionBehavior(QTableWidget.SelectRows)
        self.tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tbl.cellDoubleClicked.connect(self._ver_detalle_venta)
        root.addWidget(self.tbl)

        # --- Barra inferior ---
        bar = QHBoxLayout()
        self.lbl_resumen = QLabel("0 ventas — Total $0.00")
        bar.addWidget(self.lbl_resumen)
        bar.addStretch(1)

        self.chk_incluir_items = QCheckBox("Incluir detalle de productos en Excel")
        bar.addWidget(self.chk_incluir_items)



        self.btn_excel = QPushButton("Enviar a correo")
        self.btn_excel.clicked.connect(self._exportar_y_enviar)
        bar.addWidget(self.btn_excel)

        self.btn_guardar_xlsx = QPushButton("Exportar XLSX…")
        self.btn_guardar_xlsx.clicked.connect(self._exportar_a_xlsx_local)
        bar.addWidget(self.btn_guardar_xlsx)

        root.addLayout(bar)
        
        self.refrescar()


    def recargar_historial(self):
    # Alias compatible con llamadas existentes desde main_window
        self.refrescar()

    # ------------------- Carga / filtros -------------------
    def _rango_fechas(self):
        d1 = self.dt_desde.date().toPyDate()
        d2 = self.dt_hasta.date().toPyDate()
        # hasta fin del día
        dt_min = datetime.combine(d1, dtime.min)
        dt_max = datetime.combine(d2 + timedelta(days=1), dtime.min)
        return dt_min, dt_max

    def refrescar(self):
        dt_min, dt_max = self._rango_fechas()
        suc = self.cmb_sucursal.currentData()
        forma_txt = self.cmb_forma.currentText().lower()

        # Del repo si existe listar_por_rango; si no, fallback por fecha día a día
        ventas = []
        try:
            if hasattr(self.repo, "listar_por_rango"):
                ventas = self.repo.listar_por_rango(dt_min, dt_max, sucursal=suc)   # si tu repo soporta sucursal
            else:
                # fallback: día a día
                cur = dt_min.date()
                while cur < dt_max.date():
                    try:
                        ventas += self.repo.listar_por_fecha(cur, sucursal=suc)
                    except Exception:
                        ventas += self.repo.listar_por_fecha(cur)
                    cur += timedelta(days=1)
        except Exception:
            ventas = []

        # Filtro por forma
        if forma_txt != "todas":
            def _forma(v):
                raw = (getattr(v, "forma_pago", "") or getattr(v, "modo_pago", "") or getattr(v, "modo", "") or "").lower()
                return "tarjeta" if raw.startswith("tarj") else "efectivo"
            ventas = [v for v in ventas if _forma(v) == forma_txt]

        # Filtro por texto
        q = (self.txt_buscar.text() or "").strip().lower()
        if q:
            def _match(v):
                nro = str(getattr(v, "numero_ticket", "") or getattr(v, "id", ""))
                return q in nro.lower()
            ventas = [v for v in ventas if _match(v)]

        # Rellenar tabla
        self._ventas_cache = ventas
        self._pintar_tabla()

    def _pintar_tabla(self):
        # Asegurar 13 columnas y headers (por si no se hizo en __init__)
        if self.tbl.columnCount() != 13:
            self.tbl.setColumnCount(13)
            self.tbl.setHorizontalHeaderLabels([
                "Nº Ticket", "Fecha/Hora", "Sucursal", "Forma Pago",
                "Cuotas", "Interés", "Descuento", "Monto x cuota",
                "Total", "Pagado", "Vuelto", "Comentario", "ID"
            ])

        self.tbl.setRowCount(0)

        total = 0.0
        tot_efectivo = 0.0
        tot_tarjeta  = 0.0

        for v in self._ventas_cache:
            row = self.tbl.rowCount()
            self.tbl.insertRow(row)

            # Campos base
            nro = str(getattr(v, "numero_ticket", "") or getattr(v, "id", ""))
            fch = getattr(v, "fecha", None)
            hora = fch.strftime("%Y-%m-%d %H:%M") if fch else ""
            suc = getattr(v, "sucursal", "") or ""

            forma_raw = (getattr(v, "forma_pago", "") or getattr(v, "modo_pago", "") or getattr(v, "modo", "") or "").lower()
            forma = "Tarjeta" if forma_raw.startswith("tarj") else "Efectivo"

            try:
                cuotas = int(getattr(v, "cuotas", 0) or 0)
            except Exception:
                cuotas = 0

            try:
                tot = float(getattr(v, "total", 0.0) or 0.0)
            except Exception:
                tot = 0.0

            total += tot
            if forma == "Tarjeta":
                tot_tarjeta += tot
            else:
                tot_efectivo += tot

            try:
                interes = float(_get_any(v, ["interes_monto", "interes", "monto_interes"], 0.0) or 0.0)
            except Exception:
                interes = 0.0
            try:
                descuento = float(_get_any(v, ["descuento_monto", "descuento", "monto_descuento"], 0.0) or 0.0)
            except Exception:
                descuento = 0.0
                
            monto_cuota = (tot / cuotas) if (forma == "Tarjeta" and cuotas) else 0.0
            
            

            # Pagado / Vuelto (solo efectivo)
            pagado_txt = "-"
            vuelto_txt = "-"
            if forma == "Efectivo":
                try:
                    pv = getattr(v, "pagado", None)
                    vv = getattr(v, "vuelto", None)
                    if pv is not None:
                        pagado_txt = f"${float(pv):.2f}"
                    if vv is not None:
                        vuelto_txt = f"${float(vv):.2f}"
                except Exception:
                    pass

            # Comentario
            coment = self._obtener_comentario(v)

            # Orden EXACTO de columnas (coincide con headers)
            data = [
                nro,                                  # Nº Ticket
                hora,                                 # Fecha/Hora
                suc,                                  # Sucursal
                forma,                                # Forma Pago
                (str(cuotas) if cuotas else "-"),     # Cuotas
                (f"${interes:.2f}" if interes else "-"),      # Interés
                (f"${descuento:.2f}" if descuento else "-"),  # Descuento
                (f"${monto_cuota:.2f}" if monto_cuota else "-"),  # Monto x cuota
                f"${tot:.2f}",                        # Total
                pagado_txt,                           # Pagado
                vuelto_txt,                           # Vuelto
                coment,                               # Comentario
                str(getattr(v, "id", ""))             # ID
            ]

            for c, val in enumerate(data):
                it = QTableWidgetItem(val)
                it.setTextAlignment(Qt.AlignCenter)
                self.tbl.setItem(row, c, it)

        # Resumen inferior
        self.lbl_resumen.setText(
            f"{len(self._ventas_cache)} ventas — Efectivo ${tot_efectivo:.2f} — Tarjeta ${tot_tarjeta:.2f} — Total ${total:.2f}"
        )

        # Ocultar ID (última columna)
        self.tbl.setColumnHidden(12, True)

    def _obtener_comentario(self, v) -> str:
        # 1) Atributos directos de la venta
        for k in ("comentario", "motivo", "nota"):
            val = getattr(v, k, None)
            if val:
                return str(val)

        # 2) Logs del repositorio (nombres alternativos)
        vid = getattr(v, "id", None)
        if not vid:
            return ""
        for fn in ("obtener_ultimo_log", "ult_log"):
            try:
                if hasattr(self.repo, fn):
                    ult = getattr(self.repo, fn)(vid)
                    if ult:
                        # objeto / dict / string
                        for k in ("texto", "comentario", "motivo", "nota"):
                            if hasattr(ult, k):
                                val = getattr(ult, k)
                                if val:
                                    return str(val)
                        if isinstance(ult, dict):
                            for k in ("texto", "comentario", "motivo", "nota"):
                                if ult.get(k):
                                    return str(ult[k])
                        return str(ult)
            except Exception:
                pass

        # 3) Lista de logs completa (si existe)
        try:
            if hasattr(self.repo, "listar_logs"):
                logs = self.repo.listar_logs(vid) or []
                if logs:
                    ult = logs[-1]
                    for k in ("texto", "comentario", "motivo", "nota"):
                        if hasattr(ult, k):
                            val = getattr(ult, k)
                            if val:
                                return str(val)
                    if isinstance(ult, dict):
                        for k in ("texto", "comentario", "motivo", "nota"):
                            if ult.get(k):
                                return str(ult[k])
                    return str(ult)
        except Exception:
            pass

        # 4) Fallback directo a la DB (si está el modelo)
        try:
            from app.models import VentaLog
            q = self.session.query(VentaLog).filter_by(venta_id=vid)
            try:
                q = q.order_by(VentaLog.id.desc())
            except Exception:
                pass
            log = q.first()
            if log:
                for k in ("texto", "comentario", "motivo", "nota", "mensaje"):
                    if hasattr(log, k):
                        val = getattr(log, k)
                        if val:
                            return str(val)
        except Exception:
            pass

        return ""
    # ------------------- Exportar / enviar -------------------
    def _armar_dataframe(self) -> pd.DataFrame:
        rows = []
        for v in self._ventas_cache:
            forma_raw = (getattr(v, "forma_pago", "") or getattr(v, "modo_pago", "") or getattr(v, "modo", "") or "").lower()
            forma = "Tarjeta" if forma_raw.startswith("tarj") else "Efectivo"
            rows.append({
                "ticket":   getattr(v, "numero_ticket", None) or getattr(v, "id", None),
                "fecha":    getattr(v, "fecha", None),
                "sucursal": getattr(v, "sucursal", "") or "",
                "forma":    forma,
                "cuotas":   int(getattr(v, "cuotas", 0) or 0),
                "total":    float(getattr(v, "total", 0.0) or 0.0),
                "pagado":   float(getattr(v, "pagado", 0.0) or 0.0),
                "vuelto":   float(getattr(v, "vuelto", 0.0) or 0.0),
                "comentarios": self._obtener_comentario(v),
                "interes":   float(_get_any(v, ["interes_monto", "interes", "monto_interes"], 0.0) or 0.0),
                "descuento": float(_get_any(v, ["descuento_monto", "descuento", "monto_descuento"], 0.0) or 0.0),
                "monto_cuota": (
                    (float(getattr(v, "total", 0.0) or 0.0) / int(getattr(v, "cuotas", 0) or 0))
                    if (str((getattr(v, "forma_pago", "") or getattr(v, "modo_pago", "") or getattr(v, "modo", "")).lower()).startswith("tarj")
                        and int(getattr(v, "cuotas", 0) or 0) > 0)
                    else 0.0
                ),
            })
        return pd.DataFrame(rows)


    def _autofit_sheet(ws, df, engine_name: str):
        # Calcula un ancho aproximado según el contenido
        def _maxlen(series):
            try:
                return max([len(str(series.name))] + [len(str(x)) for x in series.astype(str).tolist()])
            except Exception:
                return 12
        if "openpyxl" in (engine_name or "").lower():
            from openpyxl.utils import get_column_letter
            for i, col in enumerate(df.columns, start=1):
                width = min(max(10, _maxlen(df[col]) + 2), 60)
                ws.column_dimensions[get_column_letter(i)].width = width
        else:  # xlsxwriter
            for i, col in enumerate(df.columns):
                width = min(max(10, _maxlen(df[col]) + 2), 60)
                try:
                    ws.set_column(i, i, width)
                except Exception:
                    pass

    



    # historialventas.py
    def _armar_dataframe_items(self) -> pd.DataFrame:
        items_rows = []
        for v in self._ventas_cache:
            vid = getattr(v, "id", None)
            if not vid:
                continue

            # 1) Intento por el repo
            try:
                items = self.repo.listar_items(vid)
            except Exception:
                items = []

            # 2) Fallback directo a la DB si el repo no trae nada
            if not items:
                try:
                    from app.models import VentaItem
                    items = self.session.query(VentaItem).filter_by(venta_id=vid).all()
                except Exception:
                    items = []

            # 3) Normalización por ítem
            for it in items:
                prod = getattr(it, "producto", None)

                # Categoría (si existe)
                cat = getattr(prod, "categoria", "") if prod else ""

                # Código (varios alias) + fallback a producto
                codigo = (
                    getattr(it, "codigo", None)
                    or getattr(it, "codigo_barra", None)
                    or getattr(it, "producto_codigo", None)
                )
                if not codigo and prod:
                    codigo = getattr(prod, "codigo_barra", "") or getattr(prod, "codigo", "")

                # Nombre (varios alias) + fallback a producto
                nombre = getattr(it, "nombre", None)
                if not nombre and prod:
                    nombre = getattr(prod, "nombre", "") or getattr(prod, "descripcion", "")

                # Cantidad
                try:
                    cant = float(getattr(it, "cantidad", 1) or 1)
                except Exception:
                    cant = 1.0

                # Precio unitario (varios alias)
                try:
                    pu = float(
                        getattr(it, "precio_unitario",
                            getattr(it, "precio_unit",
                                getattr(it, "precio", 0.0)
                            )
                        ) or 0.0
                    )
                except Exception:
                    pu = 0.0

                items_rows.append({
                    "venta_id": vid,
                    "ticket": getattr(v, "numero_ticket", None) or vid,
                    "codigo": codigo or "",
                    "nombre": nombre or "",
                    "categoria": cat,
                    "cantidad": cant,
                    "precio_unitario": pu,
                    "total_linea": cant * pu
                })

        return pd.DataFrame(items_rows)


    def _exportar_a_xlsx_local(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Guardar Excel", "historial.xlsx", "Excel (*.xlsx)"
        )
        if not path:
            return

        # Asegurar extensión .xlsx
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"

        try:
            out_path = self._crear_excel(path)
            QMessageBox.information(self, "Exportar", f"Guardado:\n{out_path}")
        except Exception as e:
            QMessageBox.warning(
                self, "Exportar",
                "No se pudo crear el archivo XLSX.\n\n"
                f"Detalle: {e}\n\n"
                "Probá actualizar dependencias:\n"
                "  pip install -U pandas openpyxl XlsxWriter"
            )
    
    def _crear_excel(self, path: str, for_freq: Optional[str] = None) -> str:
        import pandas as pd, os
        df  = self._armar_dataframe()

        # Si el caller pide contenido específico (programación), consultamos config
        cfg = load_config()
        rep = (cfg.get("reports") or {}).get("historial") or {}
        excel_content = rep.get("excel_content") or rep.get("export_content") or {}

        # Mantener el checkbox para items cuando es envío manual;
        # para auto (for_freq) también respetamos si el usuario lo tilda.
        inc = self.chk_incluir_items.isChecked()
        dfi = self._armar_dataframe_items() if inc else None

        # Writer
        xw = _make_writer(path)
        if xw is None:
            base, _ = os.path.splitext(path)
            csv1 = base + ".csv"
            df.to_csv(csv1, index=False, encoding="utf-8-sig")
            if dfi is not None and not dfi.empty:
                dfi.to_csv(base + "_items.csv", index=False, encoding="utf-8-sig")
            try:
                QMessageBox.warning(
                    self, "Exportar",
                    "No se encontró un engine XLSX (openpyxl/xlsxwriter). Guardé CSV.\n"
                    "Para XLSX instalá (o actualizá):\n"
                    "  pip install -U openpyxl\n  o bien:\n  pip install -U XlsxWriter"
                )
            except Exception:
                pass
            return csv1

        try:
            with xw:
                # --- Hoja Ventas (siempre) ---
                df.to_excel(xw, index=False, sheet_name="Ventas")

                # Ajustes de ancho
                ws = None
                try:
                    ws = xw.sheets.get("Ventas") if hasattr(xw, "sheets") else None
                except Exception:
                    ws = None
                if ws is None:
                    try:
                        wb = getattr(xw, "book", None)
                        if wb is not None:
                            ws = wb["Ventas"]
                    except Exception:
                        ws = None

                _engine = (getattr(xw, "engine", "") or getattr(xw, "_engine", "")).lower()
                if ws is not None:
                    _autofit_sheet(ws, df, _engine)

                # --- Resumen al pie ---
                desde = self.dt_desde.date().toString("yyyy-MM-dd")
                hasta = self.dt_hasta.date().toString("yyyy-MM-dd")
                n = len(df.index)
                if not df.empty and "forma" in df.columns:
                    g = df.groupby("forma", dropna=False)["total"].sum()
                    tot_eff = float(g.get("Efectivo", 0.0))
                    tot_tar = float(g.get("Tarjeta",  0.0))
                    tot_all = float(df["total"].sum())
                else:
                    tot_eff = tot_tar = tot_all = 0.0

                resumen = pd.DataFrame([
                    [f"Total vendido entre {desde} y {hasta}", ""],
                    ["Efectivo", f"{tot_eff:.2f}"],
                    ["Tarjeta",  f"{tot_tar:.2f}"],
                    ["TOTAL",    f"{tot_all:.2f}"],
                ], columns=["Detalle", "Monto"])
                resumen.to_excel(xw, index=False, header=True, sheet_name="Ventas", startrow=n + 2)
                if ws is not None:
                    try:
                        _autofit_sheet(ws, resumen, _engine)
                    except Exception:
                        pass

                # --- Hojas adicionales según contenido configurado ---
                # Mapear "Diario/Semanal/Mensual" a llaves (aceptamos también español).
                freq_key = None
                if for_freq:
                    f = (for_freq or "").strip().lower()
                    if "diar" in f or f == "daily":
                        freq_key = "daily"
                    elif "seman" in f or f == "weekly":
                        freq_key = "weekly"
                    elif "mensu" in f or f == "monthly":
                        freq_key = "monthly"

                requested = (excel_content.get(freq_key) if freq_key else None) or []

                # Productos Vendidos (si se pidió por config o si el usuario marcó incluir items)
                need_products = ("productos_mas_vendidos" in requested) or (inc and dfi is not None and not dfi.empty)
                if need_products and dfi is not None and not dfi.empty:
                    cols = [c for c in ("categoria", "codigo", "nombre", "cantidad", "total_linea") if c in dfi.columns]
                    agg = dfi[cols].copy()
                    if "categoria" not in agg.columns:
                        agg["categoria"] = ""
                    prod = (agg.groupby(["categoria", "codigo", "nombre"], dropna=False)
                            .agg(cantidad=("cantidad", "sum"), monto=("total_linea", "sum"))
                            .reset_index()
                            .sort_values(["categoria", "nombre"]))
                    prod.to_excel(xw, index=False, sheet_name="Productos Vendidos")
                    try:
                        ws_prod = xw.sheets.get("Productos Vendidos")
                    except Exception:
                        ws_prod = None
                    if ws_prod is not None:
                        _autofit_sheet(ws_prod, prod, _engine)

                # (Opcional) Aquí podrías agregar otras hojas si luego definimos
                # "ventas_diarias", "resumen_semanal", "ventas_semanales" con dataframes específicos.

            # Verificación final (archivo debe existir y tener >0 bytes)
            if not os.path.exists(path) or os.path.getsize(path) <= 0:
                base, _ = os.path.splitext(path)
                csv1 = base + ".csv"
                df.to_csv(csv1, index=False, encoding="utf-8-sig")
                if dfi is not None and not dfi.empty:
                    dfi.to_csv(base + "_items.csv", index=False, encoding="utf-8-sig")
                raise IOError("El XLSX quedó vacío; se guardó CSV como respaldo.")

            return path

        except Exception as e:
            base, _ = os.path.splitext(path)
            csv1 = base + ".csv"
            try:
                df.to_csv(csv1, index=False, encoding="utf-8-sig")
                if dfi is not None and not dfi.empty:
                    dfi.to_csv(base + "_items.csv", index=False, encoding="utf-8-sig")
            finally:
                pass
            try:
                QMessageBox.warning(
                    self, "Exportar",
                    "Hubo un problema al guardar el XLSX. Guardé CSV como respaldo.\n\n"
                    f"Detalle: {e}\n\n"
                    "Sugerencia:\n  pip install -U pandas openpyxl XlsxWriter"
                )
            except Exception:
                pass
            return csv1



        


    def _exportar_y_enviar(self, for_freq: Optional[str] = None):
        cfg = load_config()
        e = (cfg.get("email") or {})

        # Destinatarios desde config
        recipients = list(filter(None, e.get("recipients") or []))
        if not recipients:
            QMessageBox.warning(self, "Correo", "Agregá al menos un destinatario en Configuración → Email.")
            return

        # Excel temporal con los filtros actuales
        tmpdir = tempfile.gettempdir()
        fname = f"historial_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        fpath = os.path.join(tmpdir, fname)
        self._crear_excel(fpath, for_freq=for_freq)

        # Enviar
        try:
            subj_prefix = (e.get("subject_prefix") or "[Historial]")
            subj = f"{subj_prefix} Ventas {self.dt_desde.date().toString('yyyy-MM-dd')} a {self.dt_hasta.date().toString('yyyy-MM-dd')}"
            body = "Se adjunta el reporte con los filtros aplicados."
            _send_mail_with_attachments(subj, body, recipients, [fpath])
            QMessageBox.information(self, "Correo", "Enviado.")
        except Exception as ex:
            QMessageBox.warning(self, "Correo", f"No se pudo enviar:\n{ex}")



    # ------------------- Detalle de venta -------------------
    def _ver_detalle_venta(self, row: int, col: int):
        it = self.tbl.item(row, self.tbl.columnCount() - 1)  # ID oculto
        if not it:
            return
        try:
            venta_id = int(it.text())
        except Exception:
            return

        dlg = _VentaDetalleDialog(self.session, venta_id, self)
        dlg.exec_()


class _VentaDetalleDialog(QDialog):
    def __init__(self, session, venta_id: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Detalle venta #{venta_id}")
        self.resize(680, 400)
        lay = QVBoxLayout(self)

        tbl = QTableWidget(0, 6)
        tbl.setHorizontalHeaderLabels(["Código", "Nombre", "Cantidad", "P. Unit.", "Total línea", "Venta ID"])
        tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        tbl.verticalHeader().setVisible(False)
        lay.addWidget(tbl)

        repo = VentaRepo(session)   # :contentReference[oaicite:10]{index=10}
        try:
            items = repo.listar_items(venta_id)
        except Exception:
            items = session.query(VentaItem).filter_by(venta_id=venta_id).all()

        for it in items:
            row = tbl.rowCount()
            tbl.insertRow(row)

            # Código
            codigo = getattr(it, "codigo", None) or getattr(it, "codigo_barra", None) or ""
            if not codigo:
                prod = getattr(it, "producto", None)
                if prod:
                    codigo = getattr(prod, "codigo_barra", "") or getattr(prod, "codigo", "") or ""

            # Nombre
            nombre = getattr(it, "nombre", None)
            if not nombre:
                prod = getattr(it, "producto", None)
                if prod:
                    nombre = getattr(prod, "nombre", "") or getattr(prod, "descripcion", "")

            # Cantidad / P.Unit
            try:
                cant = float(getattr(it, "cantidad", 1) or 1)
            except Exception:
                cant = 1.0
            try:
                pu = float(
                    getattr(it, "precio_unitario",
                        getattr(it, "precio_unit",
                            getattr(it, "precio", 0.0)
                        )
                    ) or 0.0
                )
            except Exception:
                pu = 0.0

            tot_linea = cant * pu
            data = [codigo, nombre, f"{cant:.2f}", f"{pu:.2f}", f"{tot_linea:.2f}", str(venta_id)]
            for c, val in enumerate(data):
                cell = QTableWidgetItem(val)
                cell.setTextAlignment(Qt.AlignCenter)
                tbl.setItem(row, c, cell)

        tbl.setColumnHidden(5, True)