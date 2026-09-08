##为两个MCP Server提供延迟初始化的数据库和Repository
from __future__ import annotations

import asyncio

from eduharness.infrastructure.database import Database
from eduharness.infrastructure.repositories import EduRepository
from eduharness.settings import get_settings

_database: Database | None = None
_repository: EduRepository | None = None
_lock = asyncio.Lock()


async def get_repository() -> EduRepository:
    global _database, _repository

    if _repository is not None:
        return _repository

    async with _lock:
        if _repository is not None:
            return _repository

        settings = get_settings()
        _database = Database(settings.database_url)

        if settings.auto_create_schema:
            await _database.create_schema()

        _repository = EduRepository(
            _database.session_factory
        )
        return _repository