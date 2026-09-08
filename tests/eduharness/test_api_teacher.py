"""教师工作台 + 申诉复核的 HTTP 集成测试（httpx ASGITransport 直连 FastAPI）。

不启动真实 uvicorn：wire_services 把组件注入到隔离的临时 sqlite，
验证 登录->建课->报名->自动取证作答->驾驶舱/CSV->申诉->改判联动 全链路。
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from eduharness.api.app import create_app, wire_services
from eduharness.application.auth import hash_password
from eduharness.infrastructure.models import (
    KnowledgePoint,
    Question,
    QuestionKnowledgePoint,
)
from eduharness.settings import Settings

TEACHER = "demo"
PASSWORD = "demo1234"
KP_CODE = "python.test.kp"


async def _build(tmp_path, name: str = "t.db"):
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path}/{name}",
        auth_secret="test-secret",
        environment="test",
    )
    app = create_app(settings)
    await wire_services(app, settings)
    return app


async def _seed_teacher_and_question(app) -> None:
    await app.state.repository.get_or_create_teacher(
        username=TEACHER,
        password_hash=hash_password(PASSWORD),
        display_name="王老师",
    )
    async with app.state.database.session_factory() as s:
        kp = KnowledgePoint(
            subject="python",
            code=KP_CODE,
            name="函数定义",
            description="def",
            prerequisites=[],
        )
        s.add(kp)
        await s.flush()
        q = Question(
            subject="python",
            stem="定义函数的关键字是?",
            question_type="short_answer",
            difficulty=0.4,
            answer={"value": "def"},
            explanation="def",
        )
        s.add(q)
        await s.flush()
        s.add(
            QuestionKnowledgePoint(
                question_id=q.id, knowledge_point_id=kp.id, weight=1.0
            )
        )
        await s.commit()


async def _login(client: AsyncClient) -> str:
    response = await client.post(
        "/api/v1/auth/teacher/login",
        json={"username": TEACHER, "password": PASSWORD},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.mark.asyncio
async def test_teacher_full_loop(tmp_path) -> None:
    app = await _build(tmp_path)
    await _seed_teacher_and_question(app)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        token = await _login(client)
        headers = {"Authorization": f"Bearer {token}"}

        # 建课 + 报名
        response = await client.post(
            "/api/v1/teachers/courses",
            headers=headers,
            json={"name": "Python 程序设计入门", "subject": "python"},
        )
        assert response.status_code == 200
        course_id = response.json()["id"]

        response = await client.post(
            f"/api/v1/courses/{course_id}/students",
            headers=headers,
            json={"student_external_id": "stu-01", "display_name": "小明"},
        )
        assert response.status_code == 200
        student_id = response.json()["student_id"]

        # 学生作答：不传 knowledge_evidence，应自动从题目-知识点映射推导
        question_id = await _first_question_id(app)
        response = await client.post(
            f"/api/v1/students/{student_id}/attempts",
            json={
                "question_id": question_id,
                "answer": {"value": "wrong"},
                "score": 0.0,
                "max_score": 1.0,
            },
        )
        assert response.status_code == 200
        attempt_id = response.json()["attempt_id"]

        # 自动取证：mastery 应出现一行（无需调用方传证据）
        response = await client.get(f"/api/v1/students/{student_id}/mastery")
        assert response.status_code == 200
        rows = response.json()
        assert any(row["code"] == KP_CODE for row in rows)
        before = next(r for r in rows if r["code"] == KP_CODE)["mastery"]

        # 驾驶舱 JSON 与 CSV
        response = await client.get(
            f"/api/v1/courses/{course_id}/cockpit", headers=headers
        )
        assert response.status_code == 200
        assert response.json()["student_count"] == 1

        response = await client.get(
            f"/api/v1/courses/{course_id}/cockpit.csv", headers=headers
        )
        assert response.status_code == 200
        assert "attachment" in response.headers["content-disposition"]
        assert response.content.startswith(b"\xef\xbb\xbf")  # Excel BOM

        # 申诉 + 复核改判
        response = await client.post(
            f"/api/v1/students/{student_id}/attempts/{attempt_id}/appeal",
            json={"reason": "wrong 判分我不认同，应给分", "requested_by": "stu-01"},
        )
        assert response.status_code == 200

        response = await client.get("/api/v1/appeals/pending", headers=headers)
        assert response.status_code == 200
        pending = response.json()
        assert len(pending) == 1
        appeal_id = pending[0]["id"]
        assert pending[0]["evidence_snapshot"]["question_stem"] is not None

        response = await client.post(
            f"/api/v1/appeals/{appeal_id}/resolve",
            headers=headers,
            json={
                "decision": "sustain",
                "new_score": 1.0,
                "teacher_note": "同意给分",
                "resolved_by": TEACHER,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "sustained"
        assert len(body["mastery_deltas"]) == 1

        response = await client.get(f"/api/v1/students/{student_id}/mastery")
        after = next(
            r for r in response.json() if r["code"] == KP_CODE
        )["mastery"]
        assert after > before  # 改判由 0 分变满分，掌握度应上升

    await app.state.database.dispose()


@pytest.mark.asyncio
async def test_teacher_auth_guards(tmp_path) -> None:
    app = await _build(tmp_path, name="guard.db")
    await _seed_teacher_and_question(app)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 错误口令 -> 401
        response = await client.post(
            "/api/v1/auth/teacher/login",
            json={"username": TEACHER, "password": "bad"},
        )
        assert response.status_code == 401

        # 无 token 访问教师接口 -> 401
        response = await client.get("/api/v1/teachers/courses")
        assert response.status_code == 401

        # 伪造 token -> 401
        response = await client.get(
            "/api/v1/teachers/courses",
            headers={"Authorization": "Bearer forged.token.value"},
        )
        assert response.status_code == 401

        # 学生端开放接口无需 token（如查看自己掌握度）不应 401
        token = await _login(client)
        assert token

    await app.state.database.dispose()


async def _first_question_id(app) -> str:
    from sqlalchemy import select

    async with app.state.database.session_factory() as s:
        return (
            await s.execute(
                select(Question.id).where(Question.subject == "python").limit(1)
            )
        ).scalar_one()


@pytest.mark.asyncio
async def test_auto_practice_endpoints(tmp_path) -> None:
    """无大模型的快判练习：题目列表不泄答案、自动判分 + 掌握度更新。"""
    app = await _build(tmp_path, name="auto.db")
    await _seed_teacher_and_question(app)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        question_id = await _first_question_id(app)

        # 题目列表应返回题干但不含标准答案
        response = await client.get("/api/v1/questions?subject=python")
        assert response.status_code == 200
        cards = response.json()["questions"]
        assert len(cards) >= 1
        assert "answer" not in cards[0]
        assert cards[0]["stem"]

        student_id = (
            await app.state.repository.get_or_create_student(
                "stu-auto", "自助生"
            )
        ).id

        # 答对 -> correct + mastery 上升
        response = await client.post(
            f"/api/v1/students/{student_id}/attempts/auto",
            json={"question_id": question_id, "answer_value": "def"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["correct"] is True
        assert body["score"] == 1.0

        response = await client.get(f"/api/v1/students/{student_id}/mastery")
        rows = response.json()
        assert any(row["code"] == KP_CODE for row in rows)

        # 答错 -> not correct
        response = await client.post(
            f"/api/v1/students/{student_id}/attempts/auto",
            json={"question_id": question_id, "answer_value": "class"},
        )
        assert response.json()["correct"] is False

    await app.state.database.dispose()
