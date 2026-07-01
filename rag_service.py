"""
RAG (Retrieval-Augmented Generation) 서비스
- sentence-transformers 로컬 모델로 벡터화 (API 비용 없음)
- 코사인 유사도로 관련 청크 검색
- LLM 답변: LOCAL_LLM_URL 설정 시 Ollama(Qwen 등) 사용, 미설정 시 Gemini Fallback
"""
import json
import logging
import os
import re
from datetime import datetime, timedelta, date

import google.generativeai as genai
import numpy as np

logger = logging.getLogger(__name__)

EMBED_MODEL_NAME = 'paraphrase-multilingual-MiniLM-L12-v2'
CHAT_MODEL       = 'gemini-2.5-flash'
TOP_K            = 8

# 로컬 LLM (Ollama) 설정 — .env 에서 읽음
LOCAL_LLM_URL   = os.environ.get('LOCAL_LLM_URL', '').rstrip('/')   # e.g. http://localhost:11434
LOCAL_LLM_MODEL = os.environ.get('LOCAL_LLM_MODEL', 'qwen2.5:7b')

# 청킹 설정
CHUNK_MAX_CHARS = 500   # 서브청크 최대 길이 (문자 수)
CHUNK_OVERLAP   = 50    # 서브청크 간 겹침 길이

_embed_model = None   # 지연 로딩 (최초 호출 시 1회 초기화)


def _get_model():
    global _embed_model
    if _embed_model is None:
        from sentence_transformers import SentenceTransformer
        logger.info("로컬 임베딩 모델 로딩: %s", EMBED_MODEL_NAME)
        _embed_model = SentenceTransformer(EMBED_MODEL_NAME)
        logger.info("임베딩 모델 로딩 완료")
    return _embed_model


# ── 텍스트 유틸 ──────────────────────────────────────────────────────────────

def _strip_html(html: str) -> str:
    if not html:
        return ''
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:6000]


def _fmt_date(dt) -> str:
    """datetime/date → 'YYYY-MM-DD' 문자열. None이면 빈 문자열."""
    if dt is None:
        return ''
    if hasattr(dt, 'date'):
        return dt.date().isoformat()
    return str(dt)[:10]


def _split_text(text: str, max_chars: int = CHUNK_MAX_CHARS, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """
    긴 텍스트를 단락 우선으로 분할.
    max_chars 이하이면 분할하지 않고 그대로 반환.
    """
    if len(text) <= max_chars:
        return [text]

    # 단락(\n\n), 문장(. ), 공백 순으로 분할 경계 탐색
    chunks, start = [], 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            # 단락 경계 우선
            cut = text.rfind('\n\n', start, end)
            if cut == -1:
                cut = text.rfind('. ', start, end)
            if cut == -1:
                cut = text.rfind(' ', start, end)
            if cut != -1 and cut > start:
                end = cut + 1
        chunks.append(text[start:end].strip())
        start = max(start + 1, end - overlap)
    return [c for c in chunks if c]


# ── 임베딩 (로컬, API 비용 없음) ─────────────────────────────────────────────

def embed_document(text: str, api_key: str = '') -> list[float]:
    """문서 임베딩 — 로컬 모델 사용, api_key 불필요"""
    model = _get_model()
    return model.encode(text[:8000], normalize_embeddings=True).tolist()


def embed_query(text: str, api_key: str = '') -> list[float]:
    """쿼리 임베딩 — 로컬 모델 사용"""
    model = _get_model()
    return model.encode(text[:2000], normalize_embeddings=True).tolist()


def cosine_sim(a: list, b: list) -> float:
    a, b = np.array(a, dtype=np.float32), np.array(b, dtype=np.float32)
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / denom) if denom else 0.0


# ── 청크 빌드 ────────────────────────────────────────────────────────────────

def _parse_due_date(due_date_str: str | None) -> datetime | None:
    """할일 마감일 문자열을 datetime으로 변환"""
    if not due_date_str:
        return None
    try:
        return datetime.strptime(due_date_str, '%Y-%m-%d')
    except Exception:
        return None


