import pytest

from eduharness.application.event_bus import TurnEventBus


@pytest.mark.asyncio
async def test_event_bus_preserves_sequence() -> None:
    bus = TurnEventBus(
        session_id="session-1",
        turn_id="turn-1",
    )

    first = await bus.emit(
        "turn.started",
        {},
    )
    second = await bus.emit(
        "assistant.progress",
        {"text": "working"},
    )

    assert first.sequence == 1
    assert second.sequence == 2


@pytest.mark.asyncio
async def test_event_bus_replays_history() -> None:
    bus = TurnEventBus(
        session_id="session-1",
        turn_id="turn-1",
    )

    await bus.emit("turn.started", {})
    await bus.emit(
        "assistant.completed",
        {"text": "done"},
    )
    await bus.close()

    events = [
        event
        async for event in bus.subscribe(
            after_sequence=1
        )
    ]

    assert len(events) == 1
    assert events[0].type == "assistant.completed"