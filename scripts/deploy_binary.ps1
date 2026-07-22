# deploy_binary.ps1 — 빌드 후 운영 서버에 바이너리 자동 배포
# 사용법:
#   .\scripts\deploy_binary.ps1              # 빌드 없이 배포만
#   .\scripts\deploy_binary.ps1 -Build       # 빌드 후 배포

param(
    [switch]$Build,
    [string]$RemoteUser = "ione",
    [string]$RemoteIP   = "192.168.7.91",
    [string]$RemotePort = "20022",
    [string]$RemoteDir  = "/home/ione/reqpilot"
)

$ROOT    = Split-Path -Parent $PSScriptRoot
$DIST    = "$ROOT\dist\reqpilot"
$REMOTE  = "${RemoteUser}@${RemoteIP}"

# ── 1. 빌드 (옵션) ──────────────────────────────────────────────────────────
if ($Build) {
    Write-Host "[1/4] Docker 빌드 시작..."
    docker build -f "$ROOT\Dockerfile.build" -t reqpilot-builder:latest "$ROOT"
    if ($LASTEXITCODE -ne 0) { Write-Error "빌드 실패"; exit 1 }

    Remove-Item "$ROOT\dist\reqpilot" -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path "$ROOT\dist" | Out-Null
    docker run --rm -v "$ROOT\dist:/output" reqpilot-builder:latest
    if ($LASTEXITCODE -ne 0) { Write-Error "바이너리 추출 실패"; exit 1 }
    Write-Host "      빌드 완료."
} else {
    Write-Host "[1/4] 빌드 건너뜀 (기존 dist\reqpilot 사용)"
}

if (-not (Test-Path "$DIST\reqpilot")) {
    Write-Error "바이너리가 없습니다: $DIST\reqpilot`n먼저 -Build 옵션으로 실행하세요."
    exit 1
}

# ── 2. 압축 ─────────────────────────────────────────────────────────────────
Write-Host "[2/4] 압축 중..."
docker run --rm -v "$ROOT\dist:/dist" rockylinux:8 `
    tar -czf /dist/reqpilot.tar.gz -C /dist reqpilot
if ($LASTEXITCODE -ne 0) { Write-Error "압축 실패"; exit 1 }
$sizeMB = [math]::Round((Get-Item "$ROOT\dist\reqpilot.tar.gz").Length / 1MB, 0)
Write-Host "      reqpilot.tar.gz ($sizeMB MB)"

# ── 3. 전송 ─────────────────────────────────────────────────────────────────
Write-Host "[3/4] 서버로 전송 중 (${REMOTE}:${RemotePort}) — ${sizeMB} MB..."
& scp -P $RemotePort "$ROOT\dist\reqpilot.tar.gz" "${REMOTE}:/tmp/reqpilot.tar.gz"
if ($LASTEXITCODE -ne 0) { Write-Error "전송 실패"; exit 1 }

# ── 4. 원격 재시작 ───────────────────────────────────────────────────────────
Write-Host "[4/4] 원격 서버 업데이트 및 재시작..."
$remoteScript = @'
set -e
echo '-- 압축 해제...'
tar -xzf /tmp/reqpilot.tar.gz -C /tmp

echo '-- 기존 프로세스 종료...'
kill $(cat PIDFILE 2>/dev/null) 2>/dev/null || pkill -x reqpilot 2>/dev/null || true
sleep 3

echo '-- 바이너리 교체...'
cp -r /tmp/reqpilot/* REMOTEDIR/
chmod +x REMOTEDIR/reqpilot

echo '-- 재시작 (nohup)...'
cd REMOTEDIR
nohup ./reqpilot > REMOTEDIR/nohup.out 2>&1 &
echo $! > REMOTEDIR/reqpilot.pid
sleep 3
PID=$(cat REMOTEDIR/reqpilot.pid)
if kill -0 $PID 2>/dev/null; then
    echo "Started OK (PID: $PID)"
else
    echo '경고: 프로세스 즉시 종료 — nohup.out:'
    tail -20 REMOTEDIR/nohup.out
fi
rm -f /tmp/reqpilot.tar.gz
rm -rf /tmp/reqpilot
'@ -replace 'REMOTEDIR', $RemoteDir -replace 'PIDFILE', "$RemoteDir/reqpilot.pid"

$remoteScript -replace "`r`n", "`n" | & ssh -p $RemotePort $REMOTE "bash -s"
if ($LASTEXITCODE -ne 0) { Write-Error "원격 재시작 실패"; exit 1 }

Write-Host ""
Write-Host "배포 완료! http://${RemoteIP}:5000"
