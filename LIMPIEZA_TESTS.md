# Limpieza de Archivos de Test

## Archivos de Test Encontrados

### Archivos Actuales en Raíz:
1. `test_afip_sandbox.py`
2. `test_afip_simple.py`
3. `test_dialog_tarjeta.py`
4. `test_ticket_con_cae.py`
5. `test_tipos_comprobante.py`

---

## Análisis y Recomendaciones

### ✅ MANTENER (útiles para producción/desarrollo)

**`test_afip_sandbox.py`**
- **Propósito**: Test de conexión con AFIP en entorno sandbox
- **Utilidad**: Debug de problemas de integración AFIP
- **Acción**: MANTENER en carpeta `tests/`
- **Razón**: Útil para verificar credenciales y conexión

**`test_ticket_con_cae.py`**
- **Propósito**: Documentación de cómo funciona el CAE en tickets
- **Utilidad**: Guía para usuarios y desarrolladores
- **Acción**: MANTENER en carpeta `tests/` o renombrar a `docs/`
- **Razón**: Documenta la nueva funcionalidad de v2.0

---

### 🗑️ ARCHIVAR (ya no son necesarios)

**`test_afip_simple.py`**
- **Propósito**: Test simple de AFIP durante desarrollo
- **Razón para archivar**: Funcionalidad ya probada e integrada
- **Acción**: Mover a `tests/archive/` o eliminar

**`test_dialog_tarjeta.py`**
- **Propósito**: Test del diálogo de tarjeta durante desarrollo
- **Razón para archivar**: Diálogo ya implementado y funcionando
- **Acción**: Mover a `tests/archive/` o eliminar

**`test_tipos_comprobante.py`**
- **Propósito**: Test de tipos de comprobantes (A, B, C)
- **Razón para archivar**: Tipos ya implementados y verificados
- **Acción**: Mover a `tests/archive/` o eliminar

---

## Estructura Propuesta

```
Compraventas/
├── main.py
├── app/
│   └── ...
├── tests/                          # NUEVA carpeta
│   ├── test_afip_sandbox.py       # Mantener
│   ├── test_ticket_con_cae.py     # Mantener
│   └── archive/                    # Para tests obsoletos
│       ├── test_afip_simple.py
│       ├── test_dialog_tarjeta.py
│       └── test_tipos_comprobante.py
├── docs/                           # NUEVA carpeta (opcional)
│   ├── CHANGELOG_v2.0.md
│   ├── plantillas_tickets.md
│   └── guia_tickets_cae.md        # Renombrar test_ticket_con_cae.py
└── ...
```

---

## Plan de Acción Recomendado

### Opción 1: Crear estructura de tests (Recomendado)
```bash
# Crear carpetas
mkdir tests
mkdir tests/archive
mkdir docs

# Mover archivos útiles
mv test_afip_sandbox.py tests/
mv test_ticket_con_cae.py tests/

# Archivar archivos obsoletos
mv test_afip_simple.py tests/archive/
mv test_dialog_tarjeta.py tests/archive/
mv test_tipos_comprobante.py tests/archive/

# Mover documentación
mv CHANGELOG_v2.0.md docs/
mv plantillas_tickets.md docs/
```

### Opción 2: Eliminación directa (Más limpio)
```bash
# Eliminar archivos obsoletos
del test_afip_simple.py
del test_dialog_tarjeta.py
del test_tipos_comprobante.py

# Mantener solo los útiles en raíz o mover a carpeta tests
```

### Opción 3: Mantener todo como está (No recomendado)
- Dejar todo en raíz
- No recomendado porque genera desorden

---

## Resumen Ejecutivo

**Archivos a ELIMINAR**:
- `test_afip_simple.py` ❌
- `test_dialog_tarjeta.py` ❌
- `test_tipos_comprobante.py` ❌

**Archivos a MANTENER**:
- `test_afip_sandbox.py` ✅ (útil para debug AFIP)
- `test_ticket_con_cae.py` ✅ (documenta funcionalidad CAE)

**Total a eliminar**: 3 archivos (~300 líneas de código obsoleto)
**Total a mantener**: 2 archivos (~200 líneas de código útil)

---

## ¿Qué Hacemos?

Por favor confirma cuál opción prefieres:
1. Crear estructura `tests/` y `docs/` (profesional)
2. Eliminar directamente los 3 archivos obsoletos (rápido)
3. Dejar todo como está (no recomendado)

**Recomendación**: Opción 1 (estructura profesional para v2.0)
