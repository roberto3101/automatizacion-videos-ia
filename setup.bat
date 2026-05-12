@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
title Video Factory - Setup inicial

echo.
echo ============================================================
echo  Video Factory - Setup inicial
echo ============================================================
echo.

REM ── 1. Verificar Python ─────────────────────────────────────
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python no esta instalado o no esta en el PATH.
    echo.
    echo Descargalo en: https://www.python.org/downloads/
    echo IMPORTANTE: marca "Add Python to PATH" durante la instalacion.
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python --version 2^>^&1') do set PYVER=%%i
echo [OK] %PYVER%

REM Verificar version Python >= 3.10
for /f "tokens=2 delims= " %%a in ('python --version 2^>^&1') do set PYTHON_VERSION=%%a
for /f "tokens=1,2 delims=." %%a in ("%PYTHON_VERSION%") do (
    set PY_MAJOR=%%a
    set PY_MINOR=%%b
)
if %PY_MAJOR% LSS 3 (
    echo [ERROR] Python 3.10 o superior requerido. Tienes Python %PYTHON_VERSION%.
    pause
    exit /b 1
)
if %PY_MAJOR% EQU 3 if %PY_MINOR% LSS 10 (
    echo [ERROR] Python 3.10 o superior requerido. Tienes Python %PYTHON_VERSION%.
    pause
    exit /b 1
)

REM ── 2. Verificar FFmpeg ─────────────────────────────────────
where ffmpeg >nul 2>&1
if errorlevel 1 (
    echo.
    echo [ADVERTENCIA] FFmpeg no esta en el PATH del sistema.
    echo Sin FFmpeg no puedes ensamblar videos, generar audio, ni crear subtitulos.
    echo.
    echo Descargalo gratis en: https://www.gyan.dev/ffmpeg/builds/
    echo   1. Bajalo el "release essentials" ZIP
    echo   2. Extraelo en C:\ffmpeg
    echo   3. Agrega C:\ffmpeg\bin al PATH de Windows
    echo   4. Cierra y abre esta ventana, vuelve a correr setup.bat
    echo.
    set /p CONTINUE="Continuar de todos modos (sin FFmpeg el sistema no funciona)? (s/N): "
    if /i not "!CONTINUE!"=="s" exit /b 1
) else (
    for /f "tokens=*" %%i in ('ffmpeg -version 2^>^&1 ^| findstr /b "ffmpeg version"') do set FFVER=%%i
    echo [OK] !FFVER:~0,40!
)

echo.

REM ── 3. Crear entorno virtual ────────────────────────────────
if exist ".venv\Scripts\python.exe" (
    echo [OK] Entorno virtual ya existe en .venv\
) else (
    echo Creando entorno virtual en .venv\ ...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] No se pudo crear el entorno virtual.
        pause
        exit /b 1
    )
    echo [OK] Entorno virtual creado.
)

echo.

REM ── 4. Activar venv e instalar deps base ────────────────────
call .venv\Scripts\activate.bat
if errorlevel 1 (
    echo [ERROR] No se pudo activar el entorno virtual.
    pause
    exit /b 1
)

echo Actualizando pip...
python -m pip install --upgrade pip --quiet

echo Instalando dependencias base (FastAPI, Edge-TTS, httpx)...
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Fallo la instalacion de dependencias base.
    pause
    exit /b 1
)

echo [OK] Dependencias base instaladas.
echo.

REM ── 5. Copiar settings template si falta ────────────────────
if not exist "config\settings.json" (
    if exist "config\settings.example.json" (
        copy "config\settings.example.json" "config\settings.json" >nul
        echo [OK] config\settings.json creado desde el template.
    ) else (
        echo [ADVERTENCIA] No existe config\settings.example.json.
    )
) else (
    echo [OK] config\settings.json ya existe ^(no se sobreescribe^).
)

echo.

REM ── 6. Crear carpetas de output ────────────────────────────
for %%D in (audio clips final images music_cache previews scripts thumbnails uploads voice_previews voice_tests exports) do (
    if not exist "output\%%D" mkdir "output\%%D" >nul 2>&1
)
if not exist "data" mkdir "data" >nul 2>&1
if not exist "assets\music\horror" mkdir "assets\music\horror" >nul 2>&1
if not exist "assets\music\mystery" mkdir "assets\music\mystery" >nul 2>&1
if not exist "assets\music\calm" mkdir "assets\music\calm" >nul 2>&1
if not exist "assets\music\epic" mkdir "assets\music\epic" >nul 2>&1
if not exist "assets\voices" mkdir "assets\voices" >nul 2>&1

echo.
echo ============================================================
echo  SETUP COMPLETO
echo ============================================================
echo.
echo Proximos pasos:
echo.
echo  1. Edita config\settings.json y mete tus API keys:
echo     - fal_api_key   (necesaria para generar video)   https://fal.ai
echo     - pexels_api_key (opcional, stock gratis)        https://www.pexels.com/api
echo     - youtube_api_key (opcional, auto-upload)        https://console.cloud.google.com
echo.
echo  2. Para correr el sistema:    start.bat
echo.
echo  3. (Opcional) Para instalar features avanzadas (Kokoro, Whisper, XTTS):
echo                                install_full.bat
echo     ^(tarda 15-30 min, descarga ~3 GB^)
echo.
pause
