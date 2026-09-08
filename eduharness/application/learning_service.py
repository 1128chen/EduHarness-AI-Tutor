##保存评分证据，并生成可解释的薄弱知识点推荐。
from __future__ import annotations

from eduharness.domain.mastery import (
    RecommendationFactors,
    forgetting_risk,
)
from eduharness.infrastructure.repositories import EduRepository


class LearningService:
    def __init__(self, repository: EduRepository) -> None:
        self.repository = repository

    async def record_graded_attempt(
        self,
        *,
        student_id: str,
        session_id: str | None,
        turn_id: str | None,
        question_id: str,
        answer: dict,
        grade: dict,
        knowledge_evidence: list[dict],
        duration_seconds: int | None = None,
    ) -> dict:
        # 证据为空时按题目-知识点映射自动推导：作答记录不依赖前端/调用方手填引用，
        # "答一题 -> 自动更新掌握度"开箱即用，且引用来源唯一（题库映射），更可审计。
        if not knowledge_evidence and question_id:
            knowledge_evidence = (
                await self.repository.get_question_knowledge_points(
                    question_id
                )
            )

        attempt = await self.repository.record_attempt(
            student_id=student_id,
            session_id=session_id,
            turn_id=turn_id,
            question_id=question_id,
            answer=answer,
            score=float(grade["score"]),
            max_score=float(grade["max_score"]),
            knowledge_evidence=knowledge_evidence,
            duration_seconds=duration_seconds,
        )
        return {
            "attempt_id": attempt.id,
            "correctness": attempt.correctness,
        }

    async def submit_auto_answer(
        self,
        *,
        student_id: str,
        question_id: str,
        answer_value: str,
    ) -> dict:
        """学生自助交卷：确定性格点判分并落一条作答记录。

        面向无大模型 / 无 agent 会话的轻练习场景；证据从题目-知识点
        映射自动推导，与完整 agent 对话共用同一条 record 路径。
        """
        grade = await self.repository.grade_answer(
            question_id,
            {"value": answer_value},
        )
        attempt = await self.record_graded_attempt(
            student_id=student_id,
            session_id=None,
            turn_id=None,
            question_id=question_id,
            answer={"value": answer_value},
            grade={
                "score": grade["score"],
                "max_score": grade["max_score"],
            },
            knowledge_evidence=[],
        )
        return {
            "attempt_id": attempt["attempt_id"],
            "correct": grade.get("correct"),
            "score": grade["score"],
            "max_score": grade["max_score"],
            "feedback": grade.get("feedback"),
            "explanation": grade.get("explanation"),
        }

    async def mastery_report(
        self,
        student_id: str,
    ) -> list[dict]:
        return await self.repository.list_mastery(student_id)

    async def recommendations(
        self,
        student_id: str,
        *,
        limit: int = 10,
    ) -> list[dict]:
        mastery_rows = await self.repository.list_mastery(
            student_id
        )
        mastery_by_code = {
            row["code"]: row["mastery"]
            for row in mastery_rows
        }

        results = []

        for row in mastery_rows:
            prerequisites = row.get("prerequisites", [])
            readiness = (
                sum(
                    mastery_by_code.get(code, 0.0)
                    for code in prerequisites
                )
                / len(prerequisites)
                if prerequisites
                else 1.0
            )

            factors = RecommendationFactors(
                mastery=row["mastery"],
                confidence=row["confidence"],
                forgetting_risk=forgetting_risk(
                    row["last_practiced_at"]
                ),
                prerequisite_readiness=readiness,
            )

            results.append(
                {
                    "knowledge_point_id": row[
                        "knowledge_point_id"
                    ],
                    "code": row["code"],
                    "name": row["name"],
                    "priority": factors.score(),
                    "reason": {
                        "mastery": row["mastery"],
                        "confidence": row["confidence"],
                        "forgetting_risk": (
                            factors.forgetting_risk
                        ),
                        "prerequisite_readiness": readiness,
                    },
                }
            )

        results.sort(
            key=lambda item: item["priority"],
            reverse=True,
        )
        return results[: min(max(limit, 1), 50)]