# ReqPilot

ReqPilot은 제안요청서(RFP)의 요구사항, 목차, 제안서 분석, 추적 매트릭스, 작업일지, 할 일, AI 검색을 한곳에서 관리하기 위한 로컬 Flask 기반 업무 도구입니다.

## 주요 기능

- RFP PDF 업로드 후 Gemini를 이용한 요구사항, 목차, 사업 정보 자동 추출
- 요구사항 목록 관리 및 목차 항목과의 매핑 관리
- 목차 기준/요구사항 기준 추적 매트릭스 조회
- RFP 문서 또는 DB에 저장된 요구사항을 기준으로 제안서 충족 여부 분석
- 할 일 목록과 작업일지 관리
- 로컬 벡터 청크 동기화를 통한 RAG 기반 AI 어시스턴트

## 설치

Conda 환경을 사용하는 경우:

```powershell
conda env create -f environment.yml
conda activate req-manager
```

pip로 설치하는 경우:

```powershell
pip install -r requirements.txt
```

## 환경변수 설정

`.env.example` 파일을 복사해 로컬용 `.env` 파일을 만듭니다.

```powershell
copy .env.example .env
```

그다음 `.env` 파일에서 아래 값을 설정합니다.

- `GEMINI_API_KEY`: Gemini API 키
- `SECRET_KEY`: Flask 세션 및 로컬 인증에 사용할 임의의 비밀 키

## 실행

```powershell
python app.py
```

브라우저에서 아래 주소로 접속합니다.

```text
http://127.0.0.1:5000
```

## Git에서 제외되는 로컬 데이터

아래 경로는 비밀 정보, 개인 문서, 업로드 파일, 실행 중 생성되는 데이터가 포함될 수 있어 Git 추적 대상에서 제외합니다.

- `.env`
- `instance/`
- `uploads/`
- `logs/`
- `__pycache__/`
- `start_server.vbs`

## 참고

이 프로젝트는 로컬 업무 환경에서 사용하는 것을 전제로 만들어졌습니다. 외부 네트워크에 공개하거나 여러 사용자가 함께 쓰는 서버로 운영하려면 인증, 권한, 파일 접근 제어를 별도로 강화해야 합니다.
