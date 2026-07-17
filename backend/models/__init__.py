"""数据模型 — SQLAlchemy ORM"""
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from database import Base


class Task(Base):
    """取证任务"""
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    keyword = Column(String(200), nullable=False, comment="搜索关键词")
    status = Column(
        String(20),
        nullable=False,
        default="pending",
        comment="pending|preparing|running|completed|failed|stopped",
    )
    device_id = Column(String(100), default="", comment="执行设备标识")
    max_videos = Column(Integer, default=5, comment="最大采集视频数，0=全量")
    hold_seconds = Column(Integer, default=240, comment="每条视频停留秒数")
    capture_method = Column(String(20), default="auto", comment="auto|adb|scrcpy")
    enable_asr = Column(Boolean, default=True, comment="是否启用 ASR 台词比对")
    skip_search = Column(Boolean, default=False, comment="是否跳过搜索直接从当前视频采集")
    collect_mode = Column(String(20), default="link_first", comment="link_first（二阶段采集）")
    phase = Column(Integer, default=1, comment="1=阶段一（链接采集） 2=阶段二（视频取证）")
    work_order_id = Column(Integer, nullable=True, index=True, comment="关联工单ID")
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    log_file_path = Column(String(500), default="")
    error_message = Column(Text, default="")

    evidence_records = relationship(
        "EvidenceRecord", back_populates="task", cascade="all, delete-orphan",
        primaryjoin="Task.id == EvidenceRecord.task_id",
        foreign_keys="[EvidenceRecord.task_id]",
    )


class EvidenceRecord(Base):
    """证据记录"""
    __tablename__ = "evidence_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, nullable=False, comment="关联任务ID")
    search_keyword = Column(String(200), default="")
    video_identifier = Column(String(64), default="", index=True)
    fingerprint = Column(String(64), default="")
    capture_timestamp = Column(String(30), default="")

    # 视频信息
    blogger_name = Column(String(200), default="")
    video_channel_id = Column(String(200), default="")
    video_channel_id_raw = Column(String(200), default="")
    video_channel_id_needs_review = Column(Boolean, default=False)
    title = Column(String(500), default="")
    video_link = Column(String(500), default="")
    publish_time = Column(String(30), default="")
    like_count = Column(String(20), default="")
    comment_count = Column(String(20), default="")
    share_count = Column(String(20), default="")
    favorite_count = Column(String(20), default="")

    # 博主信息
    profile_name = Column(String(200), default="")
    profile_account = Column(String(200), default="")
    subject_type = Column(String(20), default="")
    company_full_name = Column(String(200), default="")

    # 引流信息
    has_traffic_marker = Column(Boolean, default=False)
    traffic_marker_text = Column(String(200), default="")
    traffic_video_name = Column(String(200), default="")
    target_blogger_name = Column(String(200), default="")
    target_video_channel_id = Column(String(200), default="")
    target_video_channel_id_raw = Column(String(200), default="")
    target_company_name = Column(String(200), default="")
    target_company_verified_at = Column(String(30), default="")

    # 媒体信息
    recording_video_path = Column(String(500), default="")
    recording_audio_path = Column(String(500), default="")
    recording_duration_seconds = Column(Integer, default=0)
    has_audio = Column(Boolean, default=False)
    asr_text = Column(Text, default="")
    asr_model = Column(String(50), default="")

    # 剧本比对
    script_match_status = Column(String(20), default="pending")
    script_match_similarity = Column(Float, default=0.0, comment="整体相似度（覆盖率）")
    script_match_pinyin_score = Column(Float, default=0.0, comment="拼音相似度")
    script_match_char_score = Column(Float, default=0.0, comment="字符级相似度")
    script_match_segments_matched = Column(Integer, default=0, comment="匹配到的片段数")
    script_match_segments_total = Column(Integer, default=0, comment="总片段数")
    script_match_episode = Column(String(50), default="")
    script_match_scene = Column(String(200), default="")
    script_match_character = Column(String(100), default="", comment="说话人")
    script_match_location = Column(String(200), default="", comment="地点")
    script_match_script_text = Column(Text, default="", comment="匹配剧本原文（汇总）")
    script_match_segments_json = Column(Text, default="[]", comment="逐句匹配细节 JSON")

    # 侵权评分（ASR + 剧本比对后自动计算）
    infringement_score = Column(Float, default=0.0, comment="侵权置信度 0~1")
    infringement_level = Column(String(20), default="", comment="高度疑似/疑似/待观察/无")
    infringement_reason = Column(String(200), default="", comment="侵权判定原因，如：匹配到侵权线索")

    # 证据文件
    json_path = Column(String(500), default="")
    html_path = Column(String(500), default="")
    screenshots_json = Column(Text, default="[]")

    # 复核状态
    review_status = Column(String(20), default="")
    reviewer = Column(String(100), default="")
    review_notes = Column(Text, default="")
    reviewed_at = Column(DateTime, nullable=True)
    pushed_to_police = Column(Boolean, default=False, comment="是否已推送公安")
    pushed_at = Column(DateTime, nullable=True)
    pushed_by = Column(String(100), default="")
    pushed_to_company = Column(Boolean, default=False, comment="是否已推送公司核查池")
    pushed_to_company_at = Column(DateTime, nullable=True)
    pushed_to_company_by = Column(String(100), default="")
    created_at = Column(DateTime, default=datetime.now)

    task = relationship(
        "Task", back_populates="evidence_records",
        primaryjoin="EvidenceRecord.task_id == Task.id",
        foreign_keys="[EvidenceRecord.task_id]",
    )

    @property
    def screenshots(self) -> list[str]:
        import json
        try:
            return json.loads(self.screenshots_json) if self.screenshots_json else []
        except (json.JSONDecodeError, TypeError):
            return []

    @screenshots.setter
    def screenshots(self, value: list[str]):
        import json
        self.screenshots_json = json.dumps(value, ensure_ascii=False)


