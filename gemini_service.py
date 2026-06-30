import google.generativeai as genai
import json
import re
import time
import logging
from typing import Callable, Optional

GEMINI_MODEL = 'gemini-3.1-pro-preview'
INTER_CALL_DELAY = 10  # seconds between consecutive Gemini API calls

logger = logging.getLogger(__name__)


def _configure(api_key: str):
    genai.configure(api_key=api_key)


def _upload_pdf(pdf_path: str):
    uploaded = genai.upload_file(path=pdf_path, mime_type='application/pdf')
    while uploaded.state.name == 'PROCESSING':
        time.sleep(2)
        uploaded = genai.get_file(uploaded.name)
    if uploaded.state.name == 'FAILED':
        raise RuntimeError('Gemini 파일 처리 실패')
    return uploaded


def _generate_with_retry(model, contents, max_retries: int = 4):
    """429 ResourceExhausted 발생 시 지수 백오프로 재시도."""
    delay = 15
    for attempt in range(max_retries):
        try:
            return model.generate_content(contents)
        except Exception as e:
            err = str(e)
            is_rate_limit = '429' in err or 'ResourceExhausted' in err or 'RESOURCE_EXHAUSTED' in err
            if is_rate_limit and attempt < max_retries - 1:
                logger.warning("Rate limit 429 — %ds 후 재시도 (%d/%d)", delay, attempt + 1, max_retries)
                time.sleep(delay)
                delay *= 2
            else:
                raise


