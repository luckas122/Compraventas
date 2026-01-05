@echo off
setlocal enabledelayedexpansion

echo ========================================
echo    BUILD - App Compras y Ventas
echo ========================================
echo.

REM 0) Crear/activar venv
if not exist .venv (
  echo [0/8] Creando entorno .venv...
  python -m venv .venv
)
call .venv\Scripts\activate

REM 0.5) Resetear configuracion, logs y backups a estado limpio
echo [0.5/8] Reseteando configuracion, logs y backups para el build...
python reset_config_for_build.py

REM 1) Instalar dependencias
echo [1/8] Instalando dependencias...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt

REM 2) Limpiar compilaciones anteriores
echo [2/8] Limpiando builds anteriores...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist installer_output rmdir /s /q installer_output

REM 3) Generar archivo de version (opcional)
echo [3/8] Generando archivo de version...
py create_version_file.py

REM 4) Detectar version
echo [4/8] Detectando version...
for /f "tokens=*" %%i in ('python -c "from version import __version__; print(__version__)"') do set VERSION=%%i
echo Version: %VERSION%

REM 5) Compilar con PyInstaller
echo [5/8] Compilando con PyInstaller...
python -m PyInstaller build.spec --clean --noconfirm
if errorlevel 1 (
    echo ERROR: Compilacion PyInstaller fallida
    pause
    exit /b 1
)

REM 6) Verificar que se genero dist
echo [6/8] Verificando resultado de PyInstaller...
if not exist "dist\Tu local 2025\Tu local 2025.exe" (
  echo ERROR: No se genero el ejecutable en dist
  pause
  exit /b 1
)
echo OK: Ejecutable generado correctamente

REM 7) Compilar instalador con Inno Setup
echo [7/8] Compilando instalador con Inno Setup...

REM Buscar Inno Setup en ubicaciones comunes
set "ISCC="
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
    set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
) else if exist "C:\Program Files\Inno Setup 6\ISCC.exe" (
    set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"
) else if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" (
    set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
)

if "!ISCC!"=="" (
    echo.
    echo ADVERTENCIA: Inno Setup 6 no encontrado.
    echo El ejecutable se genero en: dist\Tu local 2025\
    echo.
    echo Para crear el instalador:
    echo 1. Instala Inno Setup 6 desde https://jrsoftware.org/isinfo.php
    echo 2. Abre installer.iss con Inno Setup Compiler
    echo 3. Click en Compile
    echo.
    pause
    exit /b 0
)

echo Usando: !ISCC!
"!ISCC!" installer.iss
if errorlevel 1 (
    echo ERROR: Compilacion Inno Setup fallida
    pause
    exit /b 1
)

REM 8) Verificar instalador generado
echo [8/8] Verificando instalador...
if not exist "installer_output\Tu.local.2025.v%VERSION%.Setup.exe" (
    echo ERROR: No se genero el instalador
    pause
    exit /b 1
)

echo.
echo ========================================
echo    BUILD COMPLETADO EXITOSAMENTE
echo ========================================
echo.
echo Version: %VERSION%
echo.
echo Archivos generados:
echo   - dist\Tu local 2025\           (carpeta portable)
echo   - installer_output\Tu.local.2025.v%VERSION%.Setup.exe
echo.
echo ========================================
echo    SIGUIENTE: Crear Release en GitHub
echo ========================================
echo.
echo 1. git add . ^&^& git commit -m "build: v%VERSION%"
echo 2. git tag v%VERSION%
echo 3. git push origin main --tags
echo 4. Ir a GitHub ^> Releases ^> Create Release
echo 5. Seleccionar tag v%VERSION%
echo 6. Subir: installer_output\Tu.local.2025.v%VERSION%.Setup.exe
echo.
pause
