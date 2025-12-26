# 🚀 Comandos para Subir v2.5.1 a GitHub

## ✅ Cambios en v2.5.1

### Problema Corregido
**Error al relanzar app después de actualizar desde GitHub**

El updater intentaba ejecutar:
```
C:\Users\prueba\AppData\Local\Compraventas\app\Tu local 2025.exe
```

Pero la ruta correcta era:
```
C:\Users\prueba\AppData\Local\Tu local 2025\Tu local 2025.exe
```

### Solución Implementada
- Detección automática del ejecutable en el ZIP descargado
- Manejo correcto de nombres con espacios
- Escapado correcto de rutas en PowerShell

---

## 📝 Archivos Modificados

1. `updater.py` - Corregido manejo de rutas y nombres con espacios
2. `version.py` - Actualizado a 2.5.1
3. `CHANGELOG.md` - Agregado (nuevo archivo)

---

## 🔧 Comandos Git para v2.5.1

### Opción A: Copy-Paste (Todo en uno)

```bash
cd "C:\Users\Lucas\Desktop\aplicaciones\Compraventas"

# Agregar archivos modificados
git add updater.py version.py CHANGELOG.md

# Commit con mensaje descriptivo
git commit -m "fix: Corregir error de rutas en updater v2.5.1

Problema:
- El updater generaba rutas incorrectas al relanzar la app
- Error: 'Windows no puede encontrar el archivo'
- Afectaba a nombres de app con espacios ('Tu local 2025')

Solución:
- Detección automática del ejecutable usando glob('*.exe')
- Manejo correcto de espacios en nombres de carpeta temp
- Escapado correcto de rutas en scripts PowerShell

Cambios técnicos:
- updater.py:267-277 - Auto-detección de ejecutable
- updater.py:377 - Replace espacios en temp dirs
- updater.py:383-384 - Escapado para PowerShell
- version.py - Bump a 2.5.1
- CHANGELOG.md - Documentación completa

Fixes #issue_number

🤖 Generated with Claude Code
Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"

# Crear tag
git tag -a v2.5.1 -m "Hotfix v2.5.1 - Corregir rutas en updater"

# Subir todo
git push origin main
git push origin v2.5.1
```

---

### Opción B: Paso a Paso

#### 1. Ir al directorio del proyecto
```bash
cd "C:\Users\Lucas\Desktop\aplicaciones\Compraventas"
```

#### 2. Ver cambios
```bash
git status
git diff updater.py
git diff version.py
```

#### 3. Agregar archivos
```bash
git add updater.py
git add version.py
git add CHANGELOG.md
```

#### 4. Commit
```bash
git commit -m "fix: Corregir error de rutas en updater v2.5.1

Problema:
- El updater generaba rutas incorrectas al relanzar la app
- Error: 'Windows no puede encontrar el archivo'
- Afectaba a nombres con espacios

Solución:
- Auto-detección del ejecutable en ZIP
- Manejo correcto de espacios
- Escapado correcto para PowerShell

🤖 Generated with Claude Code
Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

#### 5. Crear tag
```bash
git tag -a v2.5.1 -m "Hotfix v2.5.1 - Corregir rutas en updater"
```

#### 6. Verificar antes de subir
```bash
git log -1
git tag
```

#### 7. Subir a GitHub
```bash
git push origin main
git push origin v2.5.1
```

---

## 📦 Crear Release en GitHub (Web)

1. **Ir a tu repositorio:** https://github.com/luckas122/Compraventas

2. **Click en "Releases"** (lado derecho)

3. **Click "Draft a new release"**

4. **Configurar release:**

   - **Choose a tag:** `v2.5.1`
   - **Release title:** `v2.5.1 - Hotfix: Corregir rutas en updater`
   - **Describe this release:**

```markdown
## 🐛 Hotfix v2.5.1 - Corrección de Updater

### Problema Corregido

Al actualizar desde GitHub, la aplicación descargaba correctamente pero fallaba al intentar relanzarse, mostrando el error:

> "Windows no puede encontrar el archivo 'C:\Users\prueba\AppData\Local\Compraventas\app\Tu local 2025.exe'"

### Solución

- ✅ Detección automática del nombre del ejecutable dentro del ZIP
- ✅ Manejo correcto de nombres de aplicación con espacios
- ✅ Escapado correcto de rutas en scripts PowerShell

### Archivos Modificados

- `updater.py` - Corregido manejo de rutas
- `version.py` - Bump a 2.5.1
- `CHANGELOG.md` - Documentación de cambios

### Cómo Actualizar

**Desde v2.5.0:**
1. La aplicación detectará automáticamente esta versión
2. Click en "Sí" cuando pregunte si desea actualizar
3. Esperar descarga
4. La app se cerrará y relanzará automáticamente ✅

**Instalación manual:**
1. Descargar el ZIP adjunto
2. Extraer en la carpeta deseada
3. Ejecutar `Tu local 2025.exe`

### Compatibilidad

- ✅ Compatible con v2.5.0
- ✅ Todas las funcionalidades de sincronización funcionan igual
- ✅ No requiere migración de base de datos

### Notas

- Esta es una corrección menor que **solo afecta al sistema de actualizaciones**
- Todas las demás funcionalidades permanecen iguales que en v2.5.0
- Si ya tienes v2.5.0 funcionando, la actualización es **opcional pero recomendada**

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

5. **Adjuntar archivos:**
   - Subir el ZIP con la carpeta ONEDIR compilada
   - Nombre sugerido: `Tu_local_2025_v2.5.1.zip`

6. **Marcar como "Set as the latest release"**

7. **Click "Publish release"**

---

## ✅ Verificación Post-Publicación

### 1. Verificar en GitHub
```bash
# Ver último commit
git log -1

# Ver todos los tags
git tag

# Ver info del tag v2.5.1
git show v2.5.1
```

### 2. Verificar URL de release
```
https://github.com/luckas122/Compraventas/releases/tag/v2.5.1
```

### 3. Probar updater en VM
1. Abrir app con v2.5.0
2. Menú → Buscar actualizaciones
3. Debe detectar v2.5.1
4. Descargar e instalar
5. **VERIFICAR que relanza correctamente** ✅

---

## 🔍 Si Algo Sale Mal

### Revertir commit (antes de push)
```bash
git reset --soft HEAD~1
```

### Eliminar tag local
```bash
git tag -d v2.5.1
```

### Eliminar tag remoto
```bash
git push origin --delete v2.5.1
```

### Re-hacer release
1. Corregir archivos
2. Hacer nuevo commit
3. Crear nuevo tag
4. Push nuevamente

---

## 📊 Resumen de Cambios

| Archivo | Líneas Modificadas | Descripción |
|---------|-------------------|-------------|
| updater.py | ~15 líneas | Auto-detección de ejecutable |
| version.py | 1 línea | Bump a 2.5.1 |
| CHANGELOG.md | +150 líneas | Documentación completa |

**Total:** ~166 líneas modificadas/agregadas

---

## 🎯 Próximos Pasos Después de Publicar

1. ✅ Actualizar VM de prueba a v2.5.1
2. ✅ Verificar que el updater funciona correctamente
3. ✅ Hacer venta de prueba para confirmar que todo funciona
4. ✅ Si todo OK, actualizar sucursales en producción
5. ✅ Cerrar issue relacionado en GitHub (si existe)

---

**¡Listo para subir v2.5.1 a GitHub!**

Ejecuta la **Opción A** (copy-paste) y luego crea el release en la web.
