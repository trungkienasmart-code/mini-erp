# Tự động kích hoạt venv + chạy uvicorn
$ErrorActionPreference = "Stop"

if (-not (Test-Path "venv\Scripts\Activate.ps1")) {
    Write-Host "❌ Không tìm thấy venv. Chạy: python -m venv venv" -ForegroundColor Red
    exit 1
}

Write-Host "🔧 Đang kích hoạt venv..." -ForegroundColor Cyan
& .\venv\Scripts\Activate.ps1

# Verify
$pyVersion = python --version
Write-Host "✅ $pyVersion" -ForegroundColor Green

# Check sqlmodel
python -c "import sqlmodel" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Thiếu package. Chạy: pip install -r requirements.txt" -ForegroundColor Red
    exit 1
}

Write-Host "🚀 Khởi động Mini ERP..." -ForegroundColor Cyan
Write-Host ""

uvicorn app.main:app --reload