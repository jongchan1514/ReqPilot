"""
migrate_sqlite_to_postgres.py
SQLite(req_manager.db) → PostgreSQL 데이터 전체 이관 스크립트

사용법:
  conda activate req-manager
  python scripts/migrate_sqlite_to_postgres.py \
      --pg-host 192.168.7.217 \
      --pg-user postgres \
      --pg-password <비밀번호> \
      --pg-db req_manager

옵션:
  --pg-host   PostgreSQL 호스트 (기본: 192.168.7.217)
  --pg-user   DB 사용자 (기본: postgres)
  --pg-password  DB 비밀번호 (기본: .env의 PG_PASSWORD 환경변수)
  --pg-port   포트 (기본: 5432)
  --pg-db     데이터베이스 이름 (기본: req_manager)
  --sqlite    SQLite 파일 경로 (기본: instance/req_manager.db)
  --drop      기존 테이블 삭제 후 재생성 (주의: 데이터 전부 삭제됨)
"""
import argparse
import os
import sqlite3
import sys

# 스크립트가 scripts/ 안에 있으므로 부모 디렉토리를 path에 추가
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(_ROOT, '.env'))


def parse_args():
    p = argparse.ArgumentParser(description='SQLite → PostgreSQL 이관')
    p.add_argument('--pg-host',     default='192.168.7.217')
    p.add_argument('--pg-user',     default='postgres')
    p.add_argument('--pg-password', default=os.environ.get('PG_PASSWORD', ''))
    p.add_argument('--pg-port',     default='5432')
    p.add_argument('--pg-db',       default='req_manager')
    p.add_argument('--sqlite',      default=os.path.join(_ROOT, 'instance', 'req_manager.db'))
    p.add_argument('--drop',        action='store_true', help='기존 테이블 삭제 후 재생성')
    return p.parse_args()


def get_pg_url(args):
    pw = args.pg_password
    if pw:
        return f'postgresql://{args.pg_user}:{pw}@{args.pg_host}:{args.pg_port}/{args.pg_db}'
    return f'postgresql://{args.pg_user}@{args.pg_host}:{args.pg_port}/{args.pg_db}'


# ── FK 의존성을 고려한 테이블 순서 ──────────────────────────────────────────
TABLE_ORDER = [
    'project',
    'pdf_document',
    'business_info',
    'requirement',
    'requirement_proposal_image',
    'toc_item',
    'toc_requirement',       # 다대다 연결 테이블
    'req_type_rule',
    'project_attachment',
    'project_file_attachment',
    'proposal_analysis',
    'todo_item',
    'work_log',
    'vector_chunk',
]


