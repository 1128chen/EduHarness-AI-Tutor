from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
# 手动定义 UTC（兼容 Python 3.10 及以下）
UTC = timezone.utc
from typing import Any, Literal
from uuid import uuid4

##EventType字面量类型，全部合法事件名称集合，就是整套事件契约。
##每个字符串代表 Agent 生命周期的一个状态节点
EventType = Literal[
    "turn.started",
    "model.delta",
    "model.thinking_delta",
    "assistant.progress",
    "assistant.completed",
    "tool.started",
    "tool.completed",
    "runtime.event",
    "approval.required",##需要人工审批，弹出审批弹窗给前端
    "approval.resolved",
    "turn.cancel_requested",
    "turn.failed",
    "turn.completed",
    "stream.closed",
]


@dataclass(frozen=True, slots=True)
class HarnessEvent:
    type: EventType
    session_id: str
    turn_id: str
    sequence: int
    data: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(
        default_factory=lambda: str(uuid4())
    )
    created_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    ##event.to_dict()转为字典
##json 序列化，通过 websocket 推送 JSON 字符串给到前端。
    def to_dict(self) -> dict[str, Any]:##对象-字典，后端发给前端
        return asdict(self)##dataclass 标准函数，把整个 dataclass 实例转为普通 python 字典。



    @classmethod
    def from_dict(##字典转化为HarnessEvent对象：接收来自网络/缓存读取的事件字典，还原成HarnessEvent实例
        cls,
        value: dict[str, Any],
    ) -> "HarnessEvent":
        return cls(
            type=value["type"],
            session_id=str(value.get("session_id", "")),
            turn_id=str(value["turn_id"]),
            sequence=int(value["sequence"]),
            data=dict(value.get("data") or {}),
            event_id=str(
                value.get("event_id") or uuid4()
            ),
            created_at=str(
                value.get("created_at")
                or datetime.now(UTC).isoformat()
            ),
        )