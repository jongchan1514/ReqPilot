from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

toc_requirement = db.Table(
    'toc_requirement',
    db.Column('toc_id', db.Integer, db.ForeignKey('toc_item.id', ondelete='CASCADE'), primary_key=True),
    db.Column('requirement_id', db.Integer, db.ForeignKey('requirement.id', ondelete='CASCADE'), primary_key=True)
)


class Project(db.Model):
    __tablename__ = 'project'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(500), nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    pdfs = db.relationship('PdfDocument', back_populates='project', cascade='all, delete-orphan')
    attachments = db.relationship('ProjectAttachment', back_populates='project', cascade='all, delete-orphan')
    file_attachments = db.relationship('ProjectFileAttachment', back_populates='project',
                                       cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description or '',
            'pdf_count': len(self.pdfs),
            'req_count': sum(len(p.requirements) for p in self.pdfs),
            'created_at': self.created_at.strftime('%Y-%m-%d') if self.created_at else '',
        }


class PdfDocument(db.Model):
    __tablename__ = 'pdf_document'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id', ondelete='CASCADE'), nullable=False)
    original_name = db.Column(db.String(500), nullable=False)
    saved_filename = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    project = db.relationship('Project', back_populates='pdfs')
    requirements = db.relationship('Requirement', back_populates='pdf', cascade='all, delete-orphan')
    toc_items = db.relationship('TOCItem', back_populates='pdf', cascade='all, delete-orphan')
    business_info = db.relationship('BusinessInfo', back_populates='pdf',
                                    cascade='all, delete-orphan', uselist=False)

    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'original_name': self.original_name,
            'has_file': bool(self.saved_filename),
            'req_count': len(self.requirements),
            'toc_count': len(self.toc_items),
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M') if self.created_at else '',
        }


class BusinessInfo(db.Model):
    """사업 개요 정보 — PDF 1개당 1개"""
    __tablename__ = 'business_info'
    id = db.Column(db.Integer, primary_key=True)
    pdf_id = db.Column(db.Integer, db.ForeignKey('pdf_document.id', ondelete='CASCADE'),
                       nullable=False, unique=True)
    business_name = db.Column(db.String(500))   # 사업명
    business_cost = db.Column(db.String(200))   # 사업비
    business_period = db.Column(db.String(200)) # 사업 기간
    client = db.Column(db.String(500))          # 발주기관
    contractor = db.Column(db.String(500))      # 수행기관
    overview = db.Column(db.Text)               # 사업 개요
    extras = db.Column(db.Text)                 # JSON — 추가 추출 필드
    pdf = db.relationship('PdfDocument', back_populates='business_info')

    def to_dict(self):
        import json
        extras = {}
        if self.extras:
            try:
                extras = json.loads(self.extras)
            except Exception:
                pass
        return {
            'id': self.id,
            'pdf_id': self.pdf_id,
            'business_name': self.business_name or '',
            'business_cost': self.business_cost or '',
            'business_period': self.business_period or '',
            'client': self.client or '',
            'contractor': self.contractor or '',
            'overview': self.overview or '',
            'extras': extras,
        }


class Requirement(db.Model):
    __tablename__ = 'requirement'
    id = db.Column(db.Integer, primary_key=True)
    pdf_id = db.Column(db.Integer, db.ForeignKey('pdf_document.id', ondelete='CASCADE'), nullable=False)
    req_id = db.Column(db.String(200), nullable=False)
    req_name = db.Column(db.String(1000), nullable=False)
    detail = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    pdf = db.relationship('PdfDocument', back_populates='requirements')
    proposal_images = db.relationship('RequirementProposalImage', back_populates='requirement',
                                      cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'pdf_id': self.pdf_id,
            'req_id': self.req_id,
            'req_name': self.req_name,
            'detail': self.detail or '',
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M') if self.created_at else '',
        }


