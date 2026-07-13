@echo off
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
    echo Python nao encontrado. Instale em https://www.python.org/downloads/
    echo Marque "Add python.exe to PATH" durante a instalacao.
    pause
    exit /b 1
)

if not exist .venv (
    python -m venv .venv
)

call .venv\Scripts\activate.bat
pip install -r requirements.txt
python main.py
