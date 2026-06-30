# deploy.ps1 — 로컬 PC에서 실행: git push + 원격 PC 자동 업데이트
# 사용법: .\scripts\deploy.ps1
# 사전 조건: 원격 PC(192.168.7.217)에 SSH 서버(OpenSSH)가 설치되어 있어야 합니다

param(
    [string]$RemoteIP   = "192.168.7.217",
    [string]$RemoteUser = "moons",
    [string]$RemoteDir  = ""    # 비워두면 원격에서 git remote 경로 자동 탐색
)

# ── 1. git push ────────────────────────────────────────────────────────
Write-Host "[1/3] GitHub에 push 중..."
git push origin main
if ($LASTEXITCODE -ne 0) {
    Write-Error "git push 실패. 먼저 커밋/conflict를 해결하세요."
    exit 1
}
Write-Host "      push 완료."

# ── 2. 원격 PC 경로 확인 ───────────────────────────────────────────────
$remote = "${RemoteUser}@${RemoteIP}"

if (-not $RemoteDir) {
    Write-Host "[2/3] 원격 PC 레포 경로 탐색..."
    $RemoteDir = (ssh $remote 'powershell -NonInteractive -Command "
        $paths = @(\"C:\ReqPilot\",\"D:\ReqPilot\",\"C:\Users\moons\ReqPilot\",\"C:\Users\user\ReqPilot\");
        ($paths | Where-Object { Test-Path (Join-Path $_ \".git\") } | Select-Object -First 1)"') -replace "`n",""
    if (-not $RemoteDir) {
        Write-Error "원격 PC에서 ReqPilot 레포를 찾지 못했습니다. -RemoteDir 를 직접 지정하세요."
        exit 1
    }
    Write-Host "      원격 경로: $RemoteDir"
} else {
    Write-Host "[2/3] 원격 경로: $RemoteDir"
}

# ── 3. 원격 PC에서 update.ps1 실행 ────────────────────────────────────
Write-Host "[3/3] 원격 PC($RemoteIP) 업데이트 시작..."
$updateScript = Join-Path $RemoteDir "scripts\update.ps1"
ssh $remote "powershell -NonInteractive -ExecutionPolicy Bypass -File `"$updateScript`""
if ($LASTEXITCODE -eq 0) {
    Write-Host "`n배포 완료! 원격 서버가 업데이트되었습니다."
} else {
    Write-Warning "원격 업데이트 실패. 원격 PC에서 수동으로 scripts\update.ps1 을 실행하세요."
}
