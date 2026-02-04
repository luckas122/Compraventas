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
from sqlalchemy.exc import IntegrityError

from app.models import SyncLog, Venta, VentaItem, Producto, Proveedor
from app.config import load as load_config, save as save_config, get_log_dir


class SyncManager:
    """Gestor de sincronización entre sucursales"""

    def __init__(self, session: Session, sucursal_local: str):
        self.session = session
        self.sucursal_local = sucursal_local
        self.config = load_config()
        self.sync_config = self.config.get("sync", {})

    def _log_sync(self, msg: str) -> None:
        try:
            log_dir = get_log_dir()
            path = os.path.join(log_dir, "sync.log")
            with open(path, "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now().isoformat()}] {msg}\n")
        except Exception:
            pass

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
        Revisa si hay ventas/productos/proveedores nuevos o modificados desde última sync.
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
            proveedores_count = self.session.query(Proveedor).count()
            return (ventas_count > 0 or productos_count > 0 or proveedores_count > 0)

        # Verificar si hay ventas nuevas desde la última sync
        ventas_nuevas = self.session.query(Venta).filter(
            Venta.fecha > ultima_sync.timestamp
        ).count()

        # Fase 2: Detectar cambios en productos y proveedores
        # Como no tienen timestamp, sincronizamos todo siempre (o usar hash para optimizar)
        sync_productos = self.sync_config.get("sync_productos", False)
        sync_proveedores = self.sync_config.get("sync_proveedores", False)

        cambios_productos = sync_productos and self.session.query(Producto).count() > 0
        cambios_proveedores = sync_proveedores and self.session.query(Proveedor).count() > 0

        return ventas_nuevas > 0 or cambios_productos or cambios_proveedores

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

        # 2. Sincronizar productos (si está habilitado)
        if self.sync_config.get("sync_productos", False):
            productos = self.session.query(Producto).all()
            for producto in productos:
                producto_data = {
                    "id": producto.id,
                    "codigo_barra": producto.codigo_barra,
                    "nombre": producto.nombre,
                    "precio": producto.precio,
                    "categoria": producto.categoria,
                    "telefono": producto.telefono,
                    "numero_cuenta": producto.numero_cuenta,
                    "cbu": producto.cbu
                }

                # Verificar si ya fue sincronizado con el mismo hash
                data_hash = self._calcular_hash(producto_data)
                ya_sincronizado = self.session.query(SyncLog).filter(
                    SyncLog.tipo == "producto",
                    SyncLog.data_hash == data_hash,
                    SyncLog.sucursal_origen == self.sucursal_local
                ).first()

                if not ya_sincronizado:
                    sync_id = self._generar_sync_id()
                    cambios.append({
                        "sync_id": sync_id,
                        "tipo": "producto",
                        "accion": "upsert",  # create or update
                        "data": producto_data,
                        "hash": data_hash
                    })

        # 3. Sincronizar proveedores (si está habilitado)
        if self.sync_config.get("sync_proveedores", False):
            proveedores = self.session.query(Proveedor).all()
            for proveedor in proveedores:
                proveedor_data = {
                    "id": proveedor.id,
                    "nombre": proveedor.nombre,
                    "telefono": proveedor.telefono,
                    "numero_cuenta": proveedor.numero_cuenta,
                    "cbu": proveedor.cbu
                }

                # Verificar si ya fue sincronizado con el mismo hash
                data_hash = self._calcular_hash(proveedor_data)
                ya_sincronizado = self.session.query(SyncLog).filter(
                    SyncLog.tipo == "proveedor",
                    SyncLog.data_hash == data_hash,
                    SyncLog.sucursal_origen == self.sucursal_local
                ).first()

                if not ya_sincronizado:
                    sync_id = self._generar_sync_id()
                    cambios.append({
                        "sync_id": sync_id,
                        "tipo": "proveedor",
                        "accion": "upsert",  # create or update
                        "data": proveedor_data,
                        "hash": data_hash
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
            self._log_sync("SMTP: Credenciales no configuradas")
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

            self._log_sync(f"SMTP: Enviado paquete con {len(paquete.get('cambios', []))} cambios")
            return True, None

        except Exception as e:
            self._log_sync(f"SMTP: Error enviando paquete: {e}")
            return False, str(e)

    
    def recibir_sync_via_imap(self) -> Tuple[int, List[str]]:
        """
        Descarga emails de sincronizacion desde Gmail.
    
        Returns:
            (cantidad_procesados, lista_de_errores)
        """
        imap_config = self.sync_config.get("gmail_imap", {})
        host = imap_config.get("host", "imap.gmail.com")
        port = int(imap_config.get("port", 993))
        username = imap_config.get("username", "")
        password = imap_config.get("password", "")
    
        if not username or not password:
            self._log_sync("IMAP: Credenciales no configuradas")
            return 0, ["Credenciales IMAP no configuradas"]
    
        errores = []
        procesados = 0
        last_uid = int(self.sync_config.get("imap_last_uid", 0) or 0)
        max_uid = last_uid
    
        try:
            # Conectar a IMAP
            mail = imaplib.IMAP4_SSL(host, port)
            mail.login(username, password)
            mail.select("INBOX")
    
            # Buscar emails con [SYNC] por UID para no depender de UNSEEN
            if last_uid > 0:
                criteria = f'(UID {last_uid + 1}:* SUBJECT "[SYNC]")'
                status, messages = mail.uid("search", None, criteria)
            else:
                status, messages = mail.uid("search", None, 'SUBJECT "[SYNC]"')
    
            if status != "OK":
                self._log_sync("IMAP: Error buscando emails")
                return 0, ["Error buscando emails"]
    
            uid_list = messages[0].split()
    
            for uid in uid_list:
                try:
                    uid_int = int(uid)
                    # Descargar email sin marcar como leido
                    status, msg_data = mail.uid("fetch", uid, "(BODY.PEEK[])")
    
                    if status != "OK":
                        continue
    
                    raw_email = msg_data[0][1] if msg_data and msg_data[0] else None
                    if not raw_email:
                        max_uid = max(max_uid, uid_int)
                        continue
    
                    msg = email.message_from_bytes(raw_email)
    
                    # Buscar adjunto JSON
                    paquete_data = None
                    for part in msg.walk():
                        if part.get_content_type() == "application/octet-stream":
                            filename = part.get_filename()
                            if filename and filename.endswith(".json"):
                                payload = part.get_payload(decode=True)
                                try:
                                    paquete_data = json.loads(payload.decode("utf-8"))
                                except (json.JSONDecodeError, UnicodeDecodeError) as e:
                                    errores.append(f"JSON inválido en email {uid}: {e}")
                                    self._log_sync(f"IMAP: JSON inválido en email {uid}: {e}")
                                    paquete_data = None
                                break

                    # Validar estructura básica del paquete
                    if paquete_data and not isinstance(paquete_data, dict):
                        errores.append(f"Paquete no es un diccionario en email {uid}")
                        paquete_data = None

                    if paquete_data and "sucursal_origen" not in paquete_data:
                        errores.append(f"Paquete sin 'sucursal_origen' en email {uid}")
                        paquete_data = None

                    if paquete_data:
                        origen = paquete_data.get("sucursal_origen")
                        if origen != self.sucursal_local:
                            ok, err = self.aplicar_paquete(paquete_data)
                            if ok:
                                procesados += 1
                                mail.uid("store", uid, "+FLAGS", "\\Seen")
                                max_uid = max(max_uid, uid_int)
                            else:
                                errores.append(f"Error aplicando paquete: {err}")
                        else:
                            # Es de esta sucursal, marcar leido y avanzar UID
                            mail.uid("store", uid, "+FLAGS", "\\Seen")
                            max_uid = max(max_uid, uid_int)
                    else:
                        # Email sin paquete valido, avanzar UID para no trabar
                        max_uid = max(max_uid, uid_int)
    
                except Exception as e:
                    errores.append(f"Error procesando email {uid}: {str(e)}")
    
            mail.close()
            mail.logout()
    
        except Exception as e:
            errores.append(f"Error conectando a IMAP: {str(e)}")
            self._log_sync(f"IMAP: Error conectando: {e}")
    
        if max_uid > last_uid:
            try:
                cfg = load_config()
                cfg.setdefault("sync", {})["imap_last_uid"] = max_uid
                save_config(cfg)
                self.sync_config["imap_last_uid"] = max_uid
            except Exception as e:
                errores.append(f"Error guardando imap_last_uid: {e}")
                self._log_sync(f"IMAP: Error guardando imap_last_uid: {e}")

        if errores:
            for err in errores:
                self._log_sync(f"IMAP: {err}")
        else:
            self._log_sync(f"IMAP: procesados={procesados}, last_uid={max_uid}")

        return procesados, errores
    
    def aplicar_paquete(self, paquete: Dict) -> Tuple[bool, Optional[str]]:
        """
        Aplica un paquete de sincronización recibido.

        Returns:
            (éxito, mensaje_error)
        """
        try:
            # Validar estructura del paquete
            if not isinstance(paquete, dict):
                return False, "Paquete no es un diccionario válido"

            sucursal_origen = paquete.get("sucursal_origen")
            if not sucursal_origen:
                return False, "Paquete sin 'sucursal_origen'"

            timestamp_str = paquete.get("timestamp")
            if not timestamp_str:
                return False, "Paquete sin 'timestamp'"

            # Parsear timestamp de forma segura
            try:
                timestamp = datetime.fromisoformat(timestamp_str)
            except (ValueError, TypeError) as e:
                return False, f"Timestamp inválido: {timestamp_str} - {e}"

            cambios = paquete.get("cambios", [])
            if not isinstance(cambios, list):
                return False, "'cambios' debe ser una lista"

            for cambio in cambios:
                if not isinstance(cambio, dict):
                    self._log_sync(f"Cambio ignorado: no es diccionario")
                    continue

                sync_id = cambio.get("sync_id")
                tipo = cambio.get("tipo")
                accion = cambio.get("accion")
                data = cambio.get("data")
                data_hash = cambio.get("hash")

                # Validar campos requeridos del cambio
                if not sync_id or not tipo or not accion:
                    self._log_sync(f"Cambio ignorado: faltan campos requeridos")
                    continue

                if data is not None and not isinstance(data, dict):
                    self._log_sync(f"Cambio ignorado: 'data' no es diccionario")
                    continue

                # Verificar si ya fue aplicado
                existe = self.session.query(SyncLog).filter_by(sync_id=sync_id).first()
                if existe:
                    continue  # Ya fue aplicado

                # Aplicar según tipo
                try:
                    if tipo == "venta" and accion == "create" and data:
                        self._aplicar_venta_nueva(data, sucursal_origen)
                    elif tipo == "producto" and accion == "upsert" and data:
                        self._aplicar_producto_upsert(data)
                    elif tipo == "proveedor" and accion == "upsert" and data:
                        self._aplicar_proveedor_upsert(data)
                except Exception as e:
                    self._log_sync(f"Error aplicando cambio {tipo}/{accion}: {e}")
                    # Continuar con el siguiente cambio, no abortar todo

                # Registrar en SyncLog
                try:
                    log = SyncLog(
                        sync_id=sync_id,
                        tipo=tipo,
                        accion=accion,
                        timestamp=timestamp,
                        aplicado=True,
                        sucursal_origen=sucursal_origen,
                        data_hash=data_hash
                    )
                    self.session.add(log)
                except Exception as e:
                    self._log_sync(f"Error registrando SyncLog: {e}")

            self.session.commit()
            return True, None

        except Exception as e:
            self.session.rollback()
            return False, str(e)

    def _aplicar_venta_nueva(self, venta_data: Dict, sucursal_origen: str):
        """
        Aplica una venta nueva recibida desde otra sucursal.

        Usa manejo de IntegrityError para evitar condiciones de carrera
        (TOCTOU - Time Of Check To Time Of Use).
        """
        # Validar datos requeridos
        required_fields = ["numero_ticket", "sucursal", "fecha", "modo_pago", "total"]
        for field in required_fields:
            if field not in venta_data:
                self._log_sync(f"Venta recibida sin campo requerido: {field}")
                return

        # Verificar que no exista ya (por numero_ticket y sucursal)
        existe = self.session.query(Venta).filter_by(
            numero_ticket=venta_data["numero_ticket"],
            sucursal=venta_data["sucursal"]
        ).first()

        if existe:
            return  # Ya existe, no duplicar

        # Parsear fecha de forma segura
        try:
            fecha = datetime.fromisoformat(venta_data["fecha"])
        except (ValueError, TypeError) as e:
            self._log_sync(f"Fecha inválida en venta: {venta_data.get('fecha')} - {e}")
            return

        # Crear nueva venta
        venta = Venta(
            sucursal=venta_data["sucursal"],
            fecha=fecha,
            modo_pago=venta_data["modo_pago"],
            cuotas=venta_data.get("cuotas"),
            total=float(venta_data.get("total", 0)),
            subtotal_base=float(venta_data.get("subtotal_base", 0.0)),
            interes_pct=float(venta_data.get("interes_pct", 0.0)),
            interes_monto=float(venta_data.get("interes_monto", 0.0)),
            descuento_pct=float(venta_data.get("descuento_pct", 0.0)),
            descuento_monto=float(venta_data.get("descuento_monto", 0.0)),
            pagado=venta_data.get("pagado"),
            vuelto=venta_data.get("vuelto"),
            numero_ticket=venta_data["numero_ticket"],
            afip_cae=venta_data.get("afip_cae"),
            afip_cae_vencimiento=venta_data.get("afip_cae_vencimiento"),
            afip_numero_comprobante=venta_data.get("afip_numero_comprobante"),
            afip_error=venta_data.get("afip_error")  # Incluir campo de error AFIP
        )

        try:
            self.session.add(venta)
            self.session.flush()  # Obtener ID de venta
        except IntegrityError:
            # Condición de carrera: otro proceso ya insertó esta venta
            self.session.rollback()
            self._log_sync(f"Venta duplicada detectada (condición de carrera): ticket {venta_data['numero_ticket']}")
            return

        # Crear items
        for item_data in venta_data.get("items", []):
            # Validar datos del item
            if "cantidad" not in item_data or "precio_unit" not in item_data:
                continue

            # Buscar producto por código de barras
            producto = None
            if item_data.get("codigo_barra"):
                producto = self.session.query(Producto).filter_by(
                    codigo_barra=item_data["codigo_barra"]
                ).first()

            try:
                item = VentaItem(
                    venta_id=venta.id,
                    producto_id=producto.id if producto else None,
                    cantidad=int(item_data["cantidad"]),
                    precio_unit=float(item_data["precio_unit"])
                )
                self.session.add(item)
            except (ValueError, TypeError) as e:
                self._log_sync(f"Item de venta inválido: {e}")

    def _aplicar_producto_upsert(self, producto_data: Dict):
        """
        Aplica un producto recibido (create o update).
        Usa código de barras como clave única.
        """
        codigo_barra = producto_data["codigo_barra"]

        # Buscar si existe por código de barras
        producto = self.session.query(Producto).filter_by(
            codigo_barra=codigo_barra
        ).first()

        if producto:
            # UPDATE: Actualizar campos
            producto.nombre = producto_data["nombre"]
            producto.precio = producto_data["precio"]
            producto.categoria = producto_data.get("categoria")
            producto.telefono = producto_data.get("telefono")
            producto.numero_cuenta = producto_data.get("numero_cuenta")
            producto.cbu = producto_data.get("cbu")
        else:
            # CREATE: Crear nuevo producto
            producto = Producto(
                codigo_barra=codigo_barra,
                nombre=producto_data["nombre"],
                precio=producto_data["precio"],
                categoria=producto_data.get("categoria"),
                telefono=producto_data.get("telefono"),
                numero_cuenta=producto_data.get("numero_cuenta"),
                cbu=producto_data.get("cbu")
            )
            self.session.add(producto)

    def _aplicar_proveedor_upsert(self, proveedor_data: Dict):
        """
        Aplica un proveedor recibido (create o update).
        Usa nombre como clave única (o podrías usar ID si prefieres).
        """
        nombre = proveedor_data["nombre"]

        # Buscar si existe por nombre (asumiendo que nombre es único)
        proveedor = self.session.query(Proveedor).filter_by(
            nombre=nombre
        ).first()

        if proveedor:
            # UPDATE: Actualizar campos
            proveedor.telefono = proveedor_data.get("telefono")
            proveedor.numero_cuenta = proveedor_data.get("numero_cuenta")
            proveedor.cbu = proveedor_data.get("cbu")
        else:
            # CREATE: Crear nuevo proveedor
            proveedor = Proveedor(
                nombre=nombre,
                telefono=proveedor_data.get("telefono"),
                numero_cuenta=proveedor_data.get("numero_cuenta"),
                cbu=proveedor_data.get("cbu")
            )
            self.session.add(proveedor)

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
