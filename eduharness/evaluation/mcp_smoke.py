from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


MODULES = {
    "question_bank": "eduharness.mcp_servers.question_bank",
    "knowledge_base": "eduharness.mcp_servers.knowledge_base",
}


def serialize(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, list):
        return [serialize(item) for item in value]
    if isinstance(value, dict):
        return {key: serialize(item) for key, item in value.items()}
    return str(value)


async def run(
    server_name: str,
    tool_name: str | None,
    arguments: dict[str, Any],
) -> None:
    module = MODULES[server_name]

    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", module],
    )

    async with stdio_client(parameters) as streams:
        read_stream, write_stream = streams

        async with ClientSession(
            read_stream,
            write_stream,
        ) as session:
            await session.initialize()

            tools_result = await session.list_tools()
            tools = tools_result.tools

            print(f"SERVER={server_name}")
            print(f"TOOL_COUNT={len(tools)}")

            for tool in tools:
                print("-" * 70)
                print(f"NAME={tool.name}")
                print(f"DESCRIPTION={tool.description}")
                print(
                    "SCHEMA="
                    + json.dumps(
                        tool.inputSchema,
                        ensure_ascii=False,
                        indent=2,
                    )
                )

            if tool_name:
                available = {tool.name for tool in tools}
                if tool_name not in available:
                    raise RuntimeError(
                        f"Tool {tool_name} not found. "
                        f"Available: {sorted(available)}"
                    )

                result = await session.call_tool(
                    tool_name,
                    arguments=arguments,
                )
                print("-" * 70)
                print("CALL_RESULT=")
                print(
                    json.dumps(
                        serialize(result),
                        ensure_ascii=False,
                        indent=2,
                    )
                )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "server",
        choices=sorted(MODULES),
    )
    parser.add_argument("--tool")
    parser.add_argument("--arguments", default="{}")
    args = parser.parse_args()

    arguments = json.loads(args.arguments)
    asyncio.run(run(args.server, args.tool, arguments))


if __name__ == "__main__":
    main()