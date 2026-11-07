$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw 'Python 3 is required. Install Python 3.10+ and ensure python is on PATH.'
}
if (-not $env:PORT) { $env:PORT = '8000' }
python -u server/app.py
