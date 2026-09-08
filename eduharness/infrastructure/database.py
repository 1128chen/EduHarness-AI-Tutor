##创建异步 SQLAlchemy 引擎；同一套代码兼容 SQLite 和 PostgreSQL
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from eduharness.infrastructure.models import Base


class Database:
    def __init__(self, database_url: str, echo: bool = False) -> None:
        connect_args = {}

        if database_url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        ##后端知识补充：SQLite 默认规定"哪个线程建的连接，只能哪个线程用"（线程安全保护）。但 asyncio 场景下，连接可能被事件循环的不同地方复用，所以要关掉这个检查。这个参数只对 SQLite 生效——PostgreSQL 是真正的"客户端-服务端"数据库，天然多线程安全，不需要它。这就是 if database_url.startswith("sqlite") 的原因。

        self.engine: AsyncEngine = create_async_engine(
            database_url,
            echo=echo,
            pool_pre_ping=True,##每次从连接池拿连接前，先发一个轻量 ping 试探连接是否还活着。防止拿到一条已断掉的"僵尸连接"——数据库重启、网络抖动后，池里的旧连接可能已失效，pre-ping 能及时发现并换一条。
            connect_args=connect_args,
        )
#         ##create_async_engine：创建异步引擎。URL 决定了用哪个驱动：
# sqlite+aiosqlite:///... → SQLite（aiosqlite 驱动）；
# postgresql+asyncpg://... → PostgreSQL（asyncpg 驱动）。
# 同一套代码两种数据库，因为引擎只认 URL，模型定义不关心底层是什么——这是 ORM 带来的"换数据库只改配置"能力。
        self.session_factory = async_sessionmaker(##会话工厂
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    async def create_schema(self) -> None:
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def drop_schema(self) -> None:
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
# ##Base.metadata 收集了所有继承 Base 的表定义（13 张表），create_all 一次性按依赖顺序建出所有表。
# run_sync 是什么？create_all 是同步函数，而连接是异步的，不能直接 await 它。run_sync 是官方提供的"把同步代码放进异步环境跑"的桥——它开一个独立的同步上下文执行该函数。这是 async SQLAlchemy 建表的标准姿势。
# 建表/删表通常只在开发和测试用（生产用真正的迁移工具 Alembic）。
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as session:
            yield session

    async def dispose(self) -> None:
        await self.engine.dispose()
