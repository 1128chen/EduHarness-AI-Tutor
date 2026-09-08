##把 MiniCode 同步权限询问转换为 Web 审批事件，并阻塞工作线程等待用户决策。
from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field
from datetime import timedelta
from datetime import datetime, timezone
# 手动定义 UTC（兼容 Python 3.10 及以下）
UTC = timezone.utc
from typing import Any, Callable
from uuid import uuid4

from eduharness.infrastructure.repositories import (
    EduRepository,
    RepositoryError,
)


@dataclass(slots=True)
class PendingApproval:
    approval_id: str
    session_id: str
    turn_id: str
    request: dict[str, Any]
    expires_at: datetime
    ready: threading.Event = field(default_factory=threading.Event)
    response: dict[str, Any] | None = None


class PermissionBridge:
    def __init__(
        self,
        repository: EduRepository,
        *,
        timeout_seconds: int = 300,
    ) -> None:
        self.repository = repository
        self.timeout_seconds = timeout_seconds
        self._pending: dict[str, PendingApproval] = {}
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self) -> None:
        self._loop = asyncio.get_running_loop()

    def sync_prompt(
        self,
        *,
        session_id: str,
        turn_id: str,
        emit: Callable[[str, dict[str, Any]], Any],
    ) -> Callable[[dict[str, Any]], dict[str, Any]]:
        def prompt(request: dict[str, Any]) -> dict[str, Any]:
            if self._loop is None:
                raise RuntimeError("permission bridge is not bound")

            approval_id = str(uuid4())
            expires_at = datetime.now(UTC) + timedelta(
                seconds=self.timeout_seconds
            )
            pending = PendingApproval(
                approval_id=approval_id,
                session_id=session_id,
                turn_id=turn_id,
                request=request,
                expires_at=expires_at,
            )

            with self._lock:
                self._pending[approval_id] = pending

            future = asyncio.run_coroutine_threadsafe(
                self.repository.create_approval(
                    approval_id=approval_id,
                    turn_id=turn_id,
                    request=request,
                    expires_at=expires_at,
                ),
                self._loop,
            )
            future.result(timeout=30)

            emit(
                "approval.required",
                {
                    "approval_id": approval_id,
                    "request": request,
                    "expires_at": expires_at.isoformat(),
                },
            )

            if not pending.ready.wait(self.timeout_seconds):
                with self._lock:
                    self._pending.pop(approval_id, None)

                return {
                    "decision": "deny_once",
                    "reason": "approval_timeout",
                }

            with self._lock:
                self._pending.pop(approval_id, None)

            return pending.response or {"decision": "deny_once"}

        return prompt
##web接口调用的异步方法
    async def resolve(
        self,
        approval_id: str,
        *,
        decision: str,
        feedback: str | None = None,
        resolved_by: str | None = None,
    ) -> PendingApproval:
        with self._lock:
            pending = self._pending.get(approval_id)

        if pending is None:
            raise RepositoryError(
                "approval不存在、已处理或已经超时"
            )

        allowed_decisions = {
            str(choice.get("decision"))
            for choice in pending.request.get("choices", [])
        }
        if decision not in allowed_decisions:
            raise RepositoryError(
                f"该审批不允许决策: {decision}"
            )

        await self.repository.resolve_approval(
            approval_id,
            decision=decision,
            feedback=feedback,
            resolved_by=resolved_by,
        )

        pending.response = {
            "decision": decision,
            "feedback": feedback or "",
        }
        pending.ready.set()
        return pending