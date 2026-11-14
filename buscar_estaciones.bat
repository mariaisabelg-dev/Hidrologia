@echo off
rem Doble clic para buscar estaciones: pide latitud y longitud y genera los entregables en salidas\
cd /d "%~dp0"
chcp 65001 >nul
if not exist ".venv\Scripts\python.exe" (
    echo Instalando el entorno por primera vez...
    python -m venv .venv || goto :error
    ".venv\Scripts\python" -m pip install -q -r requirements.txt || goto :error
)
".venv\Scripts\python" main.py %*
echo.
pause
exit /b 0
:error
echo No se pudo preparar el entorno de Python.
pause
exit /b 1
