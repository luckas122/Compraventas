@echo off
REM ========================================================================
REM SCRIPT DE ACTUALIZACION MANUAL - Tu local 2025
REM ========================================================================
REM
REM Este script permite actualizar manualmente cuando la actualizacion
REM automatica falla con ERROR 32 (archivos bloqueados).
REM
REM INSTRUCCIONES:
REM 1. Descarga el ZIP de la ultima version desde GitHub Releases
REM 2. Extrae el ZIP en una carpeta temporal (ej: C:\Temp\)
REM 3. CIERRA la aplicacion "Tu local 2025" completamente
REM 4. Ejecuta este script desde la carpeta extraida
REM 5. El script hara el resto automaticamente
REM
REM ========================================================================

echo ========================================================================
echo   ACTUALIZACION MANUAL - Tu local 2025
echo ========================================================================
echo.

REM Detectar si estamos ejecutando desde carpeta de actualizacion
set "SCRIPT_DIR=%~dp0"
echo Script ejecutandose desde: %SCRIPT_DIR%
echo.

REM Buscar instalacion actual
set "INSTALL_DIR="

REM Intentar ubicaciones comunes
if exist "%LOCALAPPDATA%\Compraventas\app\Tu local 2025.exe" (
    set "INSTALL_DIR=%LOCALAPPDATA%\Compraventas\app"
) else if exist "%APPDATA%\Compraventas\app\Tu local 2025.exe" (
    set "INSTALL_DIR=%APPDATA%\Compraventas\app"
) else if exist "%USERPROFILE%\Tu local 2025\Tu local 2025.exe" (
    set "INSTALL_DIR=%USERPROFILE%\Tu local 2025"
)

if "%INSTALL_DIR%"=="" (
    echo ERROR: No se pudo encontrar la instalacion actual de Tu local 2025
    echo.
    echo Por favor, ingresa la ruta donde esta instalada la aplicacion:
    echo Ejemplo: C:\Users\TuUsuario\AppData\Local\Compraventas\app
    echo.
    set /p "INSTALL_DIR=Ruta de instalacion: "
)

if not exist "%INSTALL_DIR%\Tu local 2025.exe" (
    echo.
    echo ERROR: No se encontro "Tu local 2025.exe" en:
    echo %INSTALL_DIR%
    echo.
    echo Verifica la ruta e intenta nuevamente.
    pause
    exit /b 1
)

echo Instalacion encontrada en: %INSTALL_DIR%
echo.

REM ========================================================================
REM PASO 1: Verificar que la app este cerrada
REM ========================================================================
echo [1/6] Verificando que la aplicacion este cerrada...
tasklist /FI "IMAGENAME eq Tu local 2025.exe" 2>NUL | find /I /N "Tu local 2025.exe">NUL
if "%ERRORLEVEL%"=="0" (
    echo.
    echo ADVERTENCIA: La aplicacion sigue corriendo!
    echo.
    choice /C SN /M "Deseas forzar el cierre de la aplicacion"
    if errorlevel 2 (
        echo Actualizacion cancelada. Cierra la app manualmente y vuelve a ejecutar este script.
        pause
        exit /b 1
    )
    echo Cerrando aplicacion...
    taskkill /F /IM "Tu local 2025.exe" >nul 2>&1
    timeout /t 2 /nobreak >nul
)
echo   - Aplicacion cerrada OK

REM ========================================================================
REM PASO 2: Respaldar configuracion y BD
REM ========================================================================
echo [2/6] Respaldando configuracion y base de datos...
set "CONFIG_FILE=%INSTALL_DIR%\_internal\app\app_config.json"
set "DB_FILE=%INSTALL_DIR%\appcomprasventas.db"
set "TEMP_BACKUP=%TEMP%\compraventas_manual_backup_%RANDOM%"

mkdir "%TEMP_BACKUP%" 2>nul

if exist "%CONFIG_FILE%" (
    copy /Y "%CONFIG_FILE%" "%TEMP_BACKUP%\app_config.json" >nul 2>&1
    if exist "%TEMP_BACKUP%\app_config.json" (
        echo   - Configuracion respaldada OK
    ) else (
        echo   - ADVERTENCIA: No se pudo respaldar configuracion
    )
) else (
    echo   - No se encontro configuracion previa
)

if exist "%DB_FILE%" (
    copy /Y "%DB_FILE%" "%TEMP_BACKUP%\appcomprasventas.db" >nul 2>&1
    if exist "%TEMP_BACKUP%\appcomprasventas.db" (
        echo   - Base de datos respaldada OK
    ) else (
        echo   - ADVERTENCIA: No se pudo respaldar BD
    )
) else (
    echo   - No se encontro BD previa
)

