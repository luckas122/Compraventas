from sqlalchemy.orm import Session
from app.models import Comprador


class CompradorService:
    def __init__(self, session: Session):
        self.session = session

    def buscar_por_cuit(self, cuit: str):
        cuit = (cuit or "").strip()
        if not cuit:
            return None
        return self.session.query(Comprador).filter(Comprador.cuit == cuit).first()

    def guardar_o_actualizar(self, cuit, nombre="", domicilio="", localidad="",
                             codigo_postal="", condicion=""):
        cuit = (cuit or "").strip()
        if not cuit:
            return None
        c = self.session.query(Comprador).filter(Comprador.cuit == cuit).first()
        if c:
            c.nombre = nombre
            c.domicilio = domicilio
            c.localidad = localidad
            c.codigo_postal = codigo_postal
            c.condicion = condicion
        else:
            c = Comprador(
                cuit=cuit, nombre=nombre, domicilio=domicilio,
                localidad=localidad, codigo_postal=codigo_postal,
                condicion=condicion,
            )
            self.session.add(c)
        self.session.commit()
        return c

    def listar_todos(self):
        return (
            self.session.query(Comprador)
            .order_by(Comprador.nombre.asc())
            .all()
        )

    def actualizar(self, comprador_id: int, **campos):
        c = self.session.query(Comprador).get(comprador_id)
        if not c:
            return None
        for k, v in campos.items():
            if hasattr(c, k):
                setattr(c, k, v)
        self.session.commit()
        return c

    def eliminar(self, comprador_id: int) -> bool:
        c = self.session.query(Comprador).get(comprador_id)
        if not c:
            return False
        self.session.delete(c)
        self.session.commit()
        return True
