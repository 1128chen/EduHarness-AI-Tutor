##算法刷题学习路径与艾宾浩斯复习调度的纯函数层。
##不碰数据库：给定输入返回确定性结果，便于单元测试与后续替换策略。
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Iterable

##艾宾浩斯复习间隔(天)：学会当天算 D0，之后第 1/2/4/7/15/30 天各复习一次
EBBINGHAUS_OFFSETS: tuple[int, ...] = (1, 2, 4, 7, 15, 30)

##章节达到"已掌握"所需通过题目比例；单题掌握度低于该值视为需重刷
CHAPTER_PASS_RATIO = 0.6
MASTERY_OK = 0.6

##代码题判定 -> 归一化得分
VERDICT_SCORE: dict[str, float] = {
    "ac": 1.0,
    "partial": 0.5,
    "wrong": 0.0,
}

##批改来源 -> 证据权重(影响 update_mastery 的 alpha 缩放)
REVIEW_WEIGHT: dict[str, float] = {
    "agent": 1.0,
    "teacher": 1.0,
    "self": 0.5,
}


def parse_day(value: date | str | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    return date.fromisoformat(text[:10])


def fmt_day(value: date) -> str:
    return value.isoformat()


def ebbinghaus_schedule(mastered_on: date) -> list[date]:
    """学会日 D0 之后，第 1/2/4/7/15/30 天的复习日期(升序、去重)。"""
    seen: set[date] = set()
    dates: list[date] = []
    for offset in EBBINGHAUS_OFFSETS:
        candidate = mastered_on + timedelta(days=offset)
        if candidate not in seen:
            seen.add(candidate)
            dates.append(candidate)
    dates.sort()
    return dates


def pending_review_date(
    mastered_on: date,
    last_done: date | None,
    today: date,
) -> date | None:
    """今天是否存在"该复习但尚未完成"的到期日。

    last_done: 该题最近一次已完成(review/done)的日期。
    规则：所有到期日 d ∈ (last_done, today] 中最早者即待办到期日。
    """
    schedule = ebbinghaus_schedule(mastered_on)
    for scheduled in schedule:
        if scheduled <= today and (last_done is None or scheduled > last_done):
            return scheduled
    return None


def next_review_date(
    mastered_on: date,
    last_done: date | None,
    today: date,
) -> date | None:
    """下一个未来到期日(用于前端展示，不一定今天)。"""
    schedule = ebbinghaus_schedule(mastered_on)
    for scheduled in schedule:
        if last_done is None or scheduled > last_done:
            if scheduled > today:
                return scheduled
    return None


##--------------------------------------------------------------------------
## 章节 / 题目排序
##--------------------------------------------------------------------------

def chapter_sort_key(code: str) -> tuple[int, ...]:
    """从 'lec02.twopointer' 这类 code 里取排序用的段。

    固定宽度章节号保证字典序 == 数值序；异常时退化为全 0 再按 code 比。
    """
    head = code.split(".", 1)[0]
    if head.startswith("lec") and head[3:].isdigit():
        return (int(head[3:]),)
    return (0,)


def question_priority(question: dict[str, Any]) -> tuple[Any, ...]:
    """单题建议优先级(越小越先刷)：
    0) 已做过但掌握度不足 -> 立即重刷
    1) 未做过             -> 新题(内部按难度升序)
    2) 已掌握             -> 放到后面
    """
    attempted = bool(question.get("attempted"))
    mastery = float(question.get("mastery") or 0.0)
    difficulty = float(question.get("difficulty") or 0.5)

    if attempted and mastery < MASTERY_OK:
        return (0, difficulty, str(question.get("id")))
    if not attempted:
        return (1, difficulty, str(question.get("id")))
    return (2, difficulty, str(question.get("id")))


def order_chapter_questions(
    questions: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    return sorted(questions, key=question_priority)


def chapter_is_done(ac_questions: int, total_questions: int) -> bool:
    """通过题数占比达到阈值才算完成本章(用于解锁下一章)。"""
    if total_questions <= 0:
        return False
    return (ac_questions / total_questions) >= CHAPTER_PASS_RATIO


def resolve_verdict_score(verdict: str) -> float:
    return VERDICT_SCORE.get(str(verdict).lower(), 0.0)


def resolve_review_weight(reviewed_by: str) -> float:
    return REVIEW_WEIGHT.get(str(reviewed_by).lower(), 0.5)
