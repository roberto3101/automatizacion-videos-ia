@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
title Video Factory - Instalacion completa (avanzada)

echo.
echo ============================================================
echo  INSTALACION COMPLETA (FEATURES AVANZADAS)
echo ============================================================
echo.
echo Esto agrega:
echo   - Kokoro AI       (voz local de alta calidad, gratis)
echo   - Whisper         (subtitulos palabra-por-palabra, perfecto sync)
echo   - Fish Audio SDK  (voz premium API)
echo   - fal_client      (cliente Python directo a fal.ai)
echo   - YouTube API     (auto-upload de videos)
echo   - soundfile/numpy (utilidades de audio)
echo.
echo Tamaño total aproximado: ~2 GB
echo Tiempo estimado:         10-20 minutos (depende de tu internet)
echo.
echo NOTA: XTTS v2 (voice cloning) requiere torch (3 GB extra) y NO se
echo       instala aqui. Si lo quieres, corre manualmente despues:
echo           pip install TTS torch torchaudio
echo.
set /p CONTINUE="Continuar con la instalacion? (s/N): "
if /i not "%CONTINUE%"=="s" (
    echo Cancelado.
    pause
    exit /b 0
)

REM ── Verificar venv ──────────────────────────────────────────
if not exist ".venv\Scripts\python.exe" (
    echo.
    echo [ERROR] El entorno virtual no existe. Corre setup.bat primero.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat
if errorlevel 1 (
    echo [ERROR] No se pudo activar el entorno virtual.
    pause
    exit /b 1
)

echo.
echo ─── [1/2] Instalando desde requirements-full.txt ──────────
pip install -r requirements-full.txt
if errorlevel 1 (
    echo [ERROR] Fallo instalacion de paquetes.
    pause
    exit /b 1
)

echo.
echo ─── [2/2] Pre-descargar modelo Whisper base ────────────────
echo Esto descarga el modelo Whisper "base" (~150 MB) para que el primer uso sea rapido.
python -c "import whisper; whisper.load_model('base'); print('Whisper base model OK')" 2>nul
if errorlevel 1 (
    echo [ADVERTENCIA] No se pudo precargar Whisper. Se descargara en el primer uso.
)

echo.
echo ============================================================
echo  INSTALACION COMPLETA TERMINADA
echo ============================================================
echo.
echo Ahora tienes acceso a:
echo   - Voz Kokoro local (kokoro:am_adam, kokoro:bm_george, etc.)
echo   - Subtitulos word-level con Whisper
echo   - Voz premium con Fish Audio (necesita fish_api_key)
echo   - Auto-upload a YouTube (necesita youtube_api_key + OAuth)
echo.
echo Corre start.bat para usar el sistema con todas las features.
echo.
pause
