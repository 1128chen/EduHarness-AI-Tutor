from __future__ import annotations

import asyncio
import csv
import io
import json
from contextlib import suppress
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse

from eduharness.api.schemas import (
    AppealCreateRequest,
    AppealResolveRequest,
    ApprovalDecisionRequest,
    AutoAttemptRequest,
    CodingAttemptRequest,
    CourseCreateRequest,
    CreateSessionRequest,
    EnrollStudentRequest,
    RecordAttemptRequest,
    SendMessageRequest,
    SessionResponse,
    TeacherLoginRequest,
    TodayPlanRequest,
    TurnResponse,
    WebSocketMessage,
)
from eduharness.application.auth import (
    TokenError,
    create_token,
    verify_password,
    verify_token,
)
from eduharness.infrastructure.repositories import (
    EduRepository,
    NotFoundError,
    RepositoryError,
)

router = APIRouter(prefix="/api/v1")


def get_repository(request: Request) -> EduRepository:
    return request.app.state.repository


def get_runtime(request: Request):
    return request.app.state.runtime


def get_permission_bridge(request: Request):
    return request.app.state.permission_bridge


def get_learning_service(request: Request):
    return request.app.state.learning_service


def get_settings(request: Request):
    return request.app.state.settings


def get_leetcode_service(request: Request):
    return request.app.state.leetcode_service
##以上的四个函数，这些对象全部是应用全局单例，在lifespan生命周期初始化，挂载到app.state。
##通过 FastAPI Depends()依赖注入，接口函数直接拿到仓库、运行时、权限桥、学习服务、配置，不需要自己实例化

async def verify_api_key(
    request: Request,
    x_api_key: str | None = Header(default=None),
) -> None:
    expected = request.app.state.settings.api_key

    if expected and x_api_key != expected:
        raise HTTPException(
            status_code=401,
            detail="invalid API key",
        )


##教师鉴权依赖：解析 Authorization: Bearer <token>，校验签名与过期，并限定 role=teacher。
async def require_teacher(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=401,
            detail="缺少 Authorization: Bearer <token>",
        )

    try:
        payload = verify_token(
            authorization.split(" ", 1)[1].strip(),
            secret=request.app.state.settings.auth_secret,
        )
    except TokenError as exc:
        raise HTTPException(
            status_code=401,
            detail=str(exc),
        ) from exc

    if payload.get("role") != "teacher":
        raise HTTPException(
            status_code=403,
            detail="该接口仅教师可访问",
        )
    return payload


async def _load_course_owned(
    course_id: str,
    teacher_id: str,
    repository: EduRepository,
):
    try:
        course = await repository.get_course(course_id)
    except NotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    if course.teacher_id != teacher_id:
        raise HTTPException(
            status_code=403,
            detail="无权访问该课程",
        )
    return course

##liveness 存活探针：进程是否活着，直接返回 ok。k8s 用于判断进程有没有卡死。
@router.get("/health/live")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}

##readiness 就绪探针：检测数据库是否可连通，执行SELECT 1；数据库不可访问返回 503。k8s 流量不会转发给未就绪实例。
@router.get("/health/ready")
async def readiness(
    request: Request,
) -> dict[str, Any]:
    database = request.app.state.database

    try:
        async with database.session_factory() as db:
            await db.execute(
                __import__("sqlalchemy").text("SELECT 1")
            )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"database unavailable: {exc}",
        ) from exc

    return {
        "status": "ready",
        "database": "ok",
        "environment": request.app.state.settings.environment,
    }


