##它封装所有 SQLAlchemy 查询，API、Harness 和 MCP 不直接编写 SQL。
from __future__ import annotations

from datetime import datetime, timezone
# 手动定义 UTC（兼容 Python 3.10 及以下）
UTC = timezone.utc
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from eduharness.domain.events import HarnessEvent
from eduharness.domain.mastery import (
    mastery_confidence,
    recompute_mastery_from_evidence,
    update_mastery,
)
from eduharness.infrastructure.models import (
    AgentEvent,
    Appeal,
    ApprovalRequest,
    AttemptKnowledgePoint,
    AttemptReview,
    Course,
    CourseEnrollment,
    DailyTask,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgePoint,
    LearningAttempt,
    LearningSession,
    MasteryState,
    Message,
    Question,
    QuestionKnowledgePoint,
    Student,
    Teacher,
    Turn,
)


class RepositoryError(RuntimeError):
    pass


class NotFoundError(RepositoryError):
    pass


##中文学科别名归一化：学生用中文提问（如"数学"），
## 与数据库内部学科标识（如 "math"）做映射，避免检索落空。
_SUBJECT_ALIASES: dict[str, str] = {
    "数学": "math",
    "代数": "math",
    "几何": "math",
    "物理": "physics",
    "化学": "chemistry",
    "英语": "english",
    "英文": "english",
    "语文": "chinese",
    "生物": "biology",
    "历史": "history",
    "地理": "geography",
    "计算机": "computer_science",
    "信息技术": "computer_science",
    "经济": "economics",
    "科学": "science",
}


def _normalize_subject(subject: str | None) -> str | None:
    if not subject:
        return subject
    lowered = subject.strip().lower()
    return _SUBJECT_ALIASES.get(lowered, lowered)


