# Instrucciones para Probar y Obtener Log de Sync

## Cambios Realizados en v2.5.2

He corregido el problema del crash al probar conexión SMTP/IMAP con 3 soluciones:

### 1. **build.spec** - Módulos SSL incluidos
- Agregados 11 módulos SSL/email a `hiddenimports`:
  - `ssl`, `_ssl`, `_hashlib`
  - `smtplib`, `imaplib`
  - `email`, `email.mime.*`
- Incluidos certificados SSL de certifi como data files

### 2. **sync_config.py** - Logging detallado
- La función `_test_connection()` ahora guarda un log completo en:
  ```
  app/logs/sync_test_connection.log
  ```
- El log incluye:
  - Versión de Python y si está en modo frozen (PyInstaller)
  - Módulos SSL disponibles
  - Certificados SSL encontrados
  - Debug paso a paso de SMTP e IMAP
  - Traceback completo de cualquier error

### 3. **Uso de certifi**
- El código intenta usar certificados de certifi si están disponibles
- Fallback a certificados del sistema si certifi no está

---

## 🔨 Paso 1: Recompilar la Aplicación

**IMPORTANTE:** Debes recompilar porque cambió `build.spec`

```bash
# 1. Activar venv
.venv\Scripts\activate

# 2. Limpiar build anterior (opcional pero recomendado)
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

# 3. Compilar con build.bat
build.bat
```

Verifica que compile sin errores. Si sale "No suitable Python runtime found", significa que el venv no está activado.

---

## 🧪 Paso 2: Probar en el Ejecutable Compilado

1. **Ir a la carpeta dist:**
   ```bash
   cd dist\Tu local 2025
   ```

2. **Ejecutar el .exe:**
   ```bash
   "Tu local 2025.exe"
   ```

3. **Ir a Configuración → Sincronización:**
   - Rellena los campos de SMTP (aunque sean datos de prueba):
     - Host: smtp.gmail.com
     - Port: 587
     - Usuario: tu-email@gmail.com
     - Contraseña: cualquier-cosa (no importa que sea incorrecta)

4. **Click en "Probar conexión"**

5. **Observar qué pasa:**
   - ¿Se cierra la aplicación? (crash)
   - ¿Aparece un mensaje de error?
   - ¿El mensaje menciona un archivo de log?

---

## 📋 Paso 3: Obtener el Log

Después de hacer la prueba, busca el archivo de log:

**Ubicación del log:**
```
C:\Users\Lucas\Desktop\aplicaciones\Compraventas\dist\Tu local 2025\app\logs\sync_test_connection.log
```

**Si la app crashea silenciosamente**, el log puede estar en:
```
C:\Users\Lucas\Desktop\aplicaciones\Compraventas\app\logs\sync_test_connection.log
```

**Cómo enviármelo:**

Opción A - Pégame el contenido del archivo completo

Opción B - Si es muy largo, envíame las últimas 100 líneas:
```bash
# En PowerShell
Get-Content "app\logs\sync_test_connection.log" -Tail 100
```

Opción C - Si no se crea el log, significa que crashea ANTES de llegar a la función. En ese caso necesitamos otro enfoque.

---

## 🔍 Paso 4: Información Adicional Útil

Además del log, si puedes proporcionar:

1. **¿La app crashea o muestra error?**
   - Si crashea: No aparece nada, la ventana se cierra
   - Si muestra error: Aparece un QMessageBox con mensaje

2. **¿Existe el archivo de log?**
   - Sí → Pégame el contenido
   - No → La app crashea antes de crear el logger

3. **Probar desde Python directamente** (para comparar):
   ```bash
   python main.py
   # Ir a Config → Sync → Probar conexión
   # ¿Funciona? ¿Crea el log?
   ```

---

## 🎯 Lo Que Espero Ver en el Log

Si todo funciona correctamente, el log debería mostrar algo así:

```
================================================================================
INICIO PRUEBA DE CONEXIÓN - 2025-12-26 14:30:00.123456
Python: 3.11.x (tags/v3.11.x:xxxxx, xxx xx xxxx, xx:xx:xx) [MSC v.xxxx 64 bit (AMD64)]
Frozen: True
Executable: C:\...\dist\Tu local 2025\Tu local 2025.exe

Verificando módulos SSL...
  ✓ _ssl disponible: <module '_ssl' (built-in)>
  ✓ _hashlib disponible: <module '_hashlib' (built-in)>
  ✓ ssl.OPENSSL_VERSION: OpenSSL 3.x.x xxx xxxx
  ✓ certifi disponible: C:\...\dist\Tu local 2025\certifi\cacert.pem
  ✓ Archivo existe: True

--- PRUEBA SMTP ---
Host: smtp.gmail.com
Port: 587
User: tu-email@gmail.com
Pass: ***
Intentando conexión SMTP...
Usando certificados de certifi
Contexto SSL creado: <ssl.SSLContext object at 0x...>
Conexión SMTP establecida
[debug SMTP aquí...]
STARTTLS exitoso
Login SMTP exitoso

--- PRUEBA IMAP ---
[similar...]

--- RESULTADO ---
✓ Conexión exitosa a SMTP e IMAP
FIN PRUEBA - 2025-12-26 14:30:05.123456
================================================================================
```

Si crashea, veremos DÓNDE se rompe exactamente.

---

## ❓ Preguntas de Diagnóstico

Si sigue crasheando después de recompilar, responde:

1. **¿Recompilaste con el build.spec modificado?** Sí / No
2. **¿El build.bat se ejecutó sin errores?** Sí / No
3. **¿Se creó el archivo de log?** Sí / No / No lo encontré
4. **¿La app crashea o muestra un mensaje de error?** Crashea / Muestra error
5. **Si muestra error, ¿qué dice exactamente?** [pegar texto]
6. **¿Desde Python (main.py) funciona bien?** Sí / No / No probé

---

## 🚀 Una Vez Que Funcione

Si la prueba de conexión funciona correctamente después de recompilar:

1. Confirmar que todo está OK
2. Actualizar SUBIR_v2.5.2_A_GITHUB.md si es necesario
3. Proceder a subir v2.5.2 a GitHub

Si SIGUE crasheando, con el log podré ver exactamente qué módulo falta o qué certificado no se encuentra.

---

**Estoy esperando el resultado de tu prueba y el contenido del log.**
