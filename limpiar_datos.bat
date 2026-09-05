@echo off
setlocal enabledelayedexpansion

title UniHub - Limpieza Total de Datos y Cache

echo ======================================================================
echo          UNIHUB - LIMPIEZA TOTAL DE DATOS Y CACHE DEL CRAWLER
echo ======================================================================
echo.
echo Este script eliminara TODOS los archivos JSON (catalogos, planes de
echo estudio, precios, checkpoints y estadisticas) asi como las bases de
echo datos SQLite y temporales para una ejecucion 100 por ciento limpia.
echo.

set "CONFIRM=N"
set "AUTO_CONFIRM=0"
if "%~1"=="-y" (set "AUTO_CONFIRM=1" & goto DO_CLEAN)
if "%~1"=="--yes" (set "AUTO_CONFIRM=1" & goto DO_CLEAN)
if "%~1"=="/y" (set "AUTO_CONFIRM=1" & goto DO_CLEAN)

set /p "CONFIRM=Deseas limpiar TODOS los datos y caches? (S/N): "
if /i "%CONFIRM%" NEQ "S" if /i "%CONFIRM%" NEQ "SI" (
    echo.
    echo [CANCELADO] Operacion de limpieza cancelada por el usuario.
    echo.
    pause
    exit /b 0
)

:DO_CLEAN
set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

echo.
echo Ejecutando motor seguro de limpieza con preservacion de semillas maestras...
"%PYTHON_EXE%" "%~dp0Codigo\Crawler\limpieza_datos.py" --force

if errorlevel 1 (
    echo [ERROR] Hubo un error durante la ejecucion de la limpieza de datos.
    if "%AUTO_CONFIRM%"=="0" pause
    exit /b 1
)
echo.
echo El entorno ha quedado completamente virgen:
echo   - Catalogos, planes, caches y temporales del crawler reinicializados.
echo   - Los secretos y archivos fuera de Datos/ no se han modificado.
echo   - Directorios de trabajo recreados para una ejecucion completa.
if "%AUTO_CONFIRM%"=="0" pause
