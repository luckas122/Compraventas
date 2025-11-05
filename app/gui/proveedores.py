# AppComprasVentasPy/app/gui/proveedores.py
from sqlalchemy.orm import Session
from app.models import Proveedor

class ProveedorService:
    def __init__(self, session: Session):
        self.session = session

    # Crear o actualizar por nombre (para tu botón Agregar/Actualizar)
    def crear_o_actualizar_por_nombre(self, nombre, telefono=None, numero_cuenta=None, cbu=None):
        nombre = (nombre or "").strip()
        if not nombre:
            return None
        p = self.session.query(Proveedor).filter(Proveedor.nombre == nombre).first()
        if p:
            p.telefono = telefono
            p.numero_cuenta = numero_cuenta
            p.cbu = cbu
        else:
            p = Proveedor(
                nombre=nombre,
                telefono=telefono,
                numero_cuenta=numero_cuenta,
                cbu=cbu
            )
            self.session.add(p)
        self.session.commit()
        return p

    def listar_todos(self):
        return (
            self.session.query(Proveedor)
            .order_by(Proveedor.nombre.asc())
            .all()
        )

    def actualizar(self, proveedor_id: int, **campos):
        p = self.session.query(Proveedor).get(proveedor_id)
        if not p:
            return None
        for k, v in campos.items():
            if hasattr(p, k):
                setattr(p, k, v)
        self.session.commit()
        return p

    def eliminar(self, proveedor_id: int) -> bool:
        p = self.session.query(Proveedor).get(proveedor_id)
        if not p:
            return False
        self.session.delete(p)
        self.session.commit()
        return True

    def buscar_por_nombre(self, texto: str):
        q = f"%{(texto or '').strip()}%"
        return self.session.query(Proveedor).filter(Proveedor.nombre.ilike(q)).all()

    def existe_nombre(self, nombre: str) -> bool:
        return self.session.query(Proveedor).filter(Proveedor.nombre == nombre).first() is not None