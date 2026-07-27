#!/usr/bin/env bash
# DocuGuard AI Lite — Unix launcher (macOS / Linux)
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

# 1. Check .env
if [ ! -f .env ]; then
    echo ">>> No .env file found. Copying .env.example to .env"
    cp .env.example .env
    echo ">>> Edit .env and set your ANTHROPIC_API_KEY before running"
fi

# 2. Activate venv or create it
if [ ! -d .venv ]; then
    echo ">>> Creating virtual environment..."
    python3 -m venv .venv
fi
source .venv/bin/activate

# 3. Install deps if needed
if [ ! -f .venv/bin/fastapi ]; then
    echo ">>> Installing dependencies..."
    pip install -r requirements.txt
fi

# 4. Seed corpus if not already done
if [ ! -f chroma_db/chroma.sqlite3 ]; then
    echo ">>> Seeding corpus normativo into ChromaDB..."
    python scripts/seed_corpus.py
fi

# 5. Launch backend + frontend
echo ">>> Starting FastAPI backend..."
uvicorn backend.api.main:app --host 127.0.0.1 --port 8000 --reload &
BACKEND_PID=$!
sleep 3

echo ">>> Starting Streamlit frontend..."
streamlit run app.py &
FRONTEND_PID=$!

echo ">>> DocuGuard AI Lite is running!"
echo "    Frontend: http://localhost:8501"
echo "    API:      http://localhost:8000"
echo "    Docs:     http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop."

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" INT TERM
wait
