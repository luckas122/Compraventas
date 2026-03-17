# -*- coding: utf-8 -*-


class TicketTemplatesMixin:
    """
    Mixin con los metodos de gestion de plantillas de ticket (_tpl_*).
    Extraido de ConfiguracionMixin para mantener archivos mas cortos.
    """

# Capturar el widget interno y actualizar (el slot esta en QPrintPreviewWidget)
    def _init_preview_widget(self):
        from PyQt5.QtPrintSupport import QPrintPreviewWidget
        try:
            self._tpl_prev_widget = self._tpl_prev_dlg.findChild(QPrintPreviewWidget)
            if self._tpl_prev_widget:
                self._tpl_prev_widget.updatePreview()
        except Exception:
            pass


#---Plantillas de ticket (todos los _tpl_*):

   # ----------------- Plantillas: slots -----------------
    def _tpl_build_slot_combo(self):
        from app.config import load as load_config
        cfg = load_config()
        tk = (cfg.get("ticket") or {})
        slots = (tk.get("slots") or {})
        slot_names = (tk.get("slot_names") or {})
        self.cfg_tpl_slot.clear()

        # Soporta hasta 10 slots con nombres editables
        for key in tuple(f"slot{i}" for i in range(1, 11)):
            # Obtener nombre personalizado o usar fallback
            label = slot_names.get(key, f"Plantilla {key[-1]}")
            txt = (slots.get(key) or "").strip()
            mark = " •" if txt else " (vacía)"
            self.cfg_tpl_slot.addItem(label + mark, key)

    # Mapeo de claves de config → atributo del combo en self
    _TPL_COMBO_MAP = {
        "template_efectivo": "cfg_tpl_efectivo",
        "template_tarjeta": "cfg_tpl_tarjeta",
        "template_factura_a": "cfg_tpl_factura_a",
        "template_factura_b": "cfg_tpl_factura_b",
        "template_cae_efectivo": "cfg_tpl_cae_efectivo",
        "template_cae_tarjeta": "cfg_tpl_cae_tarjeta",
        "template_consumidor_final": "cfg_tpl_consumidor_final",
    }

    def _tpl_build_payment_combos(self):
        """Construye los combos para seleccionar plantilla por forma de pago / tipo."""
        from app.config import load as load_config
        cfg = load_config()
        tk = (cfg.get("ticket") or {})
        slot_names = (tk.get("slot_names") or {})

        all_combos = []
        for cfg_key, attr in self._TPL_COMBO_MAP.items():
            combo = getattr(self, attr, None)
            if combo is not None:
                all_combos.append((cfg_key, combo))

        # Desconectar señales temporalmente
        for _, combo in all_combos:
            try:
                combo.currentIndexChanged.disconnect(self._tpl_save_payment_selection)
            except Exception:
                pass

        # Limpiar y rellenar todos los combos
        for cfg_key, combo in all_combos:
            combo.clear()
            # Los nuevos combos tienen opción "(Sin asignar)" excepto efectivo/tarjeta
            if cfg_key not in ("template_efectivo", "template_tarjeta"):
                combo.addItem("(Sin asignar)", "")
            for key in tuple(f"slot{i}" for i in range(1, 11)):
                label = slot_names.get(key, f"Plantilla {key[-1]}")
                combo.addItem(label, key)

        # Seleccionar valores desde config
        defaults = {"template_efectivo": "slot1", "template_tarjeta": "slot3"}
        for cfg_key, combo in all_combos:
            saved = tk.get(cfg_key, defaults.get(cfg_key, ""))
            for i in range(combo.count()):
                if combo.itemData(i) == saved:
                    combo.setCurrentIndex(i)
                    break

        # Reconectar señales
        for _, combo in all_combos:
            combo.currentIndexChanged.connect(self._tpl_save_payment_selection)

    def _tpl_save_payment_selection(self):
        """Guarda automáticamente la selección de plantilla por tipo de operación."""
        from app.config import load as load_config, save as save_config

        try:
            cfg = load_config()
            tk = cfg.get("ticket") or {}

            for cfg_key, attr in self._TPL_COMBO_MAP.items():
                combo = getattr(self, attr, None)
                if combo is not None:
                    tk[cfg_key] = combo.currentData() or ""

            cfg["ticket"] = tk
            save_config(cfg)
            self.statusBar().showMessage("Seleccion de plantilla guardada", 1500)
        except Exception:
            pass

    def _tpl_insert(self, snippet: str):
        """Inserta texto en el cursor actual del editor de plantilla."""
        cursor = self.cfg_txt_tpl.textCursor()
        cursor.insertText(snippet)
        self.cfg_txt_tpl.setTextCursor(cursor)

    def _tpl_insert_wrapped(self, tag: str):
            edit = getattr(self, "cfg_txt_tpl", None)
            if not edit:
                return
            cur = edit.textCursor()
            if cur.hasSelection():
                txt = cur.selectedText()
                cur.insertText(f"{{{{{tag}: {txt}}}}}")
            else:
                cur.insertText(f"{{{{{tag}: TU TEXTO}}}}")
            edit.setTextCursor(cur)
            edit.setFocus()

    def _tpl_load_from_slot(self):
        from app.config import load as load_config
        cfg = load_config()
        tk = (cfg.get("ticket") or {})
        key = self.cfg_tpl_slot.currentData()
        txt = (tk.get("slots", {}).get(key) or "").strip()
        if txt:
            self.cfg_txt_tpl.setPlainText(txt)
        else:
            self.statusBar().showMessage("El slot seleccionado está vacío.", 3000)

    def _tpl_open_live_preview(self):
        from PyQt5.QtCore import Qt, QTimer
        from PyQt5.QtPrintSupport import QPrinter, QPrintPreviewDialog, QPrintPreviewWidget
        from PyQt5.QtGui import QPainter
        from app.gui.ventas_helpers import _draw_ticket
        from app.config import load as load_config

        cfg = load_config()
        suc = "Sarmiento"
        dirs = (cfg.get("business") or {}).get("sucursales", {}) or {}

        # 1) Mantener REFERENCIAS -> evita GC y cierres
        self._tpl_prev_printer = QPrinter(QPrinter.HighResolution)
        self._tpl_prev_printer.setOrientation(QPrinter.Portrait)

        self._tpl_prev_dlg = QPrintPreviewDialog(self._tpl_prev_printer, self)
        self._tpl_prev_dlg.setWindowTitle("Vista previa del ticket (live)")
        self._tpl_prev_dlg.setWindowModality(Qt.NonModal)

        def _paint(prn):
            p = QPainter(prn)
            try:
                _draw_ticket(
                    p, prn.pageRect(), prn,
                    self._fake_venta_for_preview(),
                    sucursal=suc,
                    direcciones=dirs,
                    template_override=self.cfg_txt_tpl.toPlainText().strip()
                )
            finally:
                if p.isActive():
                    p.end()

        self._tpl_paint_cb = _paint
        self._tpl_prev_dlg.paintRequested.connect(self._tpl_paint_cb)

        # 2) Al cerrar: limpiar señales y referencias
        def _on_closed(*_):
            try:
                # Desconectar la señal de textChanged para evitar errores
                self.cfg_txt_tpl.textChanged.disconnect(self._tpl_on_text_changed_preview)
            except Exception:
                pass
            self._tpl_prev_widget = None
            self._tpl_prev_dlg = None
            self._tpl_prev_printer = None
            self._tpl_paint_cb = None

        self._tpl_prev_dlg.finished.connect(_on_closed)

        # 3) Mostrar (no modal) y forzar primer render al WIDGET interno
        self._tpl_prev_dlg.show()



        # usando singleShot para asegurar que el widget ya fue creado
        QTimer.singleShot(0, self._init_preview_widget)

        # 4) Refrescar en vivo cuando cambia el texto del editor
        def _refresh_if_open():
            try:
                if getattr(self, "_tpl_prev_widget", None) and self._tpl_prev_widget.isVisible():
                    self._tpl_prev_widget.updatePreview()
            except Exception:
                pass

        # Evitar conexiones duplicadas
        try:
            self.cfg_txt_tpl.textChanged.disconnect(self._tpl_on_text_changed_preview)
        except Exception:
            pass
        self._tpl_on_text_changed_preview = _refresh_if_open
        self.cfg_txt_tpl.textChanged.connect(self._tpl_on_text_changed_preview)

    def _tpl_preview(self):
        """
        Genera un ticket de prueba y abre la previsualización usando
        el texto actual del editor, sin necesidad de guardar.
        """

        from app.config import load as load_config
        from app.gui.ventas_helpers import imprimir_ticket
        cfg = load_config()
        suc = "Sarmiento"
        dirs = (cfg.get("business") or {}).get("sucursales", {}) or {}
        # Usamos exactamente el texto que está editando el usuario
        template_text = self.cfg_txt_tpl.toPlainText().strip()
        v = self._fake_venta_for_preview()
        try:
            # si tu imprimir_ticket acepta template_override
            imprimir_ticket(v, sucursal=suc, direcciones=dirs, parent=self,
                            preview=True, template_override=template_text)
        except TypeError:
            # compatibilidad con versión que no soporta template_override
            imprimir_ticket(v, sucursal=suc, direcciones=dirs, parent=self, preview=True)

    def _tpl_save_to_slot(self):
        from app.config import load as load_config, save as save_config
        cfg = load_config()
        tk = cfg.get("ticket") or {}
        slots = tk.get("slots") or {}
        key = self.cfg_tpl_slot.currentData()
        slots[key] = self.cfg_txt_tpl.toPlainText()
        tk["slots"] = slots

        # Guardar todas las selecciones de plantilla por tipo
        for cfg_key, attr in self._TPL_COMBO_MAP.items():
            combo = getattr(self, attr, None)
            if combo is not None:
                tk[cfg_key] = combo.currentData() or ""

        cfg["ticket"] = tk
        save_config(cfg)
        self._tpl_build_slot_combo()
        self._tpl_build_payment_combos()
        self.statusBar().showMessage("Plantilla guardada en el slot.", 3000)

    def _tpl_rename_slot(self):
        """Permite renombrar una plantilla."""
        from PyQt5.QtWidgets import QInputDialog
        from app.config import load as load_config, save as save_config

        cfg = load_config()
        tk = cfg.get("ticket") or {}
        slot_names = tk.get("slot_names") or {}
        key = self.cfg_tpl_slot.currentData()

        # Obtener nombre actual
        current_name = slot_names.get(key, f"Plantilla {key[-1]}")

        # Pedir nuevo nombre
        new_name, ok = QInputDialog.getText(
            self,
            "Renombrar plantilla",
            f"Nuevo nombre para {current_name}:",
            text=current_name
        )

        if ok and new_name.strip():
            # Guardar nuevo nombre
            if "slot_names" not in tk:
                tk["slot_names"] = {}
            tk["slot_names"][key] = new_name.strip()
            cfg["ticket"] = tk
            save_config(cfg)

            # Actualizar UI (tanto el combo de slots como los de pago)
            self._tpl_build_slot_combo()
            self._tpl_build_payment_combos()
            self.statusBar().showMessage(f"Plantilla renombrada a: {new_name.strip()}", 3000)

    def _tpl_restore_defaults(self):
        """Restaura el slot seleccionado a su plantilla predeterminada de DEFAULTS."""
        from PyQt5.QtWidgets import QMessageBox
        from app.config import load as load_config, save as save_config, DEFAULTS

        key = self.cfg_tpl_slot.currentData()
        if not key:
            return

        default_slots = (DEFAULTS.get("ticket") or {}).get("slots") or {}
        default_text = default_slots.get(key, "")

        if not default_text:
            QMessageBox.information(
                self, "Restaurar",
                f"No hay plantilla predeterminada para {key}."
            )
            return

        resp = QMessageBox.question(
            self, "Restaurar Predeterminados",
            f"Se reemplazara el contenido del editor con la plantilla "
            f"predeterminada para '{key}'.\n\n"
            f"El cambio se aplica solo al editor. Para guardarlo en el slot, "
            f"usa 'Guardar en slot'.\n\n"
            f"Continuar?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if resp == QMessageBox.Yes:
            self.cfg_txt_tpl.setPlainText(default_text)
            self.statusBar().showMessage(
                f"Editor restaurado con la plantilla predeterminada de {key}.", 3000
            )
