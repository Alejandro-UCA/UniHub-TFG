@echo off
setlocal EnableExtensions EnableDelayedExpansion
REM ==============================================================================
REM Script de Detencion del Proyecto UniHub (Windows Batch)
REM Detiene y apaga los 4 contenedores Docker
REM ==============================================================================
chcp 65001 >nul
title Detener UniHub Docker - Windows

echo ======================================================================
echo             DETENIENDO CONTENEDORES DOCKER DE UNIHUB
echo ======================================================================
echo.

cd /d "%~dp0Codigo\Docker"

docker compose down
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
    docker-compose down
    set "EXIT_CODE=!ERRORLEVEL!"
)

if not "%EXIT_CODE%"=="0" (
    echo [ERROR] No se pudieron detener los contenedores. Codigo: %EXIT_CODE%.
    pause
    exit /b %EXIT_CODE%
)

echo.
echo ======================================================================
echo    TODOS LOS CONTENEDORES DE UNIHUB SE HAN DETENIDO CORRECTAMENTE
echo ======================================================================
echo.
pause
exit /b 0
