@echo off
REM ========================================================================
REM BUILD MSI - Compilar instalador MSI con WiX Toolset
REM ========================================================================
setlocal enabledelayedexpansion

echo ========================================
echo    BUILD MSI - Tu local 2025
echo ========================================
echo.

REM Detectar versión
echo [1/7] Detectando version...
for /f "tokens=*" %%i in ('python -c "from version import __version__; print(__version__)"') do set VERSION=%%i
echo Version: %VERSION%
echo.

REM Verificar que existe dist\Tu local 2025
if not exist "dist\Tu local 2025" (
    echo ERROR: No se encontro dist\Tu local 2025
    echo.
    echo Primero debes compilar la aplicacion con:
    echo   python -m PyInstaller build.spec --clean --noconfirm
    echo.
    pause
    exit /b 1
)

REM Verificar que existe WiX Toolset
echo [2/7] Verificando WiX Toolset...
where candle >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: WiX Toolset no esta instalado o no esta en PATH
    echo.
    echo Descarga WiX desde: https://wixtoolset.org/
    echo O instala via: dotnet tool install --global wix
    echo.
    pause
    exit /b 1
)
echo   - WiX encontrado OK

REM Crear carpeta de salida
echo [3/7] Creando carpeta de salida...
if not exist "msi_output" mkdir msi_output
echo   - Carpeta msi_output\ creada

REM Generar GUID único para este build (ProductId)
echo [4/7] Generando GUIDs...
REM Usar timestamp como seed para generar GUID reproducible
set PRODUCT_GUID=%RANDOM%%RANDOM%-%RANDOM%-%RANDOM%-%RANDOM%-%RANDOM%%RANDOM%
echo   - Product GUID: %PRODUCT_GUID%

REM Actualizar versión en installer.wxs
echo [5/7] Actualizando version en installer.wxs...
powershell -Command "(Get-Content installer.wxs) -replace '(?<=ProductVersion = \")[0-9.]+', '%VERSION%' | Set-Content installer.wxs.tmp"
move /y installer.wxs.tmp installer.wxs >nul
echo   - Version actualizada a %VERSION%

REM Compilar con candle (WiX compiler)
echo [6/7] Compilando con WiX candle...
candle installer.wxs -o msi_output\installer.wixobj -ext WixUIExtension
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Falló compilacion con candle
    pause
    exit /b 1
)
echo   - Compilacion OK

REM Enlazar con light (WiX linker)
echo [7/7] Enlazando con WiX light...
set MSI_NAME=Tu.local.2025.v%VERSION%.msi
light msi_output\installer.wixobj -o "msi_output\%MSI_NAME%" -ext WixUIExtension -ext WixUtilExtension -cultures:es-ES -sice:ICE61
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Falló enlazado con light
    pause
    exit /b 1
)
echo   - Enlazado OK

REM Verificar resultado
if not exist "msi_output\%MSI_NAME%" (
    echo ERROR: No se genero el archivo MSI
    pause
    exit /b 1
)

REM Mostrar tamaño del archivo
for %%I in ("msi_output\%MSI_NAME%") do set MSI_SIZE=%%~zI
set /a MSI_SIZE_MB=!MSI_SIZE! / 1048576
echo.
echo ========================================
echo   BUILD MSI COMPLETADO
echo ========================================
echo.
echo Archivo generado: msi_output\%MSI_NAME%
echo Tamaño: !MSI_SIZE_MB! MB
echo.
echo SIGUIENTE PASO:
echo 1. Prueba el instalador ejecutando el .msi
echo 2. Si funciona correctamente, sube el .msi a GitHub Releases
echo.
pause