def _parse_json(text: str):
    patterns = [
        r'```json\s*([\s\S]*?)\s*```',
        r'```\s*([\s\S]*?)\s*```',
        r'(\[[\s\S]*\])',
        r'(\{[\s\S]*\})',
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                continue
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        return None


def extract_all(pdf_path: str, api_key: str, progress_cb: Optional[Callable] = None):
    def notify(step: int, msg: str):
        if progress_cb:
            progress_cb(step, msg)

    notify(1, 'Gemini API 연결 중...')
    _configure(api_key)

    notify(2, 'PDF 파일 업로드 중...')
    uploaded_file = _upload_pdf(pdf_path)

    model = genai.GenerativeModel(GEMINI_MODEL)

    try:
        notify(3, '요구사항 추출 중...')
        req_prompt = """이 PDF 문서에서 요구사항을 모두 추출해주세요.
각 요구사항의 고유번호, 명칭, 세부내용을 파악하여 아래 JSON 배열 형식으로만 반환하세요.
다른 설명 없이 JSON만 반환하세요.

[
  {
    "req_id": "요구사항 고유번호 (예: REQ-001, FR-001 등)",
    "req_name": "요구사항 명칭",
    "detail": "세부내용"
  }
]"""
        req_response = _generate_with_retry(model, [uploaded_file, req_prompt])
        requirements = _parse_json(req_response.text) or []

        notify(4, '목차 구조 추출 중...')
        time.sleep(INTER_CALL_DELAY)
        toc_prompt = """이 PDF 문서에서 제안서 작성 목차를 추출해주세요.

우선순위:
1. 문서 내 "제안서 세부 작성지침", "작성 목차", "제안서 목차", "목차 구성" 등의 섹션이 있으면 거기에 명시된 목차 항목을 기준으로 추출하세요.
2. 위 섹션이 없으면 문서 전체의 목차 구조를 추출하세요.

계층 구조(1단계~3단계)를 파악하여 아래 JSON 배열 형식으로만 반환하세요.
다른 설명 없이 JSON만 반환하세요.

[
  {
    "depth1": "1단계 항목명",
    "depth2": "2단계 항목명 (없으면 null)",
    "depth3": "3단계 항목명 (없으면 null)",
    "page_number": "페이지 번호 (없으면 null)"
  }
]"""
        toc_response = _generate_with_retry(model, [uploaded_file, toc_prompt])
        toc_items = _parse_json(toc_response.text) or []

        notify(5, '사업 정보 추출 중...')
        time.sleep(INTER_CALL_DELAY)
        biz_prompt = """이 PDF 문서에서 사업/프로젝트 기본 정보를 추출해주세요.
아래 JSON 형식으로만 반환하세요. 없는 항목은 null로 설정하세요.
다른 설명 없이 JSON만 반환하세요.

{
  "business_name": "사업명 또는 과제명",
  "business_cost": "총 사업비 (예: 5억원, 500,000천원)",
  "business_period": "사업 기간 (예: 2024.01 ~ 2024.12)",
  "client": "발주기관 또는 발주처",
  "contractor": "수행기관 또는 주관기관",
  "overview": "사업 목적 및 개요 (2~5문장 요약)",
  "extras": {
    "추가키1": "값1",
    "추가키2": "값2"
  }
}"""
        biz_response = _generate_with_retry(model, [uploaded_file, biz_prompt])
        business_info = _parse_json(biz_response.text) or {}

    finally:
        try:
            genai.delete_file(uploaded_file.name)
        except Exception:
            pass

    if isinstance(requirements, dict):
        requirements = [requirements]
    if isinstance(toc_items, dict):
        toc_items = [toc_items]
    if isinstance(business_info, list):
        business_info = business_info[0] if business_info else {}

    return requirements, toc_items, business_info


def analyze_proposal_match(rfp_path: str, proposal_path: str, api_key: str,
                           progress_cb: Optional[Callable] = None) -> dict:
    """제안서 기준으로 RFP 요구사항 충족 여부를 분석한다.

    반환 형식:
    {
      "proposal_mappings": [...],   # 제안서 섹션 → RFP 요구사항 매핑
      "uncovered_rfp": [...]        # RFP에서 미충족/부족한 요구사항 + 추가 제안
    }
    """
    def notify(step: int, msg: str):
        if progress_cb:
            progress_cb(step, msg)

    notify(1, 'Gemini API 연결 중...')
    _configure(api_key)

    notify(2, '제안요청서(RFP) 업로드 중...')
    rfp_file = _upload_pdf(rfp_path)

    notify(3, '제안서 업로드 중...')
    proposal_file = _upload_pdf(proposal_path)

    model = genai.GenerativeModel(GEMINI_MODEL)

    try:
        notify(4, 'AI 매칭 분석 중... (문서 크기에 따라 시간이 소요됩니다)')

        prompt = """두 개의 PDF 문서가 제공됩니다.
첫 번째 문서는 제안요청서(RFP), 두 번째 문서는 제안서입니다.

[분석 방향]
제안서의 각 섹션/내용을 기준으로, 그것이 RFP의 어느 요구사항을 얼마나 충족하는지 매핑하세요.
그런 다음 RFP 요구사항 중 제안서에서 제대로 다루지 못한 항목을 찾아, 어디에 무엇을 추가하면 충족할 수 있는지 제안하세요.

[매칭 수준 기준]
- 완전: 제안서가 해당 RFP 요구사항을 구체적·명시적으로 완전히 충족
- 부분: 간접 언급하거나 일부만 충족

아래 JSON 형식으로만 반환하세요. 다른 설명 없이 JSON만 반환하세요.

{
  "proposal_mappings": [
    {
      "no": 1,
      "proposal_section": "제안서 섹션명 (예: 4.2 보안 아키텍처)",
      "proposal_content": "해당 섹션의 핵심 내용 요약 (200자 이내)",
      "rfp_section": "대응하는 RFP 섹션명 (예: 3.2 보안 요구사항)",
      "rfp_requirement": "해당 RFP 요구사항 핵심 내용 (200자 이내)",
      "match_level": "완전|부분",
      "match_reason": "왜 이 매칭이 성립하는지, 부족한 점은 무엇인지 (300자 이내)"
    }
  ],
  "uncovered_rfp": [
    {
      "no": 1,
      "rfp_section": "미충족 RFP 섹션명",
      "rfp_requirement": "해당 요구사항 내용 (200자 이내)",
      "status": "미반영|부분",
      "add_to_section": "제안서의 어느 섹션에 추가하면 좋을지 (없으면 새 섹션 제안)",
      "suggestion": "구체적으로 어떤 내용을 작성하면 이 요구사항을 충족할 수 있는지 (300자 이내)"
    }
  ]
}"""

        response = _generate_with_retry(model, [rfp_file, proposal_file, prompt])
        results = _parse_json(response.text) or {}

    finally:
        for f in [rfp_file, proposal_file]:
            try:
                genai.delete_file(f.name)
            except Exception:
                pass

    if isinstance(results, list):
        # 구버전 형식 호환 처리
        results = {'proposal_mappings': results, 'uncovered_rfp': []}
    if not isinstance(results, dict):
        results = {}

    results.setdefault('proposal_mappings', [])
    results.setdefault('uncovered_rfp', [])

    total = len(results['proposal_mappings']) + len(results['uncovered_rfp'])
    notify(4, f'분석 완료: 제안서 매핑 {len(results["proposal_mappings"])}건 / 미충족 RFP {len(results["uncovered_rfp"])}건')
    return results


def analyze_proposal_with_db_requirements(
    proposal_path: str,
    requirements: list,   # [{req_id, req_name, detail}, ...]
    toc_items: list,      # [{depth1, depth2, depth3}, ...] — 구조 참고용
    api_key: str,
    progress_cb: Optional[Callable] = None,
) -> dict:
    """DB에 저장된 요구사항을 기반으로 제안서를 분석.
    RFP PDF 업로드 불필요 — 제안서 PDF만 업로드하므로 토큰 절약.
    """
    def notify(step: int, msg: str):
        if progress_cb:
            progress_cb(step, msg)

    notify(1, 'Gemini API 연결 중...')
    _configure(api_key)

    notify(2, '제안서 업로드 중...')
    proposal_file = _upload_pdf(proposal_path)

    model = genai.GenerativeModel(GEMINI_MODEL)

    # 요구사항 텍스트 구성
    req_lines = []
    for i, r in enumerate(requirements, 1):
        req_id   = r.get('req_id', f'REQ-{i:03d}')
        req_name = r.get('req_name', '')
        detail   = r.get('detail', '')
        req_lines.append(f'[{req_id}] {req_name}\n  내용: {detail}')
    req_text = '\n\n'.join(req_lines)

    # 목차 구조 텍스트 (선택적 컨텍스트)
    toc_lines = []
    for t in toc_items[:80]:   # 너무 길어지지 않도록 제한
        parts = [t.get('depth1',''), t.get('depth2',''), t.get('depth3','')]
        toc_lines.append(' > '.join(p for p in parts if p))
    toc_text = '\n'.join(toc_lines) if toc_lines else '(목차 정보 없음)'

    try:
        notify(3, 'AI 매칭 분석 중...')

        prompt = f"""아래는 제안요청서(RFP)에서 추출된 요구사항 목록과 목차 구조입니다.

== 목차 구조 (참고) ==
{toc_text}

== 요구사항 목록 ({len(requirements)}건) ==
{req_text}

첨부된 제안서 PDF를 기준으로, 제안서의 각 섹션이 위 요구사항들을 얼마나 충족하는지 분석하세요.

[분석 방향]
제안서 섹션/내용 기준으로 → 어느 RFP 요구사항을 충족하는지 매핑.
그런 다음 충분히 다루지 못한 요구사항을 찾아 추가 제안.

[매칭 수준]
- 완전: 명시적·구체적으로 완전히 충족
- 부분: 간접 언급하거나 일부만 충족

아래 JSON 형식으로만 반환하세요. 다른 설명 없이 JSON만 반환하세요.

{{
  "proposal_mappings": [
    {{
      "no": 1,
      "proposal_section": "제안서 섹션명",
      "proposal_content": "해당 섹션 핵심 내용 요약 (200자 이내)",
      "rfp_section": "대응하는 RFP 요구사항 ID 또는 섹션명",
      "rfp_requirement": "해당 RFP 요구사항 내용 (200자 이내)",
      "match_level": "완전|부분",
      "match_reason": "매칭 근거 및 부족한 점 (300자 이내)"
    }}
  ],
  "uncovered_rfp": [
    {{
      "no": 1,
      "rfp_section": "미충족 요구사항 ID 또는 섹션명",
      "rfp_requirement": "요구사항 내용 (200자 이내)",
      "status": "미반영|부분",
      "add_to_section": "제안서 어느 섹션에 추가할지",
      "suggestion": "어떤 내용을 추가하면 충족되는지 (300자 이내)"
    }}
  ]
}}"""

        response = _generate_with_retry(model, [proposal_file, prompt])
        results = _parse_json(response.text) or {}

    finally:
        try:
            genai.delete_file(proposal_file.name)
        except Exception:
            pass

    if isinstance(results, list):
        results = {'proposal_mappings': results, 'uncovered_rfp': []}
    if not isinstance(results, dict):
        results = {}
    results.setdefault('proposal_mappings', [])
    results.setdefault('uncovered_rfp', [])

    notify(3, f'분석 완료: 매핑 {len(results["proposal_mappings"])}건 / 미충족 {len(results["uncovered_rfp"])}건')
    return results


def verify_revision(revised_proposal_path: str, gap_items: list, api_key: str,
                    progress_cb: Optional[Callable] = None) -> list:
    """수정된 제안서가 이전 분석의 갭 항목들을 해결했는지 검증.

    gap_items: uncovered_rfp 리스트 (rfp_section, rfp_requirement, status, suggestion 포함)
    반환: 항목별 before/after 검증 결과 리스트
    """
    def notify(step: int, msg: str):
        if progress_cb:
            progress_cb(step, msg)

    notify(1, 'Gemini API 연결 중...')
    _configure(api_key)

    notify(2, '수정된 제안서 업로드 중...')
    proposal_file = _upload_pdf(revised_proposal_path)

    model = genai.GenerativeModel(GEMINI_MODEL)

    # 갭 항목을 텍스트로 직렬화 (RFP 재업로드 불필요)
    gap_text = json.dumps(gap_items, ensure_ascii=False, indent=2)

    try:
        notify(3, 'AI 재검증 중...')

        prompt = f"""아래는 이전 분석에서 제안서가 충분히 충족하지 못했던 RFP 요구사항 목록입니다.

{gap_text}

첨부된 수정된 제안서 PDF를 검토하여, 각 항목이 이제 얼마나 해결되었는지 확인해주세요.

판단 기준:
- 완전: 해당 요구사항을 명시적·구체적으로 완전히 충족
- 부분: 일부 충족 또는 간접 언급
- 미반영: 여전히 관련 내용 없음

아래 JSON 배열 형식으로만 반환하세요. 다른 설명 없이 JSON만 반환하세요.

[
  {{
    "no": 항목 번호,
    "rfp_section": "RFP 섹션명",
    "rfp_requirement": "요구사항 내용",
    "previous_status": "이전 상태 (미반영|부분)",
    "current_status": "현재 상태 (완전|부분|미반영)",
    "resolved": true 또는 false,
    "evidence": "제안서에서 확인된 내용과 위치 (해결된 경우, 없으면 null)",
    "remaining_issue": "아직 부족한 점 (미해결인 경우, 없으면 null)"
  }}
]"""

        response = _generate_with_retry(model, [proposal_file, prompt])
        results = _parse_json(response.text) or []

    finally:
        try:
            genai.delete_file(proposal_file.name)
        except Exception:
            pass

    if isinstance(results, dict):
        results = [results]

    resolved = sum(1 for r in results if r.get('resolved'))
    notify(3, f'검증 완료: {resolved}/{len(results)}건 해결 확인')
    return results


def generate_action_summary(results: dict, api_key: str) -> dict:
    """매칭 결과를 바탕으로 액션 플랜(추가/보완/제거) 요약을 생성."""
    _configure(api_key)
    model = genai.GenerativeModel(GEMINI_MODEL)

    results_text = json.dumps(results, ensure_ascii=False, indent=2)
    prompt = f"""아래는 제안서와 RFP의 매칭 분석 결과입니다.
- proposal_mappings: 제안서 각 섹션이 RFP 요구사항을 얼마나 충족하는지
- uncovered_rfp: RFP 요구사항 중 미충족/부족한 항목

{results_text}

이 결과를 바탕으로 제안서 작성팀을 위한 종합 액션 플랜을 작성해주세요.
다음 JSON 형식으로만 반환하세요. 다른 설명 없이 JSON만 반환하세요.

{{
  "overall_score": 전체 충족도 점수 (0~100 정수, 완전=100점, 부분=50점, 미반영=0점 가중평균),
  "overall_assessment": "전반적인 평가 (3~5문장, 핵심 강점과 약점 중심)",
  "add_items": [
    {{
      "rfp_section": "해당 RFP 섹션명",
      "requirement": "충족되지 않은 요구사항 핵심 내용",
      "priority": "높음|중간|낮음",
      "suggestion": "제안서에 추가해야 할 구체적인 내용과 작성 방향 (2~4문장)"
    }}
  ],
  "improve_items": [
    {{
      "rfp_section": "해당 RFP 섹션명",
      "proposal_section": "현재 제안서 섹션명",
      "issue": "현재 부족한 점",
      "priority": "높음|중간|낮음",
      "suggestion": "구체적인 보완 방법 (2~4문장)"
    }}
  ],
  "remove_items": [
    {{
      "proposal_section": "제안서 섹션명",
      "reason": "제거 또는 축소 권장 이유 (RFP 범위 초과, 중복, 불필요 등)"
    }}
  ],
  "priority_actions": [
    "1순위: ...",
    "2순위: ...",
    "3순위: ..."
  ]
}}"""

    try:
        resp = _generate_with_retry(model, [prompt])
        summary = _parse_json(resp.text)
        if isinstance(summary, list):
            summary = summary[0] if summary else {}
        return summary or {}
    except Exception as e:
        logger.warning("generate_action_summary 실패: %s", e)
        return {}


def _fallback_proposal_image_content(requirement: dict, options: dict | None = None) -> dict:
    req_id = requirement.get('req_id') or 'REQ'
    req_name = requirement.get('req_name') or '요구사항'
    detail = (requirement.get('detail') or '').strip()
    summary = detail[:180] if detail else f'{req_name}을 충족하기 위한 제안 구성안을 제시합니다.'
    return {
        'title': f'{req_id} {req_name}',
        'subtitle': '요구사항 충족을 위한 제안 장표 초안',
        'proposal_summary': summary,
        'sections': [
            {
                'heading': '요구사항 해석',
                'body': '요구사항의 목적과 적용 범위를 명확히 정의하고, 제안 범위 안에서 충족 기준을 구체화합니다.',
            },
            {
                'heading': '제안 내용',
                'body': '업무 흐름, 사용자 경험, 시스템 구성 요소를 기준으로 실행 가능한 기능과 산출물을 제안합니다.',
            },
            {
                'heading': '구현 방안',
                'body': '표준 기술, 단계별 적용 절차, 검증 가능한 운영 기준을 통해 안정적인 구현 방안을 제공합니다.',
            },
            {
                'heading': '기대 효과',
                'body': '요구사항 충족 여부를 명확히 확인하고, 구축 이후 운영 효율성과 품질을 높일 수 있습니다.',
            },
        ],
        'checklist': [
            '요구사항 핵심 조건 반영',
            '구현 범위와 산출물 명확화',
            '검증 가능한 충족 기준 제시',
            '운영 및 유지관리 관점 포함',
        ],
        'keywords': ['요구사항 충족', '구현 방안', '검증 기준', '운영 효율'],
    }


def generate_requirement_proposal_content(requirement: dict, options: dict, api_key: str) -> dict:
    """요구사항을 충족하기 위한 제안 장표용 구조화 문구를 생성한다."""
    if not api_key:
        return _fallback_proposal_image_content(requirement, options)

    _configure(api_key)
    model = genai.GenerativeModel(GEMINI_MODEL)

    orientation = options.get('orientation', 'landscape')
    template_type = options.get('template_type', 'auto')
    tone = options.get('tone', 'public')

    prompt = f"""아래 요구사항을 충족하기 위한 제안서 장표 1장 분량의 내용을 작성하세요.
디자인 자체는 별도 시스템이 처리하므로, 문구만 JSON으로 작성하세요.

[요구사항]
- ID: {requirement.get('req_id', '')}
- 명칭: {requirement.get('req_name', '')}
- 상세: {requirement.get('detail', '')}

[생성 옵션]
- 방향: {orientation} (landscape=가로형 16:9, portrait=세로형 A4)
- 템플릿: {template_type}
- 톤: {tone}

[작성 원칙]
- 공공/기술 제안서에 바로 붙일 수 있는 담백한 문장으로 작성
- 허황된 수치나 검증되지 않은 효과를 만들지 말 것
- 요구사항 충족 근거가 드러나게 작성
- 각 body는 80~140자 정도로 짧게 작성
- checklist는 4개, keywords는 4개 이내

아래 JSON 형식으로만 반환하세요. 다른 설명 없이 JSON만 반환하세요.

{{
  "title": "장표 제목",
  "subtitle": "짧은 부제",
  "proposal_summary": "요구사항을 어떻게 충족할지 2문장 이내 요약",
  "sections": [
    {{"heading": "요구사항 해석", "body": "내용"}},
    {{"heading": "제안 내용", "body": "내용"}},
    {{"heading": "구현 방안", "body": "내용"}},
    {{"heading": "기대 효과", "body": "내용"}}
  ],
  "checklist": ["충족 포인트 1", "충족 포인트 2", "충족 포인트 3", "충족 포인트 4"],
  "keywords": ["키워드1", "키워드2", "키워드3", "키워드4"]
}}"""

    try:
        resp = _generate_with_retry(model, [prompt])
        data = _parse_json(resp.text)
        if not isinstance(data, dict):
            return _fallback_proposal_image_content(requirement, options)
        data.setdefault('sections', [])
        data.setdefault('checklist', [])
        data.setdefault('keywords', [])
        return data
    except Exception as e:
        logger.warning("generate_requirement_proposal_content 실패: %s", e)
        return _fallback_proposal_image_content(requirement, options)
