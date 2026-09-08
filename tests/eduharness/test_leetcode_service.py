"""LeetCode 刷题训练营 service 层测试：章节归主/解锁、今日计划、代码判分。"""
from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import select

from eduharness.infrastructure.database import Database
from eduharness.infrastructure.models import (
    AttemptKnowledgePoint,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgePoint,
    LearningAttempt,
    Question,
    QuestionKnowledgePoint,
)
from eduharness.infrastructure.repositories import EduRepository
from eduharness.application.leetcode_service import LeetCodeService

UTC = timezone.utc


async def _seed_course(db: Database) -> dict:
    async with db.session_factory() as s:
        c1 = KnowledgePoint(subject="leetcode", code="lec01.array",
                            name="数组", description="d", prerequisites=[])
        c2 = KnowledgePoint(subject="leetcode", code="lec02.pointer",
                            name="双指针", description="d", prerequisites=["lec01.array"])
        s.add_all([c1, c2])
        await s.flush()
        ch1 = [
            {"editorial": 1, "difficulty": 0.3},
            {"editorial": 27, "difficulty": 0.3},
            {"editorial": 118, "difficulty": 0.3},
        ]
        ch2 = [
            {"editorial": 11, "difficulty": 0.55, "tags": ["lec01.array"]},
            {"editorial": 15, "difficulty": 0.6},
            {"editorial": 42, "difficulty": 0.85},
        ]
        qids = {"lec01.array": [], "lec02.pointer": []}
        for code, chapter, kp in [
            ("lec01.array", ch1, c1), ("lec02.pointer", ch2, c2)]:
            for item in chapter:
                q = Question(subject="leetcode", question_type="coding",
                             stem=f"q{item['editorial']}", difficulty=item["difficulty"],
                             answer={"reference": {"editorial": item["editorial"], "title": f"t{item['editorial']}"}},
                             explanation="approach")
                s.add(q)
                await s.flush()
                qids[code].append(q.id)
                s.add(QuestionKnowledgePoint(question_id=q.id,
                                             knowledge_point_id=kp.id, weight=1.0))
                for tag in item.get("tags", []):
                    tag_kp = c1 if tag == "lec01.array" else c2
                    s.add(QuestionKnowledgePoint(question_id=q.id,
                                                 knowledge_point_id=tag_kp.id, weight=0.5))
                # 题解文档
                doc = KnowledgeDocument(subject="leetcode",
                                        title=f"leetcode-solution-{q.id}",
                                        source_uri="seed://test-solution")
                s.add(doc)
                await s.flush()
                s.add(KnowledgeChunk(document_id=doc.id, ordinal=0,
                                     content=f"solution for {item['editorial']}"))
        await s.commit()
        return {
            "ch1": qids["lec01.array"], "ch2": qids["lec02.pointer"],
            "kp": {"lec01.array": c1.id, "lec02.pointer": c2.id},
        }


async def _ac_past(db: Database, repo: EduRepository, student_id, question_id,
                   kp_id, days_ago: int) -> None:
    async with db.session_factory() as s:
        attempt = LearningAttempt(
            student_id=student_id, question_id=question_id,
            answer={"code": "x"}, score=1.0, max_score=1.0, correctness=1.0,
            created_at=datetime.now(UTC) - timedelta(days=days_ago),
        )
        s.add(attempt)
        await s.flush()
        s.add(AttemptKnowledgePoint(attempt_id=attempt.id,
                                    knowledge_point_id=kp_id, evidence_weight=1.0))
        await s.commit()
    await repo.recompute_student_kp_mastery(student_id, kp_id)


