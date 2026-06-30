# docker_build.ps1 — Rocky Linux 8 Docker로 PyInstaller 빌드
# 사용법: .\scripts\docker_build.ps1
# 결과물: dist\reqpilot\ (Linux 실행 파일 + 의존 라이브러리)

param(
    [string]$OutputDir = "dist",
    [switch]$NoBuildCache    # 이미지 캐시 무시하고 처음부터 빌드
)

$ROOT  = Split-Path -Parent $PSScriptRoot
$IMAGE = "reqpilot-builder:latest"

# ── 1. Docker 설치 확인 ──────────────────────────────────────────────────────
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "Docker가 설치되지 않았거나 PATH에 없습니다."
    exit 1
}

# ── 2. Docker 이미지 빌드 ────────────────────────────────────────────────────
Write-Host "[1/3] Docker 이미지 빌드 중... (첫 빌드는 10-30분 소요)"
$buildArgs = @("build", "-f", "$ROOT\Dockerfile.build", "-t", $IMAGE)
if ($NoBuildCache) { $buildArgs += "--no-cache" }
$buildArgs += $ROOT

& docker @buildArgs
if ($LASTEXITCODE -ne 0) { Write-Error "Docker 이미지 빌드 실패"; exit 1 }

# ── 3. PyInstaller 실행 & 결과 추출 ─────────────────────────────────────────
Write-Host "[2/3] PyInstaller 빌드 중..."
$outPath = Join-Path $ROOT $OutputDir
New-Item -ItemType Directory -Force -Path $outPath | Out-Null

# WSL/Docker 경로 변환
$dockerOut = $outPath -replace '\\','/' -replace '^([A-Za-z]):','/$1'

docker run --rm -v "${outPath}:/output" $IMAGE
if ($LASTEXITCODE -ne 0) { Write-Error "PyInstaller 빌드 실패"; exit 1 }

# ── 4. 완료 ──────────────────────────────────────────────────────────────────
$finalPath = Join-Path $outPath "reqpilot"
Write-Host "[3/3] 빌드 완료!"
Write-Host ""
Write-Host "  결과물 경로: $finalPath"
Write-Host "  실행 방법 (Linux 서버에서):"
Write-Host "    scp -r $finalPath user@server:/opt/reqpilot"
Write-Host "    ssh user@server '/opt/reqpilot/reqpilot'"
Write-Host ""
Write-Host "  .env 파일은 reqpilot 실행 파일과 같은 폴더에 두세요."
