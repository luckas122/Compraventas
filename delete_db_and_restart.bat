@echo off
REM Script para eliminar la base de datos y reiniciar la aplicación
REM Argumentos: %1 = ruta DB, %2 = ruta app

echo ========================================
echo   ELIMINANDO BASE DE DATOS
echo ========================================
echo.
echo Ruta DB: %1
echo Ruta App: %2
echo.

REM Verificar que la DB existe antes de esperar
if not exist "%~1" (
    echo ERROR: No se encontro la base de datos en:
    echo %~1
    echo.
    pause
    exit /b 1
)

echo Archivo encontrado.
echo Esperando a que la aplicacion se cierre completamente...
echo.

REM Esperar más tiempo para que la app cierre
timeout /t 3 /nobreak >nul

REM CRÍTICO: Matar TODOS los procesos de la aplicación
echo Verificando procesos de "Tu local 2025"...
tasklist /FI "IMAGENAME eq Tu local 2025.exe" 2>NUL | find /I /N "Tu local 2025.exe">NUL
if "%ERRORLEVEL%"=="0" (
    echo Matando procesos de "Tu local 2025.exe"...
    taskkill /F /IM "Tu local 2025.exe" >nul 2>&1
    timeout /t 2 /nobreak >nul
)

echo Verificando archivos WAL/SHM...
if exist "%~1-wal" (
    echo Eliminando archivo WAL...
    del /F /Q "%~1-wal" 2>nul
)
if exist "%~1-shm" (
    echo Eliminando archivo SHM...
    del /F /Q "%~1-shm" 2>nul
)

timeout /t 2 /nobreak >nul

REM Intentar eliminar con reintentos
set /a intentos=0
:retry_delete
set /a intentos+=1

echo [Intento %intentos%/5] Eliminando base de datos...
del /F /Q "%~1" 2>nul

REM Verificar que se eliminó
if exist "%~1" (
    if %intentos% LSS 5 (
        echo   Archivo aun en uso, esperando 2 segundos...
        timeout /t 2 /nobreak >nul
        goto retry_delete
    ) else (
        echo.
        echo ERROR: No se pudo eliminar la base de datos despues de 5 intentos.
        echo El archivo sigue siendo usado por otro proceso.
        echo.

        REM Intentar identificar qué proceso tiene el archivo abierto
        echo Buscando procesos que tienen el archivo abierto...
        echo.

        REM Método 1: Usar openfiles (requiere permisos admin pero viene con Windows)
        openfiles /query /fo table | findstr /i "appcomprasventas.db" 2>nul
        if errorlevel 1 (
            echo No se pudo identificar el proceso ^(puede requerir permisos de admin^)
        )

        echo.
        echo Procesos Python/Tu local 2025 en ejecucion:
        tasklist | findstr /i "python Tu local" 2>nul

        echo.
        pause
        exit /b 1
    )
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
