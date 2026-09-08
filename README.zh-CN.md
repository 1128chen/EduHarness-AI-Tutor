# EduHarness · 可审计 AI 助教

<p align="center">
  <strong>用自研 Agent 运行时把「答疑 → 批改 → 复习」做成可审批、可回放、可申诉、可评测的闭环。</strong>
</p>

<p align="center">
  <a href="./README.md">English</a>
  ·
  <a href="https://github.com/1128chen/EduHarness-AI-Tutor">仓库</a>
</p>

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white">
  <img alt="Tests" src="https://img.shields.io/badge/eduharness-tests-40%20passed-brightgreen?style=flat-square">
  <img alt="Frontend" src="https://img.shields.io/badge/React-19-61DAFB?style=flat-square&logo=react&logoColor=white">
</p>

> 市面上大多数"AI 助教"只是一个会聊天的壳：会话会断、上下文会丢、批改不能申诉、教师数据无法按班级隔离、效果也无从评测。EduHarness 的不同之处在于，把教育场景里真正重要的**可解释、可回放、可申诉**做成了运行时的一等能力。

## 它解决什么问题

- **会话与记忆不可靠**：学生隔天回来上下文丢失、助教前后说法不一致。
- **评阅不可申诉**：一次扣分没有证据与回放，改判后学情状态被打补丁式污染。
- **数据无法隔离**：教师看不到"自己班级之外"的数据边界，高危动作缺乏人工审批。
- **无标准化评测**：功能好坏靠"感觉"，模型故障与本地逻辑的分界不清。

EduHarness 以一个**自研 Agent 运行时**为底座（会话 / 记忆 / 工具审批 / 事件总线），其上承载两门可直接使用的课程：**Python 程序设计入门** 与 **LeetCode Hot100 训练营**。

## 三个产品面

| 入口 | 说明 |
| --- | --- |
| **学生对话** | 浏览器里和 agent 助教连续对话、答题；agent 只经自研 MCP 边界（题库 / 知识库）取题判分，回答必带引用、不编造 |
| **LeetCode 训练营** | 15 章 × 45 题学习路径：章节知识点先行 → 按序刷题 → 代码提交 → 判题 + 详细题解；按**艾宾浩斯**自动生成每日「到期复习 + 当前章新题」 |
| **教师工作台** | 班级驾驶舱（知识点掌握度聚合、高风险学生、弱项置顶）、一键 CSV、**申诉复核**（改判自动联动掌握度重算） |

## 核心机制（面试可深挖）

- **会话可回放、断线可续传**：会话 / 作答 / Agent 事件全量落库，SSE 与 WebSocket 双通道按序列续传。
- **掌握度 = 可重放记忆**：每次作答沉淀一条带权证据；掌握度由纯函数**幂等派生重算**（增量==重算，单测守护），教师改判后不补丁、直接全量重放。
- **可申诉评阅**：每次作答保留不可变证据快照（题干 / 作答 / 引用知识点 / 得分），学生可申诉，教师复核改判后系统按新证据重算该生知识点掌握度。
- **艾宾浩斯复习调度**：对已掌握题目按 `1/2/4/7/15/30` 天生成到期日，每天先派复习、再派当前章新题，完成即出队。
- **多角色与审批**：教师 / 学生分角色，自研 HMAC-SHA256 Bearer Token + pbkdf2 口令；教师数据按归属隔离、越权统一 404；高危工具动作进入人工审批（超时自动拒绝），全程留痕。
- **安全边界**：路径沙箱防逃逸、MCP 命令白名单、**代码判题不执行学生代码**。

## 架构

```text
React (学生对话 / LeetCode / 教师工作台)
        │  37× REST + WebSocket
        ▼
FastAPI 应用层（api / application / domain / infrastructure）
        │
        ├── LeetCodeService  课程推进 + 艾宾浩斯每日计划
        ├── LearningService  作答 → 证据 → 掌握度 / 申诉复核
        └── RuntimeManager   每轮对话 = 一次 Agent turn（事件总线 + 审批桥）
                │  经自研 MCP 边界
                ▼
   自研 Agent 运行时（MiniCode 引擎）：分层记忆 / 会话回放 / 工具审批
                题库 question_bank · 知识库 knowledge_base
```

## 快速开始

环境：Python 3.11+、Node 18+。