def build_chunk_for(source_type: str, source_id: int) -> dict | None:
    """특정 항목 1개의 청크 생성. 존재하지 않으면 None 반환."""
    from models import Project, Requirement, TOCItem, WorkLog, TodoItem, BusinessInfo

    if source_type == 'worklog':
        log = WorkLog.query.get(source_id)
        if not log:
            return None
        content = _strip_html(log.content)
        tags    = json.loads(log.tags) if log.tags else []
        return {
            'source_type':  'worklog',
            'source_id':    log.id,
            'chunk_text':   f"[작업일지] 날짜: {log.created_at}\n제목: {log.title}\n태그: {', '.join(tags)}\n내용: {content}",
            'source_url':   f'/worklog?id={log.id}',
            'source_label': f"작업일지: {log.title} ({log.created_at})",
            'source_date':  log.created_at,
        }

    if source_type == 'todo':
        todo = TodoItem.query.get(source_id)
        if not todo:
            return None
        return {
            'source_type':  'todo',
            'source_id':    todo.id,
            'chunk_text':   f"[할일] {todo.title}\n상태: {todo.status} | 우선순위: {todo.priority} | 마감일: {todo.due_date or '없음'}\n메모: {todo.description or ''}",
            'source_url':   '/todos',
            'source_label': f"할일: {todo.title}",
            'source_date':  _parse_due_date(todo.due_date) or todo.created_at,
        }

    if source_type == 'toc':
        t = TOCItem.query.get(source_id)
        if not t or not t.depth3:
            return None
        proj = t.pdf.project
        path = ' > '.join(filter(None, [t.depth1, t.depth2, t.depth3]))
        return {
            'source_type':  'toc',
            'source_id':    t.id,
            'chunk_text':   f"[목차] 프로젝트: {proj.name} | 문서: {t.pdf.original_name}\n경로: {path}\n상태: {t.work_status or ''} | 페이지: {t.page_number or ''}\n비고: {t.remarks or ''}",
            'source_url':   f'/project/{proj.id}/pdf/{t.pdf_id}',
            'source_label': f"{proj.name} > {path}",
            'source_date':  t.created_at,
        }

    if source_type == 'requirement':
        r = Requirement.query.get(source_id)
        if not r:
            return None
        proj = r.pdf.project
        return {
            'source_type':  'requirement',
            'source_id':    r.id,
            'chunk_text':   f"[요구사항] 프로젝트: {proj.name} | 문서: {r.pdf.original_name}\n번호: {r.req_id} | 제목: {r.req_name}\n내용: {r.detail or ''}",
            'source_url':   f'/project/{proj.id}/pdf/{r.pdf_id}',
            'source_label': f"{proj.name} > {r.req_id} {r.req_name}",
            'source_date':  r.created_at,
        }

    if source_type == 'business_info':
        bi = BusinessInfo.query.get(source_id)
        if not bi:
            return None
        proj = bi.pdf.project
        return {
            'source_type':  'business_info',
            'source_id':    bi.id,
            'chunk_text':   f"[사업정보] 프로젝트: {proj.name} | 문서: {bi.pdf.original_name}\n사업명: {bi.business_name or ''}\n발주기관: {bi.client or ''}\n수행기관: {bi.contractor or ''}\n사업기간: {bi.business_period or ''}\n개요: {bi.overview or ''}",
            'source_url':   f'/project/{proj.id}',
            'source_label': f"{proj.name} — 사업정보",
            'source_date':  None,
        }

    return None


def _make_chunks(base: dict, content: str, max_chars: int = CHUNK_MAX_CHARS) -> list[dict]:
    """content를 분할해 서브청크 리스트 반환. base에 chunk_text 추가."""
    parts = _split_text(content, max_chars)
    if len(parts) == 1:
        return [{**base, 'chunk_text': parts[0]}]
    result = []
    for i, part in enumerate(parts, 1):
        result.append({**base, 'chunk_text': f"{part} ({i}/{len(parts)})"})
    return result


