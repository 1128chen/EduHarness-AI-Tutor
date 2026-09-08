import asyncio

from eduharness.infrastructure.database import Database
from eduharness.settings import get_settings


async def main() -> None:
    settings = get_settings()
    database = Database(settings.database_url)

    try:
        await database.create_schema()
        print("EduHarness database schema created.")
    finally:
        await database.dispose()


if __name__ == "__main__":
    asyncio.run(main())