@router.post(
    "/sessions",
    response_model=SessionResponse,
    dependencies=[Depends(verify_api_key)],
)
async def create_session(
    payload: CreateSessionRequest,
    repository: EduRepository = Depends(get_repository),
    settings=Depends(get_settings),
) -> SessionResponse:
    try:
        # 校验workspace_id，做路径沙箱校验（回顾settings模块）
        settings.resolve_workspace(payload.workspace_id)
        # get_or_create_student：有就查，没有新建学生记录
        student = await repository.get_or_create_student(
            external_id=payload.student_external_id,
            display_name=payload.student_display_name,
        )
        # 创建学习会话Session数据库记录
        session = await repository.create_learning_session(
            student_id=student.id,
            workspace_id=payload.workspace_id,
            title=payload.title,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    return SessionResponse(   ##ORM 对象转为SessionResponseSchema 返回前端
        id=session.id,
        student_id=session.student_id,
        workspace_id=session.workspace_id,
        title=session.title,
        status=session.status,
    )

##根据 session_id 查询会话；找不到抛NotFoundError转为 404；ORM 对象转SessionResponse返回。
@router.get(
    "/sessions/{session_id}",
    response_model=SessionResponse,
    dependencies=[Depends(verify_api_key)],
)
async def get_session(
    session_id: str,
    repository: EduRepository = Depends(get_repository),
) -> SessionResponse:
    try:
        session = await repository.get_learning_session(
            session_id
        )
    except NotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    return SessionResponse(
        id=session.id,
        student_id=session.student_id,
        workspace_id=session.workspace_id,
        title=session.title,
        status=session.status,
    )

##post接口仅仅提交任务，不返回大模型结果，模型输出、工具调用、审批弹窗全部通过【订阅 Turn 事件接口】流式获取。
##接口返回状态码202 Accepted：任务已接收，但是没有执行完毕，异步任务。入参：SendMessageRequest，用户消息 content。
@router.post(
    "/sessions/{session_id}/turns",
    response_model=TurnResponse,
    status_code=202,
    dependencies=[Depends(verify_api_key)],
)
async def create_turn(
    session_id: str,
    payload: SendMessageRequest,
    repository: EduRepository = Depends(get_repository),
    runtime=Depends(get_runtime),
    settings=Depends(get_settings),
) -> TurnResponse:
    try:
        # 1.校验session是否真实存在
        session = await repository.get_learning_session(
            session_id
        )
        # 校验会话绑定的workspace
        workspace = settings.resolve_workspace(
            session.workspace_id
        )
        # 2.调用RuntimeManager启动一轮Agent交互任务
        turn_id = await runtime.start_turn(
            session_id=session_id,
            user_text=payload.content,
            workspace=workspace,
        )
        ##runtime.start_turn()：
##在 Repository 层创建 Turn 数据库持久化记录；状态置为queued排队；
##在 Runtime 内部开启 Agent 后台任务，开始跑大模型、工具调用；
##返回turn_id；
    except NotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
    except (RepositoryError, ValueError) as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    return TurnResponse(
        turn_id=turn_id,
        session_id=session_id,
        status="queued",
    )

##根据 turn_id 查询单轮任务状态，客户端可以轮询这个接口，不需要长连接也能知道任务是否完成。
@router.get(
    "/turns/{turn_id}",
    dependencies=[Depends(verify_api_key)],
)
async def get_turn(
    turn_id: str,
    repository: EduRepository = Depends(get_repository),
) -> dict[str, Any]:
    try:
        turn = await repository.get_turn(turn_id)
    except NotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    return {
        "id": turn.id,
        "session_id": turn.session_id,
        "status": turn.status,
        "model_id": turn.model_id,
        "error_code": turn.error_code,
        "error_message": turn.error_message,
        "started_at": turn.started_at,
        "completed_at": turn.completed_at,
    }

##订阅Turn事件Get，SSE流式接口
@router.get(
    "/turns/{turn_id}/events",
    dependencies=[Depends(verify_api_key)],
)
async def stream_turn_events(
    turn_id: str,
    request: Request,
    after_sequence: int = Query(default=0, ge=0),
):
    repository = request.app.state.repository
    runtime = request.app.state.runtime

    try:
        turn = await repository.get_turn(turn_id)
    except NotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    last_event_id = request.headers.get(
        "last-event-id"
    )
    if last_event_id and last_event_id.isdigit():
        after_sequence = max(
            after_sequence,
            int(last_event_id),
        )

    async def generate():
        last_sequence = after_sequence

        try:
            # 1.先从数据库读取已经持久化的历史事件
            persisted = await repository.list_events(
                turn_id,
                after_sequence=last_sequence,
            )

            for event in persisted:
                if await request.is_disconnected():
                    return

                last_sequence = event.sequence

                yield {
                    "event": event.type,
                    "id": str(event.sequence),
                    "data": json.dumps(
                        event.to_dict(),
                        ensure_ascii=False,
                        default=str,
                    ),
                }##把历史事件以SSE格式推送给前端
            # 如果turn已经结束（completed/failed/cancelled），下发stream.closed事件，结束流
            if turn.status in {
                "completed",
                "failed",
                "cancelled",
            }:
                yield {
                    "event": "stream.closed",
                    "id": str(last_sequence + 1),
                    "data": json.dumps(
                        {
                            "turn_id": turn_id,
                            "status": turn.status,
                        },
                        ensure_ascii=False,
                    ),
                }
                return

            try:
                # turn还在运行，获取事件总线bus，实时订阅新产生事件
                bus = runtime.require_bus(turn_id)
            except RepositoryError:
                yield {
                    "event": "stream.error",
                    "data": json.dumps(
                        {
                            "message": (
                                "turn仍在运行，但当前进程"
                                "没有对应事件总线"
                            )
                        },
                        ensure_ascii=False,
                    ),
                }
                return

            async for event in bus.subscribe(
                after_sequence=last_sequence
            ):
                # 实时源源不断产出HarnessEvent，推送给前端
                if await request.is_disconnected():
                    return

                last_sequence = event.sequence

                yield {
                    "event": event.type,
                    "id": str(event.sequence),
                    "data": json.dumps(
                        event.to_dict(),
                        ensure_ascii=False,
                        default=str,
                    ),
                }

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            yield {
                "event": "stream.error",
                "data": json.dumps(
                    {
                        "error_type": type(exc).__name__,
                        "message": str(exc),
                    },
                    ensure_ascii=False,
                ),
            }

    return EventSourceResponse(
        generate(),
        ping=15,
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post(
    "/turns/{turn_id}/cancel",
    status_code=202,
    dependencies=[Depends(verify_api_key)],
)
async def cancel_turn(
    turn_id: str,
    runtime=Depends(get_runtime),
) -> dict[str, str]:
    try:
        await runtime.cancel_turn(turn_id)
    except RepositoryError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    return {
        "turn_id": turn_id,
        "status": "cancel_requested",
    }

##审批接口Post
@router.post(
    "/approvals/{approval_id}",
    dependencies=[Depends(verify_api_key)],
)
async def resolve_approval(
    approval_id: str,
    payload: ApprovalDecisionRequest,
    bridge=Depends(get_permission_bridge),
    runtime=Depends(get_runtime),
) -> dict[str, str]:
    try:
        pending = await bridge.resolve(
            approval_id,
            decision=payload.decision,
            feedback=payload.feedback,
            resolved_by=payload.resolved_by,
        )
        # 向事件总线发送approval.resolved事件，通知Agent继续执行
        with suppress(RepositoryError):
            bus = runtime.require_bus(pending.turn_id)
            ##主要是通知前端审批状态发生了变化。
            await bus.emit(
                "approval.resolved",
                {
                    "approval_id": approval_id,
                    "decision": payload.decision,
                },
            )
    except RepositoryError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    return {
        "approval_id": approval_id,
        "status": "resolved",
    }

##提交答题记录
@router.post(
    "/students/{student_id}/attempts",
    dependencies=[Depends(verify_api_key)],
)
async def record_attempt(
    student_id: str,
    payload: RecordAttemptRequest,
    learning_service=Depends(get_learning_service),
) -> dict[str, Any]:
    grade = {
        "score": payload.score,
        "max_score": payload.max_score,
    }

    return await learning_service.record_graded_attempt(
        student_id=student_id,
        session_id=payload.session_id,
        turn_id=payload.turn_id,
        question_id=payload.question_id,
        answer=payload.answer,
        grade=grade,
        knowledge_evidence=payload.knowledge_evidence,
        duration_seconds=payload.duration_seconds,
    )

##掌握度与推荐
@router.get(
    "/students/{student_id}/mastery",
    dependencies=[Depends(verify_api_key)],
)
async def get_mastery(
    student_id: str,
    learning_service=Depends(get_learning_service),
) -> list[dict[str, Any]]:
    return await learning_service.mastery_report(student_id)


@router.get(
    "/students/{student_id}/recommendations",
    dependencies=[Depends(verify_api_key)],
)
async def get_recommendations(
    student_id: str,
    limit: int = Query(default=10, ge=1, le=50),
    learning_service=Depends(get_learning_service),
) -> list[dict[str, Any]]:
    return await learning_service.recommendations(
        student_id,
        limit=limit,
    )


# ---------------------------------------------------------------------------
# 教师：登录 / 建课 / 报名 / 驾驶舱 / CSV 导出
# ---------------------------------------------------------------------------
@router.post("/auth/teacher/login")
async def teacher_login(
    payload: TeacherLoginRequest,
    request: Request,
    repository: EduRepository = Depends(get_repository),
) -> dict[str, Any]:
    teacher = await repository.get_teacher_by_username(
        payload.username
    )
    if teacher is None or not verify_password(
        payload.password, teacher.password_hash
    ):
        raise HTTPException(
            status_code=401,
            detail="用户名或密码错误",
        )

    token = create_token(
        {
            "sub": teacher.id,
            "username": teacher.username,
            "role": "teacher",
        },
        secret=request.app.state.settings.auth_secret,
        ttl_seconds=request.app.state.settings.token_ttl_seconds,
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "teacher": {
            "id": teacher.id,
            "username": teacher.username,
            "display_name": teacher.display_name,
        },
    }


@router.post("/teachers/courses")
async def create_course(
    payload: CourseCreateRequest,
    teacher: dict[str, Any] = Depends(require_teacher),
    repository: EduRepository = Depends(get_repository),
) -> dict[str, Any]:
    course = await repository.create_course(
        teacher_id=teacher["sub"],
        name=payload.name,
        subject=payload.subject,
        description=payload.description,
    )
    return {
        "id": course.id,
        "name": course.name,
        "subject": course.subject,
        "description": course.description,
    }


@router.get("/teachers/courses")
async def list_teacher_courses(
    teacher: dict[str, Any] = Depends(require_teacher),
    repository: EduRepository = Depends(get_repository),
) -> list[dict[str, Any]]:
    return await repository.list_teacher_courses(
        teacher["sub"]
    )


@router.post("/courses/{course_id}/students")
async def enroll_student(
    course_id: str,
    payload: EnrollStudentRequest,
    teacher: dict[str, Any] = Depends(require_teacher),
    repository: EduRepository = Depends(get_repository),
) -> dict[str, Any]:
    await _load_course_owned(
        course_id, teacher["sub"], repository
    )
    student = await repository.get_or_create_student(
        external_id=payload.student_external_id,
        display_name=payload.display_name,
    )
    await repository.enroll_student(
        course_id=course_id,
        student_id=student.id,
    )
    return {
        "course_id": course_id,
        "student_id": student.id,
        "external_id": student.external_id,
        "status": "enrolled",
    }


@router.get("/courses/{course_id}/students")
async def list_course_students(
    course_id: str,
    teacher: dict[str, Any] = Depends(require_teacher),
    repository: EduRepository = Depends(get_repository),
) -> dict[str, Any]:
    await _load_course_owned(
        course_id, teacher["sub"], repository
    )
    return {
        "course_id": course_id,
        "students": await repository.list_course_students(
            course_id
        ),
    }


@router.get("/courses/{course_id}/cockpit")
async def course_cockpit(
    course_id: str,
    teacher: dict[str, Any] = Depends(require_teacher),
    repository: EduRepository = Depends(get_repository),
) -> dict[str, Any]:
    await _load_course_owned(
        course_id, teacher["sub"], repository
    )
    return await repository.course_cockpit(course_id)


@router.get("/courses/{course_id}/cockpit.csv")
async def course_cockpit_csv(
    course_id: str,
    teacher: dict[str, Any] = Depends(require_teacher),
    repository: EduRepository = Depends(get_repository),
) -> StreamingResponse:
    await _load_course_owned(
        course_id, teacher["sub"], repository
    )
    data = await repository.course_cockpit(course_id)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "知识点代码",
            "知识点",
            "练习学生数",
            "总作答次数",
            "平均掌握度",
            "平均置信度",
            "高风险学生数",
        ]
    )
    for row in data["knowledge_points"]:
        writer.writerow(
            [
                row["code"],
                row["name"],
                row["practiced_students"],
                row["attempts"],
                row["avg_mastery"],
                row["avg_confidence"],
                row["at_risk_students"],
            ]
        )

    # BOM 前缀：让 Excel 直接打开 UTF-8 CSV 不乱码
    content = "﻿" + buffer.getvalue()
    return StreamingResponse(
        iter([content]),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="cockpit-{course_id}.csv"'
            )
        },
    )


