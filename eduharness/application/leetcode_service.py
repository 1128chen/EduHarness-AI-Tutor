##LeetCode 刷题训练营：学习路径推进 + 艾宾浩斯每日复习计划 + 代码判分。
from __future__ import annotations

from datetime import date
from typing import Any

from eduharness.domain.planning import (
    MASTERY_OK,
    chapter_is_done,
    order_chapter_questions,
    parse_day,
    pending_review_date,
    resolve_review_weight,
    resolve_verdict_score,
)
from eduharness.infrastructure.repositories import (
    EduRepository,
    NotFoundError,
    RepositoryError,
)

SUBJECT = "leetcode"


class LeetCodeService:
    def __init__(self, repository: EduRepository) -> None:
        self.repository = repository

    ##--------------------------------------------------------------------------
    ## 课程快照：章节 + 每章题目 + 学生进度(供 overview 与今日计划复用)
    ##--------------------------------------------------------------------------
    async def _snapshot(
        self,
        student_id: str | None,
        subject: str,
    ) -> dict[str, Any]:
        chapters_raw = await self.repository.list_knowledge_points(subject)
        questions = await self.repository.list_questions_by_subject(subject)
        stats = (
            await self.repository.student_question_stats(student_id, subject)
            if student_id
            else {}
        )

        # 题目归到主章：取 evidence 权重最大(主映射 weight=1.0)的那条，
        # 标签映射(weight=0.5)只用于跨章关联，不改变归属。
        by_chapter: dict[str, list[dict[str, Any]]] = {}
        for question in questions:
            points = question["knowledge_points"]
            if not points:
                continue
            main_point = max(
                points,
                key=lambda item: float(item.get("weight", 0.0)),
            )
            main_code = main_point["code"]
            by_chapter.setdefault(main_code, []).append(question)

        chapters: list[dict[str, Any]] = []
        done_codes: set[str] = set()
        for point in chapters_raw:
            chapter_questions = by_chapter.get(point["code"], [])
            ac = 0
            for question in chapter_questions:
                question["attempted"] = question["id"] in stats
                question["attempts"] = (
                    stats.get(question["id"], {}).get("attempts", 0)
                )
                question["ac"] = bool(
                    stats.get(question["id"], {}).get("ac")
                )
                question["mastery"] = (
                    stats.get(question["id"], {}).get(
                        "last_correctness", 0.0
                    )
                )
                if question["ac"]:
                    ac += 1
            done = chapter_is_done(ac, len(chapter_questions))
            if done:
                done_codes.add(point["code"])

            chapters.append(
                {
                    **point,
                    "questions": chapter_questions,
                    "ac_count": ac,
                    "total_questions": len(chapter_questions),
                    "done": done,
                }
            )

        # 解锁/当前章状态
        for chapter in chapters:
            prereqs = chapter.get("prerequisites") or []
            unlocked = all(
                prereq in done_codes for prereq in prereqs
            )
            if not unlocked:
                chapter["status"] = "locked"
            elif chapter["done"]:
                chapter["status"] = "done"
            else:
                chapter["status"] = "open"

        current_code = next(
            (
                chapter["code"]
                for chapter in chapters
                if chapter["status"] == "open"
            ),
            None,
        )
        for chapter in chapters:
            chapter["current"] = chapter["code"] == current_code

        mastered_dates: dict[str, str | None] = {}
        for question_id, item in stats.items():
            mastered_dates[question_id] = item.get("first_ac_at")

        return {
            "chapters": chapters,
            "mastered_dates": mastered_dates,
            "stats": stats,
        }

    async def overview(
        self,
        student_id: str | None,
        subject: str = SUBJECT,
    ) -> dict[str, Any]:
        snapshot = await self._snapshot(student_id, subject)
        mastery_rows = (
            await self.repository.student_mastery_by_subject(
                student_id, subject
            )
            if student_id
            else []
        )

        def summarize(chapter: dict[str, Any]) -> dict[str, Any]:
            questions = []
            for question in chapter["questions"]:
                questions.append(
                    {
                        "id": question["id"],
                        "stem": question["stem"],
                        "difficulty": question["difficulty"],
                        "editorial": question.get("editorial", {}),
                        "attempted": question["attempted"],
                        "attempts": question["attempts"],
                        "ac": question["ac"],
                        "mastery": question["mastery"],
                        "question_type": question.get("question_type"),
                    }
                )
            return {
                "id": chapter["id"],
                "code": chapter["code"],
                "name": chapter["name"],
                "description": chapter["description"],
                "prerequisites": chapter.get("prerequisites", []),
                "status": chapter["status"],
                "current": chapter["current"],
                "ac_count": chapter["ac_count"],
                "total_questions": chapter["total_questions"],
                "questions": questions,
            }

        return {
            "subject": subject,
            "chapters": [summarize(c) for c in snapshot["chapters"]],
            "mastery": mastery_rows,
        }

    ##--------------------------------------------------------------------------
    ## 今日计划：艾宾浩斯复习到期 + 当前章节新题
    ##--------------------------------------------------------------------------
    async def today_plan(
        self,
        student_id: str,
        subject: str = SUBJECT,
        *,
        today: date | str | None = None,
        new_limit: int = 3,
        review_limit: int = 10,
    ) -> dict[str, Any]:
        if not student_id:
            raise ValueError("student_id 必填")
        today = parse_day(today) or date.today()
        snapshot = await self._snapshot(student_id, subject)

        # 目标章节：第一个 status=open(current)
        target = next(
            (c for c in snapshot["chapters"] if c["status"] == "open"),
            None,
        )

        learn_tasks: list[dict[str, Any]] = []
        if target:
            candidates = []
            for question in target["questions"]:
                mastered = snapshot["stats"].get(
                    question["id"], {}
                ).get("ac", False)
                if not mastered:
                    candidates.append(question)
            ordered = order_chapter_questions(candidates)[:new_limit]
            for question in ordered:
                await self.repository.upsert_daily_task(
                    student_id=student_id,
                    subject=subject,
                    task_date=today.isoformat(),
                    kind="learn",
                    question_id=question["id"],
                    knowledge_point_id=target["id"],
                    reason={
                        "chapter": target["code"],
                        "chapter_name": target["name"],
                        "recommended_index": (
                            candidates.index(question) + 1
                        ),
                    },
                )
            learn_tasks = await self.repository.list_daily_tasks(
                student_id,
                subject,
                task_date=today.isoformat(),
                kind="learn",
                status="planned",
            )

        # 复习队列：所有已掌握(AC)的题，今天若有到期日
        mastered_ids = [
            qid
            for qid, item in snapshot["stats"].items()
            if item.get("ac")
        ]
        done_dates = await self.repository.last_done_review_dates(
            student_id, subject, mastered_ids
        )
        review_candidates: list[tuple[dict[str, Any], Any]] = []
        for question in [
            question
            for chapter in snapshot["chapters"]
            for question in chapter["questions"]
        ]:
            if not snapshot["stats"].get(question["id"], {}).get(
                "ac"
            ):
                continue
            mastered_on = parse_day(
                snapshot["mastered_dates"].get(question["id"])
            )
            if mastered_on is None:
                continue
            last_done = parse_day(
                done_dates.get(question["id"])
            )
            due = pending_review_date(mastered_on, last_done, today)
            if due is not None:
                review_candidates.append(
                    (question, due)
                )

        review_candidates.sort(key=lambda item: item[1])
        for question, due in review_candidates[:review_limit]:
            await self.repository.upsert_daily_task(
                student_id=student_id,
                subject=subject,
                task_date=today.isoformat(),
                kind="review",
                question_id=question["id"],
                knowledge_point_id=None,
                review_offset=(due - parse_day(snapshot["mastered_dates"].get(question["id"]))).days,
                reason={
                    "due_date": due.isoformat(),
                    "chapter": question["knowledge_points"][0]["code"]
                    if question["knowledge_points"]
                    else "",
                },
            )

        review_tasks = await self.repository.list_daily_tasks(
            student_id,
            subject,
            task_date=today.isoformat(),
            kind="review",
            status="planned",
        )

        next_new = target["code"] if target else None
        next_new_name = target["name"] if target else None
        return {
            "subject": subject,
            "date": today.isoformat(),
            "target_chapter": {
                "code": next_new,
                "name": next_new_name,
            },
            "learn": learn_tasks,
            "review": review_tasks,
            "limits": {"new": new_limit, "review": review_limit},
        }

    async def set_task_status(
        self,
        task_id: str,
        status: str,
    ) -> dict[str, Any]:
        await self.repository.set_daily_task_status(task_id, status)
        return {"task_id": task_id, "status": status}

    async def list_tasks(
        self,
        student_id: str,
        subject: str,
        *,
        task_date: str | None = None,
        kind: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        return await self.repository.list_daily_tasks(
            student_id,
            subject,
            task_date=task_date,
            kind=kind,
            status=status,
        )

    ##--------------------------------------------------------------------------
    ## 代码提交判分(安全边界: 不执行学生代码)
    ##    reviewed_by='self'  学生对照标准题解自查(离线可用)
    ##    reviewed_by='agent'/'teacher'  判定与解题说明写入 detail(由调用方/教练填充)
    ##--------------------------------------------------------------------------
    async def submit_coding(
        self,
        *,
        student_id: str,
        subject: str,
        question_id: str,
        code: str,
        language: str,
        verdict: str,
        notes: str | None = None,
        reviewed_by: str = "self",
    ) -> dict[str, Any]:
        question = await self.repository.get_question(question_id)
        if question is None or question.get("subject") != subject:
            raise NotFoundError("question not found")

        verdict_key = str(verdict).lower()
        if verdict_key not in {"ac", "partial", "wrong"}:
            raise RepositoryError("verdict 仅支持 ac/partial/wrong")

        score = resolve_verdict_score(verdict_key)
        weight_factor = resolve_review_weight(reviewed_by)

        mapping = await self.repository.get_question_knowledge_points(
            question_id
        )
        evidence = [
            {
                "knowledge_point_id": item["knowledge_point_id"],
                "weight": round(
                    float(item.get("weight", 1.0)) * weight_factor, 3
                ),
            }
            for item in mapping
        ]

        attempt = await self.repository.record_attempt(
            student_id=student_id,
            session_id=None,
            turn_id=None,
            question_id=question_id,
            answer={
                "code": code,
                "language": language,
                "notes": notes,
            },
            score=score,
            max_score=1.0,
            knowledge_evidence=evidence,
            duration_seconds=None,
        )

        review = await self.repository.create_attempt_review(
            attempt_id=attempt.id,
            verdict=verdict_key,
            score=score,
            detail={
                "verdict": verdict_key,
                "language": language,
                "notes": notes,
                "code_length": len(code),
            },
            reviewed_by=reviewed_by,
        )

        mastered = score >= 1.0
        return {
            "attempt_id": attempt.id,
            "verdict": verdict_key,
            "score": score,
            "review": review,
            "mastered": mastered,
            "reviewed_by": reviewed_by,
        }

    async def question_solution(
        self,
        question_id: str,
    ) -> dict[str, Any] | None:
        return await self.repository.get_question_solution(question_id)
