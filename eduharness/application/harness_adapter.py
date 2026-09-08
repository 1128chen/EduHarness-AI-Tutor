##封装 run_agent_turn()，将 MiniCode 的回调统一转换为 Harness 事件
from __future__ import annotations

import asyncio
from dataclasses import asdict
from pathlib import Path
from threading import Event
from typing import Any

from minicode.agent_loop import run_agent_turn
from minicode.config import load_runtime_config
from minicode.memory import MemoryManager
from minicode.model_registry import create_model_adapter
from minicode.permissions import PermissionManager
from minicode.prompt import build_system_prompt
from minicode.tools import create_default_tool_registry

from eduharness.application.event_bus import TurnEventBus
from eduharness.application.permission_bridge import PermissionBridge
from eduharness.settings import Settings


class MiniCodeHarnessAdapter:
    def __init__(
        self,
        *,
        settings: Settings,
        permission_bridge: PermissionBridge,##连接 MiniCode 内部PermissionManager和 EduHarness 审批能力；当 MiniCode 需要工具审批时，会回调到本项目的审批接口。
    ) -> None:
        self.settings = settings
        self.permission_bridge = permission_bridge
        prompt_path = (
            Path(__file__).parent.parent
            / "prompts"
            / "tutor_system.md"
        )
        self.tutor_prompt = prompt_path.read_text(encoding="utf-8")


##MiniCode 的 run_agent_turn 是同步阻塞函数，会占用 CPU/IO，不能直接在 asyncio 协程里直接调用，会把整个 asyncio 事件循环卡死。所以代码内部定义同步函数worker()，最后交给asyncio.to_thread()丢到线程池执行。
    async def run_turn(##入参全部来自上层RuntimeManager._execute
        self,
        *,
        session_id: str,
        turn_id: str,
        user_text: str,
        history: list[dict[str, Any]],
        workspace: Path,
        event_bus: TurnEventBus,
        cancel_requested: Event,
    ) -> list[dict[str, Any]]:
        def emit(event_type: str, data: dict[str, Any]) -> None:
            event_bus.emit_from_worker(event_type, data)
##event_bus.emit()是 async 异步方法，普通同步线程不能直接调用 await 异步函数。因此 EventBus 专门封装emit_from_worker，内部通过线程安全队列把事件投递到 asyncio 事件循环，实现跨线程发事件。

        def worker() -> list[dict[str, Any]]:##整个worker()全部是同步代码，不在 asyncio 事件循环线程执行，会被扔到线程池。
            runtime = load_runtime_config(
                workspace,
                trust_project_mcp=self.settings.trust_project_mcp,
            )
            # load_runtime_config是MiniCode提供函数：读取工作目录下的配置文件，得到模型名称、MCP服务配置、工具运行参数；
            # trust_project_mcp控制是否信任项目本地定义的
            # MCP
            # 服务，来自项目全局配置。
            tools = create_default_tool_registry(
                str(workspace),
                runtime=runtime,
            )
            memory = MemoryManager(project_root=workspace)

            permissions = PermissionManager(
                str(workspace),
                prompt=self.permission_bridge.sync_prompt(
                    session_id=session_id,
                    turn_id=turn_id,
                    emit=emit,
                ),
            )
##PermissionManager是 MiniCode 内部权限组件：当 Agent 要执行高危工具（写文件、执行 shell），会触发审批弹窗；
# self.permission_bridge.sync_prompt()：EduHarness 与 MiniCode 的审批桥接。
# 把当前session_id、turn_id、上面定义的emit回调传给底层；
# MiniCode 内部需要人工审批的时候，桥接层会调用emit("approval.required", {...})，向事件总线抛出审批事件；
# 前端收到approval.required，弹出审批 UI；用户确认 / 拒绝之后，HTTP/WebSocket 调用permission_bridge.resolve()，放行 / 拦截工具调用。
            model = create_model_adapter(
                model=runtime.get("model", ""),
                tools=tools,
                runtime=runtime,
            )

            system_prompt = build_system_prompt(
                str(workspace),
                permissions.get_summary(),
                {
                    "skills": tools.get_skills(),
                    "mcpServers": tools.get_mcp_servers(),
                    "memory_context": memory.get_relevant_context(),
                },
            )
            system_prompt = (
                system_prompt
                + "\n\n"
                + self.tutor_prompt##追加本项目自定义导师prompt
            )

            messages: list[dict[str, Any]] = [
                {"role": "system", "content": system_prompt},
                *history,
                {"role": "user", "content": user_text},
            ]

            emit("turn.started", {})
            ##Agent 正式开始执行，向事件总线发出turn.started事件，前端收到可以展示加载状态。

            try:
                if cancel_requested.is_set():
                    return messages
            ##在线程启动后，如果已经收到取消标记，直接返回消息列表，不执行 Agent 主循环。

                result = run_agent_turn(
                    model=model,
                    tools=tools,
                    messages=messages,
                    cwd=str(workspace),
                    permissions=permissions,
                    memory_manager=memory,
                    runtime=runtime,
                    ##下面都是回调函数，Minicode内部各个阶段触发
                    on_tool_start=lambda name, value: emit(
                        "tool.started",
                        {
                            "tool_name": name,
                            "input": value,
                        },
                    ),
                    on_tool_result=lambda name, output, error: emit(
                        "tool.completed",
                        {
                            "tool_name": name,
                            "output": output,
                            "is_error": error,
                        },
                    ),
                    on_progress_message=lambda text: emit(
                        "assistant.progress",
                        {"text": text},
                    ),
                    on_assistant_message=lambda text: emit(
                        "assistant.completed",
                        {"text": text},
                    ),
                    on_runtime_event=lambda event: emit(
                        "runtime.event",
                        asdict(event),
                    ),
                    on_assistant_stream_chunk=lambda text: emit(
                        "model.delta",
                        {"text": text},
                    ),
                    on_thinking_chunk=(
                        (
                            lambda text: emit(
                                "model.thinking_delta",
                                {"text": text},
                            )
                        )
                        if self.settings.expose_thinking
                        else None
                    ),
                )

                emit(
                    "turn.completed",
                    {"cancel_requested": cancel_requested.is_set()},
                )
                return result
        ##返回的result会向上给到RuntimeManager._execute；由上层 RuntimeManager 负责提取 assistant 回复，写入数据库 message 表。
##📌关键点：本适配器只负责跑 Agent、产生事件，不操作数据库写消息；数据库写入交给上层 RuntimeManager，职责分离。
            except Exception as exc:
                emit(
                    "turn.failed",
                    {
                        "error_type": type(exc).__name__,
                        "message": str(exc),
                    },
                )
                raise
        ##无论成功失败，释放工具注册表资源，关闭 MCP 客户端连接等。
            finally:
                tools.dispose()
        ##asyncio.to_thread 包装同步 worker 函数
        return await asyncio.to_thread(worker)
