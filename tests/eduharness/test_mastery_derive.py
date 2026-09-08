"""派生式掌握度重算与遗忘曲线输入归一化的领域层测试。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from eduharness.domain.mastery import (
    forgetting_risk,
    recompute_mastery_from_evidence,
    update_mastery,
)

UTC = timezone.utc


def test_recompute_equals_sequential_update() -> None:
    """派生折叠 == 顺序应用 update_mastery，保证增量存储与重放结果一致。"""
    evidence = [(1.0, 1.0), (0.0, 1.0), (1.0, 0.5), (0.0, 1.0)]
    mastery, confidence, count = recompute_mastery_from_evidence(evidence)

    expected = 0.0
    for score, weight in evidence:
        expected = update_mastery(expected, score, weight)

    assert mastery == expected
    assert count == len(evidence)
    assert 0.0 <= mastery <= 1.0
    assert 0.0 <= confidence <= 1.0


def test_recompute_empty_evidence_is_zero_state() -> None:
    mastery, confidence, count = recompute_mastery_from_evidence([])
    assert (mastery, confidence, count) == (0.0, 0.0, 0)


def test_recompute_is_deterministic() -> None:
    evidence = [(1.0, 1.0), (0.0, 1.0), (0.0, 0.5)]
    assert recompute_mastery_from_evidence(
        evidence
    ) == recompute_mastery_from_evidence(evidence)


def test_forgetting_risk_accepts_iso_string() -> None:
    """回归：learning_service 把 ISO 字符串传给 forgetting_risk 曾直接崩溃。"""
    iso = "2026-09-04T06:57:54.882735+00:00"
    zulu = "2026-09-04T06:57:54.882735Z"
    assert 0.0 <= forgetting_risk(iso) <= 1.0
    assert 0.0 <= forgetting_risk(zulu) <= 1.0
    # 两次调用间隔微秒级，now 参与计算，容忍极小抖动
    assert abs(forgetting_risk(zulu) - forgetting_risk(iso)) < 1e-4


def test_forgetting_risk_none_and_empty() -> None:
    assert forgetting_risk(None) == 1.0
    assert forgetting_risk("") == 1.0


def test_forgetting_risk_grows_over_time_for_strings() -> None:
    old = (datetime.now(UTC) - timedelta(days=30)).isoformat()
    recent = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    assert forgetting_risk(old) > forgetting_risk(recent)
