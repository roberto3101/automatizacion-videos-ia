@echo off
setlocal EnableDelayedExpansion EnableExtensions
chcp 65001 >nul
title Video Factory

set "BASE_DIR=%~dp0"
set "BIN_DIR=%BASE_DIR%bin"
set "TEMP_DIR=%TEMP%\video_factory_install"
if not exist "%TEMP_DIR%" mkdir "%TEMP_DIR%" >nul 2>&1

cls
echo.
echo ============================================================
echo  VIDEO FACTORY
echo ============================================================
echo.
echo  Si es tu primera vez: este script instala TODO automatico
echo  (Python, FFmpeg, dependencias). Puede tardar 10-30 minutos.
echo.
echo  Si ya esta todo instalado: arranca la app en 5 segundos.
echo ============================================================
echo.

REM ──────────────────────────────────────────────────────────────
REM  1. PYTHON (instalar si falta + relanzar este .bat)
REM ──────────────────────────────────────────────────────────────
where python >nul 2>&1
if !errorlevel! NEQ 0 (
    echo [INSTALAR] Python no encontrado. Descargando Python 3.11.9...
    set "PY_URL=https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
    set "PY_INSTALLER=%TEMP_DIR%\python-installer.exe"

    powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; try { Invoke-WebRequest -Uri '%PY_URL%' -OutFile '%PY_INSTALLER%' -UseBasicParsing } catch { exit 1 }"

    if not exist "%PY_INSTALLER%" (
        echo.
        echo [ERROR] No se pudo descargar Python.
        echo Verifica tu conexion a internet o bajalo manual de python.org
        echo IMPORTANTE: marca "Add Python to PATH" al instalarlo.
        pause
        exit /b 1
    )

    echo [INSTALAR] Instalando Python ^(silencioso, modo usuario, sin admin^)...
    "%PY_INSTALLER%" /quiet PrependPath=1 Include_pip=1 Include_launcher=1 InstallAllUsers=0

    REM Esperar a que el instalador termine (a veces toma 30-60s)
    timeout /t 5 /nobreak >nul

    echo [INSTALAR] Python listo. Relanzando script para refrescar PATH...
    start "" cmd /c ""%~f0""
    exit /b 0
)

REM ──────────────────────────────────────────────────────────────
REM  2. FFmpeg (portable a bin\ffmpeg si falta)
REM ──────────────────────────────────────────────────────────────
where ffmpeg >nul 2>&1
if !errorlevel! EQU 0 goto ffmpeg_ok

if exist "%BIN_DIR%\ffmpeg\bin\ffmpeg.exe" (
    set "PATH=%BIN_DIR%\ffmpeg\bin;!PATH!"
    goto ffmpeg_ok
)

echo [INSTALAR] FFmpeg no encontrado. Descargando portable ^(~140 MB^)...
set "FF_URL=https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
set "FF_ZIP=%TEMP_DIR%\ffmpeg.zip"

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; try { Invoke-WebRequest -Uri '%FF_URL%' -OutFile '%FF_ZIP%' -UseBasicParsing } catch { exit 1 }"

if not exist "%FF_ZIP%" (
    echo [ERROR] No se pudo descargar FFmpeg. Verifica tu internet.
    pause
    exit /b 1
)

if not exist "%BIN_DIR%" mkdir "%BIN_DIR%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -Path '%FF_ZIP%' -DestinationPath '%BIN_DIR%\_tmp' -Force"

for /d %%D in ("%BIN_DIR%\_tmp\ffmpeg-*") do (
    if exist "%%D\bin" xcopy /E /I /Y "%%D" "%BIN_DIR%\ffmpeg" >nul
)
rmdir /S /Q "%BIN_DIR%\_tmp" 2>nul
del "%FF_ZIP%" 2>nul

if not exist "%BIN_DIR%\ffmpeg\bin\ffmpeg.exe" (
    echo [ERROR] No se pudo extraer FFmpeg.
    pause
    exit /b 1
)
set "PATH=%BIN_DIR%\ffmpeg\bin;!PATH!"
echo [OK] FFmpeg portable instalado en bin\ffmpeg\

