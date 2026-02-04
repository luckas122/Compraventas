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
    numero_ticket = Column(Integer, unique=True, index=True, nullable=False)
    # Campos AFIP
    afip_cae = Column(String, nullable=True)
    afip_cae_vencimiento = Column(String, nullable=True)
    afip_numero_comprobante = Column(Integer, nullable=True)
    afip_error = Column(String, nullable=True)  # Guarda error si AFIP falló (para reintentar después)
    
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

class SyncLog(Base):
    """Registro de sincronizaciones entre sucursales"""
    __tablename__ = 'sync_log'
    id = Column(Integer, primary_key=True)
    sync_id = Column(String, unique=True, nullable=False, index=True)  # UUID único
    tipo = Column(String, nullable=False)  # 'venta', 'producto', 'proveedor'
    accion = Column(String, nullable=False)  # 'create', 'update', 'delete'
    timestamp = Column(DateTime, nullable=False, default=datetime.datetime.now)
    aplicado = Column(Boolean, default=False, nullable=False)
    sucursal_origen = Column(String, nullable=False)
    data_hash = Column(String, nullable=True)  # Hash del contenido para detectar duplicados

    __table_args__ = (
        Index('ix_sync_log_tipo_timestamp', 'tipo', 'timestamp'),
        Index('ix_sync_log_sucursal_timestamp', 'sucursal_origen', 'timestamp'),
    )


