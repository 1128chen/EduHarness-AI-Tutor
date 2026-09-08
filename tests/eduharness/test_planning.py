"""规划域纯函数测试：艾宾浩斯到期、章节/题目排序、判定权重。"""
from __future__ import annotations

from datetime import date

from eduharness.domain.planning import (
    chapter_is_done,
    chapter_sort_key,
    ebbinghaus_schedule,
    next_review_date,
    order_chapter_questions,
    pending_review_date,
    resolve_review_weight,
    resolve_verdict_score,
)

D = date.fromisoformat


def test_ebbinghaus_schedule_offsets() -> None:
    mastered = D("2026-09-01")
    dates = ebbinghaus_schedule(mastered)
    assert dates == [
        D("2026-09-02"),  # +1
        D("2026-09-03"),  # +2
        D("2026-09-05"),  # +4
        D("2026-09-08"),  # +7
        D("2026-09-16"),  # +15
        D("2026-10-01"),  # +30
    ]


def test_pending_review_date_when_overdue() -> None:
    mastered = D("2026-09-01")
    # 未做过任何复习，今天 D4：最早到期(+1 天)今天已逾期 -> 取 +1
    assert pending_review_date(
        mastered, last_done=None, today=D("2026-09-05")
    ) == D("2026-09-02")


def test_pending_review_date_respects_last_done() -> None:
    mastered = D("2026-09-01")
    # 已完成 +1/+2 两轮，今天已过 +4 到期日(09-05)且未做 -> 取 +4 补做
    assert pending_review_date(
        mastered, last_done=D("2026-09-03"), today=D("2026-09-08")
    ) == D("2026-09-05")
    # 今天(09-08=+7)刚 done 本轮 -> 不再出现
    assert (
        pending_review_date(
            mastered, last_done=D("2026-09-08"), today=D("2026-09-08")
        )
        is None
    )


def test_next_review_date_future_only() -> None:
    mastered = D("2026-09-01")
    assert next_review_date(
        mastered, last_done=None, today=D("2026-09-02")
    ) == D("2026-09-03")


def test_question_priority_order() -> None:
    questions = [
        {"id": "hard-unseen", "difficulty": 0.9, "attempted": False},
        {"id": "easy-unseen", "difficulty": 0.2, "attempted": False},
        {"id": "failing", "difficulty": 0.5, "attempted": True, "mastery": 0.3},
        {"id": "mastered", "difficulty": 0.1, "attempted": True, "mastery": 0.9},
    ]
    order = [q["id"] for q in order_chapter_questions(questions)]
    # 失败重刷 > 未做(易>难) > 已掌握
    assert order == ["failing", "easy-unseen", "hard-unseen", "mastered"]


def test_chapter_done_threshold() -> None:
    assert chapter_is_done(1, 3) is False  # 0.33 < 0.6
    assert chapter_is_done(2, 3) is True  # 0.67 >= 0.6
    assert chapter_is_done(3, 5) is True  # 0.6 >= 0.6
    assert chapter_is_done(0, 0) is False


def test_chapter_sort_key_extracts_number() -> None:
    assert chapter_sort_key("lec02.twopointer") == (2,)
    assert chapter_sort_key("lec11.backtrack") == (11,)


def test_verdict_and_review_weight() -> None:
    assert resolve_verdict_score("ac") == 1.0
    assert resolve_verdict_score("partial") == 0.5
    assert resolve_verdict_score("wrong") == 0.0
    assert resolve_review_weight("self") == 0.5
    assert resolve_review_weight("agent") == 1.0
    assert resolve_review_weight("teacher") == 1.0
