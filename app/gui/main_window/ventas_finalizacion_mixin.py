import sys
import logging

logger = logging.getLogger(__name__)

from PyQt5.QtWidgets import QMessageBox, QDialog
from app.gui.common import icon
from app.models import Producto, Venta, VentaItem


class VentasFinalizacionMixin:
    """Mixin con metodos de pago, finalizacion de venta y emision AFIP."""

    def _on_pago_method_changed(self, checked):
        is_tarj = bool(getattr(self, 'rb_tarjeta', None) and self.rb_tarjeta.isChecked())

        if hasattr(self, 'spin_cuotas'):
            self.spin_cuotas.setEnabled(is_tarj)
        if hasattr(self, 'cuota_label'):
            self.cuota_label.setVisible(is_tarj)

        # Si se selecciono tarjeta, abrir dialogo configuracion
        # NUEVO: Solo abrir si NO hay datos configurados ya
        if is_tarj and checked:
            # Solo abrir dialogo si no esta configurado
            if not (hasattr(self, '_datos_tarjeta') and self._datos_tarjeta):
                self._abrir_dialogo_tarjeta()
        elif not is_tarj:
            # Si se deselecciono tarjeta, limpiar datos
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
        """Abre el dialogo para configurar pago con tarjeta."""
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

                # Aplicar interes si hay
                if datos["interes_pct"] > 0:
                    self._aplicar_interes_a_cesta(datos["interes_pct"])

                logger.info(f"[Tarjeta] Configurado: {datos['cuotas']} cuotas, {datos['interes_pct']}% interes, {datos['tipo_comprobante']}")
                if datos["cuit_cliente"]:
                    logger.info(f"[Tarjeta] CUIT cliente: {datos['cuit_cliente']}")
        else:
            # Usuario cancelo, volver a efectivo
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


    #----Finalizar venta e impresion

    def finalizar_venta(self):
        # Recalcula totales / interes antes de cualquier cosa
        self.actualizar_total()

        if self.table_cesta.rowCount() == 0:
            QMessageBox.warning(self, 'Cesta vacia', 'Agrega al menos un producto.')
            return

        # Efectivo o Tarjeta?
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
            # Usar el nuevo dialogo de pago en efectivo
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

        # Agregar items
        for r in range(self.table_cesta.rowCount()):
            # Validar que las celdas existan antes de acceder
            item_codigo = self.table_cesta.item(r, 0)
            item_cant = self.table_cesta.item(r, 2)
            item_pu = self.table_cesta.item(r, 3)

            if not item_codigo or not item_cant or not item_pu:
                continue  # Saltar filas con celdas vacias

            codigo = item_codigo.text().strip()
            if not codigo:
                continue  # Saltar si no hay codigo

            # Conversiones seguras con try-except
            try:
                cant = int(float(item_cant.text().replace(",", ".").strip() or "0"))
                pu = float(item_pu.text().replace("$", "").replace(",", ".").strip() or "0")
            except (ValueError, AttributeError):
                continue  # Saltar filas con valores invalidos

            if cant <= 0 or pu < 0:
                continue  # Saltar cantidades invalidas

            self.venta_repo.agregar_item(venta.id, codigo, cant, pu)

        # Total en BD y commit
        total_bd = self.venta_repo.actualizar_total(venta.id)
        try:
            venta.subtotal_base   = float(getattr(self, "_subtotal_base", 0.0) or 0.0)
            venta.interes_pct     = float(getattr(self, "_interes_pct", 0.0) or 0.0)
            venta.interes_monto   = float(getattr(self, "_interes_monto", 0.0) or 0.0)
            venta.descuento_pct   = float(getattr(self, "_descuento_pct", 0.0) or 0.0)
            venta.descuento_monto = float(getattr(self, "_descuento_monto", 0.0) or 0.0)
            # El total final mostrado al usuario (subtotal - desc + interes)
            venta.total           = float(getattr(self, "_total_actual", 0.0) or 0.0)
            self.session.commit()
        except Exception:
            # si prefieres mantener el patron del repo
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
                    # Fallback a metodo del repo si existe
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

        # Integracion AFIP / ARCA (solo si esta habilitada en Configuracion)
        # Para efectivo con AFIP, pasar los datos especificos
        if modo == 'Efectivo' and efectivo_emitir_afip:
            self._afip_emitir_si_corresponde(
                venta, modo,
                forzar_afip=True,
                tipo_cbte=efectivo_tipo_cbte,
                cuit_cliente=efectivo_cuit_cliente
            )
        else:
            self._afip_emitir_si_corresponde(venta, modo)

        # Sync: publicar venta en Firebase
        self._sync_push("venta", venta)

        # Guardar ultimo id para exportar a PNG
        self._last_venta_id = venta.id

        # --- Enviar el ticket por WhatsApp Web en lugar de imprimir? ---
        resp = QMessageBox.question(
            self, "Ticket",
            "Enviar el ticket por WhatsApp Web en lugar de imprimir?",
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
        Integra con AFIP/ARCA via AfipSDK si:
          - esta habilitado en Configuracion -> Facturacion
          - y (por defecto) la venta es con tarjeta.
          - O si forzar_afip=True (para efectivo con factura)
        No lanza excepciones hacia afuera: cualquier error se avisa pero no rompe la venta.

        Parametros opcionales:
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

        # Por defecto solo tarjeta; si desmarcas la opcion, tambien facturaria efectivo
        # EXCEPCION: si forzar_afip=True, siempre emitir
        only_card = bool(fisc.get("only_card", True))
        if only_card and modo_pago.lower() != "tarjeta" and not forzar_afip:
            return

        # Intentamos construir los items de forma normalizada
        try:
            items = self._items_para_ticket(venta.id)
        except Exception:
            items = []

        # Cliente AfipSDK
        try:
            from app.afip_integration import crear_cliente_afip
            cfg = _load_cfg()
            # CORRECCION: La seccion se llama "fiscal" no "afip"
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
            logger.error("[AFIP] No se pudo inicializar AfipSDKClient: %s", e)
            return

        # Calcular total, subtotal e IVA para AFIP
        total = float(getattr(venta, 'total', 0.0) or 0.0)
        # Asumimos IVA 21% (puedes ajustar segun tu logica)
        iva_rate = 0.21
        subtotal = round(total / (1.0 + iva_rate), 2)
        iva = round(total - subtotal, 2)

        # Debug: Mostrar configuracion que se esta usando
        logger.debug("[AFIP] Config: enabled=%s, environment=%s, cuit=%s, has_api_key=%s",
                     fiscal_config.get('enabled'), fiscal_config.get('environment'),
                     fiscal_config.get('cuit'), bool(fiscal_config.get('access_token')))

        # Determinar tipo de comprobante y CUIT cliente
        # Prioridad: parametros explicitos > _datos_tarjeta > default
        tipo_comprobante_final = tipo_cbte
        cuit_cliente_final = cuit_cliente

        if not tipo_comprobante_final and hasattr(self, '_datos_tarjeta') and self._datos_tarjeta:
            tipo_comprobante_final = self._datos_tarjeta.get("tipo_comprobante")
            cuit_cliente_final = self._datos_tarjeta.get("cuit_cliente", "")

        logger.debug("[AFIP] Tipo comprobante: %s, CUIT cliente: %s", tipo_comprobante_final, cuit_cliente_final)

        # Emitir factura según tipo de comprobante
        try:
            if tipo_comprobante_final and "FACTURA_A" in str(tipo_comprobante_final).upper():
                # Factura A: requiere CUIT del cliente (11 dígitos)
                cuit = (cuit_cliente_final or "").replace("-", "").strip()
                if not cuit or len(cuit) != 11 or not cuit.isdigit():
                    QMessageBox.warning(
                        self, "AFIP - Factura A",
                        "Para emitir Factura A se requiere un CUIT válido de 11 dígitos.\n"
                        f"CUIT ingresado: '{cuit_cliente_final or '(vacío)'}'"
                    )
                    return
                logger.info(f"[AFIP] Emitiendo Factura A, CUIT cliente: {cuit}")
                response = client.emitir_factura_a(
                    items=items,
                    total=total,
                    subtotal=subtotal,
                    iva=iva,
                    cuit_cliente=cuit
                )
            else:
                # Factura B (default para consumidor final)
                response = client.emitir_factura_b(
                    items=items,
                    total=total,
                    subtotal=subtotal,
                    iva=iva
                )
        except Exception as e:
            logger.error("[AFIP] Error al emitir factura: %s", e, exc_info=True)

            # Mensaje de error mas especifico segun el tipo
            error_msg = str(e)
            if "400" in error_msg or "Bad Request" in error_msg:
                error_detail = (
                    "Error 400: Bad Request\n\n"
                    "Posibles causas:\n"
                    "- API Key invalida o sin permisos\n"
                    "- CUIT no registrado con esta API Key\n"
                    "- Modo (test/prod) incorrecto\n\n"
                    f"Verifica la configuracion en:\n"
                    f"Configuracion -> Facturacion Electronica\n\n"
                    f"CUIT actual: {fiscal_config.get('cuit')}\n"
                    f"Modo: {fiscal_config.get('mode')}\n\n"
                    f"Error tecnico: {error_msg}"
                )
            elif "401" in error_msg or "Unauthorized" in error_msg:
                error_detail = (
                    "Error 401: No autorizado\n\n"
                    "La API Key es invalida o ha expirado.\n"
                    "Verifica en Configuracion -> Facturacion Electronica"
                )
            else:
                error_detail = f"Error al emitir comprobante electronico:\n\n{error_msg}"

            # Guardar el error en la venta para poder reintentar despues
            try:
                venta.afip_error = f"Error AFIP: {error_msg[:500]}"  # Limitar longitud
                self.session.commit()
            except Exception:
                pass

            QMessageBox.warning(
                self,
                "AFIP - Error",
                f"{error_detail}\n\n"
                "La venta fue registrada pero SIN comprobante electronico.\n"
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
                logger.error("[AFIP] Error al guardar CAE: %s", e)

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
                    "AFIP - Factura Electronica",
                    "Comprobante electronico emitido correctamente.\n\n"
                    f"CAE: {response.cae}\n"
                    f"Vencimiento: {response.cae_vencimiento}\n"
                    f"Numero de comprobante: {response.numero_comprobante}"
                )
            else:
                # Guardar el error para poder reintentar despues
                error_msg = response.error_message or "Error desconocido de AFIP"
                try:
                    venta.afip_error = f"AFIP rechazo: {error_msg[:500]}"
                    self.session.commit()
                except Exception:
                    pass

                QMessageBox.warning(
                    self,
                    "AFIP - Error",
                    "No se pudo emitir el comprobante electronico.\n\n"
                    f"Detalle:\n{error_msg}\n\n"
                    "La venta fue registrada pero SIN comprobante electronico.\n"
                    "Puedes reintentar desde el historial de ventas."
                )
        except Exception as e:
            logger.error("[AFIP] Error mostrando mensaje AFIP: %s", e)
