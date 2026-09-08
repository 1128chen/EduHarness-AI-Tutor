##创建FastAPI应用、初始化数据库与服务，并在退出时释放资源
from __future__ import annotations

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from eduharness.api.routes import router
from eduharness.application.harness_adapter import (
    MiniCodeHarnessAdapter,
)
from eduharness.application.learning_service import (
    LearningService,
)
from eduharness.application.leetcode_service import (
    LeetCodeService,
)
from eduharness.application.permission_bridge import (
    PermissionBridge,
)
from eduharness.application.runtime_manager import (
    RuntimeManager,
)
from eduharness.infrastructure.database import Database
from eduharness.infrastructure.repositories import (
    EduRepository,
)
from eduharness.settings import Settings, get_settings


##把"组件装配"抽成独立函数：lifespan 生产用同一份装配，
##测试也能复用它，对隔离的临时库注入组件，而不会触碰真实 eduharness.db。
async def wire_services(
    app: FastAPI,
    resolved_settings: Settings,
) -> FastAPI:
    # ==========【服务启动阶段】==========：初始化数据库、仓库、运行时等全局单例
    database = Database(
        resolved_settings.database_url,
        echo=resolved_settings.environment == "development",
    )
    # 是否自动建表，由配置 auto_create_schema 控制
    if resolved_settings.auto_create_schema:
        await database.create_schema()

    repository = EduRepository(
        database.session_factory
    )

    permission_bridge = PermissionBridge(
        repository,
        timeout_seconds=(
            resolved_settings.approval_timeout_seconds
        ),
    )
    permission_bridge.bind_loop()

    harness = MiniCodeHarnessAdapter(
        settings=resolved_settings,
        permission_bridge=permission_bridge,
    )

    runtime = RuntimeManager(
        settings=resolved_settings,
        repository=repository,
        harness=harness,
    )

    learning_service = LearningService(repository)
    leetcode_service = LeetCodeService(repository)

    # 把所有组件挂载到 app.state，全局接口路由可以通过request.app.state访问这些对象
    app.state.settings = resolved_settings
    app.state.database = database
    app.state.repository = repository
    app.state.permission_bridge = permission_bridge
    app.state.harness = harness
    app.state.runtime = runtime
    app.state.learning_service = learning_service
    app.state.leetcode_service = leetcode_service
    return app


def create_app(
    settings: Settings | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()

    @asynccontextmanager##异步上下文管理器
    async def lifespan(app: FastAPI):
        await wire_services(app, resolved_settings)
        try:
            yield##这里切到：服务正式接收HTTP请求，对外提供API
        finally:
            # ==========【服务关闭阶段：yield之后 finally块】==========
            await app.state.runtime.shutdown()
            await app.state.database.dispose()

    ##实例化FastAPI,传入上面写好的lifespan生命周期管理器
    app = FastAPI(
        title=resolved_settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )
    ##注册中间件，CORS 中间件读取 settings 中的cors_origins配置。
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],##允许全部HTTP方法GET/POST/PUT/DELETE
        allow_headers=["*"],
    )
    ##注册路由,HTTP接口接受请求
    app.include_router(router)
    return app


app = create_app()


def run() -> None:
    uvicorn.run(
        "eduharness.api.app:app",##模块路径：app实例
        host="127.0.0.1",
        port=8000,
        reload=False,
    )


if __name__ == "__main__":
    run()
