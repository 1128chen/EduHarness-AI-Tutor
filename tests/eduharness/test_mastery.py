from datetime import datetime, timezone,timedelta
# 手动定义 UTC（兼容 Python 3.10 及以下）
UTC = timezone.utc

from eduharness.domain.mastery import (
    RecommendationFactors,
    forgetting_risk,
    mastery_confidence,
    update_mastery,
)


def test_correct_answer_increases_mastery() -> None:
    result = update_mastery(0.4, 1.0, 1.0)
    assert 0.4 < result <= 1.0


def test_incorrect_answer_decreases_mastery() -> None:
    result = update_mastery(0.8, 0.0, 1.0)
    assert 0.0 <= result < 0.8


def test_mastery_is_bounded() -> None:
    assert 0.0 <= update_mastery(-10, 2, 2) <= 1.0
    assert 0.0 <= update_mastery(10, -2, 2) <= 1.0


def test_confidence_increases_with_attempts() -> None:
    assert mastery_confidence(10) > mastery_confidence(1)


def test_forgetting_risk_increases_over_time() -> None:
    recent = datetime.now(UTC) - timedelta(days=1)
    old = datetime.now(UTC) - timedelta(days=30)

    assert forgetting_risk(old) > forgetting_risk(recent)


def test_recommendation_score_is_bounded() -> None:
    factors = RecommendationFactors(
        mastery=0.2,
        confidence=0.8,
        forgetting_risk=0.7,
        prerequisite_readiness=1.0,
    )
    assert 0.0 <= factors.score() <= 1.0