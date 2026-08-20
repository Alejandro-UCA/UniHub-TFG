@echo off
REM ==============================================================================
REM Script para Ejecutar la Fase 1 - Parte 1 de UniHub
REM Scraping Oficial RUCT + Descarga y Parsing de PDFs del BOE Central
REM ==============================================================================
chcp 65001 >nul
title UniHub - Ejecutar Fase 1 Parte 1 (RUCT + BOE Central)

echo ======================================================================
echo          UNIHUB - EJECUCIÓN DE LA FASE 1 PARTE 1
echo       (Scraping Oficial RUCT y Parsing Sintáctico de BOE)
echo ======================================================================
echo.

REM Navegar a la carpeta del Crawler
cd /d "%~dp0Codigo\Crawler"

REM Verificar Python disponible
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR CRÍTICO] Python no está instalado o no se encuentra en el PATH.
    echo Por favor, instala Python 3.10+ y asegúrate de que esté configurado.
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
