##定义会话、消息、Agent事件、审批、题库、知识库、作答、掌握度和推荐记录
from datetime import datetime, timezone
UTC = timezone.utc  # 手动定义 UTC
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def new_id() -> str:
    return str(uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Student(Base):
    __tablename__ = "students"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=new_id
    )
    external_id: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True
    )
    display_name: Mapped[str | None] = mapped_column(String(200))
    preferences: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class LearningSession(Base):
    __tablename__ = "learning_sessions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=new_id
    )
    student_id: Mapped[str] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), index=True
    )
    workspace_id: Mapped[str] = mapped_column(String(255))
    title: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(
        String(32), default="active", index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Turn(Base):
    __tablename__ = "turns"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=new_id
    )
    session_id: Mapped[str] = mapped_column(
        ForeignKey("learning_sessions.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(
        String(32), default="queued", index=True
    )
    model_id: Mapped[str | None] = mapped_column(String(255))
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "sequence",
            name="uq_messages_session_sequence",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=new_id
    )
    session_id: Mapped[str] = mapped_column(
        ForeignKey("learning_sessions.id", ondelete="CASCADE"), index=True
    )
    turn_id: Mapped[str | None] = mapped_column(
        ForeignKey("turns.id", ondelete="SET NULL"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(40))
    content: Mapped[str] = mapped_column(Text, default="")
    message_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class AgentEvent(Base):
    __tablename__ = "agent_events"
    __table_args__ = (
        UniqueConstraint(
            "turn_id",
            "sequence",
            name="uq_agent_events_turn_sequence",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    turn_id: Mapped[str] = mapped_column(
        ForeignKey("turns.id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    turn_id: Mapped[str] = mapped_column(
        ForeignKey("turns.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(40))
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    decision: Mapped[str | None] = mapped_column(String(40))
    feedback: Mapped[str | None] = mapped_column(Text)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True)
    )
    resolved_by: Mapped[str | None] = mapped_column(String(128))


class KnowledgePoint(Base):
    __tablename__ = "knowledge_points"
    __table_args__ = (
        UniqueConstraint(
            "subject",
            "code",
            name="uq_knowledge_points_subject_code",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=new_id
    )
    subject: Mapped[str] = mapped_column(String(100), index=True)
    code: Mapped[str] = mapped_column(String(200), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    prerequisites: Mapped[list[str]] = mapped_column(JSON, default=list)


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=new_id
    )
    subject: Mapped[str] = mapped_column(String(100), index=True)
    stem: Mapped[str] = mapped_column(Text)
    question_type: Mapped[str] = mapped_column(
        String(50), default="short_answer"
    )
    difficulty: Mapped[float] = mapped_column(
        Float, default=0.5, index=True
    )
    answer: Mapped[dict[str, Any]] = mapped_column(JSON)
    explanation: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(
        Boolean, default=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class QuestionKnowledgePoint(Base):
    __tablename__ = "question_knowledge_points"

    question_id: Mapped[str] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    knowledge_point_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="CASCADE"),
        primary_key=True,
    )
    weight: Mapped[float] = mapped_column(Float, default=1.0)


class LearningAttempt(Base):
    __tablename__ = "learning_attempts"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=new_id
    )
    student_id: Mapped[str] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), index=True
    )
    session_id: Mapped[str | None] = mapped_column(
        ForeignKey("learning_sessions.id", ondelete="SET NULL"),
        index=True,
    )
    turn_id: Mapped[str | None] = mapped_column(
        ForeignKey("turns.id", ondelete="SET NULL"), index=True
    )
    question_id: Mapped[str | None] = mapped_column(
        ForeignKey("questions.id", ondelete="SET NULL"), index=True
    )
    answer: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    score: Mapped[float] = mapped_column(Float)
    max_score: Mapped[float] = mapped_column(Float, default=1.0)
    correctness: Mapped[float] = mapped_column(Float)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class AttemptKnowledgePoint(Base):
    __tablename__ = "attempt_knowledge_points"

    attempt_id: Mapped[str] = mapped_column(
        ForeignKey("learning_attempts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    knowledge_point_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="CASCADE"),
        primary_key=True,
    )
    evidence_weight: Mapped[float] = mapped_column(
        Float, default=1.0
    )


class MasteryState(Base):
    __tablename__ = "mastery_states"

    student_id: Mapped[str] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"),
        primary_key=True,
    )
    knowledge_point_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="CASCADE"),
        primary_key=True,
    )
    mastery: Mapped[float] = mapped_column(
        Float, default=0.0, index=True
    )
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    attempts_count: Mapped[int] = mapped_column(Integer, default=0)
    last_practiced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=new_id
    )
    student_id: Mapped[str] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), index=True
    )
    knowledge_point_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="CASCADE"),
        index=True,
    )
    resource_type: Mapped[str] = mapped_column(String(50))
    resource_id: Mapped[str | None] = mapped_column(String(100))
    score: Mapped[float] = mapped_column(Float, index=True)
    reason: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(
        String(30), default="pending"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=new_id
    )
    subject: Mapped[str] = mapped_column(String(100), index=True)
    title: Mapped[str] = mapped_column(String(500))
    source_uri: Mapped[str] = mapped_column(String(1000))
    grade: Mapped[str | None] = mapped_column(
        String(50), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "ordinal",
            name="uq_knowledge_chunks_document_ordinal",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=new_id
    )
    document_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        index=True,
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict
    )