class ReviewLog(Base):
    """复核操作记录"""
    __tablename__ = "review_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    evidence_id = Column(Integer, nullable=False, comment="关联证据记录ID")
    previous_status = Column(String(20), default="")
    new_status = Column(String(20), nullable=False)
    reviewer = Column(String(100), default="")
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.now)


class AuthorCluster(Base):
    """博主聚合"""
    __tablename__ = "author_clusters"

    id = Column(Integer, primary_key=True, autoincrement=True)
    blogger_name = Column(String(200), default="")
    video_channel_id = Column(String(200), default="", unique=True, index=True)
    subject_type = Column(String(20), default="")
    company_full_name = Column(String(200), default="")
    total_videos = Column(Integer, default=0)
    infringement_count = Column(Integer, default=0)
    whitelist_count = Column(Integer, default=0)
    uncertain_count = Column(Integer, default=0)
    last_capture_time = Column(DateTime, nullable=True)
    last_updated = Column(DateTime, default=datetime.now)


class Device(Base):
    """设备信息"""
    __tablename__ = "devices"

    id = Column(String(100), primary_key=True, comment="ADB serial")
    name = Column(String(200), default="")
    status = Column(String(20), default="offline", comment="online|offline|busy")
    ip_address = Column(String(50), default="")
    connection_mode = Column(String(20), default="")
    screen_width = Column(Integer, default=0)
    screen_height = Column(Integer, default=0)
    last_checked_at = Column(DateTime, default=datetime.now)


class InfringementClue(Base):
    """侵权线索黑名单（从 Excel 导入，字段与 Excel 表头一一对应）"""
    __tablename__ = "infringement_clues"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_name = Column(String(200), default="", index=True, comment="账号名称")
    work_name = Column(String(500), default="", index=True, comment="侵权作品名称")
    our_work_name = Column(String(500), default="", comment="我方剧名")
    company_name = Column(String(200), default="", comment="账号主体公司")
    traffic_description = Column(Text, default="", comment="引流过程概述")
    video_link = Column(String(500), default="", comment="视频链接")
    created_at = Column(DateTime, default=datetime.now)


class LinkBatch(Base):
    """链接批次 — 一组链接的集合（来自一次采集、一次导入、或手动创建）"""
    __tablename__ = "link_batches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False, comment="批次名称")
    source = Column(String(20), default="collected", comment="collected|imported|manual")
    task_id = Column(Integer, nullable=True, comment="来源任务ID（采集时有值）")
    total_count = Column(Integer, default=0, comment="链接总数")
    created_at = Column(DateTime, default=datetime.now)


class VideoLink(Base):
    """视频链接暂存 — Phase 1 收集链接，Phase 2 消费"""
    __tablename__ = "video_links"

    id = Column(Integer, primary_key=True, autoincrement=True)
    batch_id = Column(Integer, nullable=True, index=True, comment="关联批次ID")
    task_id = Column(Integer, nullable=True, index=True, comment="关联任务ID")
    keyword = Column(String(200), default="")
    link_url = Column(String(500), default="")
    sort_order = Column(Integer, default=0, comment="Phase 1 采集序号")
    evidence_record_id = Column(Integer, nullable=True, comment="关联证据记录ID")
    created_at = Column(DateTime, default=datetime.now)
    collected_at = Column(DateTime, nullable=True)


class WorkOrder(Base):
    """公司端提交的取证工单"""
    __tablename__ = "work_orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_no = Column(String(32), unique=True, index=True, comment="工单号")
    drama_name = Column(String(200), nullable=False, comment="剧名/搜索关键词")
    description = Column(Text, default="", comment="诉求说明")
    priority = Column(Integer, default=0, comment="优先级，越大越优先")
    deadline = Column(DateTime, nullable=True)
    status = Column(
        String(20),
        default="draft",
        comment="draft|submitted|collecting|partial|completed|closed",
    )
    submitter = Column(String(100), default="")
    assigned_to = Column(String(100), default="")
    evidence_count = Column(Integer, default=0)
    company_pushed_count = Column(Integer, default=0, comment="已推送公司核查池条数")
    pushed_count = Column(Integer, default=0, comment="已推送公安条数")
    submitted_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class WorkOrderAttachment(Base):
    """工单附件（剧本、权属证明等）"""
    __tablename__ = "work_order_attachments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    work_order_id = Column(Integer, nullable=False, index=True)
    file_name = Column(String(255), default="")
    file_type = Column(String(50), default="", comment="script|license|clue|link|other")
    file_path = Column(String(500), default="")
    file_size = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now)


VideoLink.task = relationship(
    "Task", backref="video_links",
    primaryjoin="VideoLink.task_id == Task.id",
    foreign_keys="[VideoLink.task_id]",
)
VideoLink.batch = relationship(
    "LinkBatch", backref="video_links",
    primaryjoin="VideoLink.batch_id == LinkBatch.id",
    foreign_keys="[VideoLink.batch_id]",
)