# ---------------------------------------------------------------------------
# 题库读取 + 学生自助判分（无需大模型即可完成一次学习作答）
# ---------------------------------------------------------------------------
@router.get("/students/by-external/{external_id}")
async def resolve_student_by_external(
    external_id: str,
    repository: EduRepository = Depends(get_repository),
) -> dict[str, Any]:
    student = await repository.get_or_create_student(
        external_id=external_id
    )
    return {
        "id": student.id,
        "external_id": student.external_id,
        "display_name": student.display_name,
    }
@router.get("/questions")
async def list_questions(
    subject: str = Query(default="python", min_length=1, max_length=100),
    knowledge_point: str | None = Query(default=None, max_length=500),
    difficulty_min: float = Query(default=0.0, ge=0.0, le=1.0),
    difficulty_max: float = Query(default=1.0, ge=0.0, le=1.0),
    limit: int = Query(default=10, ge=1, le=50),
    repository: EduRepository = Depends(get_repository),
) -> dict[str, Any]:
    kp_codes = (
        [part.strip() for part in knowledge_point.split(",") if part.strip()]
        if knowledge_point
        else None
    )
    rows = await repository.search_questions(
        subject=subject,
        knowledge_point_codes=kp_codes,
        difficulty_min=difficulty_min,
        difficulty_max=difficulty_max,
        limit=limit,
    )
    return {"questions": rows}


