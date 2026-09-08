import asyncio

from sqlalchemy import select

from eduharness.infrastructure.database import Database
from eduharness.infrastructure.models import (
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgePoint,
    Question,
    QuestionKnowledgePoint,
)
from eduharness.settings import get_settings


async def main() -> None:
    settings = get_settings()
    database = Database(settings.database_url)
    await database.create_schema()

    async with database.session_factory() as db:
        existing = await db.execute(
            select(KnowledgePoint).where(
                KnowledgePoint.code
                == "math.algebra.linear_equation"
            )
        )
        point = existing.scalar_one_or_none()

        if point is None:
            point = KnowledgePoint(
                subject="math",
                code="math.algebra.linear_equation",
                name="一元一次方程",
                description=(
                    "只含一个未知数，且未知数最高次数为1的方程。"
                ),
                prerequisites=[
                    "math.arithmetic.signed_numbers"
                ],
            )
            db.add(point)
            await db.flush()

        question_result = await db.execute(
            select(Question).where(
                Question.stem == "解方程：2x + 3 = 11"
            )
        )
        question = question_result.scalar_one_or_none()

        if question is None:
            question = Question(
                subject="math",
                stem="解方程：2x + 3 = 11",
                question_type="short_answer",
                difficulty=0.3,
                answer={"value": "4"},
                explanation=(
                    "两边同时减3，得到2x=8；"
                    "两边同时除以2，得到x=4。"
                ),
            )
            db.add(question)
            await db.flush()
            db.add(
                QuestionKnowledgePoint(
                    question_id=question.id,
                    knowledge_point_id=point.id,
                    weight=1.0,
                )
            )

        document_result = await db.execute(
            select(KnowledgeDocument).where(
                KnowledgeDocument.title
                == "一元一次方程基础"
            )
        )
        document = document_result.scalar_one_or_none()

        if document is None:
            document = KnowledgeDocument(
                subject="math",
                title="一元一次方程基础",
                source_uri="edu://math/linear-equation",
                grade="初中",
            )
            db.add(document)
            await db.flush()

            db.add_all(
                [
                    KnowledgeChunk(
                        document_id=document.id,
                        ordinal=1,
                        content=(
                            "一元一次方程的一般形式是"
                            "ax+b=0，其中a不等于0。"
                        ),
                        metadata_json={
                            "concept_code": point.code
                        },
                    ),
                    KnowledgeChunk(
                        document_id=document.id,
                        ordinal=2,
                        content=(
                            "解方程时，对等式两边执行相同操作，"
                            "等式仍然成立。"
                        ),
                        metadata_json={
                            "concept_code": point.code
                        },
                    ),
                ]
            )

        await _seed_knowledge_document(
            db,
            subject="math",
            title="导数定义与基本法则",
            source_uri="edu://math/derivative",
            grade="高中",
            chunks=[
                (
                    1,
                    "导数描述函数在某一点的变化率。"
                    "函数f(x)在x0处的导数定义为"
                    "f'(x0) = lim(h->0) [f(x0+h)-f(x0)]/h。",
                ),
                (
                    2,
                    "幂函数求导法则：f(x) = x^n 的导数为"
                    " f'(x) = n*x^(n-1)。",
                ),
            ],
        )
        await _seed_knowledge_document(
            db,
            subject="physics",
            title="牛顿第二定律",
            source_uri="edu://physics/newton-second-law",
            grade="高中",
            chunks=[
                (
                    1,
                    "牛顿第二定律：物体的加速度与所受合力成正比，"
                    "与质量成反比，即 F = ma。",
                ),
                (
                    2,
                    "F = ma 中，F为合力，m为质量，a为加速度，"
                    "方向与合力方向一致。",
                ),
            ],
        )

        await db.commit()

    await database.dispose()
    print("Education seed data inserted.")


async def _seed_knowledge_document(
    db,
    *,
    subject: str,
    title: str,
    source_uri: str,
    grade: str,
    chunks: list[tuple[int, str]],
) -> None:
    from eduharness.infrastructure.models import (
        KnowledgeChunk,
        KnowledgeDocument,
    )

    existing = await db.execute(
        select(KnowledgeDocument).where(
            KnowledgeDocument.title == title
        )
    )
    document = existing.scalar_one_or_none()

    if document is None:
        document = KnowledgeDocument(
            subject=subject,
            title=title,
            source_uri=source_uri,
            grade=grade,
        )
        db.add(document)
        await db.flush()

        db.add_all(
            [
                KnowledgeChunk(
                    document_id=document.id,
                    ordinal=ordinal,
                    content=content,
                    metadata_json={},
                )
                for ordinal, content in chunks
            ]
        )


if __name__ == "__main__":
    asyncio.run(main())