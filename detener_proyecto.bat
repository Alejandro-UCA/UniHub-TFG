@echo off
:: ==============================================================================
:: Script de Detención del Proyecto UniHub / RUCT (Windows Batch)
:: Detiene y apaga los 4 contenedores Docker
:: ==============================================================================
chcp 65001 > nul
title Detener UniHub Docker - Windows

echo ======================================================================
echo             DETENIENDO CONTENEDORES DOCKER DE UNIHUB
echo ======================================================================
echo.

cd /d "%~dp0Codigo\Docker"

docker compose down >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    docker-compose down
)

echo.
echo ======================================================================
echo    ¡TODOS LOS CONTENEDORES DE UNIHUB SE HAN DETENIDO CORRECTAMENTE!
echo ======================================================================
echo.
pause
