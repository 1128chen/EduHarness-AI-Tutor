from datetime import datetime, timedelta, timezone

from eduharness.domain.mastery import (

    forgetting_risk,
    update_mastery,
)
from eduharness.infrastructure.models import MasteryState


def new_state() -> MasteryState:
    return MasteryState(
        mastery=0.3,
        confidence=0.2,
        attempts_count=0,
        last_practiced_at=None,
    )


def test_correct_answer_does_not_reduce_mastery() -> None:
    state = new_state()
    old_mastery = state.mastery

    updated = update_mastery(
        state=state,
        score_ratio=1.0,
        occurred_at=datetime.now(timezone.utc),
    )

    assert updated.mastery >= old_mastery
    assert 0 <= updated.mastery <= 1
    assert 0 <= updated.confidence <= 1
    assert updated.attempts_count == 1


def test_wrong_answer_keeps_values_in_range() -> None:
    state = new_state()

    updated = update_mastery(
        state=state,
        score_ratio=0.0,
        occurred_at=datetime.now(timezone.utc),
    )

    assert 0 <= updated.mastery <= 1
    assert 0 <= updated.confidence <= 1
    assert updated.attempts_count == 1


def test_forgetting_risk_increases_with_time() -> None:
    now = datetime.now(timezone.utc)
    last_practice = now - timedelta(days=1)

    risk_after_one_day = forgetting_risk(
        last_practice,
        now,
    )
    risk_after_thirty_days = forgetting_risk(
        last_practice,
        now + timedelta(days=29),
    )

    assert risk_after_thirty_days >= risk_after_one_day
    assert 0 <= risk_after_one_day <= 1
    assert 0 <= risk_after_thirty_days <= 1


def test_forgetting_risk_accepts_iso_datetime() -> None:
    now = datetime.now(timezone.utc)
    last_practice = now - timedelta(days=2)

    risk = forgetting_risk(
        last_practice.isoformat(),
        now,
    )

    assert 0 <= risk <= 1