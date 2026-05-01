@echo off
setlocal

REM Provisiona el entorno virtual .venv del proyecto e instala dependencias.
REM Prioridad de Python: py -3.11, py -3.10, python (en PATH).

cd /d "%~dp0"

if "%~1"=="--recreate" (
    echo [INFO] Forzando recreacion de .venv (eliminando carpeta existente)...
    rmdir /s /q ".venv" 2>nul || echo [INFO] .venv no existia o ya eliminada.
)
 
set "PY_CMD="
py -3.11 -c "import sys" >nul 2>&1
if %ERRORLEVEL%==0 set "PY_CMD=py -3.11"

if not defined PY_CMD (
    py -3.10 -c "import sys" >nul 2>&1
    if %ERRORLEVEL%==0 set "PY_CMD=py -3.10"
)

if not defined PY_CMD (
    python -c "import sys" >nul 2>&1
    if %ERRORLEVEL%==0 set "PY_CMD=python"
)

if not defined PY_CMD (
    echo [ERROR] No se ha encontrado Python. Instala Python 3.11 o 3.10.
    exit /b 1
)

echo Usando interprete: %PY_CMD%

if not exist ".venv\Scripts\python.exe" (
    echo Creando entorno virtual en .venv ...
    %PY_CMD% -m venv .venv
    if errorlevel 1 (
        echo [ERROR] No se pudo crear el entorno virtual.
        exit /b 1
    )
) else (
    echo Reutilizando .venv existente.
)

echo Actualizando pip ...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (
    echo [ERROR] Fallo al actualizar pip.
    exit /b 1
)

echo Instalando dependencias de requirements.txt ...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Fallo al instalar dependencias.
    exit /b 1
)

echo.
echo [OK] Entorno listo. Ejecuta run.bat para arrancar la app.
endlocal
