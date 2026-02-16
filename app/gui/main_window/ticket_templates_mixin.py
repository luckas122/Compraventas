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

        # Soporta 4 slots ahora, con nombres editables
        for key in ("slot1", "slot2", "slot3", "slot4"):
            # Obtener nombre personalizado o usar fallback
            label = slot_names.get(key, f"Plantilla {key[-1]}")
            txt = (slots.get(key) or "").strip()
            mark = " •" if txt else " (vacía)"
            self.cfg_tpl_slot.addItem(label + mark, key)

    def _tpl_build_payment_combos(self):
        """Construye los combos para seleccionar plantilla por forma de pago."""
        from app.config import load as load_config
        cfg = load_config()
        tk = (cfg.get("ticket") or {})
        slot_names = (tk.get("slot_names") or {})

        # Desconectar señales temporalmente para evitar guardados durante la reconstrucción
        try:
            self.cfg_tpl_efectivo.currentIndexChanged.disconnect(self._tpl_save_payment_selection)
            self.cfg_tpl_tarjeta.currentIndexChanged.disconnect(self._tpl_save_payment_selection)
        except Exception:
            pass  # Si no estaban conectadas, ignorar

        # Limpiar y rellenar ambos combos
        for combo in (self.cfg_tpl_efectivo, self.cfg_tpl_tarjeta):
            combo.clear()
            for key in ("slot1", "slot2", "slot3", "slot4"):
                label = slot_names.get(key, f"Plantilla {key[-1]}")
                combo.addItem(label, key)

        # Seleccionar los valores actuales desde config
        efectivo_slot = tk.get("template_efectivo", "slot1")
        tarjeta_slot = tk.get("template_tarjeta", "slot3")

        # Buscar índice y seleccionar
        for i in range(self.cfg_tpl_efectivo.count()):
            if self.cfg_tpl_efectivo.itemData(i) == efectivo_slot:
                self.cfg_tpl_efectivo.setCurrentIndex(i)
                break

        for i in range(self.cfg_tpl_tarjeta.count()):
            if self.cfg_tpl_tarjeta.itemData(i) == tarjeta_slot:
                self.cfg_tpl_tarjeta.setCurrentIndex(i)
                break

        # Reconectar las señales
        self.cfg_tpl_efectivo.currentIndexChanged.connect(self._tpl_save_payment_selection)
        self.cfg_tpl_tarjeta.currentIndexChanged.connect(self._tpl_save_payment_selection)

    def _tpl_save_payment_selection(self):
        """Guarda automáticamente la selección de plantilla por forma de pago."""
        from app.config import load as load_config, save as save_config

        try:
            cfg = load_config()
            tk = cfg.get("ticket") or {}

            # Guardar las selecciones actuales
            tk["template_efectivo"] = self.cfg_tpl_efectivo.currentData()
            tk["template_tarjeta"] = self.cfg_tpl_tarjeta.currentData()

            cfg["ticket"] = tk
            save_config(cfg)

            # Opcional: mostrar confirmación breve
            self.statusBar().showMessage("Selección de plantilla guardada", 1500)
        except Exception as e:
            # Si falla, no mostrar error para no interrumpir la experiencia del usuario
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

        # Guardar también las selecciones de plantilla por forma de pago
        tk["template_efectivo"] = self.cfg_tpl_efectivo.currentData()
        tk["template_tarjeta"] = self.cfg_tpl_tarjeta.currentData()

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
