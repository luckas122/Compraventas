@echo off
REM Script de compilación para TuLocal V1 - App Compras y Ventas
REM Ejecutar: build.bat

echo ========================================
echo    BUILD - App Compras y Ventas
echo ========================================
echo.

REM Limpiar compilaciones anteriores
echo [1/5] Limpiando builds anteriores...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
echo OK

REM Generar archivo de versión
echo.
echo [2/5] Generando archivo de versión...
python create_version_file.py
if errorlevel 1 (
    echo ERROR: No se pudo generar version_info.txt
    pause
    exit /b 1
)
echo OK

REM Obtener versión actual
echo.
echo [3/5] Detectando versión...
for /f "tokens=*" %%i in ('python -c "from version import __version__; print(__version__)"') do set VERSION=%%i
echo Versión: %VERSION%

REM Compilar con PyInstaller
echo.
echo [4/5] Compilando con PyInstaller...
echo (Esto puede tardar varios minutos)
pyinstaller build.spec --clean
if errorlevel 1 (
    echo ERROR: Compilación fallida
    pause
    exit /b 1
)
echo OK

REM Verificar resultado
echo.
echo [5/5] Verificando resultado...
if exist dist\*.exe (
    echo ========================================
    echo    BUILD COMPLETADO
    echo ========================================
    echo.
    echo Ejecutable generado en: dist\
    dir /b dist\*.exe
    echo.
    echo Presiona cualquier tecla para abrir la carpeta...
    pause >nul
    explorer dist
) else (
    echo ERROR: No se encontró el ejecutable
    pause
    exit /b 1
)

echo.
echo ========================================
echo Siguiente paso: Crear release en GitHub
echo ========================================
echo.
echo 1. Actualiza version.py con la nueva versión
echo 2. Commit y push a GitHub
echo 3. Crea un tag: git tag v%VERSION%
echo 4. Push del tag: git push origin v%VERSION%
echo 5. GitHub Actions compilará y creará el release automáticamente
echo.
pause