from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Index
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
import datetime

Base = declarative_base()

class Usuario(Base):
    __tablename__ = 'usuarios'
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    es_admin = Column(Boolean, default=False, nullable=False)

class Comprador(Base):
    __tablename__ = 'compradores'
    id = Column(Integer, primary_key=True)
    cuit = Column(String, unique=True, nullable=False)
    nombre = Column(String, nullable=True)
    domicilio = Column(String, nullable=True)
    localidad = Column(String, nullable=True)
    codigo_postal = Column(String, nullable=True)
    condicion = Column(String, nullable=True)

class Producto(Base):
    __tablename__ = 'productos'

    id            = Column(Integer, primary_key=True)
    codigo_barra  = Column(String, unique=True, nullable=False)   # <-- aquí
    nombre        = Column(String, nullable=False)
    precio        = Column(Float,  nullable=False)
    categoria     = Column(String)
    telefono      = Column(String)
    numero_cuenta = Column(String)
    cbu           = Column(String)
    last_modified = Column(DateTime, default=datetime.datetime.now,
                           onupdate=datetime.datetime.now, nullable=True)
    version       = Column(Integer, default=1, nullable=False)

class Venta(Base):
    __tablename__ = 'ventas'
    id         = Column(Integer, primary_key=True)
    sucursal   = Column(String, nullable=False)
    fecha      = Column(DateTime, default=datetime.datetime.now, nullable=False)
    modo_pago  = Column(String, nullable=False)     # Efectivo o Tarjeta
    cuotas     = Column(Integer, nullable=True)     # Sólo si Tarjeta
    total      = Column(Float, nullable=False)
    # --- Totales detallados / persistencia de ajustes ---
    subtotal_base   = Column(Float, nullable=False, default=0.0)

    interes_pct     = Column(Float, nullable=False, default=0.0)
    interes_monto   = Column(Float, nullable=False, default=0.0)

    descuento_pct   = Column(Float, nullable=False, default=0.0)
    descuento_monto = Column(Float, nullable=False, default=0.0)

    # (Opcional pero recomendado; ya los usas en la UI)
    pagado          = Column(Float, nullable=True)
    vuelto          = Column(Float, nullable=True)
    items      = relationship("VentaItem", back_populates="venta")
    # v6.9.5: numero_ticket pasa a nullable=True. Las ventas tarjeta+CAE tienen
    # numero_ticket=null y numero_ticket_cae=N. Al pull-ear ventas de otra
    # sucursal con esa forma, el NOT NULL anterior rechazaba la insercion en
    # silencio (IntegrityError -> rollback -> ventas perdidas).
    numero_ticket = Column(Integer, index=True, nullable=True)  # secuencia independiente por sucursal (ventas sin CAE)
    numero_ticket_cae = Column(Integer, index=True, nullable=True)  # secuencia independiente por sucursal (ventas con CAE)
    # Campos AFIP
    afip_cae = Column(String, nullable=True)
    afip_cae_vencimiento = Column(String, nullable=True)
    afip_numero_comprobante = Column(Integer, nullable=True)
    afip_error = Column(String, nullable=True)  # Guarda error si AFIP falló (para reintentar después)
    tipo_comprobante = Column(String, nullable=True)  # FACTURA_A, FACTURA_B, FACTURA_B_MONO
    cuit_cliente = Column(String, nullable=True)  # CUIT/CUIL del comprador (Factura A y B Mono)
    nombre_cliente = Column(String, nullable=True)  # Nombre y Apellido del comprador
    domicilio_cliente = Column(String, nullable=True)  # Domicilio del comprador
    localidad_cliente = Column(String, nullable=True)  # Localidad del comprador
    codigo_postal_cliente = Column(String, nullable=True)  # Código postal del comprador
    condicion_cliente = Column(String, nullable=True)  # Condición fiscal del comprador
    vendedor = Column(String, nullable=True)  # Username del vendedor que realizó la venta
    nota_credito_cae = Column(String, nullable=True)  # CAE de la nota de crédito emitida
    nota_credito_numero = Column(Integer, nullable=True)  # Nº comprobante de la nota de crédito

    __table_args__ = (
        Index('ix_ventas_sucursal_fecha', 'sucursal', 'fecha'),
    )
    items = relationship("VentaItem", back_populates="venta", cascade="all, delete-orphan")

