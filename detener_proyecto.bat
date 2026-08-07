@echo off
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
if %ERRORLEVEL% NEQ 0 (
    docker-compose down
)

echo.
echo ======================================================================
echo    !TODOS LOS CONTENEDORES DE UNIHUB SE HAN DETENIDO CORRECTAMENTE!
echo ======================================================================
echo.
pause