@router.post("/students/{student_id}/attempts/auto")
async def submit_auto_attempt(
    student_id: str,
    payload: AutoAttemptRequest,
    learning_service=Depends(get_learning_service),
) -> dict[str, Any]:
    try:
        return await learning_service.submit_auto_answer(
            student_id=student_id,
            question_id=payload.question_id,
            answer_value=payload.answer_value,
        )
    except NotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc


# ---------------------------------------------------------------------------
# 学生：作答证据 / 申诉
# ---------------------------------------------------------------------------
@router.get("/students/{student_id}/attempts/{attempt_id}")
async def get_attempt_evidence(
    student_id: str,
    attempt_id: str,
    repository: EduRepository = Depends(get_repository),
) -> dict[str, Any]:
    try:
        evidence = await repository.get_attempt_with_evidence(
            attempt_id
        )
    except NotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    if evidence["student_id"] != student_id:
        raise HTTPException(
            status_code=404,
            detail="attempt not found",
        )
    return evidence


@router.post("/students/{student_id}/attempts/{attempt_id}/appeal")
async def create_student_appeal(
    student_id: str,
    attempt_id: str,
    payload: AppealCreateRequest,
    repository: EduRepository = Depends(get_repository),
) -> dict[str, Any]:
    try:
        appeal = await repository.create_appeal(
            attempt_id=attempt_id,
            student_id=student_id,
            reason=payload.reason,
            requested_by=payload.requested_by,
        )
    except NotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
    except RepositoryError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    return {
        "appeal_id": appeal.id,
        "attempt_id": attempt_id,
        "status": appeal.status,
    }