def build_chunks() -> list[dict]:
    """DB 전체 데이터를 RAG 청크 목록으로 변환 (긴 텍스트는 서브청크 분할)"""
    from models import Project, WorkLog, TodoItem
    chunks = []

    # ── 프로젝트 / PDF / 요구사항 / 목차 / 사업정보 ─────────────────────────
    for proj in Project.query.all():
        for pdf in proj.pdfs:
            base_url = f'/project/{proj.id}'

            # 사업 정보
            if pdf.business_info:
                bi = pdf.business_info
                parts = [
                    f"[사업정보] 프로젝트: {proj.name} | 문서: {pdf.original_name}",
                    f"사업명: {bi.business_name}" if bi.business_name else '',
                    f"발주기관: {bi.client}" if bi.client else '',
                    f"수행기관: {bi.contractor}" if bi.contractor else '',
                    f"사업기간: {bi.business_period}" if bi.business_period else '',
                    f"사업비: {bi.business_cost}" if bi.business_cost else '',
                    f"개요: {bi.overview}" if bi.overview else '',
                ]
                text = '\n'.join(p for p in parts if p)
                chunks.append({
                    'source_type':  'business_info',
                    'source_id':    bi.id,
                    'chunk_text':   text,
                    'source_url':   base_url,
                    'source_label': f"{proj.name} — 사업정보",
                    'source_date':  None,
                })

            # 요구사항 (detail이 길면 분할)
            for r in pdf.requirements:
                header = (
                    f"[요구사항] 프로젝트: {proj.name} | 문서: {pdf.original_name}\n"
                    f"번호: {r.req_id} | 제목: {r.req_name}"
                )
                detail = r.detail or ''
                base = {
                    'source_type':  'requirement',
                    'source_id':    r.id,
                    'source_url':   f'/project/{proj.id}/pdf/{pdf.id}',
                    'source_label': f"{proj.name} > {r.req_id} {r.req_name}",
                    'source_date':  r.created_at,
                }
                full = f"{header}\n내용: {detail}" if detail else header
                chunks.extend(_make_chunks(base, full))

            # 목차 (depth3 항목만)
            for t in pdf.toc_items:
                if not t.depth3:
                    continue
                path = ' > '.join(filter(None, [t.depth1, t.depth2, t.depth3]))
                parts = [
                    f"[목차] 프로젝트: {proj.name} | 문서: {pdf.original_name}",
                    f"경로: {path}",
                    f"상태: {t.work_status}" if t.work_status else '',
                    f"페이지: {t.page_number}" if t.page_number else '',
                    f"비고: {t.remarks}" if t.remarks else '',
                ]
                text = '\n'.join(p for p in parts if p)
                chunks.append({
                    'source_type':  'toc',
                    'source_id':    t.id,
                    'chunk_text':   text,
                    'source_url':   f'/project/{proj.id}/pdf/{pdf.id}',
                    'source_label': f"{proj.name} > {path}",
                    'source_date':  t.created_at,
                })

    # ── 작업일지 (내용이 길면 단락 단위로 분할) ──────────────────────────────
    for log in WorkLog.query.all():
        content = _strip_html(log.content)
        tags    = ', '.join(json.loads(log.tags)) if log.tags else ''
        date_str = _fmt_date(log.created_at)
        header  = (
            f"[작업일지] 날짜: {date_str}\n"
            f"제목: {log.title}"
            + (f"\n태그: {tags}" if tags else '')
        )
        base = {
            'source_type':  'worklog',
            'source_id':    log.id,
            'source_url':   f'/worklog?id={log.id}',
            'source_label': f"작업일지: {log.title} ({date_str})",
            'source_date':  log.created_at,
        }
        if content:
            # 헤더 + 내용을 분할 (헤더는 각 서브청크에 반복)
            sub_parts = _split_text(content)
            if len(sub_parts) == 1:
                chunks.append({**base, 'chunk_text': f"{header}\n내용: {sub_parts[0]}"})
            else:
                for i, part in enumerate(sub_parts, 1):
                    chunks.append({**base, 'chunk_text': f"{header}\n내용({i}/{len(sub_parts)}): {part}"})
        else:
            chunks.append({**base, 'chunk_text': header})

    # ── 할일 ─────────────────────────────────────────────────────────────────
    for todo in TodoItem.query.all():
        parts = [
            f"[할일] {todo.title}",
            f"상태: {todo.status} | 우선순위: {todo.priority}",
            f"마감일: {todo.due_date}" if todo.due_date else '',
            f"메모: {todo.description}" if todo.description else '',
        ]
        text = '\n'.join(p for p in parts if p)
        chunks.append({
            'source_type':  'todo',
            'source_id':    todo.id,
            'chunk_text':   text,
            'source_url':   '/todos',
            'source_label': f"할일: {todo.title}",
            'source_date':  _parse_due_date(todo.due_date) or todo.created_at,
        })

    return chunks


# ── 동기화 (임베딩 생성 후 DB 저장) ─────────────────────────────────────────

