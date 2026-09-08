##集中管理数据库、工作区、并发、权限等待和跨域配置
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="EDUHARNESS_",
        extra="ignore",
    )

    app_name: str = "EduHarness"
    environment: str = "development"
    database_url: str = "sqlite+aiosqlite:///./eduharness.db"##默认是异步 sqlite sqlite+aiosqlite:///./eduharness.db，开发环境使用。
    workspace_root: Path = Field(default_factory=Path.cwd)
    cors_origins: list[str] = ["http://localhost:5173"]

    event_queue_size: int = Field(default=512, ge=32, le=10_000)
    event_history_size: int = Field(default=2_000, ge=100, le=50_000)
    approval_timeout_seconds: int = Field(default=300, ge=10, le=3_600)
    max_concurrent_turns: int = Field(default=4, ge=1, le=64)
    ##MCP信任开关，默认关闭
    trust_project_mcp: bool = False
    auto_create_schema: bool = True
    expose_thinking: bool = False
    api_key: str | None = None

    ##教师账号 Token 认证。生产必须用环境变量覆盖默认值。
    auth_secret: str = "dev-insecure-change-me"
    token_ttl_seconds: int = Field(default=7_200, ge=60, le=86_400)

    @field_validator("workspace_root")
    @classmethod
    def normalize_workspace_root(cls, value: Path) -> Path:
        return value.expanduser().resolve()

    def resolve_workspace(self, workspace_id: str) -> Path:
        if workspace_id in {"", ".", "default"}:
            candidate = self.workspace_root
        else:
            candidate = (self.workspace_root / workspace_id).resolve()
        ##安全沙箱校验：子目录不能跳出 workspace_root，路径逃逸防护
        try:
            candidate.relative_to(self.workspace_root)
        except ValueError as exc:
            raise ValueError("workspace_id 超出允许的工作区") from exc
        ##目标目录必须真实存在
        if not candidate.is_dir():
            raise ValueError(f"工作区不存在: {workspace_id}")

        return candidate

##整个项目统一调用get_settings()拿配置，不会多次读取.env、多次解析环境变量。
@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()