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
$SSH     = "ssh -p $RemotePort"
$SCP     = "scp -P $RemotePort"

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
$totalBytes = (Get-Item "$ROOT\dist\reqpilot.tar.gz").Length
$scpJob = Start-Job -ScriptBlock {
    param($port, $src, $dst)
    & scp -P $port $src $dst
    $LASTEXITCODE
} -ArgumentList $RemotePort, "$ROOT\dist\reqpilot.tar.gz", "${REMOTE}:/tmp/reqpilot.tar.gz"

while ($scpJob.State -eq 'Running') {
    Start-Sleep -Seconds 3
    try {
        $remoteSize = & ssh -p $RemotePort $REMOTE "stat -c%s /tmp/reqpilot.tar.gz 2>/dev/null || echo 0"
        $remoteSize = [long]$remoteSize
        $pct = [math]::Round($remoteSize / $totalBytes * 100, 1)
        $remoteMB = [math]::Round($remoteSize / 1MB, 1)
        Write-Host "      $remoteMB MB / $sizeMB MB ($pct%)" -NoNewline
        Write-Host "`r" -NoNewline
    } catch {}
}
$scpExit = Receive-Job $scpJob
Remove-Job $scpJob
Write-Host ""
if ($scpExit -ne 0) { Write-Error "전송 실패"; exit 1 }

# ── 4. 원격 재시작 ───────────────────────────────────────────────────────────
Write-Host "[4/4] 원격 서버 업데이트 및 재시작..."
$remoteScript = @"
set -e
echo '-- 압축 해제...'
tar -xzf /tmp/reqpilot.tar.gz -C /tmp

echo '-- 기존 프로세스 종료...'
pkill -f $RemoteDir/reqpilot || true
sleep 2

echo '-- 바이너리 교체...'
cp -r /tmp/reqpilot/* $RemoteDir/
chmod +x $RemoteDir/reqpilot

echo '-- 재시작 (nohup)...'
cd $RemoteDir
nohup ./reqpilot > $RemoteDir/nohup.out 2>&1 &
echo \$! > $RemoteDir/reqpilot.pid
sleep 2
if kill -0 \$(cat $RemoteDir/reqpilot.pid) 2>/dev/null; then
    echo "서버 기동 확인 (PID: \$(cat $RemoteDir/reqpilot.pid))"
else
    echo '경고: 프로세스 즉시 종료 — nohup.out 확인 필요'
    tail -20 $RemoteDir/nohup.out
fi
rm -f /tmp/reqpilot.tar.gz /tmp/reqpilot
"@

& ssh -p $RemotePort $REMOTE $remoteScript
if ($LASTEXITCODE -ne 0) { Write-Error "원격 재시작 실패"; exit 1 }

Write-Host ""
Write-Host "배포 완료! http://${RemoteIP}:5000"