REM ========================================================================
REM PASO 3: Renombrar carpeta actual → backup
REM ========================================================================
echo [3/6] Renombrando carpeta actual a backup...

REM Obtener directorio padre y nombre de carpeta
for %%I in ("%INSTALL_DIR%") do (
    set "PARENT_DIR=%%~dpI"
    set "FOLDER_NAME=%%~nxI"
)

set "BACKUP_NAME=%FOLDER_NAME%_backup_%RANDOM%"
set "BACKUP_PATH=%PARENT_DIR%%BACKUP_NAME%"

move "%INSTALL_DIR%" "%BACKUP_PATH%" >nul 2>&1
if exist "%BACKUP_PATH%" (
    echo   - Carpeta renombrada: %BACKUP_NAME%
) else (
    echo ERROR: No se pudo renombrar la carpeta actual
    echo.
    echo Verifica que no haya procesos usando archivos en:
    echo %INSTALL_DIR%
    pause
    exit /b 1
)

REM ========================================================================
REM PASO 4: Copiar nueva version
REM ========================================================================
echo [4/6] Instalando nueva version...

REM Verificar que existan archivos en el directorio del script
if not exist "%SCRIPT_DIR%_internal" (
    echo ERROR: No se encuentra la carpeta _internal en el directorio actual
    echo.
    echo Asegurate de ejecutar este script desde la carpeta donde extrajiste el ZIP
    echo.
    echo Restaurando carpeta original...
    move "%BACKUP_PATH%" "%INSTALL_DIR%" >nul 2>&1
    pause
    exit /b 1
)

REM Copiar toda la carpeta del script al directorio de instalacion
xcopy "%SCRIPT_DIR%*" "%INSTALL_DIR%\" /E /I /H /Y >nul 2>&1

if exist "%INSTALL_DIR%\Tu local 2025.exe" (
    echo   - Nueva version instalada OK
) else (
    echo ERROR: No se pudo copiar la nueva version
    echo.
    echo Restaurando carpeta original...
    move "%BACKUP_PATH%" "%INSTALL_DIR%" >nul 2>&1
    pause
    exit /b 1
)

REM ========================================================================
REM PASO 5: Restaurar configuracion y BD
REM ========================================================================
echo [5/6] Restaurando configuracion y base de datos...
set "NEW_CONFIG_FILE=%INSTALL_DIR%\_internal\app\app_config.json"
set "NEW_DB_FILE=%INSTALL_DIR%\appcomprasventas.db"

if exist "%TEMP_BACKUP%\app_config.json" (
    copy /Y "%TEMP_BACKUP%\app_config.json" "%NEW_CONFIG_FILE%" >nul 2>&1
    if exist "%NEW_CONFIG_FILE%" (
        echo   - Configuracion restaurada OK
    ) else (
        echo   - ADVERTENCIA: No se pudo restaurar configuracion
    )
)

if exist "%TEMP_BACKUP%\appcomprasventas.db" (
    copy /Y "%TEMP_BACKUP%\appcomprasventas.db" "%NEW_DB_FILE%" >nul 2>&1
    if exist "%NEW_DB_FILE%" (
        echo   - Base de datos restaurada OK
    ) else (
        echo   - ADVERTENCIA: No se pudo restaurar BD
    )
)

REM Limpiar backup temporal
rd /s /q "%TEMP_BACKUP%" 2>nul

REM ========================================================================
REM PASO 6: Crear acceso directo
REM ========================================================================
echo [6/6] Creando acceso directo en escritorio...
set "EXE_PATH=%INSTALL_DIR%\Tu local 2025.exe"
powershell -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\Tu local 2025.lnk'); $s.TargetPath = '%EXE_PATH%'; $s.WorkingDirectory = '%INSTALL_DIR%'; $s.Save()" 2>nul

REM ========================================================================
REM Finalizacion
REM ========================================================================
echo.
echo ========================================================================
echo   ACTUALIZACION COMPLETADA EXITOSAMENTE
echo ========================================================================
echo.
echo Nueva version instalada en:
echo %INSTALL_DIR%
echo.
echo Carpeta antigua guardada en:
echo %BACKUP_PATH%
echo (Puedes eliminarla manualmente si la app funciona correctamente)
echo.
echo.
choice /C SN /M "Deseas iniciar la aplicacion ahora"
if errorlevel 2 goto :end

echo.
echo Iniciando aplicacion...
start "" "%EXE_PATH%"

:end
echo.
echo Presiona cualquier tecla para salir...
pause >nul
