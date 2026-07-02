Write-Host "Starting Forecast Pipeline V2..."
Write-Host "================================"

# -----------------------------
# Backend
# -----------------------------
Write-Host "[1/2] Starting FastAPI backend..."

# Stop stale backends on port 8000 (avoids hung / duplicate API processes)
Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue |
  ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }

Push-Location backend

if (!(Test-Path ".venv")) {
    python -m venv .venv
}

& .\.venv\Scripts\Activate.ps1

pip install -r requirements.txt

Start-Process powershell -ArgumentList "-NoExit", "-Command", ".\.venv\Scripts\Activate.ps1; python run_backend.py"

Pop-Location

# -----------------------------
# Frontend
# -----------------------------
Write-Host "[2/2] Starting Next.js frontend..."

Push-Location frontend

npm install

Start-Process powershell -ArgumentList "-NoExit", "-Command", "npm run dev"

Pop-Location

Write-Host ""
Write-Host "================================"
Write-Host "Backend : http://localhost:8000"
Write-Host "Frontend: http://localhost:3000"