def migrate(args):
    try:
        import psycopg2
        from psycopg2.extras import execute_values
    except ImportError:
        print('[오류] psycopg2-binary 가 설치되지 않았습니다.')
        print('       pip install psycopg2-binary')
        sys.exit(1)

    from sqlalchemy import create_engine, text as sa_text
    from models import db as _db

    # ── SQLite 연결 ──────────────────────────────────────────────────────────
    if not os.path.exists(args.sqlite):
        print(f'[오류] SQLite 파일을 찾을 수 없습니다: {args.sqlite}')
        sys.exit(1)

    print(f'[1/5] SQLite 연결: {args.sqlite}')
    src = sqlite3.connect(args.sqlite)
    src.row_factory = sqlite3.Row

    # ── PostgreSQL 연결 ──────────────────────────────────────────────────────
    pg_url = get_pg_url(args)
    print(f'[2/5] PostgreSQL 연결: {args.pg_host}:{args.pg_port}/{args.pg_db}')

    # 데이터베이스 자동 생성 시도 (postgres DB에 접속해서 CREATE DATABASE)
    try:
        admin_url = pg_url.replace(f'/{args.pg_db}', '/postgres')
        adm_conn = psycopg2.connect(admin_url)
        adm_conn.autocommit = True
        cur = adm_conn.cursor()
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (args.pg_db,))
        if not cur.fetchone():
            cur.execute(f'CREATE DATABASE "{args.pg_db}" ENCODING \'UTF8\'')
            print(f'       DB "{args.pg_db}" 생성 완료')
        else:
            print(f'       DB "{args.pg_db}" 이미 존재')
        adm_conn.close()
    except Exception as e:
        print(f'       DB 자동 생성 실패 (수동으로 생성해주세요): {e}')

    # ── SQLAlchemy로 테이블 생성 ─────────────────────────────────────────────
    from flask import Flask
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = pg_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    _db.init_app(app)

    with app.app_context():
        print('[3/5] PostgreSQL 테이블 생성 중...')
        if args.drop:
            print('      --drop 옵션: 기존 테이블 전부 삭제')
            _db.drop_all()
        _db.create_all()
        print('      테이블 생성 완료')

    # ── 데이터 이관 ──────────────────────────────────────────────────────────
    print('[4/5] 데이터 이관 시작...')

    if args.pg_password:
        pg_conn = psycopg2.connect(
            host=args.pg_host, port=int(args.pg_port),
            dbname=args.pg_db, user=args.pg_user, password=args.pg_password
        )
    else:
        pg_conn = psycopg2.connect(
            host=args.pg_host, port=int(args.pg_port),
            dbname=args.pg_db, user=args.pg_user
        )

    pg_cur = pg_conn.cursor()

    # FK 체크 비활성화 (순서가 맞더라도 안전하게)
    pg_cur.execute('SET session_replication_role = replica;')

    total_rows = 0
    for table in TABLE_ORDER:
        # SQLite에 해당 테이블이 있는지 확인
        src_cur = src.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
        )
        if not src_cur.fetchone():
            continue

        # SQLite 컬럼 목록
        sqlite_cols = [d[0] for d in src.execute(f'SELECT * FROM "{table}" LIMIT 0').description]

        # PostgreSQL 실제 컬럼 목록 (모델 기준, 구버전 컬럼 자동 제외)
        pg_cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position
        """, (table,))
        pg_cols_set = {r[0] for r in pg_cur.fetchall()}

        # 교집합만 복사 (SQLite에만 있는 구버전 컬럼은 건너뜀)
        cols = [c for c in sqlite_cols if c in pg_cols_set]
        skipped = [c for c in sqlite_cols if c not in pg_cols_set]
        if skipped:
            print(f'      {table}: 구버전 컬럼 무시 → {skipped}')

        col_idx = [sqlite_cols.index(c) for c in cols]
        col_list = ', '.join(f'"{c}"' for c in cols)

        rows = src.execute(f'SELECT * FROM "{table}"').fetchall()
        if not rows:
            print(f'      {table}: 0건 (건너뜀)')
            continue

        # 기존 데이터 삭제 후 재삽입 (--drop 없이도 재실행 가능하게)
        pg_cur.execute(f'DELETE FROM "{table}"')

        data = [tuple(row[i] for i in col_idx) for row in rows]
        execute_values(
            pg_cur,
            f'INSERT INTO "{table}" ({col_list}) VALUES %s',
            data,
            page_size=500
        )
        print(f'      {table}: {len(rows)}건 이관')
        total_rows += len(rows)

    # ── 시퀀스 리셋 (자동 증가 ID 충돌 방지) ────────────────────────────────
    seq_tables = [t for t in TABLE_ORDER if t != 'toc_requirement']
    for table in seq_tables:
        try:
            pg_cur.execute(f"""
                SELECT setval(
                    pg_get_serial_sequence('"{table}"', 'id'),
                    COALESCE((SELECT MAX(id) FROM "{table}"), 0) + 1,
                    false
                )
            """)
        except Exception:
            pass  # 시퀀스 없는 테이블 무시

    pg_conn.commit()
    pg_cur.close()
    pg_conn.close()
    src.close()

    print(f'[5/5] 완료! 총 {total_rows}건 이관')
    print()
    print('── 다음 단계 ─────────────────────────────────────────────────────')
    print('1. 원격 PC의 .env 파일에 DATABASE_URL 추가:')
    print(f'   DATABASE_URL={pg_url}')
    print('2. 앱 재시작: scripts\\update.ps1')
    print('──────────────────────────────────────────────────────────────────')


if __name__ == '__main__':
    migrate(parse_args())