@router.get("/students/{student_id}/appeals")
async def list_student_appeals(
    student_id: str,
    repository: EduRepository = Depends(get_repository),
) -> list[dict[str, Any]]:
    return await repository.list_student_appeals(student_id)


# ---------------------------------------------------------------------------
# 教师：申诉复核（改判联动掌握度重算）
# ---------------------------------------------------------------------------
@router.get("/appeals/pending")
async def list_pending_appeals(
    teacher: dict[str, Any] = Depends(require_teacher),
    repository: EduRepository = Depends(get_repository),
) -> list[dict[str, Any]]:
    return await repository.list_appeals(status="pending")


@router.get("/appeals")
async def list_appeals(
    teacher: dict[str, Any] = Depends(require_teacher),
    limit: int = Query(default=50, ge=1, le=100),
    repository: EduRepository = Depends(get_repository),
) -> list[dict[str, Any]]:
    return await repository.list_appeals(limit=limit)


@router.post("/appeals/{appeal_id}/resolve")
async def resolve_appeal(
    appeal_id: str,
    payload: AppealResolveRequest,
    teacher: dict[str, Any] = Depends(require_teacher),
    repository: EduRepository = Depends(get_repository),
) -> dict[str, Any]:
    try:
        resolved = await repository.resolve_appeal(
            appeal_id,
            outcome=(
                "sustained"
                if payload.decision == "sustain"
                else "rejected"
            ),
            new_score=payload.new_score,
            teacher_note=payload.teacher_note,
            resolved_by=(
                payload.resolved_by or teacher["username"]
            ),
        )
    except NotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
    except RepositoryError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    mastery_deltas: list[dict[str, Any]] = []
    if resolved.status == "sustained":
        # 重新取一次避免 detached 对象读字段；按作答引用的知识点逐一派生重算
        fresh = await repository.get_appeal(appeal_id)
        kp_ids = (
            await repository.knowledge_point_ids_for_attempt(
                fresh.attempt_id
            )
        )
        for kp_id in kp_ids:
            mastery_deltas.append(
                await repository.recompute_student_kp_mastery(
                    fresh.student_id, kp_id
                )
            )

    return {
        "appeal_id": appeal_id,
        "status": resolved.status,
        "teacher_note": payload.teacher_note,
        "mastery_deltas": mastery_deltas,
    }