:ffmpeg_ok

REM ──────────────────────────────────────────────────────────────
REM  3. Entorno virtual
REM ──────────────────────────────────────────────────────────────
if not exist ".venv\Scripts\python.exe" (
    echo [INSTALAR] Creando entorno virtual...
    python -m venv .venv
    if !errorlevel! NEQ 0 (
        echo [ERROR] No se pudo crear el venv.
        pause
        exit /b 1
    )
)
call .venv\Scripts\activate.bat
if !errorlevel! NEQ 0 (
    echo [ERROR] No se pudo activar el entorno virtual.
    pause
    exit /b 1
)

REM ──────────────────────────────────────────────────────────────
REM  4. Dependencias base (verifica/instala rapido)
REM ──────────────────────────────────────────────────────────────
if not exist ".venv\.base_installed" (
    echo [INSTALAR] Instalando dependencias base ^(FastAPI, Edge-TTS, httpx^)...
    python -m pip install --upgrade pip --quiet
    python -m pip install -q -r requirements.txt
    if !errorlevel! NEQ 0 (
        echo [ERROR] Fallo instalacion de deps base.
        pause
        exit /b 1
    )
    echo. > ".venv\.base_installed"
)

REM ──────────────────────────────────────────────────────────────
REM  5. Dependencias avanzadas (Kokoro, Whisper, etc. — primera vez)
REM ──────────────────────────────────────────────────────────────
if not exist ".venv\.full_installed" (
    echo [INSTALAR] Instalando features avanzadas ^(Kokoro, Whisper, etc^)
    echo            ^(~2 GB, solo primera vez, tarda 10-20 min^)...
    python -m pip install -q -r requirements-full.txt
    if !errorlevel! EQU 0 (
        echo [INSTALAR] Pre-cargando modelo Whisper...
        python -c "import whisper; whisper.load_model('base')" 2>nul
        echo. > ".venv\.full_installed"
        echo [OK] Features avanzadas instaladas.
    ) else (
        echo [!] Algunas features avanzadas fallaron, el sistema funciona igual.
        echo     Puedes reintentar despues borrando .venv\.full_installed.
    )
)

REM ──────────────────────────────────────────────────────────────
REM  6. Settings + carpetas
REM ──────────────────────────────────────────────────────────────
set "FIRST_RUN=0"
if not exist "config\settings.json" (
    copy "config\settings.example.json" "config\settings.json" >nul
    set "FIRST_RUN=1"
    echo [OK] config\settings.json creado.
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

REM ──────────────────────────────────────────────────────────────
REM  7. Liberar puerto 8000 (matar zombies)
REM ──────────────────────────────────────────────────────────────
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)

REM ──────────────────────────────────────────────────────────────
REM  8. Abrir notepad con settings (solo primera vez) + browser + server
REM ──────────────────────────────────────────────────────────────
if "!FIRST_RUN!"=="1" (
    echo.
    echo ============================================================
    echo  PRIMERA EJECUCION
    echo ============================================================
    echo  Abriendo config\settings.json en Notepad para que metas
    echo  tus API keys. La principal:
    echo.
    echo    fal_api_key   ^(para generar video^)  https://fal.ai
    echo.
    echo  Guarda el archivo y vuelve a esta ventana — el servidor
    echo  esta corriendo y leera los cambios.
    echo ============================================================
    echo.
    start notepad config\settings.json
)

start "" cmd /c "timeout /t 5 /nobreak >nul && start http://localhost:8000"

echo.
echo ============================================================
echo  VIDEO FACTORY CORRIENDO
echo  http://localhost:8000
echo  ^(El navegador se abre solo en 5 segundos^)
echo  Cierra esta ventana para detener el servidor.
echo ============================================================
echo.

python server.py

echo.
echo [Servidor detenido]
pause