class RequirementProposalImage(db.Model):
    """요구사항 기반 제안 장표 이미지 생성 이력"""
    __tablename__ = 'requirement_proposal_image'
    id = db.Column(db.Integer, primary_key=True)
    requirement_id = db.Column(db.Integer, db.ForeignKey('requirement.id', ondelete='CASCADE'), nullable=False)
    orientation = db.Column(db.String(20), default='landscape')   # landscape/portrait
    template_type = db.Column(db.String(50), default='auto')
    tone = db.Column(db.String(50), default='public')
    title = db.Column(db.String(500))
    saved_filename = db.Column(db.String(500), nullable=False)
    payload_json = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    requirement = db.relationship('Requirement', back_populates='proposal_images')

    def to_dict(self):
        return {
            'id': self.id,
            'requirement_id': self.requirement_id,
            'orientation': self.orientation or 'landscape',
            'template_type': self.template_type or 'auto',
            'tone': self.tone or 'public',
            'title': self.title or '',
            'image_url': f'/api/proposal-images/{self.id}/file',
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M') if self.created_at else '',
        }


class ReqTypeRule(db.Model):
    """요구사항 타입 자동 감지 규칙 (prefix → 라벨/색상)"""
    __tablename__ = 'req_type_rule'
    id = db.Column(db.Integer, primary_key=True)
    prefix = db.Column(db.String(50), nullable=False)
    label = db.Column(db.String(100), nullable=False)
    bg_color = db.Column(db.String(20), default='#dbeafe')
    text_color = db.Column(db.String(20), default='#1d4ed8')
    order_index = db.Column(db.Integer, default=0)

    def to_dict(self):
        return {
            'id': self.id,
            'prefix': self.prefix,
            'label': self.label,
            'bg_color': self.bg_color,
            'text_color': self.text_color,
            'order_index': self.order_index,
        }


ATTACHMENT_SLOTS = {
    'presentation_original': ('발표자료', '원본'),
    'presentation_copy':     ('발표자료', '사본'),
    'proposal_original':     ('제안서',   '원본'),
    'proposal_copy':         ('제안서',   '사본'),
}

PROJECT_FILE_CATEGORIES = {
    'misc':      ('기타 파일함', '넣고 싶은 파일을 자유롭게 보관'),
    'reference': ('참고자료/예상질문', '예상질문, 답변 초안, 보충자료 보관'),
}


class ProjectAttachment(db.Model):
    """프로젝트별 4개 고정 슬롯 첨부파일 (발표자료/제안서 × 원본/사본)"""
    __tablename__ = 'project_attachment'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id', ondelete='CASCADE'), nullable=False)
    slot = db.Column(db.String(50), nullable=False)       # e.g. 'presentation_original'
    original_name = db.Column(db.String(500), nullable=False)
    saved_filename = db.Column(db.String(500), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('project_id', 'slot', name='uq_project_slot'),)
    project = db.relationship('Project', back_populates='attachments')

    def to_dict(self):
        label = ATTACHMENT_SLOTS.get(self.slot, (self.slot, ''))
        return {
            'id': self.id,
            'project_id': self.project_id,
            'slot': self.slot,
            'label': f'{label[0]} {label[1]}',
            'original_name': self.original_name,
            'uploaded_at': self.uploaded_at.strftime('%Y-%m-%d %H:%M') if self.uploaded_at else '',
        }


class ProjectFileAttachment(db.Model):
    """프로젝트별 자유 파일함 첨부파일 (기타 / 참고자료·예상질문)."""
    __tablename__ = 'project_file_attachment'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id', ondelete='CASCADE'), nullable=False)
    category = db.Column(db.String(30), nullable=False)
    original_name = db.Column(db.String(500), nullable=False)
    saved_filename = db.Column(db.String(500), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    project = db.relationship('Project', back_populates='file_attachments')

    def to_dict(self):
        label, description = PROJECT_FILE_CATEGORIES.get(self.category, (self.category, ''))
        return {
            'id': self.id,
            'project_id': self.project_id,
            'category': self.category,
            'category_label': label,
            'category_description': description,
            'original_name': self.original_name,
            'uploaded_at': self.uploaded_at.strftime('%Y-%m-%d %H:%M') if self.uploaded_at else '',
        }


class ProposalAnalysis(db.Model):
    """제안서 ↔ RFP 매칭 분석 이력"""
    __tablename__ = 'proposal_analysis'
    id            = db.Column(db.Integer, primary_key=True)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)
    rfp_name      = db.Column(db.String(500), nullable=False)
    proposal_name = db.Column(db.String(500), nullable=False)
    results_json  = db.Column(db.Text, nullable=False)   # 매칭 결과 JSON 배열
    summary_json  = db.Column(db.Text)                   # AI 액션 플랜 JSON
    total_count   = db.Column(db.Integer, default=0)
    full_count    = db.Column(db.Integer, default=0)
    partial_count = db.Column(db.Integer, default=0)
    missing_count = db.Column(db.Integer, default=0)

    def to_dict(self):
        import json as _json
        return {
            'id':            self.id,
            'created_at':    self.created_at.strftime('%Y-%m-%d %H:%M') if self.created_at else '',
            'rfp_name':      self.rfp_name,
            'proposal_name': self.proposal_name,
            'total_count':   self.total_count,
            'full_count':    self.full_count,
            'partial_count': self.partial_count,
            'missing_count': self.missing_count,
        }

    def to_full_dict(self):
        import json as _json
        d = self.to_dict()
        d['results'] = _json.loads(self.results_json) if self.results_json else []
        d['summary'] = _json.loads(self.summary_json) if self.summary_json else {}
        return d


