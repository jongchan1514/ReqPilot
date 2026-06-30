# update.ps1 — 원격 PC에서 실행: git pull + 서버 재시작
# 이 파일은 레포지토리 루트의 scripts/ 폴더에 있어야 합니다

$repoRoot = Split-Path -Parent $PSScriptRoot

Write-Host "[1/4] 기존 서버 프로세스 종료..."
Get-Process -Name python -ErrorAction SilentlyContinue | Where-Object {
    try { $_.MainModule.FileName -like "*req-manager*" } catch { $false }
} | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1

Write-Host "[2/4] 최신 코드 받는 중..."
Set-Location $repoRoot
git pull origin main

Write-Host "[3/4] conda 환경 Python 경로 탐색..."
$candidates = @(
    "$env:USERPROFILE\anaconda3\envs\req-manager\python.exe",
    "$env:USERPROFILE\miniconda3\envs\req-manager\python.exe",
    "C:\anaconda3\envs\req-manager\python.exe",
    "C:\miniconda3\envs\req-manager\python.exe"
)
$pythonExe = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $pythonExe) {
    Write-Error "req-manager conda 환경을 찾을 수 없습니다. scripts\setup_remote.ps1 를 먼저 실행하세요."
    exit 1
}

Write-Host "[4/4] 서버 재시작: $pythonExe"
Start-Process -FilePath $pythonExe -ArgumentList "$repoRoot\app.py" -WindowStyle Hidden
Write-Host "완료! 서버가 http://127.0.0.1:5000 에서 실행 중입니다."