def sync_vectors(api_key: str = '', progress_cb=None):
    """
    전체 데이터를 임베딩해서 vector_chunk 테이블에 저장.
    progress_cb(current, total, msg) 로 진행상황 전달.
    """
    from models import db, VectorChunk
    from datetime import datetime as dt

    chunks = build_chunks()
    total  = len(chunks)
    logger.info("RAG 동기화 시작: %d 청크", total)

    # 기존 데이터 전체 삭제 후 재생성
    VectorChunk.query.delete()
    db.session.commit()

    for i, c in enumerate(chunks):
        if progress_cb:
            progress_cb(i + 1, total, c['source_label'])
        try:
            emb = embed_document(c['chunk_text'])
            vc  = VectorChunk(
                source_type  = c['source_type'],
                source_id    = c['source_id'],
                chunk_text   = c['chunk_text'],
                source_url   = c['source_url'],
                source_label = c['source_label'],
                embedding    = json.dumps(emb),
                updated_at   = dt.utcnow(),
                source_date  = c.get('source_date'),
            )
            db.session.add(vc)
            if (i + 1) % 20 == 0:
                db.session.commit()
        except Exception as e:
            logger.warning("청크 임베딩 실패 [%s]: %s", c['source_label'], e)

    db.session.commit()
    logger.info("RAG 동기화 완료: %d 청크 저장", total)
    return total


# ── 검색 ─────────────────────────────────────────────────────────────────────

# 쿼리 키워드 → 강제 포함할 source_type 매핑
_TYPE_KEYWORDS = {
    'worklog':       ['작업일지', '일지', '업무일지', '작업 일지',
                      '작업 내용', '작업한', '작업했', '진행 내용', '진행했',
                      '오늘 한 일', '오늘 작업', '어제 작업', '이번 주 작업',
                      '작업 현황', '업무 내용', '업무 현황'],
    'todo':          ['할일', '할 일', '투두', 'todo', '작업 목록', '긴급'],
    'requirement':   ['요구사항', '기능요구', 'sfr', 'nfr', 'qr'],
    'toc':           ['목차', '항목', '챕터'],
    'business_info': ['사업정보', '사업 정보', '발주기관', '수행기관', '사업기간', '사업비'],
}


def _forced_types(query: str) -> set[str]:
    """쿼리에 포함된 키워드로 강제 포함할 source_type 집합 반환"""
    q_lower = query.lower()
    forced = set()
    for stype, keywords in _TYPE_KEYWORDS.items():
        if any(kw in q_lower for kw in keywords):
            forced.add(stype)
    return forced


