$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
Write-Host '앱을 먼저 중지하세요. 백업을 새 DB 파일로 복원하며 기존 DB는 덮어쓰지 않습니다.'
$backupSource = Read-Host '백업 .db 파일의 전체 경로'
$restoreDestination = Read-Host '새 복원 파일 경로 (예: data/restored-2026.db)'
$confirmation = Read-Host '복원할 파일과 영향을 확인했다면 복원 을 입력'
if ($confirmation -ne '복원') { Write-Host '변경 없이 취소했습니다.'; exit }
& "$PSScriptRoot\.venv\Scripts\python.exe" backup_db.py restore $backupSource $restoreDestination
if ($LASTEXITCODE -ne 0) { throw '복원하지 못했습니다. 경로와 기존 파일 유무를 확인하세요.' }
$resolvedRestore = (Resolve-Path -LiteralPath $restoreDestination).Path.Replace('\','/')
$env:DATABASE_URL = 'sqlite:///' + $resolvedRestore
@{DATABASE_URL=$env:DATABASE_URL} | ConvertTo-Json | Set-Content -LiteralPath "$PSScriptRoot\data\recovery-settings.json" -Encoding utf8
Write-Host '복원본으로 앱을 실행합니다. 로그인, 이력, 성과를 확인하세요. 이후에는 start_recovered.ps1로 같은 복원본을 실행하세요.'
& "$PSScriptRoot\.venv\Scripts\python.exe" -m streamlit run app.py
