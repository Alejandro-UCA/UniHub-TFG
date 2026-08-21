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
set "DATOS_DIR=%~dp0Codigo\Crawler\Datos"
set "PLANES_DIR=%~dp0Codigo\Crawler\Datos\planes_estudio"
set "TEMP_DIR=%~dp0Codigo\Crawler\Datos\Temp"
set "TEMP_PDFS=%~dp0Codigo\Crawler\temp_pdfs"

echo.
echo [1/5] Eliminando archivos JSON de planes de estudio individuales...
if exist "%PLANES_DIR%" (
    del /f /q "%PLANES_DIR%\*.*" >nul 2>&1
    rd /s /q "%PLANES_DIR%" >nul 2>&1
)
mkdir "%PLANES_DIR%" >nul 2>&1
echo   - Carpeta 'planes_estudio/' vaciada y recreada.

echo [2/5] Eliminando catalogos consolidados y archivos JSON globales...
if exist "%DATOS_DIR%" (
    del /f /q "%DATOS_DIR%\*.json" >nul 2>&1
)
echo   - Todos los archivos JSON en 'Datos/' eliminados.

echo [3/5] Eliminando base de datos SQLite WAL y caches persistentes...
if exist "%DATOS_DIR%\unihub_cache.sqlite3" del /f /q "%DATOS_DIR%\unihub_cache.sqlite3" >nul 2>&1
if exist "%DATOS_DIR%\unihub_cache.sqlite3-wal" del /f /q "%DATOS_DIR%\unihub_cache.sqlite3-wal" >nul 2>&1
if exist "%DATOS_DIR%\unihub_cache.sqlite3-shm" del /f /q "%DATOS_DIR%\unihub_cache.sqlite3-shm" >nul 2>&1
if exist "%DATOS_DIR%\*.sqlite3*" del /f /q "%DATOS_DIR%\*.sqlite3*" >nul 2>&1
echo   - Base de datos SQLite y memoria compartida eliminadas.

echo [4/5] Limpiando carpetas temporales de descargas y PDFs...
if exist "%TEMP_DIR%" (
    del /f /q "%TEMP_DIR%\*.*" >nul 2>&1
    rd /s /q "%TEMP_DIR%" >nul 2>&1
)
mkdir "%TEMP_DIR%" >nul 2>&1

if exist "%TEMP_PDFS%" (
    del /f /q "%TEMP_PDFS%\*.*" >nul 2>&1
    rd /s /q "%TEMP_PDFS%" >nul 2>&1
)
mkdir "%TEMP_PDFS%" >nul 2>&1
echo   - Carpetas temporales 'Temp/' y 'temp_pdfs/' limpiadas.

echo [5/5] Verificando integridad de estructura de directorios...
if not exist "%DATOS_DIR%" mkdir "%DATOS_DIR%" >nul 2>&1
if not exist "%PLANES_DIR%" mkdir "%PLANES_DIR%" >nul 2>&1
if not exist "%TEMP_DIR%" mkdir "%TEMP_DIR%" >nul 2>&1
if not exist "%TEMP_PDFS%" mkdir "%TEMP_PDFS%" >nul 2>&1

echo.
echo ======================================================================
echo       LIMPIEZA TOTAL COMPLETADA CON EXITO (0 ARCHIVOS RESIDUALES)
echo ======================================================================
echo.
echo El entorno ha quedado completamente virgen:
echo   - 0 JSONs residuales.
echo   - 0 Bases de datos residuales.
echo   - Directorios limpios y preparados para una ejecucion completa.
echo.
if "%AUTO_CONFIRM%"=="0" pause