@pytest.mark.asyncio
async def test_overview_groups_question_to_main_chapter(tmp_path) -> None:
    db = Database(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    await db.create_schema()
    repo = EduRepository(db.session_factory)
    seed = await _seed_course(db)
    student = await repo.get_or_create_student("s1", "小明")
    svc = LeetCodeService(repo)

    ov = await svc.overview(student.id)
    by_code = {c["code"]: c for c in ov["chapters"]}
    ch1_ids = {q["id"] for q in by_code["lec01.array"]["questions"]}
    ch2_ids = {q["id"] for q in by_code["lec02.pointer"]["questions"]}
    assert len(ch1_ids) == 3
    assert len(ch2_ids) == 3
    # 带标签(tags=array)的 #11 仍应归主章 twopointer
    assert set(seed["ch2"]) == ch2_ids
    # 先修未满足 -> ch2 locked
    assert by_code["lec01.array"]["status"] == "open"
    assert by_code["lec02.pointer"]["status"] == "locked"
    await db.dispose()


@pytest.mark.asyncio
async def test_today_plan_learn_review_after_ac(tmp_path) -> None:
    db = Database(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    await db.create_schema()
    repo = EduRepository(db.session_factory)
    seed = await _seed_course(db)
    student = await repo.get_or_create_student("s1", "小明")
    svc = LeetCodeService(repo)

    # 三天前把 ch1 全部 AC -> ch1 完成解锁 ch2
    for qid in seed["ch1"]:
        await _ac_past(db, repo, student.id, qid,
                       seed["kp"]["lec01.array"], days_ago=3)

    ov = await svc.overview(student.id)
    by_code = {c["code"]: c for c in ov["chapters"]}
    assert by_code["lec01.array"]["status"] == "done"
    assert by_code["lec02.pointer"]["status"] == "open"

    from datetime import date
    plan = await svc.today_plan(student.id, today=date.today(),
                                new_limit=3, review_limit=10)
    assert plan["target_chapter"]["code"] == "lec02.pointer"
    learn_ids = {t["question"]["id"] for t in plan["learn"]}
    assert learn_ids and learn_ids <= set(seed["ch2"])
    review_ids = {t["question"]["id"] for t in plan["review"]}
    # ch1 的 AC 题在第 1/2/4 天均已到期 -> 复习队列非空
    assert set(seed["ch1"]) <= review_ids

    # 完成某条复习后，同日重生成不再出现该题
    first_review = plan["review"][0]
    await svc.set_task_status(first_review["id"], "done")
    plan2 = await svc.today_plan(student.id, today=date.today(),
                                 new_limit=3, review_limit=10)
    review2_ids = {t["question"]["id"] for t in plan2["review"]}
    assert first_review["question"]["id"] not in review2_ids
    await db.dispose()


@pytest.mark.asyncio
async def test_coding_submit_self_weight(tmp_path) -> None:
    db = Database(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    await db.create_schema()
    repo = EduRepository(db.session_factory)
    seed = await _seed_course(db)
    student = await repo.get_or_create_student("s1", "小明")
    svc = LeetCodeService(repo)
    qid = seed["ch2"][0]

    # 自评错
    wrong = await svc.submit_coding(student_id=student.id, subject="leetcode",
                                    question_id=qid, code="x", language="python",
                                    verdict="wrong", notes="n", reviewed_by="self")
    assert wrong["verdict"] == "wrong" and wrong["mastered"] is False
    # 自评 AC：证据权重减半(.5) -> 掌握度 = alpha(.125)*(1-0)
    ok = await svc.submit_coding(student_id=student.id, subject="leetcode",
                                 question_id=qid, code="def f(): pass",
                                 language="python", verdict="ac", reviewed_by="self")
    assert ok["mastered"] is True
    review = await repo.get_attempt_review(ok["attempt_id"])
    assert review is not None and review["reviewed_by"] == "self"

    mastery = await repo.student_mastery_by_subject(student.id, "leetcode")
    row = next(m for m in mastery
               if m["knowledge_point_id"] == seed["kp"]["lec02.pointer"])
    assert row["attempts_count"] == 2
    assert 0.10 < row["mastery"] < 0.15  # 自评权重减半下的保守估计

    # 题解文档可读
    solution = await svc.question_solution(qid)
    assert solution is not None
    assert solution["chunks"][0]["text"].startswith("solution")
    assert await svc.question_solution("missing-id") is None
    await db.dispose()
