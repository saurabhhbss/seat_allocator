@echo off
cd /d "%~dp0"

if not exist ".venv" (
    echo Creating virtual environment ...
    python -m venv .venv
)

call .venv\Scripts\activate

python -c "import streamlit" 2>nul
if errorlevel 1 (
    echo Installing dependencies ...
    pip install -e .
)

echo Starting REAP Seat Allocator ...
python -m streamlit run ui\app.py --server.headless=false
