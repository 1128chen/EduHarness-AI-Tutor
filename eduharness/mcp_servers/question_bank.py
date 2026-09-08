##向 Agent 暴露题目检索、读取、评分和自适应练习工具。


import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from eduharness.mcp_servers.common import get_repository

mcp = FastMCP("eduharness-question-bank")


@mcp.tool()
async def search_questions(
    subject: str,
    knowledge_points: list[str] | None = None,
    difficulty_min: float = 0.0,
    difficulty_max: float = 1.0,
    limit: int = 10,
) -> dict[str, Any]:
    """按学科、知识点和难度搜索练习题。"""
    repository = await get_repository()

    questions = await repository.search_questions(
        subject=subject,
        knowledge_point_codes=knowledge_points,
        difficulty_min=max(0.0, difficulty_min),
        difficulty_max=min(1.0, difficulty_max),
        limit=min(max(limit, 1), 50),
    )

    return {
        "count": len(questions),
        "questions": questions,
    }

##核心是一个防作弊开关
##为什么这么设计？防止 AI 抄答案。学生问"这道题怎么做"，AI 不应该偷偷 get_question(include_answer=True) 把答案读出来念给学生——那等于作弊。正确路径是：学生作答 → 调用 grade_answer 判分 → AI 根据判分反馈讲解。环境变量开关给了部署方一个"完全禁用答案披露"的总闸。
@mcp.tool()
async def get_question(
    question_id: str,
    include_answer: bool = False,
) -> dict[str, Any]:
    """读取一道题。默认不返回标准答案。"""
    repository = await get_repository()

    answer_reveal_enabled = (
        os.environ.get(
            "EDUHARNESS_ALLOW_ANSWER_REVEAL",
            "false",
        ).lower()
        in {"1", "true", "yes", "on"}
    )

    effective_include_answer = (
        include_answer and answer_reveal_enabled
    )

    question = await repository.get_question(
        question_id,
        include_answer=effective_include_answer,
    )
    question["answer_revealed"] = (
        effective_include_answer
    )

    if include_answer and not answer_reveal_enabled:
        question["answer_policy"] = (
            "标准答案披露未启用，请先调用grade_answer。"
        )

    return question

##查这道题关联了哪些知识点，把"题→知识点"的关联关系附在判分结果里返回。这样 AI 不仅能告诉学生对错，还能指出"这道题考的是『分数加减法』，权重 0.8"——为后续掌握度更新和推荐提供依据。
@mcp.tool()
async def grade_answer(
    question_id: str,
    answer: dict[str, Any],
) -> dict[str, Any]:
    """对答案评分，并返回知识点证据。"""
    repository = await get_repository()

    grade = await repository.grade_answer(
        question_id,
        answer,
    )
    evidence = (
        await repository.get_question_knowledge_points(
            question_id
        )
    )

    grade["knowledge_evidence"] = [
        {
            "knowledge_point_id": item[
                "knowledge_point_id"
            ],
            "code": item["code"],
            "name": item["name"],
            "weight": item["weight"],
        }
        for item in evidence
    ]
    return grade

##结合掌握度的推荐
@mcp.tool()
async def recommend_practice(
    student_id: str,
    subject: str,
    limit: int = 5,
) -> dict[str, Any]:
    """根据学生薄弱知识点推荐下一组练习题。"""
    repository = await get_repository()
    mastery = await repository.list_mastery(student_id)

    weak_points = [
        item
        for item in mastery
        if item["subject"] == subject
        and item["mastery"] < 0.8##0.8是已掌握的阈值
    ]
    weak_points.sort(
        key=lambda item: item["mastery"]
    )

    knowledge_codes = [
        item["code"]
        for item in weak_points[:5]
    ]

    questions = await repository.search_questions(
        subject=subject,
        knowledge_point_codes=knowledge_codes or None,
        difficulty_min=0.0,
        difficulty_max=0.75,
        limit=min(max(limit, 1), 20),
    )

    return {
        "student_id": student_id,
        "target_knowledge_points": knowledge_codes,
        "questions": questions,
    }


def main() -> None:
    mcp.run(transport="stdio")
##transport="stdio" 就是上一份代码讲的 stdio 通信：服务器进程由客户端（MiniCode）拉起，通过 stdin 收请求、stdout 回响应、stderr 打日志。


if __name__ == "__main__":
    main()