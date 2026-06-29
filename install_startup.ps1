# install_startup.ps1
# 업무 관리 시스템을 Windows 시작 프로그램에 등록합니다.
# 관리자 권한 없이 현재 사용자 레지스트리(HKCU)에 등록합니다.

$AppName = "업무관리시스템"
$ExeDir  = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ExePath = Join-Path $ExeDir "dist\업무관리시스템.exe"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  업무 관리 시스템 - 자동시작 등록" -ForegroundColor Cyan
Write-Host "============================================"
Write-Host ""

# exe 존재 여부 확인
if (-not (Test-Path $ExePath)) {
    Write-Host "[오류] 실행 파일을 찾을 수 없습니다:" -ForegroundColor Red
    Write-Host "  $ExePath" -ForegroundColor Red
    Write-Host ""
    Write-Host "먼저 build.bat 을 실행하여 빌드를 완료하세요." -ForegroundColor Yellow
    Read-Host "엔터를 눌러 종료"
    exit 1
}

$RegPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$RegValue = "`"$ExePath`""

try {
    Set-ItemProperty -Path $RegPath -Name $AppName -Value $RegValue
    Write-Host "[완료] 자동시작 등록 성공!" -ForegroundColor Green
    Write-Host ""
    Write-Host "등록 정보:" -ForegroundColor White
    Write-Host "  이름: $AppName"
    Write-Host "  경로: $ExePath"
    Write-Host ""
    Write-Host "다음 PC 시작 시 자동으로 실행됩니다." -ForegroundColor Green
    Write-Host "브라우저에서 http://127.0.0.1:5000 으로 접속하세요."
    Write-Host ""
    Write-Host "제거하려면: uninstall_startup.ps1 실행"
} catch {
    Write-Host "[오류] 레지스트리 등록 실패: $_" -ForegroundColor Red
}

Read-Host "엔터를 눌러 종료"
