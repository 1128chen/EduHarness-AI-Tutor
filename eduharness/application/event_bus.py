##提供线程安全的广播事件总线。Agent 在线程中运行，SSE/WS 在 asyncio 中消费事件。
from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from eduharness.domain.events import EventType, HarnessEvent

PersistCallback = Callable[[HarnessEvent], Awaitable[None]]

##1.一个turn一个实例，（runtime_manager.py 第 77 行在每次启动 turn 时 TurnEventBus(session_id=..., turn_id=turn.id, ...)）。turn 结束就关闭丢弃，新 turn 用新总线。
# ##deque(maxlen=history_size)：Python 的双端队列，设了 maxlen 就变成环形缓冲——塞满 2000 条后，新的事件会自动挤掉最老的。这是"历史重放"的存储，内存有上限。
# _subscribers 是个 set（集合）：存着所有订阅者的队列。用 set 是为了去重 + O(1) 增删。
# _loop 记录事件循环：在 __init__ 里 get_running_loop() 要求必须在事件循环内创建（runtime_manager 的异步上下文里创建的，满足）。记住它，是为了后面 emit_from_worker 能把任务"投递回"这个循环。
class TurnEventBus:
    def __init__(
        self,
        *,
        session_id: str,
        turn_id: str,
        queue_size: int = 512,
        history_size: int = 2_000,
        persist: PersistCallback | None = None,
    ) -> None:
        self.session_id = session_id
        self.turn_id = turn_id
        self.queue_size = queue_size
        self._history = deque(maxlen=history_size)
        self._subscribers: set[asyncio.Queue[HarnessEvent | None]] = set()
        self._persist = persist
        self._sequence = 0
        self._closed = False
        self._lock = asyncio.Lock()
        self._loop = asyncio.get_running_loop()

    @property
    def closed(self) -> bool:
        return self._closed
    ##发布事件（生产端核心）
    async def emit(
        self,
        event_type: EventType,
        data: dict[str, Any] | None = None,
    ) -> HarnessEvent:
        async with self._lock:
            if self._closed:
                raise RuntimeError("event bus is closed")##关闭后禁止再发

            self._sequence += 1
            event = HarnessEvent(
                type=event_type,
                session_id=self.session_id,
                turn_id=self.turn_id,
                sequence=self._sequence,##唯一递增序号
                data=data or {},
            )

            if self._persist is not None:
                await self._persist(event)##持久化（写数据库）

            self._history.append(event)##进历史（供重放）
            subscribers = list(self._subscribers)##锁内拍照订阅者列表

        for queue in subscribers:##锁外逐个投递
            await queue.put(event)

        return event

    def emit_from_worker(
        self,
        event_type: EventType,
        data: dict[str, Any] | None = None,
    ) -> HarnessEvent:
        future = asyncio.run_coroutine_threadsafe(
            self.emit(event_type, data),##将一个协程包装成Future
            self._loop,
        )
        return future.result(timeout=30)

    async def subscribe(
        self,
        *,
        after_sequence: int = 0,
    ) -> AsyncIterator[HarnessEvent]:
        queue: asyncio.Queue[HarnessEvent | None] = asyncio.Queue(
            maxsize=self.queue_size
        )

        async with self._lock:
            replay = [
                event
                for event in self._history
                if event.sequence > after_sequence
            ]
            closed = self._closed

            if not closed:
                self._subscribers.add(queue)# ① 注册：把队列加进订阅者集合


        try:
            for event in replay:# ② 重放：先补发历史
                yield event

            if closed:
                return

            while True:# ③ 实时：循环等新事件
                event = await queue.get()
                if event is None:# ④ 哨兵：收到 None 就结束
                    return
                yield event
        finally:
            async with self._lock:
                self._subscribers.discard(queue)# ⑤ 退订：离开时把自己摘掉

    async def close(self) -> None:
        async with self._lock:
            if self._closed:
                return

            self._closed = True
            subscribers = list(self._subscribers)

        for queue in subscribers:
            await queue.put(None)### 给每个订阅者投递"结束哨兵