class EduRepository:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self.session_factory = session_factory

    async def get_or_create_student(
        self,
        external_id: str,
        display_name: str | None = None,
    ) -> Student:
        async with self.session_factory() as db:
            result = await db.execute(
                select(Student).where(Student.external_id == external_id)
            )
            student = result.scalar_one_or_none()

            if student is not None:
                if display_name and student.display_name != display_name:
                    student.display_name = display_name
                    await db.commit()
                    await db.refresh(student)
                return student

            student = Student(
                external_id=external_id,
                display_name=display_name,
            )
            db.add(student)
            await db.commit()
            await db.refresh(student)
            return student

    async def create_learning_session(
        self,
        student_id: str,
        workspace_id: str,
        title: str | None = None,
    ) -> LearningSession:
        async with self.session_factory() as db:
            student = await db.get(Student, student_id)
            if student is None:
                raise NotFoundError("student not found")

            learning_session = LearningSession(
                student_id=student_id,
                workspace_id=workspace_id,
                title=title,
            )
            db.add(learning_session)
            await db.commit()
            await db.refresh(learning_session)
            return learning_session

    async def get_learning_session(
        self,
        session_id: str,
    ) -> LearningSession:
        async with self.session_factory() as db:
            learning_session = await db.get(
                LearningSession,
                session_id,
            )
            if learning_session is None:
                raise NotFoundError("learning session not found")
            return learning_session

    async def create_turn(
        self,
        session_id: str,
        model_id: str | None = None,
    ) -> Turn:
        async with self.session_factory() as db:
            learning_session = await db.get(
                LearningSession,
                session_id,
            )
            if learning_session is None:
                raise NotFoundError("learning session not found")

            turn = Turn(
                session_id=session_id,
                model_id=model_id,
                status="queued",
            )
            db.add(turn)
            await db.commit()
            await db.refresh(turn)
            return turn

    async def get_turn(self, turn_id: str) -> Turn:
        async with self.session_factory() as db:
            turn = await db.get(Turn, turn_id)
            if turn is None:
                raise NotFoundError("turn not found")
            return turn

    async def update_turn_status(
        self,
        turn_id: str,
        status: str,
        *,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        async with self.session_factory() as db:
            turn = await db.get(Turn, turn_id)
            if turn is None:
                raise NotFoundError("turn not found")

            turn.status = status

            if status == "running" and turn.started_at is None:
                turn.started_at = datetime.now(UTC)

            if status in {"completed", "failed", "cancelled"}:
                turn.completed_at = datetime.now(UTC)

            turn.error_code = error_code
            turn.error_message = error_message

            await db.commit()
    async def get_question_knowledge_points(
        self,
        question_id: str,
    ) -> list[dict[str, Any]]:
        async with self.session_factory() as db:
            result = await db.execute(
                select(
                    KnowledgePoint,
                    QuestionKnowledgePoint.weight,
                )
                .join(
                    QuestionKnowledgePoint,
                    QuestionKnowledgePoint.knowledge_point_id
                    == KnowledgePoint.id,
                )
                .where(
                    QuestionKnowledgePoint.question_id
                    == question_id
                )
            )

            return [
                {
                    "knowledge_point_id": point.id,
                    "code": point.code,
                    "name": point.name,
                    "weight": weight,
                }
                for point, weight in result.all()
            ]

    async def get_knowledge_point(
        self,
        knowledge_point_id: str,
    ) -> dict[str, Any]:
        async with self.session_factory() as db:
            point = await db.get(
                KnowledgePoint,
                knowledge_point_id,
            )
            if point is None:
                raise NotFoundError(
                    "knowledge point not found"
                )

            return {
                "id": point.id,
                "subject": point.subject,
                "code": point.code,
                "name": point.name,
                "description": point.description,
                "prerequisites": point.prerequisites,
            }

    async def get_knowledge_point_by_code(
        self,
        code: str,
    ) -> dict[str, Any]:
        async with self.session_factory() as db:
            result = await db.execute(
                select(KnowledgePoint).where(
                    KnowledgePoint.code == code
                )
            )
            point = result.scalar_one_or_none()

            if point is None:
                raise NotFoundError(
                    "knowledge point not found"
                )

            return {
                "id": point.id,
                "subject": point.subject,
                "code": point.code,
                "name": point.name,
                "description": point.description,
                "prerequisites": point.prerequisites,
            }

    async def get_knowledge_document(
        self,
        document_id: str,
    ) -> dict[str, Any]:
        async with self.session_factory() as db:
            document = await db.get(
                KnowledgeDocument,
                document_id,
            )
            if document is None:
                raise NotFoundError(
                    "knowledge document not found"
                )

            chunks_result = await db.execute(
                select(KnowledgeChunk)
                .where(
                    KnowledgeChunk.document_id
                    == document_id
                )
                .order_by(KnowledgeChunk.ordinal.asc())
            )

            return {
                "id": document.id,
                "title": document.title,
                "subject": document.subject,
                "grade": document.grade,
                "source_uri": document.source_uri,
                "updated_at": document.updated_at.isoformat(),
                "chunks": [
                    {
                        "chunk_id": chunk.id,
                        "ordinal": chunk.ordinal,
                        "text": chunk.content,
                        "metadata": chunk.metadata_json,
                    }
                    for chunk in chunks_result.scalars()
                ],
            }

    async def get_knowledge_chunks(
        self,
        chunk_ids: list[str],
    ) -> list[dict[str, Any]]:
        if not chunk_ids:
            return []

        async with self.session_factory() as db:
            result = await db.execute(
                select(KnowledgeChunk, KnowledgeDocument)
                .join(
                    KnowledgeDocument,
                    KnowledgeDocument.id
                    == KnowledgeChunk.document_id,
                )
                .where(KnowledgeChunk.id.in_(chunk_ids))
            )

            return [
                {
                    "chunk_id": chunk.id,
                    "document_id": document.id,
                    "title": document.title,
                    "text": chunk.content,
                    "source_uri": document.source_uri,
                    "updated_at": (
                        document.updated_at.isoformat()
                    ),
                }
                for chunk, document in result.all()
            ]

    async def append_message(
        self,
        *,
        session_id: str,
        turn_id: str | None,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> Message:
        async with self.session_factory() as db:
            sequence_result = await db.execute(
                select(func.coalesce(func.max(Message.sequence), 0)).where(
                    Message.session_id == session_id
                )
            )
            sequence = int(sequence_result.scalar_one()) + 1

            message = Message(
                session_id=session_id,
                turn_id=turn_id,
                sequence=sequence,
                role=role,
                content=content,
                message_metadata=metadata or {},
            )
            db.add(message)
            await db.commit()
            await db.refresh(message)
            return message

    async def list_messages(
        self,
        session_id: str,
    ) -> list[dict[str, Any]]:
        async with self.session_factory() as db:
            result = await db.execute(
                select(Message)
                .where(Message.session_id == session_id)
                .order_by(Message.sequence.asc())
            )

            return [
                {
                    "role": message.role,
                    "content": message.content,
                    **message.message_metadata,
                }
                for message in result.scalars()
            ]

    async def append_event(self, event: HarnessEvent) -> None:
        async with self.session_factory() as db:
            db.add(
                AgentEvent(
                    id=event.event_id,
                    turn_id=event.turn_id,
                    sequence=event.sequence,
                    event_type=event.type,
                    payload=event.to_dict(),
                    created_at=datetime.fromisoformat(event.created_at),
                )
            )
            await db.commit()

    async def list_events(
        self,
        turn_id: str,
        *,
        after_sequence: int = 0,
    ) -> list[HarnessEvent]:
        async with self.session_factory() as db:
            result = await db.execute(
                select(AgentEvent)
                .where(
                    AgentEvent.turn_id == turn_id,
                    AgentEvent.sequence > after_sequence,
                )
                .order_by(AgentEvent.sequence.asc())
            )

            return [
                HarnessEvent.from_dict(event.payload)
                for event in result.scalars()
            ]

    async def create_approval(
        self,
        *,
        approval_id: str,
        turn_id: str,
        request: dict[str, Any],
        expires_at: datetime,
    ) -> None:
        async with self.session_factory() as db:
            db.add(
                ApprovalRequest(
                    id=approval_id,
                    turn_id=turn_id,
                    kind=str(request.get("kind", "unknown")),
                    request_payload=request,
                    expires_at=expires_at,
                )
            )
            await db.commit()

    async def resolve_approval(
        self,
        approval_id: str,
        *,
        decision: str,
        feedback: str | None,
        resolved_by: str | None,
    ) -> None:
        async with self.session_factory() as db:
            approval = await db.get(ApprovalRequest, approval_id)
            if approval is None:
                raise NotFoundError("approval request not found")

            if approval.resolved_at is not None:
                raise RepositoryError("approval request already resolved")

            approval.decision = decision
            approval.feedback = feedback
            approval.resolved_by = resolved_by
            approval.resolved_at = datetime.now(UTC)
            await db.commit()

    async def search_questions(
        self,
        *,
        subject: str,
        knowledge_point_codes: list[str] | None = None,
        difficulty_min: float = 0.0,
        difficulty_max: float = 1.0,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        normalized_subject = _normalize_subject(subject)
        async with self.session_factory() as db:
            statement = (
                select(Question)
                .where(
                    Question.active.is_(True),
                    Question.subject == normalized_subject,
                    Question.difficulty >= difficulty_min,
                    Question.difficulty <= difficulty_max,
                )
                .order_by(Question.difficulty.asc())
                .limit(min(max(limit, 1), 50))
            )

            if knowledge_point_codes:
                ##知识点过滤按 code 或中文名匹配；若传入值均无匹配，
                ## 视为宽松条件，退回学科内检索，避免用户措辞不同导致结果为空。
                codes = list(knowledge_point_codes)
                points = (
                    await db.execute(
                        select(KnowledgePoint).where(
                            or_(
                                KnowledgePoint.code.in_(codes),
                                KnowledgePoint.name.in_(codes),
                            )
                        )
                    )
                ).scalars().all()
                matched_ids = {point.id for point in points}
                if matched_ids:
                    statement = (
                        statement.join(
                            QuestionKnowledgePoint,
                            QuestionKnowledgePoint.question_id == Question.id,
                        )
                        .where(
                            QuestionKnowledgePoint.knowledge_point_id.in_(
                                matched_ids
                            )
                        )
                        .distinct()
                    )

            result = await db.execute(statement)

            return [
                {
                    "id": question.id,
                    "subject": question.subject,
                    "stem": question.stem,
                    "question_type": question.question_type,
                    "difficulty": question.difficulty,
                }
                for question in result.scalars()
            ]

    async def get_question(
        self,
        question_id: str,
        *,
        include_answer: bool = False,
    ) -> dict[str, Any]:
        async with self.session_factory() as db:
            question = await db.get(Question, question_id)
            if question is None or not question.active:
                raise NotFoundError("question not found")

            payload: dict[str, Any] = {
                "id": question.id,
                "subject": question.subject,
                "stem": question.stem,
                "question_type": question.question_type,
                "difficulty": question.difficulty,
            }

            if include_answer:
                payload["answer"] = question.answer
                payload["explanation"] = question.explanation

            return payload

    async def grade_answer(
        self,
        question_id: str,
        answer: dict[str, Any],
    ) -> dict[str, Any]:
        async with self.session_factory() as db:
            question = await db.get(Question, question_id)
            if question is None:
                raise NotFoundError("question not found")

            expected = str(question.answer.get("value", "")).strip().lower()
            actual = str(answer.get("value", "")).strip().lower()
            correct = bool(expected) and actual == expected

            return {
                "question_id": question_id,
                "score": 1.0 if correct else 0.0,
                "max_score": 1.0,
                "correct": correct,
                "feedback": (
                    "回答正确。"
                    if correct
                    else "回答不正确，请检查解题步骤。"
                ),
                "explanation": question.explanation if correct else None,
            }

    async def record_attempt(
        self,
        *,
        student_id: str,
        session_id: str | None,
        turn_id: str | None,
        question_id: str | None,
        answer: dict[str, Any],
        score: float,
        max_score: float,
        knowledge_evidence: list[dict[str, Any]],
        duration_seconds: int | None = None,
    ) -> LearningAttempt:
        normalized_score = (
            max(0.0, min(score / max_score, 1.0))
            if max_score > 0
            else 0.0
        )

        async with self.session_factory() as db:
            attempt = LearningAttempt(
                student_id=student_id,
                session_id=session_id,
                turn_id=turn_id,
                question_id=question_id,
                answer=answer,
                score=score,
                max_score=max_score,
                correctness=normalized_score,
                duration_seconds=duration_seconds,
            )
            db.add(attempt)
            await db.flush()

            now = datetime.now(UTC)

            for evidence in knowledge_evidence:
                knowledge_point_id = evidence["knowledge_point_id"]
                weight = float(evidence.get("weight", 1.0))

                db.add(
                    AttemptKnowledgePoint(
                        attempt_id=attempt.id,
                        knowledge_point_id=knowledge_point_id,
                        evidence_weight=weight,
                    )
                )

                mastery = await db.get(
                    MasteryState,
                    {
                        "student_id": student_id,
                        "knowledge_point_id": knowledge_point_id,
                    },
                )

                if mastery is None:
                    mastery = MasteryState(
                        student_id=student_id,
                        knowledge_point_id=knowledge_point_id,
                        mastery=0.0,
                        confidence=0.0,
                        attempts_count=0,
                    )
                    db.add(mastery)

                mastery.attempts_count += 1
                mastery.mastery = update_mastery(
                    mastery.mastery,
                    normalized_score,
                    weight,
                )
                mastery.confidence = mastery_confidence(
                    mastery.attempts_count
                )
                mastery.last_practiced_at = now

            await db.commit()
            await db.refresh(attempt)
            return attempt

    async def list_mastery(
        self,
        student_id: str,
    ) -> list[dict[str, Any]]:
        async with self.session_factory() as db:
            result = await db.execute(
                select(MasteryState, KnowledgePoint)
                .join(
                    KnowledgePoint,
                    KnowledgePoint.id
                    == MasteryState.knowledge_point_id,
                )
                .where(MasteryState.student_id == student_id)
                .order_by(MasteryState.mastery.asc())
            )

            return [
                {
                    "knowledge_point_id": knowledge_point.id,
                    "code": knowledge_point.code,
                    "name": knowledge_point.name,
                    "subject": knowledge_point.subject,
                    "mastery": mastery.mastery,
                    "confidence": mastery.confidence,
                    "attempts_count": mastery.attempts_count,
                    "prerequisites": knowledge_point.prerequisites,
                    "last_practiced_at": (
                        mastery.last_practiced_at.isoformat()
                        if mastery.last_practiced_at
                        else None
                    ),
                }
                for mastery, knowledge_point in result.all()
            ]

    # ------------------------------------------------------------------
    # 教师 / 班级 / 课程
    # ------------------------------------------------------------------
    async def get_or_create_teacher(
        self,
        *,
        username: str,
        password_hash: str,
        display_name: str | None = None,
    ) -> Teacher:
        async with self.session_factory() as db:
            result = await db.execute(
                select(Teacher).where(Teacher.username == username)
            )
            teacher = result.scalar_one_or_none()
            if teacher is not None:
                return teacher

            teacher = Teacher(
                username=username,
                password_hash=password_hash,
                display_name=display_name,
            )
            db.add(teacher)
            await db.commit()
            await db.refresh(teacher)
            return teacher

    async def get_teacher_by_username(
        self,
        username: str,
    ) -> Teacher | None:
        async with self.session_factory() as db:
            result = await db.execute(
                select(Teacher).where(Teacher.username == username)
            )
            return result.scalar_one_or_none()

    async def create_course(
        self,
        *,
        teacher_id: str,
        name: str,
        subject: str,
        description: str = "",
    ) -> Course:
        async with self.session_factory() as db:
            course = Course(
                teacher_id=teacher_id,
                name=name,
                subject=_normalize_subject(subject),
                description=description,
            )
            db.add(course)
            await db.commit()
            await db.refresh(course)
            return course

    async def get_course(self, course_id: str) -> Course:
        async with self.session_factory() as db:
            course = await db.get(Course, course_id)
            if course is None:
                raise NotFoundError("course not found")
            return course

    async def list_teacher_courses(
        self,
        teacher_id: str,
    ) -> list[dict[str, Any]]:
        async with self.session_factory() as db:
            result = await db.execute(
                select(Course)
                .where(Course.teacher_id == teacher_id)
                .order_by(Course.created_at.asc())
            )

            return [
                {
                    "id": course.id,
                    "name": course.name,
                    "subject": course.subject,
                    "description": course.description,
                    "created_at": course.created_at.isoformat(),
                }
                for course in result.scalars()
            ]

    async def enroll_student(
        self,
        *,
        course_id: str,
        student_id: str,
    ) -> None:
        async with self.session_factory() as db:
            course = await db.get(Course, course_id)
            if course is None:
                raise NotFoundError("course not found")

            student = await db.get(Student, student_id)
            if student is None:
                raise NotFoundError("student not found")

            existing = await db.get(
                CourseEnrollment,
                {
                    "course_id": course_id,
                    "student_id": student_id,
                },
            )
            if existing is not None:
                return

            db.add(
                CourseEnrollment(
                    course_id=course_id,
                    student_id=student_id,
                )
            )
            await db.commit()

    async def list_course_students(
        self,
        course_id: str,
    ) -> list[dict[str, Any]]:
        async with self.session_factory() as db:
            result = await db.execute(
                select(Student)
                .join(
                    CourseEnrollment,
                    CourseEnrollment.student_id == Student.id,
                )
                .where(CourseEnrollment.course_id == course_id)
                .order_by(Student.created_at.asc())
            )

            return [
                {
                    "id": student.id,
                    "external_id": student.external_id,
                    "display_name": student.display_name,
                }
                for student in result.scalars()
            ]

    async def course_cockpit(
        self,
        course_id: str,
    ) -> dict[str, Any]:
        """把班级内所有学生的作答按知识点聚合成'驾驶舱'：
        每个知识点练习人数、总作答次数、平均掌握度、高风险学生数。
        """
        async with self.session_factory() as db:
            course = await db.get(Course, course_id)
            if course is None:
                raise NotFoundError("course not found")

            student_ids = list(
                (
                    await db.execute(
                        select(CourseEnrollment.student_id).where(
                            CourseEnrollment.course_id == course_id
                        )
                    )
                ).scalars()
            )

            buckets: dict[str, dict[str, Any]] = {}

            if student_ids:
                states = (
                    await db.execute(
                        select(MasteryState, KnowledgePoint)
                        .join(
                            KnowledgePoint,
                            KnowledgePoint.id
                            == MasteryState.knowledge_point_id,
                        )
                        .where(
                            MasteryState.student_id.in_(student_ids),
                            KnowledgePoint.subject == course.subject,
                        )
                    )
                ).all()

                for state, point in states:
                    bucket = buckets.setdefault(
                        point.id,
                        {
                            "knowledge_point_id": point.id,
                            "code": point.code,
                            "name": point.name,
                            "practiced_students": 0,
                            "attempts": 0,
                            "at_risk_students": 0,
                            "mastery_sum": 0.0,
                            "confidence_sum": 0.0,
                        },
                    )
                    bucket["practiced_students"] += 1
                    bucket["attempts"] += state.attempts_count
                    bucket["mastery_sum"] += state.mastery
                    bucket["confidence_sum"] += state.confidence
                    if (
                        state.mastery < 0.5
                        and state.attempts_count >= 1
                    ):
                        bucket["at_risk_students"] += 1

            rows = []
            for bucket in buckets.values():
                practiced = bucket["practiced_students"]
                rows.append(
                    {
                        "knowledge_point_id": bucket[
                            "knowledge_point_id"
                        ],
                        "code": bucket["code"],
                        "name": bucket["name"],
                        "practiced_students": practiced,
                        "attempts": bucket["attempts"],
                        "avg_mastery": round(
                            bucket["mastery_sum"] / practiced, 6
                        ),
                        "avg_confidence": round(
                            bucket["confidence_sum"] / practiced, 6
                        ),
                        "at_risk_students": bucket[
                            "at_risk_students"
                        ],
                    }
                )

            rows.sort(
                key=lambda row: (
                    row["avg_mastery"],
                    -row["attempts"],
                )
            )

            return {
                "course_id": course.id,
                "name": course.name,
                "subject": course.subject,
                "student_count": len(student_ids),
                "knowledge_points": rows,
            }

    # ------------------------------------------------------------------
    # 申诉与证据链
    # ------------------------------------------------------------------
    async def get_attempt_with_evidence(
        self,
        attempt_id: str,
    ) -> dict[str, Any]:
        """一次作答的完整证据快照：题干 + 作答 + 得分 + 引用的知识点。"""
        async with self.session_factory() as db:
            attempt = await db.get(LearningAttempt, attempt_id)
            if attempt is None:
                raise NotFoundError("attempt not found")

            question = (
                await db.get(Question, attempt.question_id)
                if attempt.question_id
                else None
            )

            kp_result = await db.execute(
                select(
                    KnowledgePoint,
                    AttemptKnowledgePoint.evidence_weight,
                )
                .join(
                    AttemptKnowledgePoint,
                    AttemptKnowledgePoint.knowledge_point_id
                    == KnowledgePoint.id,
                )
                .where(
                    AttemptKnowledgePoint.attempt_id == attempt_id
                )
            )

            return {
                "attempt_id": attempt.id,
                "student_id": attempt.student_id,
                "session_id": attempt.session_id,
                "turn_id": attempt.turn_id,
                "question_id": attempt.question_id,
                "question_stem": (
                    question.stem if question else None
                ),
                "answer": attempt.answer,
                "score": attempt.score,
                "max_score": attempt.max_score,
                "correctness": attempt.correctness,
                "duration_seconds": attempt.duration_seconds,
                "created_at": attempt.created_at.isoformat(),
                "knowledge_points": [
                    {
                        "knowledge_point_id": point.id,
                        "code": point.code,
                        "name": point.name,
                        "weight": weight,
                    }
                    for point, weight in kp_result.all()
                ],
            }

    async def knowledge_point_ids_for_attempt(
        self,
        attempt_id: str,
    ) -> list[str]:
        async with self.session_factory() as db:
            result = await db.execute(
                select(
                    AttemptKnowledgePoint.knowledge_point_id
                ).where(
                    AttemptKnowledgePoint.attempt_id == attempt_id
                )
            )
            return list(result.scalars())

    async def create_appeal(
        self,
        *,
        attempt_id: str,
        student_id: str,
        reason: str,
        requested_by: str | None,
    ) -> Appeal:
        snapshot = await self.get_attempt_with_evidence(attempt_id)
        if snapshot["student_id"] != student_id:
            raise NotFoundError("attempt not found")

        async with self.session_factory() as db:
            duplicate = await db.execute(
                select(Appeal.id).where(
                    Appeal.attempt_id == attempt_id
                )
            )
            if duplicate.scalar_one_or_none() is not None:
                raise RepositoryError("该作答已提交过申诉")

            appeal = Appeal(
                attempt_id=attempt_id,
                student_id=student_id,
                reason=reason,
                status="pending",
                evidence_snapshot=snapshot,
                requested_by=requested_by,
            )
            db.add(appeal)
            await db.commit()
            await db.refresh(appeal)
            return appeal

    async def get_appeal(self, appeal_id: str) -> Appeal:
        async with self.session_factory() as db:
            appeal = await db.get(Appeal, appeal_id)
            if appeal is None:
                raise NotFoundError("appeal not found")
            return appeal

    async def list_appeals(
        self,
        *,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        async with self.session_factory() as db:
            statement = select(Appeal)
            if status:
                statement = statement.where(Appeal.status == status)
            statement = statement.order_by(
                Appeal.created_at.desc()
            ).limit(min(max(limit, 1), 100))
            result = await db.execute(statement)

            appeals = list(result.scalars())
            student_ids = {a.student_id for a in appeals}
            names: dict[str, str | None] = {}
            if student_ids:
                students = (
                    await db.execute(
                        select(Student.id, Student.display_name).where(
                            Student.id.in_(student_ids)
                        )
                    )
                ).all()
                names = {sid: name for sid, name in students}

            return [
                {
                    "id": appeal.id,
                    "attempt_id": appeal.attempt_id,
                    "student_id": appeal.student_id,
                    "display_name": names.get(
                        appeal.student_id
                    ),
                    "reason": appeal.reason,
                    "status": appeal.status,
                    "evidence_snapshot": appeal.evidence_snapshot,
                    "new_score": appeal.new_score,
                    "teacher_note": appeal.teacher_note,
                    "created_at": appeal.created_at.isoformat(),
                    "resolved_at": (
                        appeal.resolved_at.isoformat()
                        if appeal.resolved_at
                        else None
                    ),
                }
                for appeal in appeals
            ]

    async def list_student_appeals(
        self,
        student_id: str,
    ) -> list[dict[str, Any]]:
        async with self.session_factory() as db:
            result = await db.execute(
                select(Appeal)
                .where(Appeal.student_id == student_id)
                .order_by(Appeal.created_at.desc())
            )
            return [
                {
                    "id": appeal.id,
                    "attempt_id": appeal.attempt_id,
                    "reason": appeal.reason,
                    "status": appeal.status,
                    "evidence_snapshot": appeal.evidence_snapshot,
                    "new_score": appeal.new_score,
                    "teacher_note": appeal.teacher_note,
                    "created_at": appeal.created_at.isoformat(),
                    "resolved_at": (
                        appeal.resolved_at.isoformat()
                        if appeal.resolved_at
                        else None
                    ),
                }
                for appeal in result.scalars()
            ]

    async def resolve_appeal(
        self,
        appeal_id: str,
        *,
        outcome: str,
        new_score: float | None,
        teacher_note: str | None,
        resolved_by: str | None,
    ) -> Appeal:
        if outcome not in {"sustained", "rejected"}:
            raise RepositoryError(f"非法复核结论: {outcome}")

        async with self.session_factory() as db:
            appeal = await db.get(Appeal, appeal_id)
            if appeal is None:
                raise NotFoundError("appeal not found")
            if appeal.status != "pending":
                raise RepositoryError("申诉已被复核，不可重复处理")

            appeal.status = outcome
            appeal.new_score = new_score
            appeal.teacher_note = teacher_note
            appeal.resolved_by = resolved_by
            appeal.resolved_at = datetime.now(UTC)
            await db.commit()
            await db.refresh(appeal)
            return appeal

    async def recompute_student_kp_mastery(
        self,
        student_id: str,
        knowledge_point_id: str,
    ) -> dict[str, Any]:
        """对该学生在某知识点上的全部作答证据做派生式重算。

        支持申诉改判：若某次作答存在 status=sustained 且带 new_score
        的申诉，重算时用新分数替代原分数——而不是在历史状态上打补丁，
        因此结果确定、可审计、可重放。
        """
        async with self.session_factory() as db:
            rows = (
                await db.execute(
                    select(
                        LearningAttempt,
                        AttemptKnowledgePoint.evidence_weight,
                    )
                    .join(
                        AttemptKnowledgePoint,
                        AttemptKnowledgePoint.attempt_id
                        == LearningAttempt.id,
                    )
                    .where(
                        LearningAttempt.student_id == student_id,
                        AttemptKnowledgePoint.knowledge_point_id
                        == knowledge_point_id,
                    )
                    .order_by(
                        LearningAttempt.created_at.asc(),
                        LearningAttempt.id.asc(),
                    )
                )
            ).all()

            corrections: dict[str, float] = {}
            attempt_ids = [attempt.id for attempt, _ in rows]
            if attempt_ids:
                cor = (
                    await db.execute(
                        select(
                            Appeal.attempt_id,
                            Appeal.new_score,
                        ).where(
                            Appeal.attempt_id.in_(attempt_ids),
                            Appeal.status == "sustained",
                            Appeal.new_score.is_not(None),
                        )
                    )
                ).all()
                corrections = dict(cor)

            evidence: list[tuple[float, float]] = []
            last_practiced_at = None
            for attempt, weight in rows:
                effective_score = corrections.get(
                    attempt.id, attempt.score
                )
                ratio = (
                    max(
                        0.0,
                        min(
                            effective_score / attempt.max_score,
                            1.0,
                        ),
                    )
                    if attempt.max_score > 0
                    else 0.0
                )
                evidence.append((ratio, float(weight)))
                last_practiced_at = attempt.created_at

            mastery, confidence, attempts_count = (
                recompute_mastery_from_evidence(evidence)
            )

            state = await db.get(
                MasteryState,
                {
                    "student_id": student_id,
                    "knowledge_point_id": knowledge_point_id,
                },
            )
            old_mastery = state.mastery if state else 0.0

            if state is None:
                state = MasteryState(
                    student_id=student_id,
                    knowledge_point_id=knowledge_point_id,
                    mastery=0.0,
                    confidence=0.0,
                    attempts_count=0,
                )
                db.add(state)

            state.mastery = mastery
            state.confidence = confidence
            state.attempts_count = attempts_count
            state.last_practiced_at = last_practiced_at
            state.updated_at = datetime.now(UTC)
            await db.commit()

            return {
                "knowledge_point_id": knowledge_point_id,
                "old_mastery": round(old_mastery, 6),
                "mastery": mastery,
                "confidence": confidence,
                "attempts_count": attempts_count,
            }

    # ------------------------------------------------------------------
    # 算法刷题课程(章节/题/作答统计)
    # ------------------------------------------------------------------
    async def list_knowledge_points(
        self,
        subject: str,
    ) -> list[dict[str, Any]]:
        async with self.session_factory() as db:
            result = await db.execute(
                select(KnowledgePoint)
                .where(KnowledgePoint.subject == subject)
                .order_by(KnowledgePoint.code.asc())
            )
            return [
                {
                    "id": point.id,
                    "code": point.code,
                    "name": point.name,
                    "description": point.description,
                    "prerequisites": point.prerequisites,
                }
                for point in result.scalars()
            ]

    async def list_questions_by_subject(
        self,
        subject: str,
    ) -> list[dict[str, Any]]:
        """学科下全部题目，附带关联知识点 code 与题号/标题元数据(不含判据)。"""
        async with self.session_factory() as db:
            result = await db.execute(
                select(Question)
                .where(Question.subject == subject)
                .order_by(Question.created_at.asc())
            )
            questions = list(result.scalars())
            question_ids = [q.id for q in questions]

            kp_rows: dict[str, list[dict[str, Any]]] = {}
            if question_ids:
                kp_result = await db.execute(
                    select(
                        QuestionKnowledgePoint.question_id,
                        KnowledgePoint.id,
                        KnowledgePoint.code,
                        QuestionKnowledgePoint.weight,
                    )
                    .join(
                        KnowledgePoint,
                        KnowledgePoint.id
                        == QuestionKnowledgePoint.knowledge_point_id,
                    )
                    .where(
                        QuestionKnowledgePoint.question_id.in_(
                            question_ids
                        )
                    )
                )
                for question_id, kp_id, code, weight in kp_result.all():
                    kp_rows.setdefault(question_id, []).append(
                        {
                            "knowledge_point_id": kp_id,
                            "code": code,
                            "weight": weight,
                        }
                    )

            return [
                {
                    "id": question.id,
                    "subject": question.subject,
                    "stem": question.stem,
                    "question_type": question.question_type,
                    "difficulty": question.difficulty,
                    "editorial": (
                        question.answer.get("reference", {})
                        if isinstance(question.answer, dict)
                        else {}
                    ),
                    "created_at": question.created_at.isoformat(),
                    "knowledge_points": kp_rows.get(question.id, []),
                }
                for question in questions
            ]

    async def student_question_stats(
        self,
        student_id: str,
        subject: str,
    ) -> dict[str, dict[str, Any]]:
        """学生在该学科每题的作答统计: 次数/是否AC/最近得分/首次AC日期。"""
        async with self.session_factory() as db:
            rows = (
                await db.execute(
                    select(
                        LearningAttempt.question_id,
                        LearningAttempt.correctness,
                        LearningAttempt.created_at,
                    )
                    .join(
                        Question,
                        Question.id == LearningAttempt.question_id,
                    )
                    .where(
                        LearningAttempt.student_id == student_id,
                        Question.subject == subject,
                        LearningAttempt.question_id.is_not(None),
                    )
                    .order_by(LearningAttempt.created_at.asc())
                )
            ).all()

        stats: dict[str, dict[str, Any]] = {}
        for question_id, correctness, created_at in rows:
            bucket = stats.setdefault(
                question_id,
                {
                    "attempts": 0,
                    "ac": False,
                    "last_correctness": 0.0,
                    "first_ac_at": None,
                },
            )
            bucket["attempts"] += 1
            bucket["last_correctness"] = correctness
            if correctness >= 1.0 and bucket["first_ac_at"] is None:
                bucket["first_ac_at"] = created_at.date().isoformat()
            if correctness >= 1.0:
                bucket["ac"] = True
        return stats

    async def student_mastery_by_subject(
        self,
        student_id: str,
        subject: str,
    ) -> list[dict[str, Any]]:
        async with self.session_factory() as db:
            result = await db.execute(
                select(MasteryState, KnowledgePoint)
                .join(
                    KnowledgePoint,
                    KnowledgePoint.id
                    == MasteryState.knowledge_point_id,
                )
                .where(
                    MasteryState.student_id == student_id,
                    KnowledgePoint.subject == subject,
                )
            )
            return [
                {
                    "knowledge_point_id": knowledge_point.id,
                    "code": knowledge_point.code,
                    "name": knowledge_point.name,
                    "mastery": mastery.mastery,
                    "confidence": mastery.confidence,
                    "attempts_count": mastery.attempts_count,
                }
                for mastery, knowledge_point in result.all()
            ]

    # ------------------------------------------------------------------
    # 按日学习/复习任务
    # ------------------------------------------------------------------
    async def upsert_daily_task(
        self,
        *,
        student_id: str,
        subject: str,
        task_date: str,
        kind: str,
        question_id: str | None,
        knowledge_point_id: str | None = None,
        review_offset: int | None = None,
        reason: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        async with self.session_factory() as db:
            existing = await db.execute(
                select(DailyTask).where(
                    DailyTask.student_id == student_id,
                    DailyTask.subject == subject,
                    DailyTask.task_date == task_date,
                    DailyTask.kind == kind,
                    DailyTask.question_id == question_id,
                )
            )
            task = existing.scalar_one_or_none()
            if task is not None:
                return {
                    "id": task.id,
                    "created": False,
                    "status": task.status,
                }

            task = DailyTask(
                student_id=student_id,
                subject=subject,
                task_date=task_date,
                kind=kind,
                question_id=question_id,
                knowledge_point_id=knowledge_point_id,
                review_offset=review_offset,
                reason=reason or {},
                status="planned",
            )
            db.add(task)
            await db.commit()
            await db.refresh(task)
            return {
                "id": task.id,
                "created": True,
                "status": task.status,
            }

    async def list_daily_tasks(
        self,
        student_id: str,
        subject: str,
        *,
        task_date: str | None = None,
        kind: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        async with self.session_factory() as db:
            statement = select(DailyTask).where(
                DailyTask.student_id == student_id,
                DailyTask.subject == subject,
            )
            if task_date:
                statement = statement.where(
                    DailyTask.task_date == task_date
                )
            if kind:
                statement = statement.where(DailyTask.kind == kind)
            if status:
                statement = statement.where(DailyTask.status == status)
            statement = statement.order_by(
                DailyTask.task_date.desc(),
                DailyTask.kind.asc(),
            )
            tasks = list((await db.execute(statement)).scalars())

            question_ids = {
                task.question_id
                for task in tasks
                if task.question_id
            }
            questions: dict[str, dict[str, Any]] = {}
            if question_ids:
                qrows = await db.execute(
                    select(Question).where(
                        Question.id.in_(question_ids)
                    )
                )
                for q in qrows.scalars():
                    questions[q.id] = {
                        "id": q.id,
                        "stem": q.stem,
                        "difficulty": q.difficulty,
                        "editorial": (
                            q.answer.get("reference", {})
                            if isinstance(q.answer, dict)
                            else {}
                        ),
                    }

            return [
                {
                    "id": task.id,
                    "subject": task.subject,
                    "task_date": task.task_date,
                    "kind": task.kind,
                    "review_offset": task.review_offset,
                    "reason": task.reason,
                    "status": task.status,
                    "question": questions.get(task.question_id),
                    "question_id": task.question_id,
                    "knowledge_point_id": task.knowledge_point_id,
                }
                for task in tasks
            ]

    async def set_daily_task_status(
        self,
        task_id: str,
        status: str,
    ) -> None:
        if status not in {"planned", "done", "skipped"}:
            raise RepositoryError(f"非法任务状态: {status}")
        async with self.session_factory() as db:
            task = await db.get(DailyTask, task_id)
            if task is None:
                raise NotFoundError("daily task not found")
            task.status = status
            await db.commit()

    async def last_done_review_dates(
        self,
        student_id: str,
        subject: str,
        question_ids: list[str],
    ) -> dict[str, str]:
        """每题最近一次已完成 review 的日期(task_date, ISO str)。"""
        if not question_ids:
            return {}
        async with self.session_factory() as db:
            rows = (
                await db.execute(
                    select(
                        DailyTask.question_id,
                        DailyTask.task_date,
                    )
                    .where(
                        DailyTask.student_id == student_id,
                        DailyTask.subject == subject,
                        DailyTask.kind == "review",
                        DailyTask.status == "done",
                        DailyTask.question_id.in_(question_ids),
                    )
                )
            ).all()
        latest: dict[str, str] = {}
        for question_id, task_date in rows:
            if question_id is None:
                continue
            current = latest.get(question_id)
            if current is None or task_date > current:
                latest[question_id] = task_date
        return latest

    # ------------------------------------------------------------------
    # 代码批改记录
    # ------------------------------------------------------------------
    async def create_attempt_review(
        self,
        *,
        attempt_id: str,
        verdict: str,
        score: float,
        detail: dict[str, Any],
        reviewed_by: str,
    ) -> dict[str, Any]:
        async with self.session_factory() as db:
            review = AttemptReview(
                attempt_id=attempt_id,
                verdict=verdict,
                score=score,
                detail=detail,
                reviewed_by=reviewed_by,
            )
            db.add(review)
            await db.commit()
            await db.refresh(review)
            return {
                "id": review.id,
                "attempt_id": review.attempt_id,
                "verdict": review.verdict,
                "score": review.score,
                "reviewed_by": review.reviewed_by,
            }

    async def get_attempt_review(
        self,
        attempt_id: str,
    ) -> dict[str, Any] | None:
        async with self.session_factory() as db:
            result = await db.execute(
                select(AttemptReview).where(
                    AttemptReview.attempt_id == attempt_id
                )
            )
            review = result.scalar_one_or_none()
            if review is None:
                return None
            return {
                "id": review.id,
                "attempt_id": review.attempt_id,
                "verdict": review.verdict,
                "score": review.score,
                "detail": review.detail,
                "reviewed_by": review.reviewed_by,
            }

    async def get_document_by_title(
        self,
        subject: str,
        title: str,
    ) -> dict[str, Any] | None:
        async with self.session_factory() as db:
            result = await db.execute(
                select(KnowledgeDocument).where(
                    KnowledgeDocument.subject == subject,
                    KnowledgeDocument.title == title,
                )
            )
            document = result.scalar_one_or_none()
            if document is None:
                return None

            chunks_result = await db.execute(
                select(KnowledgeChunk)
                .where(
                    KnowledgeChunk.document_id == document.id
                )
                .order_by(KnowledgeChunk.ordinal.asc())
            )
            return {
                "document_id": document.id,
                "title": document.title,
                "subject": document.subject,
                "source_uri": document.source_uri,
                "chunks": [
                    {
                        "chunk_id": chunk.id,
                        "ordinal": chunk.ordinal,
                        "text": chunk.content,
                    }
                    for chunk in chunks_result.scalars()
                ],
            }

    async def get_chapter_knowledge(
        self,
        chapter_code: str,
        subject: str = "leetcode",
    ) -> dict[str, Any] | None:
        return await self.get_document_by_title(
            subject,
            f"leetcode-chapter-{chapter_code}",
        )

    async def get_question_solution(
        self,
        question_id: str,
        subject: str = "leetcode",
    ) -> dict[str, Any] | None:
        return await self.get_document_by_title(
            subject,
            f"leetcode-solution-{question_id}",
        )

    async def search_knowledge(
        self,
        *,
        query: str,
        subject: str | None = None,
        grade: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        async with self.session_factory() as db:
            pattern = f"%{query}%"

            statement = (
                select(KnowledgeChunk, KnowledgeDocument)
                .join(
                    KnowledgeDocument,
                    KnowledgeDocument.id
                    == KnowledgeChunk.document_id,
                )
                .where(
                    or_(
                        KnowledgeChunk.content.ilike(pattern),
                        KnowledgeDocument.title.ilike(pattern),
                    )
                )
            )

            if subject:
                statement = statement.where(
                    KnowledgeDocument.subject
                    == _normalize_subject(subject)
                )

            if grade:
                statement = statement.where(
                    KnowledgeDocument.grade == grade
                )

            statement = statement.limit(min(max(limit, 1), 50))
            result = await db.execute(statement)

            return [
                {
                    "chunk_id": chunk.id,
                    "document_id": document.id,
                    "title": document.title,
                    "subject": document.subject,
                    "grade": document.grade,
                    "text": chunk.content,
                    "source_uri": document.source_uri,
                    "metadata": chunk.metadata_json,
                    
                }
                for chunk, document in result.all()
            ]