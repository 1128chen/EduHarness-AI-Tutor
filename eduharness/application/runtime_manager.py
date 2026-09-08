##限制并发、确保同一会话只能运行一个 turn，并保存消息与状态。
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from threading import Event

from eduharness.application.event_bus import TurnEventBus
from eduharness.application.harness_adapter import (
    MiniCodeHarnessAdapter,
)
from eduharness.infrastructure.repositories import (
    EduRepository,
    RepositoryError,
)
from eduharness.settings import Settings

##内存对象，只保存在进程内存，不持久化数据库，代表一个正在运行的 Turn。
@dataclass(slots=True)
class ActiveTurn:
    turn_id: str
    session_id: str
    bus: TurnEventBus
    cancel_requested: Event
    task: asyncio.Task[None]


class RuntimeManager:
    def __init__(
        self,
        *,
        settings: Settings,
        repository: EduRepository,
        harness: MiniCodeHarnessAdapter,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.harness = harness
        self._semaphore = asyncio.Semaphore(
            settings.max_concurrent_turns
        )##asyncio.Semaphore异步信号量，用来做全局并发限流。max_concurrent_turns配置最大同时运行 Agent 任务数量。
##async with self._semaphore: 同一时间最多 N 个协程进入上下文；超过的任务会在信号量处挂起排队，不会直接报错。
##作用：防止大模型并发请求打垮模型服务，限制系统整体负载。
        self._turns: dict[str, ActiveTurn] = {}
        self._active_sessions: dict[str, str] = {}
        self._lock = asyncio.Lock()
        ##异步锁。多请求同时调用start_turn()，会并发读写_turns、_active_sessions两个共享字典。asyncio.Lock()保证同一时刻只有一个协程操作内存状态，防止并发下字典状态错乱。

    async def start_turn(
        self,
        *,
        session_id: str,
        user_text: str,
        workspace: Path,
    ) -> str:
        async with self._lock:
            ##防止同一个session同时跑多个turn】核心逻辑
            if session_id in self._active_sessions:
                raise RepositoryError(
                    "该会话已有正在执行的 turn"
                )
            ##读取历史消息，给大模型上下文
            history = await self.repository.list_messages(
                session_id
            )
            ##数据库创建turn记录，状态初始为queued
            turn = await self.repository.create_turn(session_id)
            ##用户消息持久化存入message表
            await self.repository.append_message(
                session_id=session_id,
                turn_id=turn.id,
                role="user",
                content=user_text,
            )
            # 创建本turn专属事件总线
            bus = TurnEventBus(
                session_id=session_id,
                turn_id=turn.id,
                queue_size=self.settings.event_queue_size,
                history_size=self.settings.event_history_size,
                persist=self.repository.append_event,##将事件持久化数据库
            )
            cancel_requested = Event()
            # ✅创建内存后台协程任务，真正执行Agent逻辑，进程消失任务直接销毁
            task = asyncio.create_task(##将协程包装成后台Task,立刻返回不会等待协程执行完毕
                self._execute(
                    session_id=session_id,
                    turn_id=turn.id,
                    user_text=user_text,
                    history=history,
                    workspace=workspace,
                    bus=bus,
                    cancel_requested=cancel_requested,
                )
            )
            # 封装内存ActiveTurn对象
            active = ActiveTurn(
                turn_id=turn.id,
                session_id=session_id,
                bus=bus,
                cancel_requested=cancel_requested,
                task=task,
            )
            # 存入内存两个字典
            self._turns[turn.id] = active
            self._active_sessions[session_id] = turn.id
            return turn.id

    async def _execute(
        self,
        *,
        session_id: str,
        turn_id: str,
        user_text: str,
        history: list[dict],
        workspace: Path,
        bus: TurnEventBus,
        cancel_requested: Event,
    ) -> None:
        try:
            async with self._semaphore:
                # 获取到信号量，更新turn数据库状态 running
                await self.repository.update_turn_status(
                    turn_id,
                    "running",
                )
                # 调用底层MiniCodeHarnessAdapter，真正跑Agent
                result = await self.harness.run_turn(
                    session_id=session_id,
                    turn_id=turn_id,
                    user_text=user_text,
                    history=history,
                    workspace=workspace,
                    event_bus=bus,
                    cancel_requested=cancel_requested,
                )

                final_text = ""
                # 1.优先从harness返回结果取assistant消息
                for message in reversed(result):
                    if message.get("role") == "assistant":
                        content = str(message.get("content", "")).strip()
                        if content:
                            final_text = content
                            break

                events = await self.repository.list_events(turn_id)
                # 2.上面拿不到，去数据库事件里找assistant.completed事件
                if not final_text:
                    for event in reversed(events):
                        if event.type == "assistant.completed":
                            content = str(
                                event.data.get("text", "")
                            ).strip()
                            if content:
                                final_text = content
                                break
                # 3.还拿不到，拼接全部model.delta流式片段
                if not final_text:
                    final_text = "".join(
                        str(event.data.get("text", ""))
                        for event in events
                        if event.type == "model.delta"
                    ).strip()
                # 4.全部失败抛出异常
                if not final_text:
                    raise RuntimeError(
                        "Agent执行完成，但没有获得最终回答文本"
                    )
                # 助手回复存入数据库message表
                await self.repository.append_message(
                    session_id=session_id,
                    turn_id=turn_id,
                    role="assistant",
                    content=final_text,
                )
                # 判断最终状态：是被取消，还是正常完成
                status = (
                    "cancelled"
                    if cancel_requested.is_set()
                    else "completed"
                )
                await self.repository.update_turn_status(
                    turn_id,
                    status,
                )

        #         result = await self.harness.run_turn(
        #             session_id=session_id,
        #             turn_id=turn_id,
        #             user_text=user_text,
        #             history=history,
        #             workspace=workspace,
        #             event_bus=bus,
        #             cancel_requested=cancel_requested,
        #         )
        #
        #         final_message = next(
        #             (
        #                 message
        #                 for message in reversed(result)
        #                 if message.get("role") == "assistant"
        #             ),
        #             None,
        #         )
        #
        #         if final_message:
        #             await self.repository.append_message(
        #                 session_id=session_id,
        #                 turn_id=turn_id,
        #                 role="assistant",
        #                 content=str(
        #                     final_message.get("content", "")
        #                 ),
        #             )
        #
        #         status = (
        #             "cancelled"
        #             if cancel_requested.is_set()
        #             else "completed"
        #         )
        #         await self.repository.update_turn_status(
        #             turn_id,
        #             status,
        #         )
        # except Exception as exc:
        #     await self.repository.update_turn_status(
        #         turn_id,
        #         "failed",
        #         error_code=type(exc).__name__,
        #         error_message=str(exc),
        #     )
        finally:##不管正常结束、抛出异常、任务被取消，一定会执行
            await bus.close()##关闭事件总线，停止事件生产；

            async with self._lock:##加锁，从_active_sessions字典删除当前 session_id
                self._active_sessions.pop(session_id, None)

    def require_bus(self, turn_id: str) -> TurnEventBus:
        active = self._turns.get(turn_id)
        if active is None:
            raise RepositoryError("turn事件流不在当前进程中")
        return active.bus

    async def cancel_turn(self, turn_id: str) -> None:##请求取消任务
        active = self._turns.get(turn_id)
        if active is None:
            raise RepositoryError("turn不存在或已经结束")

        active.cancel_requested.set()
        await active.bus.emit(
            "turn.cancel_requested",
            {},
        )

    async def shutdown(self) -> None:
        active_turns = list(self._turns.values())

        for active in active_turns:
            if not active.task.done():
                active.cancel_requested.set()

        if active_turns:
            await asyncio.gather(
                *(active.task for active in active_turns),
                return_exceptions=True,
            )