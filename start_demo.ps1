$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& "$PSScriptRoot\.venv\Scripts\python.exe" seed_demo.py
if ($LASTEXITCODE -ne 0) { throw '데모 데이터 준비에 실패했습니다.' }
$previousDatabase = $env:DATABASE_URL
$previousDemo = $env:APP_DEMO
try {
    $env:DATABASE_URL = 'sqlite:///data/demo.db'
    $env:APP_DEMO = '1'
    & "$PSScriptRoot\.venv\Scripts\python.exe" -m streamlit run app.py --server.address=127.0.0.1 --server.port=8502
} finally {
    $env:DATABASE_URL = $previousDatabase
    $env:APP_DEMO = $previousDemo
}
