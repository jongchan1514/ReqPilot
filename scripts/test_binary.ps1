# test_binary.ps1 — 빌드된 Linux 바이너리를 Rocky 8 컨테이너에서 실행 테스트
# 사용법: .\scripts\test_binary.ps1

param(
    [string]$Port    = "5000",
    [string]$DistDir = "dist\reqpilot"
)

$ROOT    = Split-Path -Parent $PSScriptRoot
$BINARY  = Join-Path $ROOT $DistDir

if (-not (Test-Path "$BINARY\reqpilot")) {
    Write-Error "바이너리를 찾을 수 없습니다: $BINARY\reqpilot"
    Write-Host "먼저 .\scripts\docker_build.ps1 을 실행하세요."
    exit 1
}

Write-Host "[1/3] Rocky Linux 8 컨테이너에서 reqpilot 실행..."
Write-Host "      포트: $Port"

# 컨테이너 이름 (중복 방지)
$CNAME = "reqpilot-test"
docker rm -f $CNAME 2>$null

# 실행 (백그라운드 데몬 모드)
docker run -d --name $CNAME `
    -p "${Port}:${Port}" `
    -v "${BINARY}:/app" `
    -e PORT=$Port `
    -e HOST=0.0.0.0 `
    -e SECRET_KEY=test-secret `
    -e GEMINI_API_KEY=dummy `
    rockylinux:8 `
    /app/reqpilot

Write-Host "[2/3] 서버 기동 대기 중 (5초)..."
Start-Sleep -Seconds 5

# 로그 확인
Write-Host "--- 컨테이너 로그 ---"
docker logs $CNAME

Write-Host ""
Write-Host "[3/3] HTTP 헬스체크..."
try {
    $res = Invoke-WebRequest -Uri "http://localhost:${Port}/" -TimeoutSec 10 -UseBasicParsing
    Write-Host "  상태 코드: $($res.StatusCode)"
    if ($res.StatusCode -eq 200) {
        Write-Host "  [OK] 정상 응답!"
    }
} catch {
    Write-Warning "  응답 없음: $($_.Exception.Message)"
}

Write-Host ""
Write-Host "컨테이너 정리..."
docker rm -f $CNAME | Out-Null
Write-Host "완료."