# ---------------------------------------------------------------------------
# LeetCode 刷题训练营：课程 / 章节知识点 / 题解 / 今日计划 / 代码判分
# ---------------------------------------------------------------------------
@router.get("/leetcode/curriculum")
async def leetcode_curriculum(
    student_id: str | None = Query(default=None, max_length=128),
    subject: str = Query(default="leetcode", max_length=100),
    leetcode_service=Depends(get_leetcode_service),
) -> dict[str, Any]:
    return await leetcode_service.overview(student_id, subject)


@router.get("/leetcode/curriculum/{chapter_code}/knowledge")
async def leetcode_chapter_knowledge(
    chapter_code: str,
    subject: str = Query(default="leetcode", max_length=100),
    repository: EduRepository = Depends(get_repository),
) -> dict[str, Any]:
    document = await repository.get_chapter_knowledge(
        chapter_code, subject
    )
    if document is None:
        raise HTTPException(
            status_code=404,
            detail="该章节还没有知识点文档",
        )
    return document


@router.get("/questions/{question_id}/solution")
async def question_solution(
    question_id: str,
    leetcode_service=Depends(get_leetcode_service),
) -> dict[str, Any]:
    document = await leetcode_service.question_solution(question_id)
    if document is None:
        raise HTTPException(
            status_code=404,
            detail="该题还没有详细题解",
        )
    return document


@router.post("/students/{student_id}/leetcode/today")
async def generate_today_plan(
    student_id: str,
    payload: TodayPlanRequest,
    leetcode_service=Depends(get_leetcode_service),
) -> dict[str, Any]:
    try:
        return await leetcode_service.today_plan(
            student_id,
            subject=payload.subject,
            new_limit=payload.new_limit,
            review_limit=payload.review_limit,
        )
    except (RepositoryError, ValueError) as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc


@router.get("/students/{student_id}/leetcode/plan")
async def get_daily_plan(
    student_id: str,
    task_date: str | None = Query(default=None, max_length=10),
    kind: str | None = Query(default=None, max_length=20),
    status: str | None = Query(default=None, max_length=20),
    subject: str = Query(default="leetcode", max_length=100),
    leetcode_service=Depends(get_leetcode_service),
) -> list[dict[str, Any]]:
    return await leetcode_service.list_tasks(
        student_id,
        subject,
        task_date=task_date,
        kind=kind,
        status=status,
    )


@router.post("/students/{student_id}/attempts/coding")
async def submit_coding_attempt(
    student_id: str,
    payload: CodingAttemptRequest,
    leetcode_service=Depends(get_leetcode_service),
) -> dict[str, Any]:
    try:
        return await leetcode_service.submit_coding(
            student_id=student_id,
            subject=payload.subject,
            question_id=payload.question_id,
            code=payload.code,
            language=payload.language,
            verdict=payload.verdict,
            notes=payload.notes,
            reviewed_by=payload.reviewed_by,
        )
    except NotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
    except RepositoryError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc


@router.post("/leetcode/tasks/{task_id}/done")
async def complete_daily_task(
    task_id: str,
    leetcode_service=Depends(get_leetcode_service),
) -> dict[str, Any]:
    try:
        return await leetcode_service.set_task_status(task_id, "done")
    except NotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
    except RepositoryError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc


@router.post("/leetcode/tasks/{task_id}/skip")
async def skip_daily_task(
    task_id: str,
    leetcode_service=Depends(get_leetcode_service),
) -> dict[str, Any]:
    try:
        return await leetcode_service.set_task_status(task_id, "skipped")
    except NotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
    except RepositoryError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc


async def forward_events(
    websocket: WebSocket,
    bus,
    *,
    request_id: str | None,
) -> None:
    async for event in bus.subscribe():
        await websocket.send_json(
            {
                "type": event.type,
                "request_id": request_id,
                "data": event.to_dict(),
            }
        )


@router.websocket("/sessions/{session_id}/ws")
async def session_websocket(
    websocket: WebSocket,
    session_id: str,
) -> None:
    settings = websocket.app.state.settings
    provided_key = websocket.headers.get("x-api-key")

    if settings.api_key and provided_key != settings.api_key:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    forward_tasks: set[asyncio.Task] = set()

    try:
        ##收到前端 json，用 Pydantic 做完整校验；type 只能是chat.send / approval.resolve / turn.cancel / ping。
        while True:
            raw_message = await websocket.receive_json()
            message = WebSocketMessage.model_validate(
                raw_message
            )
            ##ping → pong 心跳：保活，防止 websocket 被中间代理切断。
            if message.type == "ping":
                await websocket.send_json(
                    {
                        "type": "pong",
                        "request_id": message.request_id,
                        "data": {},
                    }
                )
                continue
            ##chat.send：前端发送聊天消息
##取出 data.content，校验非空；
##查询 session，拿到 workspace；
# 调用runtime.start_turn()创建 turn 任务；
# 获取 turn 对应的事件总线 bus；
# 创建asyncio.Task后台任务forward_events，在后台持续订阅 bus 事件，把 HarnessEvent 通过 websocket 推送给前端。
            if message.type == "chat.send":
                content = str(
                    message.data.get("content", "")
                ).strip()
                if not content:
                    raise ValueError("content不能为空")

                repository = websocket.app.state.repository
                session = await repository.get_learning_session(
                    session_id
                )
                workspace = settings.resolve_workspace(
                    session.workspace_id
                )
                turn_id = (
                    await websocket.app.state.runtime.start_turn(
                        session_id=session_id,
                        user_text=content,
                        workspace=workspace,
                    )
                )
                bus = websocket.app.state.runtime.require_bus(
                    turn_id
                )

                await websocket.send_json(
                    {
                        "type": "turn.accepted",
                        "request_id": message.request_id,
                        "data": {"turn_id": turn_id},
                    }
                )

                task = asyncio.create_task(
                    forward_events(
                        websocket,
                        bus,
                        request_id=message.request_id,
                    )
                )
                forward_tasks.add(task)
                task.add_done_callback(forward_tasks.discard)
                continue

            if message.type == "turn.cancel":
                turn_id = str(
                    message.data.get("turn_id", "")
                )
                await websocket.app.state.runtime.cancel_turn(
                    turn_id
                )
                continue
            ##websocket 通道完成审批操作；调用permission_bridge.resolve()做审批决议，再向事件总线 emitapproval.resolved事件，事件会推送给前端。
            if message.type == "approval.resolve":
                approval_id = str(
                    message.data.get("approval_id", "")
                )
                decision = str(
                    message.data.get("decision", "")
                )
                feedback = message.data.get("feedback")

                pending = (
                    await websocket.app.state.permission_bridge.resolve(
                        approval_id,
                        decision=decision,
                        feedback=feedback,
                        resolved_by=session_id,
                    )
                )

                bus = websocket.app.state.runtime.require_bus(
                    pending.turn_id
                )
                await bus.emit(
                    "approval.resolved",
                    {
                        "approval_id": approval_id,
                        "decision": decision,
                    },
                )

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        with suppress(Exception):
            await websocket.send_json(
                {
                    "type": "error",
                    "data": {
                        "error_type": type(exc).__name__,
                        "message": str(exc),
                    },
                }
            )
    finally:
        for task in forward_tasks:
            task.cancel()

        if forward_tasks:
            await asyncio.gather(
                *forward_tasks,
                return_exceptions=True,
            )