class TodoItem(db.Model):
    __tablename__ = 'todo_item'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(500), nullable=False)
    description = db.Column(db.Text)
    priority = db.Column(db.String(20), default='보통')   # 긴급/보통/낮음
    status = db.Column(db.String(20), default='할일')     # 할일/진행중/완료
    start_date = db.Column(db.String(20))
    due_date = db.Column(db.String(20))
    order_index = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description or '',
            'priority': self.priority or '보통',
            'status': self.status or '할일',
            'start_date': self.start_date or '',
            'due_date': self.due_date or '',
            'order_index': self.order_index,
            'created_at': self.created_at.strftime('%Y-%m-%d') if self.created_at else '',
        }


class WorkLog(db.Model):
    __tablename__ = 'work_log'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(500), nullable=False)
    content = db.Column(db.Text)   # Quill HTML
    tags = db.Column(db.Text)      # JSON array
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self, include_content=False):
        import json as _json
        d = {
            'id': self.id,
            'title': self.title,
            'tags': _json.loads(self.tags) if self.tags else [],
            'created_at': self.created_at.strftime('%Y-%m-%d') if self.created_at else '',
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M') if self.updated_at else '',
        }
        if include_content:
            d['content'] = self.content or ''
        return d


class VectorChunk(db.Model):
    """RAG용 벡터 청크 저장소"""
    __tablename__ = 'vector_chunk'
    id          = db.Column(db.Integer, primary_key=True)
    source_type = db.Column(db.String(50), nullable=False)   # requirement/toc/worklog/todo/business_info
    source_id   = db.Column(db.Integer, nullable=False)
    chunk_text  = db.Column(db.Text, nullable=False)
    source_url  = db.Column(db.String(500))                  # 바로가기 URL
    source_label= db.Column(db.String(500))                  # 표시 제목
    embedding   = db.Column(db.Text)                         # JSON float array
    updated_at  = db.Column(db.DateTime)
    source_date = db.Column(db.DateTime)                     # 아이템 생성일/마감일 (날짜 필터용)
    __table_args__ = (db.UniqueConstraint('source_type', 'source_id', name='uq_vector_chunk_src'),)

    def to_dict(self):
        return {
            'id': self.id,
            'source_type': self.source_type,
            'source_id': self.source_id,
            'chunk_text': self.chunk_text,
            'source_url': self.source_url or '',
            'source_label': self.source_label or '',
        }


class TOCItem(db.Model):
    __tablename__ = 'toc_item'
    id = db.Column(db.Integer, primary_key=True)
    pdf_id = db.Column(db.Integer, db.ForeignKey('pdf_document.id', ondelete='CASCADE'), nullable=False)
    depth1 = db.Column(db.String(1000))
    depth2 = db.Column(db.String(1000))
    depth3 = db.Column(db.String(1000))
    remarks = db.Column(db.Text)
    work_status = db.Column(db.String(50), default='신규')
    page_number = db.Column(db.String(50))
    order_index = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    pdf = db.relationship('PdfDocument', back_populates='toc_items')
    requirements = db.relationship('Requirement', secondary=toc_requirement, lazy='subquery')

    def to_dict(self):
        return {
            'id': self.id,
            'pdf_id': self.pdf_id,
            'depth1': self.depth1 or '',
            'depth2': self.depth2 or '',
            'depth3': self.depth3 or '',
            'remarks': self.remarks or '',
            'work_status': self.work_status or '신규',
            'page_number': self.page_number or '',
            'order_index': self.order_index,
            'requirement_ids': [r.id for r in self.requirements],
            'requirement_labels': [r.req_id for r in self.requirements],
        }
