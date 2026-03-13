@echo off
setlocal EnableExtensions

cd /d "%~dp0"

echo [1/4] Verification de Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo Python est introuvable dans le PATH.
    echo Installe Python 3.11+ puis relance ce script.
    exit /b 1
)

echo [2/4] Installation des dependances...
python -m pip install --upgrade pip
if errorlevel 1 exit /b 1
python -m pip install -r requirements.txt
if errorlevel 1 exit /b 1

echo [3/4] Nettoyage des anciens builds...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [4/4] Build PyInstaller (spec avec assets embarques)...
python -m PyInstaller --noconfirm --clean ninja-chess.spec
if errorlevel 1 (
    echo Echec de compilation PyInstaller.
    exit /b 1
)

echo.
echo Build termine avec succes.
echo Executable: dist\NinjaChess.exe
echo.
echo Astuce: si un antivirus bloque le lancement, ajoute une exception sur le dossier dist.

endlocal
