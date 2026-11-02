$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$deps = Join-Path $root ".deps"

$python = $env:CTW_PYTHON
if (-not $python) {
    foreach ($candidate in @("python3", "python", "py")) {
        if (-not (Get-Command $candidate -ErrorAction SilentlyContinue)) {
            continue
        }
        & $candidate -c "import sys" *> $null
        if ($LASTEXITCODE -eq 0) {
            $python = $candidate
            break
        }
    }
}

if (-not $python) {
    throw "Python 3.9+ not found. Install Python or set CTW_PYTHON."
}

Write-Host "Using interpreter: $(& $python --version)"
& $python -m pip install --target $deps `
    "faster-whisper>=1.0,<1.2" `
    "requests>=2.28,<3" `
    "av>=11,<19" `
    "fastapi>=0.110,<1" `
    "uvicorn>=0.29,<1" `
    "python-multipart>=0.0.9,<1"

Write-Host "Done. Run: .\ctw.cmd serve"
