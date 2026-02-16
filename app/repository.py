from datetime import datetime, date, time,timedelta
from sqlalchemy import func, and_, or_, delete
from sqlalchemy.orm import joinedload
from werkzeug.security import generate_password_hash, check_password_hash
import pandas as pd
from app.models import Producto
#from app.gui.proveedores import ProveedorService

from app.models import (
    Usuario, Producto, Proveedor,
    Venta, VentaItem, VentaLog
)

class OptimisticLockError(Exception):
    """Raised when optimistic locking detects a version conflict."""
    def __init__(self, nombre, prod_id):
        self.nombre = nombre
        self.prod_id = prod_id
        super().__init__(
            f'El producto "{nombre}" (ID {prod_id}) fue modificado por otro usuario. '
            f'Recarga los datos e intenta de nuevo.'
        )

class UsuarioRepo:
    def __init__(self, session):
        self.session = session

    def crear(self, username, password, es_admin=False):
        u = Usuario(
            username=username,
            password_hash=generate_password_hash(password),
            es_admin=es_admin
        )
        self.session.add(u)
        self.session.commit()
        return u

    def obtener_por_username(self, username):
        return self.session.query(Usuario).filter_by(username=username).first()

    def listar(self):
        return self.session.query(Usuario).all()

    def actualizar(self, usuario_id, username=None, password=None, es_admin=None):
        u = self.session.query(Usuario).get(usuario_id)
        if not u:
            return None
        if username is not None:
            u.username = username
        if password is not None:
            u.password_hash = generate_password_hash(password)
        if es_admin is not None:
            u.es_admin = es_admin
        self.session.commit()
        return u

    def eliminar(self, usuario_id):
        u = self.session.query(Usuario).get(usuario_id)
        if u:
            self.session.delete(u)
            self.session.commit()

    def verificar(self, username, password):
        u = self.obtener_por_username(username)
        if u and check_password_hash(u.password_hash, password):
            return u
        return None

class prod_repo:
    def __init__(self, session, modelo=None):
        self.session = session
        self.modelo = modelo or Producto  # Si no le pasan, usa Producto por defecto

    def obtener(self, prod_id):
        return self.session.query(self.modelo).filter_by(id=prod_id).first()

    def buscar_por_codigo(self, codigo):
        return self.session.query(Producto)\
            .filter_by(codigo_barra=codigo).first()

    def crear(self, codigo, nombre, precio, categoria=None):
        p = Producto(
            codigo_barra=codigo,
            nombre=nombre,
            precio=precio,
            categoria=categoria
        )
        self.session.add(p)
        self.session.commit()
        return p

    def listar_todos(self):
        return self.session.query(Producto).all()

    def buscar(self, texto: str, limit: int = 500):
        """Busca productos por codigo, nombre o categoria usando SQL LIKE.
        Mucho mas rapido que cargar 13K objetos y filtrar en Python."""
        patron = f"%{texto}%"
        return (
            self.session.query(Producto)
            .filter(
                or_(
                    Producto.nombre.ilike(patron),
                    Producto.codigo_barra.ilike(patron),
                    Producto.categoria.ilike(patron),
                )
            )
            .limit(limit)
            .all()
        )

    def actualizar_nombre(self, prod_id, nuevo_nombre, expected_version=None):
        prod = self.obtener(prod_id)
        if prod:
            if expected_version is not None and getattr(prod, 'version', 1) != expected_version:
                raise OptimisticLockError(prod.nombre, prod_id)
            prod.nombre = nuevo_nombre
            if hasattr(prod, 'version'):
                prod.version = (prod.version or 1) + 1
            self.session.commit()

    def actualizar_precio(self, prod_id, nuevo_precio, expected_version=None):
        prod = self.obtener(prod_id)
        if prod:
            if expected_version is not None and getattr(prod, 'version', 1) != expected_version:
                raise OptimisticLockError(prod.nombre, prod_id)
            prod.precio = nuevo_precio
            if hasattr(prod, 'version'):
                prod.version = (prod.version or 1) + 1
            self.session.commit()

    def actualizar_categoria(self, prod_id, nueva_cat, expected_version=None):
        prod = self.obtener(prod_id)
        if prod:
            if expected_version is not None and getattr(prod, 'version', 1) != expected_version:
                raise OptimisticLockError(prod.nombre, prod_id)
            prod.categoria = nueva_cat
            if hasattr(prod, 'version'):
                prod.version = (prod.version or 1) + 1
            self.session.commit()
            
    

    def eliminar_ids(self, ids):
        if not ids:
            return
        # Borrado por lote sin sincronización de sesión (más rápido)
        self.session.execute(delete(Producto).where(Producto.id.in_(ids)))
        self.session.commit()
        
    def listar_codigos_nombres(self):
    # Devuelve lista de tuplas (codigo_barra, nombre) sin cargar columnas que no usamos
        return self.session.query(self.modelo.codigo_barra, self.modelo.nombre).all()

