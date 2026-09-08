from datetime import datetime, timezone

from eduharness.domain.events import HarnessEvent


def test_event_round_trip() -> None:
    event = HarnessEvent(
        type="model.delta",
        turn_id="turn-001",
        sequence=1,
        timestamp=datetime.now(timezone.utc),
        payload={"text": "hello"},
    )

    restored = HarnessEvent.from_dict(event.to_dict())

    assert restored.type == event.type
    assert restored.turn_id == event.turn_id
    assert restored.sequence == event.sequence
    assert restored.payload == event.payload


def test_event_payload_is_independent() -> None:
    payload = {"text": "first"}

    event = HarnessEvent(
        type="model.delta",
        turn_id="turn-001",
        sequence=1,
        timestamp=datetime.now(timezone.utc),
        payload=payload,
    )

    serialized = event.to_dict()
    assert serialized["payload"]["text"] == "first"


def test_event_timestamp_is_serializable() -> None:
    event = HarnessEvent(
        type="turn.started",
        turn_id="turn-001",
        sequence=0,
        timestamp=datetime.now(timezone.utc),
        payload={},
    )

    serialized = event.to_dict()

    assert serialized["timestamp"]
    datetime.fromisoformat(
        str(serialized["timestamp"]).replace("Z", "+00:00")
    )