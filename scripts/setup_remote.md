# 원격 PC 최초 설정 가이드

대상 PC: `192.168.7.217`

## 1. 사전 요구사항

- Windows 10/11
- Git for Windows (`winget install Git.Git`)
- Miniconda 또는 Anaconda (`winget install Anaconda.Miniconda3`)
- OpenSSH 서버 (아래 참조)

## 2. OpenSSH 서버 설정 (원격 PC에서)

```powershell
# PowerShell (관리자 권한)
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
Start-Service sshd
Set-Service -Name sshd -StartupType Automatic
```

## 3. GitHub 레포 클론

```powershell
# 원하는 위치에 클론 (예: C:\ReqPilot)
git clone https://github.com/jongchan1514/ReqPilot.git C:\ReqPilot
cd C:\ReqPilot
```

## 4. conda 환경 생성 및 패키지 설치

```powershell
cd C:\ReqPilot
conda env create -f environment.yml
# 또는 수동:
# conda create -n req-manager python=3.11 -y
# conda activate req-manager && pip install -r requirements.txt
```

## 5. 환경 변수 파일 생성

`.env` 파일은 git에 포함되지 않으므로 직접 생성합니다:

```
C:\ReqPilot\.env 파일 내용:

GEMINI_API_KEY=<Gemini API 키>
SECRET_KEY=<임의의 비밀키>
ADMIN_PASSWORD=<관리자 비밀번호>
LOCAL_LLM_URL=   ← 원격 PC에 Ollama 없으면 빈칸 (Gemini 사용)
LOCAL_LLM_MODEL=qwen2.5:3b
```

## 6. 서버 시작

```powershell
# 수동 실행
conda activate req-manager
cd C:\ReqPilot
python app.py

# 또는 VBS 더블클릭
scripts\start_server.vbs
```

## 7. 자동 배포 흐름

로컬 PC(192.168.7.109)에서:
```powershell
# 변경사항 커밋 후
git add .
git commit -m "변경 내용"
.\scripts\deploy.ps1   # push + 원격 PC 자동 업데이트
```

원격 PC에서 수동 업데이트:
```powershell
cd C:\ReqPilot
.\scripts\update.ps1
```

## 8. PostgreSQL 연동 (선택 — 기본은 SQLite)

원격 PC에 PostgreSQL이 설치되어 있다면 SQLite 대신 PostgreSQL을 사용할 수 있습니다.

### 8-1. 로컬 PC에서 데이터 이관 (최초 1회)

```powershell
# 로컬 PC에서 실행 (conda req-manager 환경)
conda activate req-manager
cd p:\python\요구사항

python scripts\migrate_sqlite_to_postgres.py `
    --pg-host 192.168.7.217 `
    --pg-user postgres `
    --pg-password <postgres_비밀번호> `
    --pg-db req_manager
```

비밀번호가 없는 기본 설치라면 `--pg-password` 생략.

### 8-2. 원격 PC .env 설정

```
DATABASE_URL=postgresql://postgres:비밀번호@localhost:5432/req_manager
```

> 원격 PC 자신의 PostgreSQL이므로 `localhost` 사용 (외부 IP 불필요)

### 8-3. PostgreSQL이 외부 접속을 허용하지 않는 경우

PostgreSQL 기본 설치는 `localhost`만 허용합니다.  
로컬 PC에서 마이그레이션 스크립트를 실행하려면 일시적으로 허용:

```
# 원격 PC: C:\Program Files\PostgreSQL\<버전>\data\pg_hba.conf 끝에 추가
host    req_manager     postgres     192.168.7.0/24      md5

# postgresql.conf
listen_addresses = '*'
```

변경 후 PostgreSQL 서비스 재시작.

## 9. 방화벽 설정 (필요 시)

원격 PC 포트 5000을 같은 LAN에서 접근 가능하게 열기:
```powershell
# PowerShell (관리자 권한)
New-NetFirewallRule -DisplayName "ReqPilot Flask" -Direction Inbound -Protocol TCP -LocalPort 5000 -Action Allow
```
