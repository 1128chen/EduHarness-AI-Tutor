"""申诉复核 + 派生式掌握度重算的仓储层测试。"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from eduharness.infrastructure.database import Database
from eduharness.infrastructure.models import (
    KnowledgePoint,
    LearningAttempt,
    Question,
    QuestionKnowledgePoint,
)
from eduharness.infrastructure.repositories import (
    EduRepository,
    NotFoundError,
    RepositoryError,
)


async def _make_question(db: Database) -> dict[str, str]:
    """建一个知识点 + 一道题，返回 {kp_id, question_id}。"""
    async with db.session_factory() as s:
        kp = KnowledgePoint(
            subject="python",
            code="python.test.func",
            name="函数定义",
            description="def",
            prerequisites=[],
        )
        s.add(kp)
        await s.flush()
        q = Question(
            subject="python",
            stem="定义函数的关键字是?",
            question_type="short_answer",
            difficulty=0.4,
            answer={"value": "def"},
            explanation="def 关键字",
        )
        s.add(q)
        await s.flush()
        s.add(
            QuestionKnowledgePoint(
                question_id=q.id,
                knowledge_point_id=kp.id,
                weight=1.0,
            )
        )
        await s.commit()
        return {"kp_id": kp.id, "question_id": q.id}


@pytest.mark.asyncio
async def test_appeal_sustain_recomputes_mastery(tmp_path) -> None:
    database = Database(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    await database.create_schema()
    repository = EduRepository(database.session_factory)

    ids = await _make_question(database)
    student = await repository.get_or_create_student("s1", "小明")

    # 三次作答：错、对、错
    for answer, score in [
        ({"value": "class"}, 0.0),
        ({"value": "def"}, 1.0),
        ({"value": "func"}, 0.0),
    ]:
        await repository.record_attempt(
            student_id=student.id,
            session_id=None,
            turn_id=None,
            question_id=ids["question_id"],
            answer=answer,
            score=score,
            max_score=1.0,
            knowledge_evidence=[
                {
                    "knowledge_point_id": ids["kp_id"],
                    "weight": 1.0,
                }
            ],
        )

    before = await repository.list_mastery(student.id)
    assert len(before) == 1
    incremental = before[0]["mastery"]

    # 派生重算与增量结果一致
    recomputed = await repository.recompute_student_kp_mastery(
        student.id, ids["kp_id"]
    )
    assert recomputed["mastery"] == incremental
    assert recomputed["attempts_count"] == 3

    # 取第一次（答错）的作答发起申诉
    async with database.session_factory() as s:
        first_attempt = (
            await s.execute(
                select(LearningAttempt)
                .where(LearningAttempt.student_id == student.id)
                .order_by(LearningAttempt.created_at.asc())
            )
        ).scalars().first()
        first_id = first_attempt.id

    appeal = await repository.create_appeal(
        attempt_id=first_id,
        student_id=student.id,
        reason="class 不是函数关键字,但我认为判分依据不充分",
        requested_by="s1",
    )
    assert appeal.status == "pending"
    assert appeal.evidence_snapshot["question_stem"] is not None
    assert len(appeal.evidence_snapshot["knowledge_points"]) == 1

    # 同一次作答不可重复申诉
    with pytest.raises(RepositoryError):
        await repository.create_appeal(
            attempt_id=first_id,
            student_id=student.id,
            reason="再申诉",
            requested_by="s1",
        )

    # 教师复核：支持申诉，改判第一题满分 -> 派生重算
    await repository.resolve_appeal(
        appeal.id,
        outcome="sustained",
        new_score=1.0,
        teacher_note="同意改判",
        resolved_by="demo",
    )
    kp_ids = await repository.knowledge_point_ids_for_attempt(first_id)
    assert kp_ids == [ids["kp_id"]]

    delta = await repository.recompute_student_kp_mastery(
        student.id, ids["kp_id"]
    )
    assert delta["old_mastery"] == incremental
    assert delta["mastery"] > incremental  # 第一题由错改对，掌握度应上升

    after = await repository.list_mastery(student.id)
    assert after[0]["mastery"] == delta["mastery"]

    await database.dispose()


@pytest.mark.asyncio
async def test_appeal_reject_keeps_mastery(tmp_path) -> None:
    database = Database(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    await database.create_schema()
    repository = EduRepository(database.session_factory)

    ids = await _make_question(database)
    student = await repository.get_or_create_student("s1", "小明")

    await repository.record_attempt(
        student_id=student.id,
        session_id=None,
        turn_id=None,
        question_id=ids["question_id"],
        answer={"value": "wrong"},
        score=0.0,
        max_score=1.0,
        knowledge_evidence=[
            {"knowledge_point_id": ids["kp_id"], "weight": 1.0}
        ],
    )
    before = (await repository.list_mastery(student.id))[0]["mastery"]

    async with database.session_factory() as s:
        attempt_id = (
            await s.execute(select(LearningAttempt.id).limit(1))
        ).scalar_one()

    appeal = await repository.create_appeal(
        attempt_id=attempt_id,
        student_id=student.id,
        reason="求改判",
        requested_by="s1",
    )
    await repository.resolve_appeal(
        appeal.id,
        outcome="rejected",
        new_score=None,
        teacher_note="答案与标准不符",
        resolved_by="demo",
    )
    after = (await repository.list_mastery(student.id))[0]["mastery"]
    assert after == before

    # 已复核申诉不能重复处理
    with pytest.raises(RepositoryError):
        await repository.resolve_appeal(
            appeal.id,
            outcome="sustained",
            new_score=1.0,
            teacher_note=None,
            resolved_by="demo",
        )
    await database.dispose()


@pytest.mark.asyncio
async def test_appeal_foreign_attempt_is_not_found(tmp_path) -> None:
    database = Database(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    await database.create_schema()
    repository = EduRepository(database.session_factory)

    ids = await _make_question(database)
    owner = await repository.get_or_create_student("owner", "本人")
    stranger = await repository.get_or_create_student("stranger", "别人")

    await repository.record_attempt(
        student_id=owner.id,
        session_id=None,
        turn_id=None,
        question_id=ids["question_id"],
        answer={"value": "def"},
        score=1.0,
        max_score=1.0,
        knowledge_evidence=[
            {"knowledge_point_id": ids["kp_id"], "weight": 1.0}
        ],
    )

    async with database.session_factory() as s:
        attempt_id = (
            await s.execute(select(LearningAttempt.id).limit(1))
        ).scalar_one()

    # 非本人不能对别人的作答申诉（当作不存在，不泄露存在性）
    with pytest.raises(NotFoundError):
        await repository.create_appeal(
            attempt_id=attempt_id,
            student_id=stranger.id,
            reason="越权",
            requested_by=stranger.external_id,
        )
    await database.dispose()