class VentaRepo:
    def __init__(self, session):
        self.session = session
    
    
    def commit(self):
        self.session.commit()

    # NUEVO: siguiente número para la sucursal, conservando paridad
    def siguiente_ticket(self, sucursal: str) -> int:
        base = 1 if sucursal == 'Sarmiento' else 2  # impares Sarmiento, pares Salta
        last = (
            self.session.query(Venta)
            .filter(Venta.sucursal == sucursal, Venta.numero_ticket.isnot(None))
            .order_by(Venta.numero_ticket.desc())
            .first()
        )
        if not last or not getattr(last, 'numero_ticket', None):
            return base
        # siempre saltamos de a 2 para conservar la paridad
        return last.numero_ticket + 2

    
    # ====== CREAR VENTA CON total=0.0 ======
    def crear_venta(self, sucursal: str, modo_pago: str, cuotas: int | None):
        numero_ticket = self.siguiente_ticket(sucursal)
        v = Venta(
            sucursal=sucursal,
            fecha=datetime.now(),
            modo_pago=modo_pago,
            cuotas=cuotas,
            total=0.0,                 # <- CLAVE
            numero_ticket=numero_ticket
        )
        self.session.add(v)
        self.session.flush()  # asegura v.id
        return v
    def obtener_por_numero(self, numero_ticket: int):
        return self.session.query(Venta).filter(Venta.numero_ticket == numero_ticket).first()

    # Ya lo tendrás, lo dejo por si faltaba
    def obtener(self, venta_id: int):
        return self.session.query(Venta).get(venta_id)

    # Ya lo tendrás, lo dejo por si faltaba
    def agregar_item(self, venta_id: int, codigo: str, cantidad: int, precio_unit: float):
        # asumiendo que puedes resolver Producto por codigo_barra:
        prod = self.session.query(Producto).filter_by(codigo_barra=codigo).first()
        item = VentaItem(
            venta_id=venta_id,
            producto_id=prod.id if prod else None,
            cantidad=cantidad,
            precio_unit=precio_unit
        )
        self.session.add(item)

    # OPCIONAL: actualizar items a partir de mods [(codigo_barra, nueva_cantidad)]
    def actualizar_items(self, venta_id: int, mods):
        items = self.session.query(VentaItem).filter(VentaItem.venta_id == venta_id).all()
        # indexar por codigo_barra
        by_code = {}
        for it in items:
            codigo = getattr(it, 'codigo', None) or (
                getattr(it, 'producto', None) and getattr(it.producto, 'codigo_barra', None)
            )
            if codigo:
                by_code[codigo] = it

        for codigo, nueva_cant in mods:
            it = by_code.get(codigo)
            if it:
                it.cantidad = max(int(nueva_cant), 0)

        # recalcular total de la venta si tu modelo lo tiene como campo persistido
        v = self.obtener(venta_id)
        if v:
            total = 0.0
            for it in self.session.query(VentaItem).filter(VentaItem.venta_id == venta_id):
                total += (it.cantidad or 0) * float(
                    getattr(it, 'precio_unit', None) or getattr(it, 'precio', 0.0)
                )
            v.total = total  # si tu modelo tiene columna total    
    
    def actualizar_total(self, venta_id: int) -> float:
        items = self.session.query(VentaItem).filter(VentaItem.venta_id == venta_id).all()
        total = 0.0
        for it in items:
            pu = getattr(it, 'precio_unit', None) or getattr(it, 'precio', 0.0)
            total += (it.cantidad or 0) * float(pu)
        v = self.session.query(Venta).get(venta_id)
        v.total = total
        self.session.flush()
        return total
    
    def listar_hoy(self, sucursal: str):
        """Devuelve las ventas de HOY para la sucursal dada, con total calculado si hace falta."""
        inicio = datetime.combine(date.today(), time.min)
        fin    = datetime.combine(date.today(), time.max)

        ventas = (
            self.session.query(Venta)
            .filter(Venta.sucursal == sucursal, Venta.fecha >= inicio, Venta.fecha <= fin)
            .order_by(Venta.fecha.desc())
            .all()
        )

        # Si tu modelo Venta no guarda 'total', lo calculamos al vuelo
        for v in ventas:
            if not getattr(v, 'total', None):
                total = 0.0
                items = self.session.query(VentaItem).filter(VentaItem.venta_id == v.id).all()
                for it in items:
                    pu = getattr(it, 'precio_unit', None) or getattr(it, 'precio', 0.0)
                    total += float(pu) * (it.cantidad or 0)
                v.total = total
        return ventas

    # --- Logs de venta (comentarios) ---
    def agregar_log(self, venta_id: int, comentario: str):
        log = VentaLog(venta_id=venta_id, comentario=comentario.strip())
        self.session.add(log)
        self.session.commit()
        return log

    def ult_log(self, venta_id: int):
        return (self.session.query(VentaLog)
                .filter(VentaLog.venta_id == venta_id)
                .order_by(VentaLog.fecha.desc())
                .first())

    def exportar_rango(self, sucursal: str, inicio, fin):
        ventas = (self.session.query(Venta)
                    .filter(Venta.sucursal == sucursal,
                            Venta.fecha >= inicio, Venta.fecha <= fin)
                    .order_by(Venta.fecha.asc())
                    .all())
        rows = []
        for v in ventas:
            # asegurar total
            total = getattr(v, 'total', None)
            if total is None:
                total = 0.0
                for it in self.session.query(VentaItem).filter(VentaItem.venta_id == v.id).all():
                    total += float(getattr(it, 'precio_unit', 0.0)) * int(it.cantidad or 0)

            log = self.ult_log(v.id)
            comentario = log.comentario if log else ''

            rows.append({
                'ticket': v.numero_ticket,
                'fecha': v.fecha.strftime('%Y-%m-%d %H:%M:%S'),
                'modo_pago': v.modo_pago,
                'cuotas': v.cuotas or '',
                'total': round(total, 2),
                'comentario': comentario
            })
        return pd.DataFrame(rows)

    def top_producto(self, sucursal: str, inicio, fin, n=1):
        # Cuenta unidades vendidas por producto
        q = (self.session.query(Producto.nombre, func.sum(VentaItem.cantidad).label('unidades'))
             .join(VentaItem, VentaItem.producto_id == Producto.id)
             .join(Venta, Venta.id == VentaItem.venta_id)
             .filter(Venta.sucursal == sucursal, Venta.fecha >= inicio, Venta.fecha <= fin)
             .group_by(Producto.id)
             .order_by(func.sum(VentaItem.cantidad).desc()))
        return q.limit(n).all()
    def listar_por_fecha(self, fecha: datetime.date, sucursal: str | None = None):
        q = self.session.query(Venta).filter(
            Venta.fecha >= datetime.combine(fecha, datetime.min.time()),
            Venta.fecha <  datetime.combine(fecha + timedelta(days=1), datetime.min.time())
        )
        if sucursal:
            q = q.filter(Venta.sucursal == sucursal)
        return q.order_by(Venta.fecha.desc()).all()

    def listar_por_rango(self, desde: datetime, hasta: datetime, sucursal: str | None = None):
        """
        Lista ventas en un rango de fechas.

        Args:
            desde: Fecha/hora inicial (inclusive)
            hasta: Fecha/hora final (inclusive)
            sucursal: Filtrar por sucursal (opcional)

        Returns:
            Lista de objetos Venta ordenados por fecha descendente
        """
        q = self.session.query(Venta).filter(
            Venta.fecha >= desde,
            Venta.fecha <= hasta
        )
        if sucursal:
            q = q.filter(Venta.sucursal == sucursal)
        return q.order_by(Venta.fecha.desc()).all()

    def eliminar_anteriores_a(self, dias: int = 31):
        limite = datetime.now() - timedelta(days=dias)
        self.session.query(Venta).filter(Venta.fecha < limite).delete(synchronize_session=False)
        self.session.commit()

    def productos_sin_ventas(self, dias: int = 90):
        """Productos que no se vendieron en los últimos N días.
        LEFT JOIN Producto → VentaItem → Venta filtrado por fecha."""
        from sqlalchemy import func
        from datetime import datetime, timedelta
        limite = datetime.now() - timedelta(days=dias)

        # Subquery: productos que SÍ tuvieron ventas en el período
        vendidos = (
            self.session.query(VentaItem.producto_id)
            .join(Venta, Venta.id == VentaItem.venta_id)
            .filter(Venta.fecha >= limite)
            .filter(VentaItem.producto_id.isnot(None))
            .distinct()
            .subquery()
        )

        # Productos que NO están en la subquery
        return (
            self.session.query(Producto)
            .filter(~Producto.id.in_(self.session.query(vendidos.c.producto_id)))
            .order_by(Producto.nombre)
            .all()
        )