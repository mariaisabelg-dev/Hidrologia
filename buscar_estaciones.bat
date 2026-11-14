@echo off
rem =====================================================================
rem  BUSCAR ESTACIONES PLUVIOMETRICAS CERCANAS A UN PROYECTO
rem
rem  1. Escriba los datos del proyecto en las 3 filas de abajo,
rem     despues del signo "=" (sin borrar las comillas del inicio y final).
rem  2. Guarde el archivo (Ctrl+S).
rem  3. Ejecutelo: doble clic sobre este archivo en el Explorador de
rem     Windows, o en la terminal de VS Code escriba:  .\buscar_estaciones.bat
rem
rem  - Latitud y longitud en grados decimales, con PUNTO decimal.
rem    La longitud en Colombia es negativa (Oeste).   Ej: 6.2442 / -75.5812
rem  - Tambien acepta grados minutos segundos SIN simbolos.
rem    Ej: 6 14 39 N  /  75 34 52 W
rem  - Si deja Latitud o Longitud vacias, el programa se las pedira
rem    en la pantalla al ejecutarlo.
rem =====================================================================

set "LATITUD=6.2442"
set "LONGITUD=-75.5812"
set "NOMBRE_PROYECTO=Prueba Medellin"

rem ---------------------- No modificar debajo de esta linea ----------------------
cd /d "%~dp0"
chcp 65001 >nul
if not exist ".venv\Scripts\python.exe" (
    echo Instalando el entorno de Python por primera vez...
    python -m venv .venv || goto :error
    ".venv\Scripts\python" -m pip install -q -r requirements.txt || goto :error
)
if "%NOMBRE_PROYECTO%"=="" set "NOMBRE_PROYECTO=Proyecto"
if "%LATITUD%"=="" goto :preguntar
if "%LONGITUD%"=="" goto :preguntar
".venv\Scripts\python" main.py "%LATITUD%, %LONGITUD%" --nombre "%NOMBRE_PROYECTO%"
goto :fin
:preguntar
".venv\Scripts\python" main.py
:fin
echo.
pause
exit /b 0
:error
echo No se pudo preparar el entorno de Python.
pause
exit /b 1
