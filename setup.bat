@echo off
setlocal EnableDelayedExpansion EnableExtensions
chcp 65001 >nul
title Video Factory - Instalador completo

set "BASE_DIR=%~dp0"
set "BIN_DIR=%BASE_DIR%bin"
set "TEMP_DIR=%TEMP%\video_factory_install"
if not exist "%TEMP_DIR%" mkdir "%TEMP_DIR%" >nul 2>&1

cls
echo.
echo ============================================================
echo  VIDEO FACTORY - INSTALADOR COMPLETO
echo ============================================================
echo  Este instalador hace TODO solo:
echo    1. Detecta Python (lo instala si falta)
echo    2. Detecta FFmpeg (lo descarga portable si falta)
echo    3. Crea entorno virtual
echo    4. Instala dependencias base
echo    5. (Opcional) Instala features avanzadas (Kokoro, Whisper)
echo    6. Configura archivos por defecto
echo.
echo  Tiempo estimado: 5-30 min (depende de tu internet)
echo  Descarga total: 50 MB a 3 GB (depende de que ya tengas)
echo ============================================================
echo.
pause

REM ──────────────────────────────────────────────────────────────
REM [1/6] PYTHON
REM ──────────────────────────────────────────────────────────────
echo.
echo [1/6] Verificando Python...
where python >nul 2>&1
if !errorlevel! EQU 0 (
    for /f "tokens=2 delims= " %%a in ('python --version 2^>^&1') do set "PYV=%%a"
    echo   [OK] Python !PYV! detectado.
    goto python_ok
)

echo   [!] Python NO encontrado en el sistema.
echo   Descargando Python 3.11.9 desde python.org ...
set "PY_URL=https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
set "PY_INSTALLER=%TEMP_DIR%\python-installer.exe"

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; try { Invoke-WebRequest -Uri '%PY_URL%' -OutFile '%PY_INSTALLER%' -UseBasicParsing } catch { Write-Host 'DOWNLOAD FAILED'; exit 1 }"

if not exist "%PY_INSTALLER%" (
    echo.
    echo   [ERROR] No se pudo descargar Python.
    echo   Bajalo manualmente de https://www.python.org/downloads/
    echo   IMPORTANTE: marca "Add Python to PATH" en el instalador.
    echo   Luego vuelve a correr setup.bat.
    pause
    exit /b 1
)

echo   Instalando Python ^(modo usuario, sin admin, silencioso^)...
"%PY_INSTALLER%" /quiet PrependPath=1 Include_pip=1 Include_launcher=1 InstallAllUsers=0
echo.
echo   ========================================================
echo   PYTHON INSTALADO. AHORA HAZ ESTO:
echo   ========================================================
echo   1. CIERRA esta ventana
echo   2. Vuelve a hacer DOBLE-CLICK en setup.bat
echo   3. El instalador continua desde donde quedo
echo.
echo   (Windows necesita re-leer el PATH despues de instalar Python)
echo   ========================================================
echo.
pause
exit /b 0

:python_ok

REM ──────────────────────────────────────────────────────────────
REM [2/6] FFmpeg
REM ──────────────────────────────────────────────────────────────
echo.
echo [2/6] Verificando FFmpeg...
where ffmpeg >nul 2>&1
if !errorlevel! EQU 0 (
    echo   [OK] FFmpeg detectado en el sistema.
    goto ffmpeg_ok
)

if exist "%BIN_DIR%\ffmpeg\bin\ffmpeg.exe" (
    echo   [OK] FFmpeg portable ya extraido en bin\ffmpeg\
    set "PATH=%BIN_DIR%\ffmpeg\bin;%PATH%"
    goto ffmpeg_ok
)

echo   [!] FFmpeg NO encontrado. Descargando portable ^(~140 MB^)...
set "FF_URL=https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
set "FF_ZIP=%TEMP_DIR%\ffmpeg.zip"

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; try { Invoke-WebRequest -Uri '%FF_URL%' -OutFile '%FF_ZIP%' -UseBasicParsing } catch { Write-Host 'DOWNLOAD FAILED'; exit 1 }"

if not exist "%FF_ZIP%" (
    echo.
    echo   [ERROR] No se pudo descargar FFmpeg.
    echo   Bajalo manualmente de https://www.gyan.dev/ffmpeg/builds/
    pause
    exit /b 1
)

echo   Extrayendo FFmpeg en bin\ffmpeg\ ...
if not exist "%BIN_DIR%" mkdir "%BIN_DIR%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -Path '%FF_ZIP%' -DestinationPath '%BIN_DIR%\_tmp' -Force"

REM Mover la carpeta extraida al nombre final
for /d %%D in ("%BIN_DIR%\_tmp\ffmpeg-*") do (
    if exist "%%D\bin" (
        xcopy /E /I /Y "%%D" "%BIN_DIR%\ffmpeg" >nul
    )
)
rmdir /S /Q "%BIN_DIR%\_tmp" 2>nul
del "%FF_ZIP%" 2>nul

