# uninstall_startup.ps1
# 업무 관리 시스템 자동시작 등록을 해제합니다.

$AppName = "업무관리시스템"
$RegPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  업무 관리 시스템 - 자동시작 해제" -ForegroundColor Cyan
Write-Host "============================================"
Write-Host ""

try {
    $existing = Get-ItemProperty -Path $RegPath -Name $AppName -ErrorAction SilentlyContinue
    if ($null -eq $existing) {
        Write-Host "자동시작에 등록되어 있지 않습니다." -ForegroundColor Yellow
    } else {
        Remove-ItemProperty -Path $RegPath -Name $AppName
        Write-Host "[완료] 자동시작에서 제거되었습니다." -ForegroundColor Green
    }
} catch {
    Write-Host "[오류] $_" -ForegroundColor Red
}

Read-Host "엔터를 눌러 종료"