class Teacher(Base):
    __tablename__ = "teachers"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=new_id
    )
    username: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=new_id
    )
    teacher_id: Mapped[str] = mapped_column(
        ForeignKey("teachers.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    subject: Mapped[str] = mapped_column(String(100), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class CourseEnrollment(Base):
    __tablename__ = "course_enrollments"

    course_id: Mapped[str] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"),
        primary_key=True,
    )
    student_id: Mapped[str] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class Appeal(Base):
    __tablename__ = "appeals"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=new_id
    )
    attempt_id: Mapped[str] = mapped_column(
        ForeignKey("learning_attempts.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    student_id: Mapped[str] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), index=True
    )
    reason: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(
        String(20), default="pending", index=True
    )
    evidence_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict
    )
    requested_by: Mapped[str | None] = mapped_column(String(128))
    new_score: Mapped[float | None] = mapped_column(Float)
    teacher_note: Mapped[str | None] = mapped_column(Text)
    resolved_by: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )


class DailyTask(Base):
    """按日学习/复习任务。task_date 存 'YYYY-MM-DD'，避免时区换算歧义。

    kind='learn'  由学习路径(当前章节)推进算法生成；
    kind='review' 由艾宾浩斯间隔调度在到期日生成。
    """

    __tablename__ = "daily_tasks"
    __table_args__ = (
        UniqueConstraint(
            "student_id",
            "subject",
            "task_date",
            "kind",
            "question_id",
            name="uq_daily_task_slot",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=new_id
    )
    student_id: Mapped[str] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), index=True
    )
    subject: Mapped[str] = mapped_column(String(100), index=True)
    task_date: Mapped[str] = mapped_column(String(10), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    question_id: Mapped[str | None] = mapped_column(
        ForeignKey("questions.id", ondelete="SET NULL"), index=True
    )
    knowledge_point_id: Mapped[str | None] = mapped_column(
        ForeignKey("knowledge_points.id", ondelete="SET NULL"),
        index=True,
    )
    review_offset: Mapped[int | None] = mapped_column(Integer)
    reason: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(
        String(20), default="planned", index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class AttemptReview(Base):
    """一次代码题批改的产物：判定 + 详细题解/判分理由。

    reviewed_by: agent(LLM判) / self(学生对照题解自查) / teacher(教练复核)。
    detail 存结构化解题：思路、正确代码、复杂度、易错点、判分理由。
    """

    __tablename__ = "attempt_reviews"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=new_id
    )
    attempt_id: Mapped[str] = mapped_column(
        ForeignKey("learning_attempts.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    verdict: Mapped[str] = mapped_column(String(20))
    score: Mapped[float] = mapped_column(Float)
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    reviewed_by: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


Index("ix_messages_session_created", Message.session_id, Message.created_at)
Index("ix_events_turn_created", AgentEvent.turn_id, AgentEvent.created_at)
Index(
    "ix_questions_subject_difficulty",
    Question.subject,
    Question.difficulty,
)
