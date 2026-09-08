##校验所有API输入，避免未经验证的数据进入Agent和数据库
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


##1.没有写 default = xxx 的字段就是必填字段：student_external_id没有 default，前端必须传，否则接口直接返回 422 校验错误。
##2.default=xxx：前端不传该参数，Pydantic 自动填充默认值。
##3.所有字符串全部做最大长度限制：防御数据库字段超长截断，防御恶意超长输入传给 Agent 大模型。
class CreateSessionRequest(BaseModel):##创建会话，请求模型
    student_external_id: str = Field(
        min_length=1,
        max_length=128,
    )
    student_display_name: str | None = Field(
        default=None,
        max_length=200,
    )
    workspace_id: str = Field(
        default="default",
        min_length=1,
        max_length=255,
    )
    title: str | None = Field(
        default=None,
        max_length=255,
    )

##会话返回模型（出参，返回给前端）,全部字段没有default，全部为必填输出字段
##这是响应 Schema：ORM数据库对象 → 转换成这个Pydantic,模型再返回 JSON。
class SessionResponse(BaseModel):
    id: str
    student_id: str
    workspace_id: str
    title: str | None
    status: str

##发送消息请求
class SendMessageRequest(BaseModel):
    content: str = Field(
        min_length=1,
        max_length=50_000,
    )

##一轮交互响应，turn代表一次agent交互轮次，返回轮次 ID、所属会话 ID、轮次状态。全部输出必填。
class TurnResponse(BaseModel):
    turn_id: str
    session_id: str
    status: str

##工具审批决策请求
class ApprovalDecisionRequest(BaseModel):
    decision: Literal[
        "allow_once",
        "allow_turn",
        "allow_all_turn",
        "allow_always",
        "deny_once",
        "deny_with_feedback",
        "deny_always",
    ]##decision使用Literal：只能传入列表内的 7 个固定字符串。
    feedback: str | None = Field(
        default=None,
        max_length=2_000,
    )
    resolved_by: str | None = Field(
        default=None,
        max_length=128,
    )


class RecordAttemptRequest(BaseModel):
    session_id: str | None = None
    turn_id: str | None = None
    question_id: str
    answer: dict[str, Any]
    score: float = Field(ge=0)
    max_score: float = Field(gt=0)
    duration_seconds: int | None = Field(
        default=None,
        ge=0,
    )
    knowledge_evidence: list[dict[str, Any]] = Field(
        default_factory=list
    )


##教师账号登录
class TeacherLoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


##教师创建课程（一门真实课程 = 一个 subject 下的教学单元）
class CourseCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    subject: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=4_000)


##把学生（按 external_id 幂等）报名进班级
class EnrollStudentRequest(BaseModel):
    student_external_id: str = Field(
        min_length=1, max_length=128
    )
    display_name: str | None = Field(
        default=None, max_length=200
    )


##学生就某次作答发起申诉
class AppealCreateRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2_000)
    requested_by: str | None = Field(
        default=None, max_length=128
    )


##学生提交答案自动判分（无需大模型，走确定性判题）
class AutoAttemptRequest(BaseModel):
    question_id: str
    answer_value: str = Field(min_length=1, max_length=2_000)


##代码题提交(判定来源见 reviewed_by)
class CodingAttemptRequest(BaseModel):
    question_id: str
    subject: str = Field(default="leetcode", max_length=100)
    code: str = Field(min_length=1, max_length=60_000)
    language: str = Field(default="python", max_length=30)
    verdict: Literal["ac", "partial", "wrong"] = "wrong"
    notes: str | None = Field(default=None, max_length=4_000)
    reviewed_by: Literal["self", "agent", "teacher"] = "self"


##生成某天的新题/复习计划
class TodayPlanRequest(BaseModel):
    subject: str = Field(default="leetcode", max_length=100)
    new_limit: int = Field(default=3, ge=1, le=10)
    review_limit: int = Field(default=10, ge=1, le=30)


##教师复核申诉：sustain(支持申诉)/reject(驳回)；new_score 仅在 sustain 时生效
class AppealResolveRequest(BaseModel):
    decision: Literal["sustain", "reject"]
    new_score: float | None = Field(default=None, ge=0)
    teacher_note: str | None = Field(
        default=None, max_length=2_000
    )
    resolved_by: str | None = Field(
        default=None, max_length=128
    )


##用于websocket二进制/文本消息解析
class WebSocketMessage(BaseModel):
    type: Literal[
        "chat.send",
        "approval.resolve",
        "turn.cancel",
        "ping",
    ]
    request_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)