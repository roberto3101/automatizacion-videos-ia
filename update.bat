@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
title Video Factory - Actualizar

echo.
echo ============================================================
echo  ACTUALIZAR VIDEO FACTORY
echo ============================================================
echo.

REM ── Verificar git ───────────────────────────────────────────
where git >nul 2>&1
if !errorlevel! NEQ 0 (
    echo [ERROR] Git no esta instalado.
    echo Descargalo en: https://git-scm.com/download/win
    pause
    exit /b 1
)

REM ── Verificar que estamos en un repo ────────────────────────
if not exist ".git" (
    echo [ERROR] Esta carpeta no es un repo git.
    echo Clonalo primero con:
    echo   git clone https://github.com/roberto3101/automatizacion-videos-ia.git
    pause
    exit /b 1
)

REM ── Guardar hash anterior de requirements.txt ───────────────
set "REQ_HASH_BEFORE="
if exist requirements.txt (
    for /f %%H in ('certutil -hashfile requirements.txt MD5 ^| findstr /v "hash CertUtil"') do (
        if "!REQ_HASH_BEFORE!"=="" set "REQ_HASH_BEFORE=%%H"
    )
)

REM ── Pull ────────────────────────────────────────────────────
echo [1/3] Jalando ultimos cambios desde GitHub...
git pull --ff-only 2>&1
if !errorlevel! NEQ 0 (
    echo.
    echo [ERROR] git pull fallo. Probablemente tienes cambios locales sin commit.
    echo Para descartar tus cambios y forzar update:
    echo   git stash    ^(guarda tus cambios^)
    echo   git pull
    echo   git stash pop ^(opcional, restaura tus cambios^)
    pause
    exit /b 1
)
echo   [OK]

REM ── Detectar si requirements.txt cambio ─────────────────────
set "REQ_HASH_AFTER="
if exist requirements.txt (
    for /f %%H in ('certutil -hashfile requirements.txt MD5 ^| findstr /v "hash CertUtil"') do (
        if "!REQ_HASH_AFTER!"=="" set "REQ_HASH_AFTER=%%H"
    )
)

echo.
echo [2/3] Verificando dependencias...
if "!REQ_HASH_BEFORE!"=="!REQ_HASH_AFTER!" (
    echo   [OK] requirements.txt sin cambios.
) else (
    echo   requirements.txt CAMBIO. Reinstalando deps...
    if exist ".venv\Scripts\activate.bat" (
        call .venv\Scripts\activate.bat
        pip install -r requirements.txt
        echo   [OK] Deps actualizadas.
    ) else (
        echo   [!] .venv\ no existe. Corre setup.bat para instalar.
    )
)

REM ── Mostrar cambios ─────────────────────────────────────────
echo.
echo [3/3] Cambios desde la version anterior:
git log --oneline -5 2>nul

echo.
echo ============================================================
echo  ACTUALIZACION COMPLETA
echo ============================================================
echo.
echo Para correr la nueva version: doble-click en  start.bat
echo.
pause
