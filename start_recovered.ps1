$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$settingsPath = Join-Path $PSScriptRoot 'data\recovery-settings.json'
if (!(Test-Path -LiteralPath $settingsPath)) { throw '먼저 recovery.ps1로 복원하세요.' }
$recoveredSettings = Get-Content -LiteralPath $settingsPath -Raw | ConvertFrom-Json
$env:DATABASE_URL = $recoveredSettings.DATABASE_URL
$env:APP_DEMO = '0'
& "$PSScriptRoot\.venv\Scripts\python.exe" -m streamlit run app.py --server.address=127.0.0.1
