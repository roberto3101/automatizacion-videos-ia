@echo off
chcp 65001 >nul
title Video Factory

REM ── Verificar que setup.bat se corrio ───────────────────────
if not exist ".venv\Scripts\python.exe" (
    echo.
    echo [ERROR] El entorno virtual no existe.
    echo Corre setup.bat primero.
    echo.
    pause
    exit /b 1
)

if not exist "config\settings.json" (
    echo.
    echo [ERROR] config\settings.json no existe.
    echo Corre setup.bat primero.
    echo.
    pause
    exit /b 1
)

REM ── Activar venv ────────────────────────────────────────────
call .venv\Scripts\activate.bat
if errorlevel 1 (
    echo [ERROR] No se pudo activar el entorno virtual.
    pause
    exit /b 1
)

REM ── Matar procesos previos en puerto 8000 ──────────────────
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do (
    echo Matando proceso previo en puerto 8000 ^(PID %%a^)...
    taskkill /F /PID %%a >nul 2>&1
)

REM ── Abrir navegador después de 3s ──────────────────────────
start "" cmd /c "timeout /t 3 /nobreak >nul && start http://localhost:8000"

REM ── Levantar servidor ───────────────────────────────────────
echo.
echo ============================================================
echo  Video Factory corriendo en http://localhost:8000
echo  Cierra esta ventana para detener el servidor.
echo ============================================================
echo.

python server.py

REM Si el servidor cae, pausa para que el usuario vea el error
echo.
echo [Servidor detenido]
pause