def _parse_date_filter(query: str):
    """
    쿼리에서 날짜 표현을 감지해 필터 정보 반환.
    반환: None | ('recent', N) | ('range', date_from, date_to)
    """
    today = datetime.now().date()
    q = query.lower()

    # 상대적 최신/최근 (날짜 범위 없이 최신순 정렬)
    if re.search(r'최근|최신|최후|가장\s*새|요즘|근래|방금|마지막|최종|제일\s*최근|가장\s*최근', q):
        return ('recent', 5)

    # 오늘/금일
    if re.search(r'오늘|금일|today', q):
        return ('range', today, today)

    # 어제/전일
    if re.search(r'어제|전일|yesterday', q):
        d = today - timedelta(days=1)
        return ('range', d, d)

    # 그제/그저께
    if re.search(r'그제|그저께', q):
        d = today - timedelta(days=2)
        return ('range', d, d)

    # 이번 주/금주
    if re.search(r'이번\s*주|금주|이번주|this\s*week', q):
        start = today - timedelta(days=today.weekday())
        return ('range', start, today)

    # 지난주/저번 주
    if re.search(r'지난\s*주|저번\s*주|지난주|저번주|last\s*week', q):
        start = today - timedelta(days=today.weekday() + 7)
        end = start + timedelta(days=6)
        return ('range', start, end)

    # 이번 달/금월
    if re.search(r'이번\s*달|금월|이번달|이번\s*월|this\s*month', q):
        start = today.replace(day=1)
        return ('range', start, today)

    # 지난달/저번 달
    if re.search(r'지난\s*달|저번\s*달|지난달|저번달|지난\s*월|last\s*month', q):
        first_of_this = today.replace(day=1)
        last_month_end = first_of_this - timedelta(days=1)
        start = last_month_end.replace(day=1)
        return ('range', start, last_month_end)

    # 올해/금년
    if re.search(r'올해|금년|올\s*해|this\s*year', q):
        start = today.replace(month=1, day=1)
        return ('range', start, today)

    # 작년/지난해
    if re.search(r'작년|지난\s*해|지난해|last\s*year', q):
        start = today.replace(year=today.year - 1, month=1, day=1)
        end = today.replace(year=today.year - 1, month=12, day=31)
        return ('range', start, end)

    # N일 전/N주 전/N달 전
    m = re.search(r'(\d+)\s*일\s*전', q)
    if m:
        d = today - timedelta(days=int(m.group(1)))
        return ('range', d, today)

    m = re.search(r'(\d+)\s*주\s*전', q)
    if m:
        d = today - timedelta(weeks=int(m.group(1)))
        return ('range', d, today)

    m = re.search(r'(\d+)\s*(달|개월)\s*전', q)
    if m:
        months = int(m.group(1))
        d = today.replace(month=((today.month - months - 1) % 12) + 1,
                          year=today.year - (months + today.month - 1) // 12)
        return ('range', d, today)

    # 특정 날짜: "5월 19일", "05/19", "2025-05-19", "25년 5월"
    m = re.search(r'(\d{4})[-/년\s]*(\d{1,2})[-/월\s]*(\d{1,2})일?', q)
    if m:
        try:
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return ('range', d, d)
        except ValueError:
            pass

    m = re.search(r'(\d{1,2})월\s*(\d{1,2})일', q)
    if m:
        try:
            d = date(today.year, int(m.group(1)), int(m.group(2)))
            return ('range', d, d)
        except ValueError:
            pass

    m = re.search(r'(\d{1,2})[-/](\d{1,2})', q)
    if m:
        try:
            d = date(today.year, int(m.group(1)), int(m.group(2)))
            return ('range', d, d)
        except ValueError:
            pass

    return None


def _chunk_date(c) -> datetime | None:
    """VectorChunk의 source_date 반환 (없으면 None)"""
    return getattr(c, 'source_date', None)


def search(query: str, api_key: str = '', top_k: int = TOP_K) -> list[dict]:
    """질문과 유사한 청크를 상위 top_k개 반환.
    - 소스 타입 키워드가 있으면 해당 타입 강제 포함
    - 날짜 표현이 있으면 date 필터링/최신순 정렬 적용
    """
    from models import VectorChunk

    chunks = VectorChunk.query.filter(VectorChunk.embedding.isnot(None)).all()
    if not chunks:
        return []

    q_emb       = embed_query(query)
    forced      = _forced_types(query)
    date_filter = _parse_date_filter(query)

    scored = []
    for c in chunks:
        try:
            emb   = json.loads(c.embedding)
            score = cosine_sim(q_emb, emb)
            scored.append((score, c))
        except Exception:
            pass

    scored.sort(key=lambda x: x[0], reverse=True)

    results  = []
    seen_ids = set()

    # 1) 강제 포함 타입 처리 (날짜 필터/정렬 적용)
    if forced:
        per_type_limit = max(2, 6 // len(forced))
        for ftype in forced:
            type_items = [(s, c) for s, c in scored if c.source_type == ftype]

            if date_filter and date_filter[0] == 'range':
                _, d_from, d_to = date_filter
                dt_from = datetime(d_from.year, d_from.month, d_from.day)
                dt_to   = datetime(d_to.year, d_to.month, d_to.day, 23, 59, 59)
                type_items = [
                    (s, c) for s, c in type_items
                    if _chunk_date(c) and dt_from <= _chunk_date(c) <= dt_to
                ]
            elif date_filter and date_filter[0] == 'recent':
                # 최신순 정렬 후 상위 N개
                type_items.sort(key=lambda x: _chunk_date(x[1]) or datetime.min, reverse=True)
                type_items = type_items[:date_filter[1]]

            for score, c in type_items[:per_type_limit]:
                results.append({**c.to_dict(), 'score': round(score, 4)})
                seen_ids.add(c.id)

    # 2) 나머지 슬롯은 유사도 상위 청크로 채움 (임계값 0.25)
    for score, c in scored:
        if len(results) >= top_k:
            break
        if c.id in seen_ids:
            continue
        if score < 0.25:
            break
        results.append({**c.to_dict(), 'score': round(score, 4)})

    return results


# ── 답변 생성 ────────────────────────────────────────────────────────────────

def answer(query: str, history: list[dict], api_key: str, use_local: bool = False, local_llm_url: str = None) -> dict:
    """
    RAG 기반 답변 생성.
    history: [{'role': 'user'|'model', 'content': str}, ...]
    반환: {'answer': str, 'sources': [...]}
    """
    # 1. 상대 날짜 표현 → 실제 날짜로 치환하여 검색 정확도 향상
    _today = date.today()
    _search_query = (query
        .replace('오늘', _today.isoformat())
        .replace('어제', (_today - timedelta(days=1)).isoformat())
        .replace('그제', (_today - timedelta(days=2)).isoformat()))

    # 1. 관련 청크 검색
    relevant  = search(_search_query, api_key)
    forced    = _forced_types(query)

    # 2. 컨텍스트 구성 — forced 타입 우선, 나머지는 보조
    forced_chunks  = [r for r in relevant if r['source_type'] in forced] if forced else relevant
    support_chunks = [r for r in relevant if r['source_type'] not in forced] if forced else []

    ctx_lines = []
    for r in forced_chunks:
        ctx_lines.append(f"[{r['source_type']}] {r['source_label']}\n{r['chunk_text']}")
    for r in support_chunks[:2]:   # 보조 데이터는 최대 2개
        ctx_lines.append(f"[참고/{r['source_type']}] {r['source_label']}\n{r['chunk_text']}")

    context = '\n\n---\n\n'.join(ctx_lines) if ctx_lines else '(검색된 관련 데이터 없음)'

    # 3. 시스템 프롬프트
    system_prompt = f"""당신은 프로젝트 업무 어시스턴트입니다.
오늘 날짜: {_today.isoformat()}
아래 [관련 데이터]를 바탕으로 사용자의 질문에 답하세요.

## 답변 형식 규칙
- **반드시 마크다운 형식**으로 작성하세요 (##, ###, **, -, 번호 목록 등 적극 활용)
- 정보가 여러 개면 글머리 기호(-)나 번호 목록으로 정리하세요
- 중요한 이름·날짜·상태는 **굵게** 표시하세요
- 답변은 간결하되 핵심 정보가 빠지지 않게 하세요

## 내용 규칙
- [관련 데이터]에 있는 내용만 답변하세요
- [참고/...] 로 표시된 데이터는 질문과 직접 관련 없는 보조 자료이므로, 질문에 꼭 필요할 때만 언급하세요
- 데이터에 없는 내용은 "관련 기록을 찾지 못했습니다"라고 하세요
- 출처 목록은 별도로 표시되므로 답변 안에 URL이나 출처 목록을 나열하지 마세요

## 관련 데이터
{context}
"""

    # 4. 답변 생성 — 로컬 LLM 선택 시 (클라이언트 IP 또는 서버 .env URL), 아니면 Gemini
    effective_llm_url = (local_llm_url or LOCAL_LLM_URL or '').rstrip('/')
    if use_local and effective_llm_url:
        import requests as _req
        messages = [{"role": "system", "content": system_prompt}]
        for h in history[:-1]:
            messages.append({
                "role": "user" if h['role'] == 'user' else "assistant",
                "content": h['content'],
            })
        messages.append({"role": "user", "content": query})
        resp = _req.post(
            f"{effective_llm_url}/v1/chat/completions",
            json={"model": LOCAL_LLM_MODEL, "messages": messages, "stream": False},
            timeout=120,
        )
        resp.raise_for_status()
        answer_text = resp.json()["choices"][0]["message"]["content"]

        class _FakeResponse:
            def __init__(self, text): self.text = text
        response = _FakeResponse(answer_text)

    else:
        # Gemini fallback
        genai.configure(api_key=api_key)
        gemini_history = []
        for h in history[:-1]:
            role = 'user' if h['role'] == 'user' else 'model'
            gemini_history.append({'role': role, 'parts': [h['content']]})
        model = genai.GenerativeModel(CHAT_MODEL, system_instruction=system_prompt)
        chat     = model.start_chat(history=gemini_history)
        response = chat.send_message(query)

    # 6. 소스 카드: forced 타입 우선, 없으면 고득점 상위 5개만
    if forced and forced_chunks:
        display_sources = forced_chunks[:5]
    else:
        # forced 타입 없을 때는 score 0.70 이상만 표시 (무관한 목차 등 제외)
        display_sources = [r for r in relevant if r.get('score', 0) >= 0.70][:5]

    return {
        'answer':  response.text,
        'sources': display_sources,
    }