if not exist "%BIN_DIR%\ffmpeg\bin\ffmpeg.exe" (
    echo   [ERROR] No se pudo extraer FFmpeg correctamente.
    pause
    exit /b 1
)
set "PATH=%BIN_DIR%\ffmpeg\bin;%PATH%"
echo   [OK] FFmpeg portable instalado en bin\ffmpeg\

:ffmpeg_ok

REM ──────────────────────────────────────────────────────────────
REM [3/6] Entorno virtual
REM ──────────────────────────────────────────────────────────────
echo.
echo [3/6] Creando entorno virtual...
if exist ".venv\Scripts\python.exe" (
    echo   [OK] .venv\ ya existe.
) else (
    python -m venv .venv
    if !errorlevel! NEQ 0 (
        echo   [ERROR] No se pudo crear el venv.
        pause
        exit /b 1
    )
    echo   [OK] .venv\ creado.
)
call .venv\Scripts\activate.bat
if !errorlevel! NEQ 0 (
    echo   [ERROR] No se pudo activar .venv\
    pause
    exit /b 1
)

REM ──────────────────────────────────────────────────────────────
REM [4/6] Dependencias base
REM ──────────────────────────────────────────────────────────────
echo.
echo [4/6] Instalando dependencias base ^(FastAPI, Edge-TTS, httpx^)...
python -m pip install --upgrade pip --quiet
pip install -r requirements.txt
if !errorlevel! NEQ 0 (
    echo   [ERROR] Fallo instalacion de deps base.
    pause
    exit /b 1
)
echo   [OK] Deps base instaladas.

REM ──────────────────────────────────────────────────────────────
REM [5/6] Features avanzadas (opcional)
REM ──────────────────────────────────────────────────────────────
echo.
echo [5/6] Features avanzadas ^(opcional^):
echo        - Kokoro AI         voz local de alta calidad, gratis
echo        - Whisper           subtitulos word-level perfectos
echo        - Fish Audio SDK    voz premium API
echo        - fal_client        cliente directo a fal.ai
echo        - YouTube API       auto-upload de videos
echo.
echo        Tamano: ~2 GB. Tiempo: 10-20 min.
echo.
set /p WANT_FULL="   Instalar AHORA tambien? (s/N): "
if /i "!WANT_FULL!"=="s" (
    echo.
    echo   Instalando desde requirements-full.txt ...
    pip install -r requirements-full.txt
    if !errorlevel! NEQ 0 (
        echo   [!] Algunos paquetes fallaron. Puedes reintentar con install_full.bat
    )

    echo.
    echo   Pre-cargando modelo Whisper base ^(~150 MB, solo primera vez^)...
    python -c "import whisper; whisper.load_model('base'); print('   [OK] Whisper listo.')" 2>nul

    echo   [OK] Features avanzadas instaladas.
) else (
    echo   Saltado. Puedes correr install_full.bat despues si los quieres.
)

REM ──────────────────────────────────────────────────────────────
REM [6/6] Config + carpetas
REM ──────────────────────────────────────────────────────────────
echo.
echo [6/6] Configurando archivos y carpetas...

if not exist "config\settings.json" (
    if exist "config\settings.example.json" (
        copy "config\settings.example.json" "config\settings.json" >nul
        echo   [OK] config\settings.json creado desde el template.
    ) else (
        echo   [!] No existe settings.example.json. Saltando.
    )
) else (
    echo   [OK] config\settings.json ya existia.
)

for %%D in (audio clips final images music_cache previews scripts thumbnails uploads voice_previews voice_tests exports) do (
    if not exist "output\%%D" mkdir "output\%%D" >nul 2>&1
)
if not exist "data" mkdir "data" >nul 2>&1
for %%M in (horror mystery calm epic) do (
    if not exist "assets\music\%%M" mkdir "assets\music\%%M" >nul 2>&1
)
if not exist "assets\voices" mkdir "assets\voices" >nul 2>&1
if not exist "assets\references\skeleton" mkdir "assets\references\skeleton" >nul 2>&1
echo   [OK] Carpetas listas.

REM ──────────────────────────────────────────────────────────────
echo.
echo ============================================================
echo  INSTALACION COMPLETA
echo ============================================================
echo.
echo  PROXIMOS PASOS:
echo  ---------------
echo  1. Edita  config\settings.json  con tus API keys
echo       fal_api_key      ^(necesario para video^)   https://fal.ai
echo       pexels_api_key   ^(opcional, stock gratis^) https://pexels.com/api
echo       youtube_api_key  ^(opcional, auto-upload^)  https://console.cloud.google.com
echo.
echo  2. Doble-click en  INICIAR.bat  para correr el sistema
echo.
echo ============================================================
echo.

set /p OPEN_NOW="Abrir config\settings.json en notepad ahora? (s/N): "
if /i "!OPEN_NOW!"=="s" (
    start notepad config\settings.json
)

echo.
pause
exit /b 0
