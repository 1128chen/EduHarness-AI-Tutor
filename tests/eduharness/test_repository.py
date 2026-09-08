import pytest

from eduharness.infrastructure.database import Database
from eduharness.infrastructure.repositories import EduRepository


@pytest.mark.asyncio
async def test_create_session_and_messages(
    tmp_path,
) -> None:
    database = Database(
        f"sqlite+aiosqlite:///{tmp_path}/test.db"
    )
    await database.create_schema()

    repository = EduRepository(
        database.session_factory
    )
    student = await repository.get_or_create_student(
        "student-1",
        "Student One",
    )
    session = await repository.create_learning_session(
        student.id,
        "default",
        "Test session",
    )
    turn = await repository.create_turn(session.id)

    await repository.append_message(
        session_id=session.id,
        turn_id=turn.id,
        role="user",
        content="hello",
    )
    await repository.append_message(
        session_id=session.id,
        turn_id=turn.id,
        role="assistant",
        content="world",
    )

    messages = await repository.list_messages(
        session.id
    )

    assert [item["content"] for item in messages] == [
        "hello",
        "world",
    ]

    await database.dispose()