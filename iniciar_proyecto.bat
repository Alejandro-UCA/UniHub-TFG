@echo off
:: ==============================================================================
:: Script de Lanzamiento del Proyecto UniHub / RUCT (Windows Batch)
:: Construye e inicia los 4 contenedores Docker (Fases 1, 2 y 3)
:: ==============================================================================
chcp 65001 > nul
title Lanzador UniHub Docker - Windows

echo ======================================================================
echo          INICIANDO PROYECTO UNIHUB (RUCT) EN ENTORNO DOCKER
echo ======================================================================
echo.

:: 1. Verificación de Docker en ejecución
docker info >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR CRÍTICO] Docker Desktop no está en ejecución.
    echo Por favor, arranca Docker Desktop en Windows y vuelve a ejecutar este script.
    echo.
    pause
    exit /b 1
)

:: 2. Navegar a la carpeta de configuración Docker
cd /d "%~dp0Codigo\Docker"

echo [1/3] Construyendo imágenes e iniciando contenedores en segundo plano...
docker compose up --build -d >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ADVERTENCIA] Falló 'docker compose', intentando con 'docker-compose'...
    docker-compose up --build -d
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR CRÍTICO] No se pudieron iniciar los contenedores Docker.
    echo Revisa los mensajes de error superiores.
    pause
    exit /b 1
)

echo [2/3] Verificando estado de los 4 contenedores...
echo.
docker compose ps

echo.
echo ======================================================================
echo       ¡PROYECTO UNIHUB DESPLEGADO Y EN EJECUCIÓN EXITOSA!
echo ======================================================================
echo.
echo  • Portal Web Frontend (Fase 3):          http://localhost:80
echo  • Portal Web (Puerto Alternativo):       http://localhost:5173
echo  • API REST & Swagger UI (Fase 2):        http://localhost:8000/docs
echo  • Documentación ReDoc:                   http://localhost:8000/redoc
echo  • Panel de Administración & Analizador:  http://localhost/admin
echo.
echo ======================================================================
echo Presiona cualquier tecla para salir de este script (los contenedores seguirán activos).
pause > nul