class VentaItem(Base):
    __tablename__ = "venta_items"
    id = Column(Integer, primary_key=True)
    venta_id = Column(Integer, ForeignKey("ventas.id"), nullable=False)
    producto_id = Column(Integer, ForeignKey("productos.id"), nullable=True)

    cantidad = Column(Integer, nullable=False, default=1)
    precio_unit = Column(Float, nullable=False, default=0.0)

    venta = relationship("Venta", back_populates="items")
    producto = relationship("Producto")

class Proveedor(Base):
    __tablename__ = 'proveedores'
    id = Column(Integer, primary_key=True)
    nombre = Column(String, nullable=False)
    telefono = Column(String)
    numero_cuenta = Column(String)
    cbu = Column(String)
    last_modified = Column(DateTime, default=datetime.datetime.now,
                           onupdate=datetime.datetime.now, nullable=True)

class VentaLog(Base):
    __tablename__ = 'venta_logs'
    id = Column(Integer, primary_key=True)
    venta_id = Column(Integer, ForeignKey('ventas.id'), nullable=False, index=True)
    fecha = Column(DateTime, default=datetime.datetime.now, nullable=False)
    comentario = Column(String, nullable=False)

    venta = relationship('Venta')

class VentaBorrador(Base):
    __tablename__ = 'ventas_borradores'
    id = Column(Integer, primary_key=True)
    nombre = Column(String, nullable=False)  # Nombre del borrador
    sucursal = Column(String, nullable=False)
    fecha_creacion = Column(DateTime, default=datetime.datetime.now, nullable=False)

    # Datos de la venta (copiados de Venta)
    modo_pago = Column(String, nullable=False, default='Efectivo')
    cuotas = Column(Integer, nullable=True)
    total = Column(Float, nullable=False, default=0.0)
    subtotal_base = Column(Float, nullable=False, default=0.0)
    interes_pct = Column(Float, nullable=False, default=0.0)
    interes_monto = Column(Float, nullable=False, default=0.0)
    descuento_pct = Column(Float, nullable=False, default=0.0)
    descuento_monto = Column(Float, nullable=False, default=0.0)

    # Relación con items
    items = relationship("VentaBorradorItem", back_populates="borrador", cascade="all, delete-orphan")

class VentaBorradorItem(Base):
    __tablename__ = "venta_borrador_items"
    id = Column(Integer, primary_key=True)
    borrador_id = Column(Integer, ForeignKey("ventas_borradores.id"), nullable=False)
    producto_id = Column(Integer, ForeignKey("productos.id"), nullable=True)

    # Guardamos también código y nombre por si el producto se elimina
    codigo_barra = Column(String, nullable=False)
    nombre = Column(String, nullable=False)

    cantidad = Column(Integer, nullable=False, default=1)
    precio_unit = Column(Float, nullable=False, default=0.0)

    borrador = relationship("VentaBorrador", back_populates="items")
    producto = relationship("Producto")


class PagoProveedor(Base):
    __tablename__ = 'pagos_proveedores'
    id = Column(Integer, primary_key=True)
    proveedor_id = Column(Integer, ForeignKey('proveedores.id'), nullable=True)
    proveedor_nombre = Column(String, nullable=False)
    fecha = Column(DateTime, default=datetime.datetime.now, nullable=False)
    monto = Column(Float, nullable=False)
    metodo_pago = Column(String, nullable=False, default='Efectivo')
    pago_de_caja = Column(Boolean, default=False, nullable=False)
    sucursal = Column(String, nullable=False)
    numero_ticket = Column(Integer, index=True, nullable=True)
    nota = Column(String, nullable=True)
    incluye_iva = Column(Boolean, default=False, nullable=False)

    proveedor = relationship("Proveedor")

    __table_args__ = (
        Index('ix_pagos_prov_sucursal_fecha', 'sucursal', 'fecha'),
    )
