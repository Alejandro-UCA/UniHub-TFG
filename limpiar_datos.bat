@echo off
REM ==============================================================================
REM Script de Limpieza Completa de Datos y Caché de UniHub
REM Prepara el entorno para una ejecución 100% limpia desde cero
REM ==============================================================================
chcp 65001 >nul
title UniHub - Limpieza de Datos y Caché

echo ======================================================================
echo          UNIHUB - LIMPIEZA DE DATOS Y CACHÉ DEL CRAWLER
echo ======================================================================
echo.
echo Este script eliminará los planes de estudio antiguos y las bases de
echo datos de caché para que la próxima ejecución procese el 100%% del
echo catálogo desde cero con las últimas correcciones del parser.
echo.

set "CONFIRM=N"
if "%~1"=="-y" goto DO_CLEAN
if "%~1"=="--yes" goto DO_CLEAN
if "%~1"=="/y" goto DO_CLEAN

set /p "CONFIRM=¿Estás seguro de que deseas limpiar todos los datos descargados? (S/N): "
if /i "%CONFIRM%" NEQ "S" if /i "%CONFIRM%" NEQ "SI" (
    echo.
    echo [CANCELADO] Operación de limpieza cancelada por el usuario.
    echo.
    pause
    exit /b 0
)

:DO_CLEAN
echo.
echo [1/4] Eliminando archivos JSON de planes de estudio antiguos...
set "PLANES_DIR=%~dp0Codigo\Crawler\Datos\planes_estudio"
if exist "%PLANES_DIR%" (
    del /f /q "%PLANES_DIR%\*.json" >nul 2>&1
    rd /s /q "%PLANES_DIR%" >nul 2>&1
)
mkdir "%PLANES_DIR%" >nul 2>&1
echo   -> Carpeta 'planes_estudio/' vaciada y lista.

echo [2/4] Eliminando base de datos de caché SQLite WAL y checkpoints...
set "DATOS_DIR=%~dp0Codigo\Crawler\Datos"
if exist "%DATOS_DIR%\unihub_cache.sqlite3" del /f /q "%DATOS_DIR%\unihub_cache.sqlite3" >nul 2>&1
if exist "%DATOS_DIR%\unihub_cache.sqlite3-wal" del /f /q "%DATOS_DIR%\unihub_cache.sqlite3-wal" >nul 2>&1
if exist "%DATOS_DIR%\unihub_cache.sqlite3-shm" del /f /q "%DATOS_DIR%\unihub_cache.sqlite3-shm" >nul 2>&1
if exist "%DATOS_DIR%\checkpoint.json" del /f /q "%DATOS_DIR%\checkpoint.json" >nul 2>&1
if exist "%DATOS_DIR%\errores_crawler.json" del /f /q "%DATOS_DIR%\errores_crawler.json" >nul 2>&1
if exist "%DATOS_DIR%\estadisticas_rendimiento.json" del /f /q "%DATOS_DIR%\estadisticas_rendimiento.json" >nul 2>&1
echo   -> Archivos de caché y checkpoint eliminados.

echo [3/4] Limpiando carpeta temporal de descargas de PDFs/XLS...
set "TEMP_DIR=%~dp0Codigo\Crawler\Datos\Temp"
if exist "%TEMP_DIR%" (
    del /f /q "%TEMP_DIR%\*.*" >nul 2>&1
    rd /s /q "%TEMP_DIR%" >nul 2>&1
)
mkdir "%TEMP_DIR%" >nul 2>&1
echo   -> Carpeta 'Temp/' limpiada.

echo [4/4] Verificando integridad de estructura de directorios...
if not exist "%DATOS_DIR%" mkdir "%DATOS_DIR%" >nul 2>&1
if not exist "%PLANES_DIR%" mkdir "%PLANES_DIR%" >nul 2>&1
if not exist "%TEMP_DIR%" mkdir "%TEMP_DIR%" >nul 2>&1

echo.
echo ======================================================================
echo       ¡LIMPIEZA COMPLETADA CON ÉXITO!
echo ======================================================================
echo.
echo El entorno ha quedado completamente limpio.
echo La próxima vez que ejecutes el proyecto o el crawler:
echo   - Se descargarán e inspeccionarán todos los planes de estudio.
echo   - Se aplicará el nuevo motor de parsing y segmentación sin datos residuales.
echo.
pause
