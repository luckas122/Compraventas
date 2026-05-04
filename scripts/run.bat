@echo off
rem ─────────────────────────────────────────────────────────────────────
rem  Wrapper que activa el venv y corre cualquier script en /scripts.
rem
rem  Uso:
rem    scripts\run.bat bulk_migrate_to_supabase.py
rem    scripts\run.bat diff_backends.py
rem    scripts\run.bat bulk_migrate_to_supabase.py --tipos productos
rem
rem  Requiere que el venv ya este creado (build.bat lo crea la primera vez).
rem ─────────────────────────────────────────────────────────────────────

setlocal

rem ir a la raiz del repo (un nivel arriba del directorio del .bat)
pushd "%~dp0\.."

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: el venv no existe en .venv\
    echo Corre build.bat primero para crearlo, o crealo a mano:
    echo   python -m venv .venv
    echo   .venv\Scripts\activate
    echo   pip install -r requirements.txt
    popd
    exit /b 1
)

if "%~1"=="" (
    echo Uso: scripts\run.bat ^<script.py^> [args...]
    echo Ejemplos:
    echo   scripts\run.bat bulk_migrate_to_supabase.py
    echo   scripts\run.bat diff_backends.py
    popd
    exit /b 1
)

set "SCRIPT=scripts\%~1"
shift

if not exist "%SCRIPT%" (
    echo ERROR: %SCRIPT% no existe
    popd
    exit /b 1
)

rem activar venv y ejecutar
call .venv\Scripts\activate.bat
python "%SCRIPT%" %1 %2 %3 %4 %5 %6 %7 %8 %9
set EXITCODE=%ERRORLEVEL%
call .venv\Scripts\deactivate.bat 2>nul

popd
exit /b %EXITCODE%
