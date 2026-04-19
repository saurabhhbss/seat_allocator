#!/usr/bin/env bash
# One-click launcher for the REAP-2026 Seat Allocator
set -e
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment …"
    python3 -m venv .venv
fi

source .venv/bin/activate

if ! python -c "import streamlit" 2>/dev/null; then
    echo "Installing dependencies …"
    pip install -e .
fi

echo "Starting REAP Seat Allocator …"
python -m streamlit run ui/app.py --server.headless=false
