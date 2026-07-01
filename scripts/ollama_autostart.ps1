# ollama_autostart.ps1 — Ollama를 OLLAMA_HOST=0.0.0.0 으로 자동시작 등록
# 사용법: 관리자 권한 없이 실행 가능 (현재 사용자 Task Scheduler)
#   등록: .\scripts\ollama_autostart.ps1 -Register
#   해제: .\scripts\ollama_autostart.ps1 -Unregister
#   테스트: .\scripts\ollama_autostart.ps1 -Test

param(
    [switch]$Register,
    [switch]$Unregister,
    [switch]$Test
)

$TASK_NAME = "OllamaAutostart"
$OLLAMA    = (Get-Command ollama -ErrorAction SilentlyContinue)?.Source
if (-not $OLLAMA) { $OLLAMA = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" }

if ($Test) {
    Write-Host "Ollama 경로: $OLLAMA"
    $env:OLLAMA_HOST = "0.0.0.0"
    & $OLLAMA serve
    exit
}

if ($Unregister) {
    Unregister-ScheduledTask -TaskName $TASK_NAME -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "[$TASK_NAME] 자동시작 해제 완료"
    exit
}

if ($Register) {
    if (-not (Test-Path $OLLAMA)) {
        Write-Error "Ollama 실행파일을 찾을 수 없습니다: $OLLAMA"
        exit 1
    }

    # 환경변수 설정 후 ollama serve를 실행하는 래퍼
    $wrapperPath = "$env:APPDATA\OllamaAutostart.ps1"
    @"
`$env:OLLAMA_HOST = '0.0.0.0'
Start-Process -FilePath '$OLLAMA' -ArgumentList 'serve' -WindowStyle Hidden
"@ | Set-Content $wrapperPath -Encoding UTF8

    $action  = New-ScheduledTaskAction `
        -Execute "powershell.exe" `
        -Argument "-NonInteractive -WindowStyle Hidden -File `"$wrapperPath`""

    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 0)

    Register-ScheduledTask `
        -TaskName  $TASK_NAME `
        -Action    $action `
        -Trigger   $trigger `
        -Settings  $settings `
        -Force | Out-Null

    Write-Host "[$TASK_NAME] 자동시작 등록 완료!"
    Write-Host "  - 로그인 시 Ollama가 0.0.0.0:11434 로 자동 시작됩니다"
    Write-Host "  - 지금 바로 시작하려면: .\scripts\ollama_autostart.ps1 -Test"
    exit
}

Write-Host "사용법:"
Write-Host "  .\scripts\ollama_autostart.ps1 -Register    # 자동시작 등록"
Write-Host "  .\scripts\ollama_autostart.ps1 -Unregister  # 자동시작 해제"
Write-Host "  .\scripts\ollama_autostart.ps1 -Test        # 지금 바로 실행 (테스트)"
