@echo off
setlocal enabledelayedexpansion

echo ========================================
echo    BUILD - App Compras y Ventas
echo ========================================
echo.

REM 0) Crear/activar venv
if not exist .venv (
  echo [0/6] Creando entorno .venv...
  py -m venv .venv
)
call .venv\Scripts\activate

REM 1) Instalar dependencias
echo [1/6] Instalando dependencias...
py -m pip install --upgrade pip
py -m pip install -r requirements.txt
py -m pip install -r requirements-dev.txt

REM 2) Limpiar compilaciones anteriores
echo [2/6] Limpiando builds anteriores...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM 3) Generar archivo de version (opcional)
echo [3/6] Generando archivo de versión...
py create_version_file.py

REM 4) Detectar versión
echo [4/6] Detectando versión...
for /f "tokens=*" %%i in ('py -c "from version import __version__; print(__version__)"') do set VERSION=%%i
echo Version: %VERSION%

REM 5) Compilar con PyInstaller (USAR -m)
echo [5/6] Compilando con PyInstaller...
py -m PyInstaller build.spec --clean
if errorlevel 1 (
    echo ERROR: Compilacion fallida
    exit /b 1
)

REM 6) Verificar resultado
echo [6/6] Verificando resultado...
if not exist dist (
  echo ERROR: No se genero la carpeta dist
  exit /b 1
)

echo.
echo ========================================
echo Build OK. Siguiente paso: crear release en GitHub
echo ========================================
echo 1. Edita version.py (si corresponde)
echo 2. git add/commit/push
echo 3. git tag v%VERSION%
echo 4. git push origin v%VERSION%
echo 5. El release subira el .exe
pause
