# app/sync_manager.py
"""
Sincronización entre sucursales via Gmail (SMTP + IMAP)
"""
import os
import json
import uuid
import hashlib
import imaplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
from sqlalchemy.orm import Session

from app.models import SyncLog, Venta, VentaItem, Producto, Proveedor
from app.config import load as load_config


class SyncManager:
    """Gestor de sincronización entre sucursales"""

    def __init__(self, session: Session, sucursal_local: str):
        self.session = session
        self.sucursal_local = sucursal_local
        self.config = load_config()
        self.sync_config = self.config.get("sync", {})

    def _generar_sync_id(self) -> str:
        """Genera un ID único para la sincronización"""
        return str(uuid.uuid4())

    def _calcular_hash(self, data: dict) -> str:
        """Calcula hash MD5 del contenido para detectar duplicados"""
        content = json.dumps(data, sort_keys=True)
        return hashlib.md5(content.encode()).hexdigest()

    def detectar_cambios_pendientes(self) -> bool:
        """
        Detecta si hay cambios pendientes de sincronizar.
        Revisa si hay ventas/productos nuevos o modificados desde última sync.
        """
        # Obtener timestamp de última sincronización enviada
        ultima_sync = self.session.query(SyncLog).filter(
            SyncLog.sucursal_origen == self.sucursal_local,
            SyncLog.aplicado == True
        ).order_by(SyncLog.timestamp.desc()).first()

        if not ultima_sync:
            # Primera vez: considerar todo como pendiente si hay datos
            ventas_count = self.session.query(Venta).count()
            productos_count = self.session.query(Producto).count()
            return (ventas_count > 0 or productos_count > 0)

        # Verificar si hay ventas nuevas desde la última sync
        ventas_nuevas = self.session.query(Venta).filter(
            Venta.fecha > ultima_sync.timestamp
        ).count()

        # Por ahora solo sincronizamos ventas nuevas
        # En fase 2 agregaremos productos modificados
        return ventas_nuevas > 0

    def generar_paquete_cambios(self, desde: Optional[datetime] = None) -> Dict:
        """
        Genera un paquete JSON con los cambios a sincronizar.

        Args:
            desde: Fecha desde donde buscar cambios. Si es None, busca desde última sync.

        Returns:
            Dict con estructura: {
                "sync_id": "uuid",
                "sucursal_origen": "Sarmiento",
                "timestamp": "2025-01-15T10:30:00",
                "cambios": [
                    {
                        "tipo": "venta",
                        "accion": "create",
                        "data": {...}
                    }
                ]
            }
        """
        if desde is None:
            # Buscar desde última sincronización
            ultima_sync = self.session.query(SyncLog).filter(
                SyncLog.sucursal_origen == self.sucursal_local
            ).order_by(SyncLog.timestamp.desc()).first()

            if ultima_sync:
                desde = ultima_sync.timestamp
            else:
                # Primera sincronización: últimas 24 horas
                desde = datetime.now() - timedelta(days=1)

        cambios = []

        # 1. Obtener ventas nuevas
        ventas_nuevas = self.session.query(Venta).filter(
            Venta.fecha > desde,
            Venta.sucursal == self.sucursal_local
        ).all()

        for venta in ventas_nuevas:
            # Serializar venta con sus items
            items_data = []
            for item in venta.items:
                items_data.append({
                    "producto_id": item.producto_id,
                    "cantidad": item.cantidad,
                    "precio_unit": item.precio_unit,
                    "codigo_barra": item.producto.codigo_barra if item.producto else None,
                    "nombre": item.producto.nombre if item.producto else None
                })

            venta_data = {
                "id": venta.id,
                "sucursal": venta.sucursal,
                "fecha": venta.fecha.isoformat(),
                "modo_pago": venta.modo_pago,
                "cuotas": venta.cuotas,
                "total": venta.total,
                "subtotal_base": venta.subtotal_base,
                "interes_pct": venta.interes_pct,
                "interes_monto": venta.interes_monto,
                "descuento_pct": venta.descuento_pct,
                "descuento_monto": venta.descuento_monto,
                "pagado": venta.pagado,
                "vuelto": venta.vuelto,
                "numero_ticket": venta.numero_ticket,
                "afip_cae": venta.afip_cae,
                "afip_cae_vencimiento": venta.afip_cae_vencimiento,
                "afip_numero_comprobante": venta.afip_numero_comprobante,
                "items": items_data
            }

            sync_id = self._generar_sync_id()

            cambios.append({
                "sync_id": sync_id,
                "tipo": "venta",
                "accion": "create",
                "data": venta_data,
                "hash": self._calcular_hash(venta_data)
            })

        # Construir paquete completo
        paquete = {
            "sync_id": self._generar_sync_id(),
            "sucursal_origen": self.sucursal_local,
            "timestamp": datetime.now().isoformat(),
            "cambios": cambios
        }

        return paquete

    def enviar_sync_via_gmail(self, paquete: Dict) -> Tuple[bool, Optional[str]]:
        """
        Envía el paquete de sincronización por Gmail.

        Returns:
            (éxito, mensaje_error)
        """
        import smtplib

        smtp_config = self.sync_config.get("gmail_smtp", {})
        host = smtp_config.get("host", "smtp.gmail.com")
        port = int(smtp_config.get("port", 587))
        username = smtp_config.get("username", "")
        password = smtp_config.get("password", "")

        if not username or not password:
            return False, "Credenciales SMTP no configuradas"

        try:
            # Crear mensaje
            msg = MIMEMultipart()
            msg["From"] = username
            msg["To"] = username  # Se envía a sí mismo
            msg["Subject"] = f"[SYNC] {paquete['sucursal_origen']} - {paquete['timestamp'][:19]}"

            # Cuerpo del mensaje
            body = f"""Sincronización automática
Sucursal: {paquete['sucursal_origen']}
Timestamp: {paquete['timestamp']}
Cambios: {len(paquete['cambios'])} registros
"""
            msg.attach(MIMEText(body, "plain"))

            # Adjuntar JSON
            json_data = json.dumps(paquete, indent=2, ensure_ascii=False)
            attachment = MIMEApplication(json_data.encode('utf-8'), Name="sync.json")
            attachment["Content-Disposition"] = f'attachment; filename="sync_{paquete["sync_id"][:8]}.json"'
            msg.attach(attachment)

            # Enviar
            with smtplib.SMTP(host, port, timeout=15) as server:
                server.starttls()
                server.login(username, password)
                server.send_message(msg)

            # Registrar envío en SyncLog
            for cambio in paquete["cambios"]:
                log = SyncLog(
                    sync_id=cambio["sync_id"],
                    tipo=cambio["tipo"],
                    accion=cambio["accion"],
                    timestamp=datetime.fromisoformat(paquete["timestamp"]),
                    aplicado=True,  # Marcado como aplicado porque es local
                    sucursal_origen=self.sucursal_local,
                    data_hash=cambio["hash"]
                )
                self.session.add(log)

            self.session.commit()

            return True, None

        except Exception as e:
            return False, str(e)

    def recibir_sync_via_imap(self) -> Tuple[int, List[str]]:
        """
        Descarga emails de sincronización no leídos desde Gmail.

        Returns:
            (cantidad_procesados, lista_de_errores)
        """
        imap_config = self.sync_config.get("gmail_imap", {})
        host = imap_config.get("host", "imap.gmail.com")
        port = int(imap_config.get("port", 993))
        username = imap_config.get("username", "")
        password = imap_config.get("password", "")

        if not username or not password:
            return 0, ["Credenciales IMAP no configuradas"]

        errores = []
        procesados = 0

        try:
            # Conectar a IMAP
            mail = imaplib.IMAP4_SSL(host, port)
            mail.login(username, password)
            mail.select("INBOX")

            # Buscar emails con [SYNC] en asunto que NO sean de esta sucursal
            status, messages = mail.search(None, 'UNSEEN SUBJECT "[SYNC]"')

            if status != "OK":
                return 0, ["Error buscando emails"]

            email_ids = messages[0].split()

            for email_id in email_ids:
                try:
                    # Descargar email
                    status, msg_data = mail.fetch(email_id, "(RFC822)")

                    if status != "OK":
                        continue

                    # Parsear email
                    raw_email = msg_data[0][1]
                    msg = email.message_from_bytes(raw_email)

                    # Buscar adjunto JSON
                    paquete_data = None
                    for part in msg.walk():
                        if part.get_content_type() == "application/octet-stream":
                            filename = part.get_filename()
                            if filename and filename.endswith(".json"):
                                payload = part.get_payload(decode=True)
                                paquete_data = json.loads(payload.decode('utf-8'))
                                break

                    if paquete_data:
                        # Verificar que no sea de esta sucursal
                        if paquete_data.get("sucursal_origen") != self.sucursal_local:
                            # Aplicar cambios
                            ok, err = self.aplicar_paquete(paquete_data)
                            if ok:
                                procesados += 1
                                # Marcar como leído
                                mail.store(email_id, '+FLAGS', '\\Seen')
                            else:
                                errores.append(f"Error aplicando paquete: {err}")
                        else:
                            # Marcar como leído (es de esta sucursal, ignorar)
                            mail.store(email_id, '+FLAGS', '\\Seen')

                except Exception as e:
                    errores.append(f"Error procesando email {email_id}: {str(e)}")

            mail.close()
            mail.logout()

        except Exception as e:
            errores.append(f"Error conectando a IMAP: {str(e)}")

        return procesados, errores

    def aplicar_paquete(self, paquete: Dict) -> Tuple[bool, Optional[str]]:
        """
        Aplica un paquete de sincronización recibido.

        Returns:
            (éxito, mensaje_error)
        """
        try:
            sucursal_origen = paquete.get("sucursal_origen")

            for cambio in paquete.get("cambios", []):
                sync_id = cambio.get("sync_id")
                tipo = cambio.get("tipo")
                accion = cambio.get("accion")
                data = cambio.get("data")
                data_hash = cambio.get("hash")

                # Verificar si ya fue aplicado
                existe = self.session.query(SyncLog).filter_by(sync_id=sync_id).first()
                if existe:
                    continue  # Ya fue aplicado

                # Aplicar según tipo
                if tipo == "venta" and accion == "create":
                    self._aplicar_venta_nueva(data, sucursal_origen)

                # Registrar en SyncLog
                log = SyncLog(
                    sync_id=sync_id,
                    tipo=tipo,
                    accion=accion,
                    timestamp=datetime.fromisoformat(paquete["timestamp"]),
                    aplicado=True,
                    sucursal_origen=sucursal_origen,
                    data_hash=data_hash
                )
                self.session.add(log)

            self.session.commit()
            return True, None

        except Exception as e:
            self.session.rollback()
            return False, str(e)

    def _aplicar_venta_nueva(self, venta_data: Dict, sucursal_origen: str):
        """Aplica una venta nueva recibida desde otra sucursal"""

        # Verificar que no exista ya (por numero_ticket y sucursal)
        existe = self.session.query(Venta).filter_by(
            numero_ticket=venta_data["numero_ticket"],
            sucursal=venta_data["sucursal"]
        ).first()

        if existe:
            return  # Ya existe, no duplicar

        # Crear nueva venta
        venta = Venta(
            sucursal=venta_data["sucursal"],
            fecha=datetime.fromisoformat(venta_data["fecha"]),
            modo_pago=venta_data["modo_pago"],
            cuotas=venta_data.get("cuotas"),
            total=venta_data["total"],
            subtotal_base=venta_data.get("subtotal_base", 0.0),
            interes_pct=venta_data.get("interes_pct", 0.0),
            interes_monto=venta_data.get("interes_monto", 0.0),
            descuento_pct=venta_data.get("descuento_pct", 0.0),
            descuento_monto=venta_data.get("descuento_monto", 0.0),
            pagado=venta_data.get("pagado"),
            vuelto=venta_data.get("vuelto"),
            numero_ticket=venta_data["numero_ticket"],
            afip_cae=venta_data.get("afip_cae"),
            afip_cae_vencimiento=venta_data.get("afip_cae_vencimiento"),
            afip_numero_comprobante=venta_data.get("afip_numero_comprobante")
        )

        self.session.add(venta)
        self.session.flush()  # Obtener ID de venta

        # Crear items
        for item_data in venta_data.get("items", []):
            # Buscar producto por código de barras
            producto = None
            if item_data.get("codigo_barra"):
                producto = self.session.query(Producto).filter_by(
                    codigo_barra=item_data["codigo_barra"]
                ).first()

            item = VentaItem(
                venta_id=venta.id,
                producto_id=producto.id if producto else None,
                cantidad=item_data["cantidad"],
                precio_unit=item_data["precio_unit"]
            )
            self.session.add(item)

    def ejecutar_sincronizacion_completa(self) -> Dict:
        """
        Ejecuta un ciclo completo de sincronización:
        1. Genera paquete con cambios locales
        2. Envía por Gmail
        3. Recibe cambios de otras sucursales
        4. Aplica cambios recibidos

        Returns:
            Dict con resultado: {
                "enviados": int,
                "recibidos": int,
                "errores": List[str]
            }
        """
        resultado = {
            "enviados": 0,
            "recibidos": 0,
            "errores": []
        }

        # 1. Generar y enviar cambios locales
        if self.detectar_cambios_pendientes():
            paquete = self.generar_paquete_cambios()
            if paquete["cambios"]:
                ok, err = self.enviar_sync_via_gmail(paquete)
                if ok:
                    resultado["enviados"] = len(paquete["cambios"])
                else:
                    resultado["errores"].append(f"Error enviando: {err}")

        # 2. Recibir y aplicar cambios remotos
        procesados, errores = self.recibir_sync_via_imap()
        resultado["recibidos"] = procesados
        resultado["errores"].extend(errores)

        return resultado
