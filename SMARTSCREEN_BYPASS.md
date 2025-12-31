# Cómo instalar "Tu local 2025" con la advertencia de SmartScreen

## ¿Por qué aparece la advertencia?

Windows SmartScreen muestra una advertencia porque el instalador **NO está firmado digitalmente** con un certificado de código. Esto es **completamente normal** para aplicaciones sin firma y **no significa que sea peligroso**.

---

## 🛡️ Instalación paso a paso

### Paso 1: Descargar el instalador
Descarga `Tu.local.2025.vX.X.X.Setup.exe` desde GitHub Releases.

### Paso 2: SmartScreen aparece
Al ejecutar el instalador, verás una de estas dos pantallas:

#### Opción A: "Windows protegió su equipo"
```
┌─────────────────────────────────────────┐
│ Windows protegió su equipo              │
│                                          │
│ Microsoft Defender SmartScreen impidió  │
│ el inicio de una aplicación no          │
│ reconocida...                            │
│                                          │
│         [No ejecutar]                    │
│         Más información                  │  ← HACER CLIC AQUÍ
└─────────────────────────────────────────┘
```

**SOLUCIÓN**:
1. Hacer clic en **"Más información"**
2. Aparecerá un nuevo botón: **"Ejecutar de todas formas"**
3. Hacer clic en **"Ejecutar de todas formas"**

#### Opción B: "¿Desea permitir que esta aplicación..."
```
┌─────────────────────────────────────────┐
│ Control de cuentas de usuario           │
│                                          │
│ ¿Desea permitir que esta aplicación de  │
│ un editor desconocido realice cambios?  │
│                                          │
│ Editor desconocido                       │  ← Normal sin certificado
│ Tu.local.2025.vX.X.X.Setup.exe          │
│                                          │
│         [Sí]            [No]             │
└─────────────────────────────────────────┘
```

**SOLUCIÓN**:
1. Hacer clic en **"Sí"**
2. El instalador se ejecutará normalmente

### Paso 3: Elegir carpeta de instalación
El instalador te preguntará **DÓNDE** instalar la aplicación:

```
Carpeta predeterminada: C:\Program Files\Tu local 2025
```

**Puedes**:
- Dejar la carpeta predeterminada (recomendado)
- Cambiar a otra ubicación haciendo clic en "Examinar..."
- Ejemplos válidos:
  - `C:\Program Files\Tu local 2025` (predeterminado)
  - `D:\Aplicaciones\Tu local 2025`
  - `C:\MisSoftware\Tu local 2025`

> **Nota**: El instalador pedirá permisos de **administrador** para instalar en `C:\Program Files\`. Esto es normal y seguro.

### Paso 4: Finalizar instalación
El instalador:
1. ✅ Copiará todos los archivos necesarios
2. ✅ Creará accesos directos en escritorio y menú inicio
3. ✅ Preservará tu configuración y base de datos (si es una actualización)

---

## 🔄 Actualizaciones: ¿Se pierde la configuración?

**NO**, el instalador está diseñado para preservar:
- ✅ **Base de datos** (`appcomprasventas.db`) - tus ventas, productos, clientes
- ✅ **Configuración** (`app_config.json`) - SMTP, AFIP, tickets, etc.

### Cómo funciona la preservación:

**Antes de instalar**:
```
1. Instalador detecta instalación previa
2. Respalda appcomprasventas.db → C:\Windows\Temp\
3. Respalda app_config.json → C:\Windows\Temp\
```

**Durante instalación**:
```
4. Sobrescribe archivos de programa (.exe, .dll, etc.)
```

**Después de instalar**:
```
5. Restaura appcomprasventas.db → carpeta de instalación
6. Restaura app_config.json → _internal\app\
7. Elimina backups temporales
```

### Verificar que se preservó la configuración:

Después de actualizar, abre la app y verifica:
1. **Configuración → Email**: ¿Sigue tu configuración SMTP?
2. **Configuración → AFIP**: ¿Siguen tus credenciales?
3. **Ventas**: ¿Aparecen tus datos anteriores?

Si algo se perdió, busca el log del instalador:
```
C:\Users\TuUsuario\AppData\Local\Temp\Setup Log YYYY-MM-DD #001.txt
```

Busca líneas como:
```
✓ Config respaldado exitosamente
✓ BD respaldada exitosamente
✓ Config restaurado exitosamente
✓ BD restaurada exitosamente
```

---

## 🔒 ¿Es seguro instalar sin firma digital?

**SÍ**, pero debes asegurarte de descargar desde la **fuente oficial**:

### ✅ Fuente oficial (SEGURA):
```
https://github.com/luckas122/Compraventas/releases
```

### ✅ Verificar integridad (opcional pero recomendado):

1. **Verificar hash SHA256** del archivo descargado:

En PowerShell:
```powershell
Get-FileHash "Tu.local.2025.vX.X.X.Setup.exe" -Algorithm SHA256
```

Compara el hash con el publicado en la página de Release.

2. **Verificar tamaño del archivo**:
- El instalador debe tener ~90-120 MB aproximadamente
- Si es mucho más pequeño o grande, puede ser un archivo corrupto

### ❌ NUNCA descargar de:
- Sitios de descarga de terceros
- Enlaces en correos electrónicos no solicitados
- Sitios de "cracks" o "activadores"

---

## 🎯 Solución definitiva: Certificado de firma de código

Para eliminar completamente la advertencia de SmartScreen, se necesita un **certificado de firma de código**.

Ver archivo: `CERTIFICADO_FIRMA.md` para más detalles.

**Resumen**:
- **Costo**: $100-500 USD/año (según tipo)
- **Efecto**: SmartScreen desaparece completamente
- **Proceso**: 7-14 días de validación empresarial

---

## 📞 ¿Problemas?

Si el instalador falla o no preserva la configuración:

1. **Revisar el log**:
   ```
   C:\Users\TuUsuario\AppData\Local\Temp\Setup Log YYYY-MM-DD #001.txt
   ```

2. **Desinstalar e instalar limpio**:
   - Panel de Control → Desinstalar programas → "Tu local 2025"
   - Respaldar manualmente:
     - `C:\Program Files\Tu local 2025\appcomprasventas.db`
     - `C:\Program Files\Tu local 2025\_internal\app\app_config.json`
   - Instalar de nuevo
   - Restaurar archivos manualmente

3. **Alternativa ZIP** (sin instalador):
   - Descargar `Compraventas-vX.X.X-onedir.zip`
   - Extraer a cualquier carpeta
   - Ejecutar `Tu local 2025.exe` directamente
   - **NO aparece SmartScreen** (solo al instalador .exe)

---

## 📝 Resumen ejecutivo

| Pregunta | Respuesta |
|----------|-----------|
| ¿Es seguro? | ✅ Sí, si descargas desde GitHub oficial |
| ¿Por qué SmartScreen? | Sin firma digital (normal en software sin certificado) |
| ¿Cómo instalar? | "Más información" → "Ejecutar de todas formas" |
| ¿Se pierde config? | ❌ NO, el instalador la preserva automáticamente |
| ¿Puedo elegir carpeta? | ✅ Sí, durante instalación |
| ¿Necesito admin? | ✅ Solo para Program Files, no para otras carpetas |
| ¿Cómo eliminar advertencia? | Certificado de firma ($100-500/año) |
