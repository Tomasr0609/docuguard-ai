# DocuGuard AI Lite — Windows launcher
# Usage: .\run.ps1

$ErrorActionPreference = "Stop"

# 1. Check .env
if (-not (Test-Path ".env")) {
    Write-Warning "No .env file found. Copying .env.example to .env"
    Copy-Item ".env.example" ".env"
    Write-Host ">>> Edit .env and set your ANTHROPIC_API_KEY before running" -ForegroundColor Yellow
}

# 2. Activate venv or create it
if (-not (Test-Path ".venv")) {
    Write-Host ">>> Creating virtual environment..." -ForegroundColor Cyan
    python -m venv .venv
}

$venvActivate = Join-Path $PWD ".venv\Scripts\Activate.ps1"
. $venvActivate

# 3. Install deps if needed
if (-not (Test-Path ".venv\Lib\site-packages\fastapi")) {
    Write-Host ">>> Installing dependencies..." -ForegroundColor Cyan
    pip install -r requirements.txt
}

# 4. Seed corpus if not already done
if (-not (Test-Path "chroma_db\chroma.sqlite3")) {
    Write-Host ">>> Seeding corpus normativo into ChromaDB..." -ForegroundColor Cyan
    python scripts/seed_corpus.py
}

# 5. Launch backend + frontend
Write-Host ">>> Starting FastAPI backend..." -ForegroundColor Cyan
$job = Start-Job -ScriptBlock {
    Set-Location -LiteralPath $using:PWD
    . .venv\Scripts\Activate.ps1
    uvicorn backend.api.main:app --host 127.0.0.1 --port 8000 --reload
}
Start-Sleep -Seconds 3

Write-Host ">>> Starting Streamlit frontend..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PWD'; . .venv\Scripts\Activate.ps1; streamlit run app.py"

Write-Host ">>> DocuGuard AI Lite is running!" -ForegroundColor Green
Write-Host "    Frontend: http://localhost:8501" -ForegroundColor Green
Write-Host "    API:      http://localhost:8000" -ForegroundColor Green
Write-Host "    Docs:     http://localhost:8000/docs" -ForegroundColor Green
Write-Host ""
Write-Host "Press Ctrl+C to stop the backend when done."

# Wait for backend job
Receive-Job -Job $job -Wait
