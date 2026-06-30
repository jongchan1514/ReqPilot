# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

block_cipher = None

# ── 동적 로딩이 많은 패키지는 전체 수집 ──────────────────────────────────────
torch_d,  torch_b,  torch_h  = collect_all('torch')
tf_d,     tf_b,     tf_h     = collect_all('transformers')
st_d,     st_b,     st_h     = collect_all('sentence_transformers')
genai_d,  genai_b,  genai_h  = collect_all('google.generativeai')
tqdm_d,   tqdm_b,   tqdm_h   = collect_all('tqdm')

datas = [
    ('templates', 'templates'),   # Flask 템플릿
]
datas += torch_d + tf_d + st_d + genai_d + tqdm_d
datas += collect_data_files('tokenizers')
datas += collect_data_files('huggingface_hub')
datas += collect_data_files('filelock')

binaries = torch_b + tf_b + st_b + genai_b + tqdm_b

hiddenimports = [
    # SQLAlchemy 방언
    'sqlalchemy.dialects.sqlite',
    'sqlalchemy.dialects.sqlite.pysqlite',
    'sqlalchemy.dialects.postgresql',
    'sqlalchemy.dialects.postgresql.psycopg2',
    'sqlalchemy.orm.events',
    'sqlalchemy.sql.visitors',
    # Flask
    'flask_sqlalchemy',
    'jinja2',
    'jinja2.ext',
    'markupsafe',
    'werkzeug',
    'werkzeug.serving',
    'werkzeug.middleware.proxy_fix',
    # psycopg2
    'psycopg2',
    'psycopg2.extensions',
    'psycopg2._psycopg',
    # PIL
    'PIL._imaging',
    'PIL.Image',
    'PIL.ImageFilter',
    # numpy / scipy
    'numpy.core._methods',
    'numpy.lib.format',
    # openpyxl
    'openpyxl',
    'openpyxl.styles',
    'openpyxl.utils',
    # google
    'google.auth',
    'google.auth.transport',
    'google.auth.transport.requests',
    'google.api_core',
    'google.protobuf',
    'proto',
    # grpc
    'grpc',
    'grpc._channel',
]
hiddenimports += torch_h + tf_h + st_h + genai_h + tqdm_h
hiddenimports += collect_submodules('google.api_core')
hiddenimports += collect_submodules('google.auth')
hiddenimports += collect_submodules('grpc')

a = Analysis(
    ['app.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter', 'matplotlib', 'IPython', 'jupyter',
        'notebook', 'cv2', 'PyQt5', 'wx',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='reqpilot',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,   # Rocky 8에서 upx 미설치 시 오류 방지
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='reqpilot',
)
