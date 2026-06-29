@echo off
chcp 65001 > nul
echo ============================================
echo   업무 관리 시스템 - 실행파일 빌드
echo ============================================
echo.

:: conda 환경 활성화 (req-manager)
call conda activate req-manager 2>nul || (
  echo [경고] conda 환경 활성화 실패. 현재 환경으로 진행합니다.
)

:: PyInstaller 설치
pip install pyinstaller --quiet

echo [1/3] PyInstaller 빌드 시작...
echo.

pyinstaller ^
  --onefile ^
  --noconsole ^
  --name "업무관리시스템" ^
  --add-data "templates;templates" ^
  --hidden-import=flask_sqlalchemy ^
  --hidden-import=sqlalchemy.dialects.sqlite ^
  --hidden-import=sqlalchemy.orm ^
  --hidden-import=pkg_resources.py2_compat ^
  --hidden-import=google.generativeai ^
  --hidden-import=dotenv ^
  --collect-all=google.generativeai ^
  app.py

if %ERRORLEVEL% neq 0 (
  echo.
  echo [오류] 빌드 실패! 위 오류 메시지를 확인하세요.
  pause
  exit /b 1
)

echo.
echo [2/3] .env 파일 복사...
if exist ".env" (
  copy ".env" "dist\.env" > nul
  echo     .env 복사 완료
) else (
  echo     [경고] .env 파일이 없습니다. GEMINI_API_KEY 설정이 필요합니다.
)

echo.
echo [3/3] 완료!
echo ============================================
echo   dist\업무관리시스템.exe 생성됨
echo ============================================
echo.
echo 다음 단계:
echo   1. dist 폴더 전체를 원하는 위치에 복사
echo   2. install_startup.ps1 을 실행하여 자동시작 등록
echo.
pause