```bash
# 1) 后端依赖
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install fastapi "uvicorn[standard]" sse-starlette pydantic-settings \
            "sqlalchemy[asyncio]" aiosqlite pytest pytest-asyncio httpx

# 2) 灌入两门演示课程（幂等，可重复执行；默认写 ./eduharness.db）
python -m eduharness.scripts.seed_python_course
python -m eduharness.scripts.seed_leetcode_course

# 3) 启动 API（http://127.0.0.1:8000）
python -m eduharness.api.app

# 4) 启动前端（http://localhost:5173，/api 已代理到 8000）
cd frontend && npm install && npm run dev
```

**演示账号**

- 教师工作台：`demo` / `demo1234`（进入后可见两门课与驾驶舱）
- 学生：Python 课 `demo.stu01 / demo.stu02 / demo.stu03`；LeetCode 课 `demo.lc01 / demo.lc02 / demo.lc03`

**配置**：环境变量以 `EDUHARNESS_` 为前缀，例如 `EDUHARNESS_DATABASE_URL` 切换数据库（SQLite 或 PostgreSQL 均支持，仅换连接串）、`EDUHARNESS_AUTH_SECRET` 覆盖默认签名密钥。密钥一律走本地 `.env`（已被 git 忽略），不要提交。

## API 一览

| 分组 | 端点（前缀 `/api/v1`） |
| --- | --- |
| 健康 | `GET /health/live`、`GET /health/ready` |
| 鉴权 | `POST /auth/teacher/login` |
| 教师 | `POST/GET /teachers/courses`、`POST/GET /courses/{id}/students` |
| 驾驶舱 | `GET /courses/{id}/cockpit`、`GET /courses/{id}/cockpit.csv` |
| 会话对话 | `POST/GET /sessions`、`POST /sessions/{id}/turns`、`GET /turns/{id}/events`(SSE)、`POST /approvals/{id}` |
| 作答 | `POST /students/{id}/attempts`、`POST /students/{id}/attempts/auto`、`POST /students/{id}/attempts/coding`、`GET /questions` |
| 申诉 | `POST /students/{id}/attempts/{aid}/appeal`、`GET /appeals/pending`、`POST /appeals/{id}/resolve` |
| LeetCode | `GET /leetcode/curriculum`、`POST /students/{id}/leetcode/today`、`GET/…/plan`、`POST /leetcode/tasks/{id}/done` |

## 测试与量化

```bash
python -m pytest tests/eduharness -q        # 40 项分层用例（本地可全绿）
python -m pytest -q                          # 引擎全量用例（需 Python 3.11+ 与 dev 依赖）
```

- 自建三条件记忆评测（14 中断任务 × 28 目标）：恢复率 **100%（28/28）**，弱会话 **29%**、无记忆 **0%**。
- 掌握度"增量==重算"、艾宾浩斯到期、申诉改判单调性均由用例断言守护。
- 40 项分层用例 + 引擎 1300+ 用例跨平台 CI；结构合规门禁 0 违规。
- 无模型凭据也能跑通全部演示与回归（判题走自评 / 离线对照，agent 对话才需要 provider）。

## 仓库结构

| 路径 | 说明 |
| --- | --- |
| `eduharness/` | 主应用：FastAPI（api）/ 服务（application）/ 领域（domain）/ 存储（infrastructure） |
| `eduharness/scripts/` | `seed_python_course.py`、`seed_leetcode_course.py` 等幂等灌数脚本 |
| `minicode/` | 自研 Agent 引擎底座（会话 / 记忆 / MCP / 审批） |
| `frontend/` | React 19 前端（学生对话、LeetCode、教师工作台三个视图） |
| `tests/eduharness/` | 分层测试（领域纯函数 / 仓储 / HTTP 端到端） |

## 已知边界（诚实说明）

- **判题默认走"自评/离线对照"**：学生对照系统给出的详细题解自查 AC/错误；字段与接口已保留 `reviewed_by=agent/teacher` 通道，接入真实 LLM 或教练复核只需替换判题来源，服务端始终不执行学生代码。
- **演示数据为合成轨迹**：`demo.*` 学员的作答用于演示"到期复习 / 驾驶舱 / 改判联动"，接入真实班级只需替换课程 seed。
- **题目为自写转述**：LeetCode 题目仅以题号做课程编排引用，题面/题解为自写内容，不复制官方文本，规避版权问题。

## License

本项目为演示 / 教学用途开源，License 待定。
