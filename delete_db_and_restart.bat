@echo off
REM Script para eliminar la base de datos y reiniciar la aplicación
REM Argumentos: %1 = ruta DB, %2 = ruta app

echo ========================================
echo   ELIMINANDO BASE DE DATOS
echo ========================================
echo.
echo Esperando a que la aplicacion se cierre...
timeout /t 5 /nobreak >nul

echo.
echo Ruta DB: %1
echo Ruta App: %2
echo.

REM Verificar que la DB existe
if not exist "%~1" (
    echo ERROR: No se encontro la base de datos en:
    echo %~1
    echo.
    pause
    exit /b 1
)

REM Mostrar info del archivo
echo Archivo encontrado. Tamanio:
dir "%~1" | find /i ".db"
echo.

REM Intentar eliminar
echo Eliminando base de datos...
del /F /Q "%~1" 2>nul

REM Verificar que se eliminó
if exist "%~1" (
    echo.
    echo ERROR: No se pudo eliminar la base de datos.
    echo El archivo puede estar siendo usado por otro proceso.
    echo.
    pause
    exit /b 1
) else (
    echo.
    echo [OK] Base de datos eliminada exitosamente
    echo.
)

REM Reiniciar la aplicación
echo Reiniciando aplicacion...
cd /d "%~dp2"
start "" "%~2"

REM Esperar un poco antes de autodestruirse
timeout /t 2 /nobreak >nul

REM Autodestruir el script
del "%~f0"
