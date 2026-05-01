@echo off
setlocal

REM Activa .venv y arranca la app Streamlit.

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] No existe .venv. Ejecuta primero setup.bat.
    exit /b 1
)

".venv\Scripts\python.exe" -m streamlit run app.py %*
endlocal
