##向 Agent 暴露知识检索、文档读取、概念和引用工具。


from typing import Any

from mcp.server.fastmcp import FastMCP

from eduharness.infrastructure.repositories import (
    NotFoundError,
)
from eduharness.mcp_servers.common import get_repository

mcp = FastMCP("eduharness-knowledge-base")


@mcp.tool()
async def search_knowledge(
    query: str,
    subject: str | None = None,
    grade: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """搜索课程知识库，返回可引用的知识片段。"""
    repository = await get_repository()

    results = await repository.search_knowledge(
        query=query,
        subject=subject,
        grade=grade,
        limit=min(max(limit, 1), 50),
    )

    return {
        "query": query,
        "count": len(results),
        "results": results,
    }


@mcp.tool()
async def get_knowledge_document(
    document_id: str,
) -> dict[str, Any]:
    """读取知识文档及其全部内容块。"""
    repository = await get_repository()
    return await repository.get_knowledge_document(
        document_id
    )


@mcp.tool()
async def get_concept(
    concept_id: str,
) -> dict[str, Any]:
    """读取知识点定义、描述和先修知识。"""
    repository = await get_repository()
    return await repository.get_knowledge_point(
        concept_id
    )


@mcp.tool()
async def list_prerequisites(
    concept_id: str,
    depth: int = 2,
) -> dict[str, Any]:
    """递归读取知识点的先修关系。"""
    repository = await get_repository()
    max_depth = min(max(depth, 1), 5)
    root = await repository.get_knowledge_point(
        concept_id
    )

    visited: set[str] = set()
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []

    async def visit(
        point: dict[str, Any],
        current_depth: int,
    ) -> None:
        if current_depth > max_depth:
            return

        if point["code"] in visited:
            return

        visited.add(point["code"])
        nodes.append(point)

        for prerequisite_code in point.get(
            "prerequisites",
            [],
        ):
            try:
                prerequisite = (
                    await repository.get_knowledge_point_by_code(
                        prerequisite_code
                    )
                )
            except NotFoundError:
                continue

            edges.append(
                {
                    "from": prerequisite["code"],
                    "to": point["code"],
                }
            )
            await visit(
                prerequisite,
                current_depth + 1,
            )

    await visit(root, 0)

    return {
        "root": root["code"],
        "nodes": nodes,
        "edges": edges,
    }


@mcp.tool()
async def cite_sources(
    chunk_ids: list[str],
) -> dict[str, Any]:
    """将知识片段转换为可审计引用。"""
    repository = await get_repository()
    chunks = await repository.get_knowledge_chunks(
        chunk_ids
    )

    citations = [
        {
            "index": index,
            "chunk_id": chunk["chunk_id"],
            "document_id": chunk["document_id"],
            "title": chunk["title"],
            "source_uri": chunk["source_uri"],
            "quote": chunk["text"][:500],
            "updated_at": chunk["updated_at"],
        }
        for index, chunk in enumerate(
            chunks,
            start=1,
        )
    ]

    return {
        "count": len(citations),
        "citations": citations,
    }


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()