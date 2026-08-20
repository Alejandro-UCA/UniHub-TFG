@echo off
setlocal enabledelayedexpansion

title UniHub - Ejecutar Fase 1 Parte 1 (RUCT + BOE Central)

echo ======================================================================
echo          UNIHUB - EJECUCION DE LA FASE 1 PARTE 1
echo       (Scraping Oficial RUCT y Parsing Sintactico de BOE)
echo ======================================================================
echo.

REM Navegar a la carpeta del Crawler
cd /d "%~dp0Codigo\Crawler"

REM Verificar Python disponible
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR CRITICO] Python no esta instalado o no se encuentra en el PATH.
    echo Por favor, instala Python 3.10+ y asegurate de que este configurado.
    echo.
    pause
    exit /b 1
)

echo [INFO] Iniciando ejecucion de la Parte 1...
if "%~1"=="" (
    echo [INFO] Parametros: Modo estandar (Todas las universidades y titulaciones)
    python main.py --only-part 1
) else (
    echo [INFO] Parametros adicionales detectados: %*
    python main.py --only-part 1 %*
)

echo.
echo ======================================================================
echo       FASE 1 PARTE 1 FINALIZADA
echo ======================================================================
echo.
pause
