# EduHarness · Auditable AI Tutor

<p align="center">
  <strong>A self-built Agent runtime that turns "Q&A → grading → review" into an auditable loop: approvable, replayable, appealable, and testable.</strong>
</p>

<p align="center">
  <a href="./README.zh-CN.md">中文</a>
  ·
  <a href="https://github.com/1128chen/EduHarness-AI-Tutor">Repository</a>
</p>

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white">
  <img alt="Tests" src="https://img.shields.io/badge/eduharness-tests-40%20passed-brightgreen?style=flat-square">
  <img alt="Frontend" src="https://img.shields.io/badge/React-19-61DAFB?style=flat-square&logo=react&logoColor=white">
</p>

Most "AI tutors" are just chat shells: sessions drop, context is lost, grading cannot be appealed, and nothing is measurable. EduHarness makes the things that actually matter in education — **explainable, replayable, appealable grading** — first-class runtime capabilities.

## Problem

- Unreliable sessions & memory across days.
- Grading without evidence; after a re-grade the mastery model is patched, not recomputed.
- No per-teacher data isolation; risky agent actions lack human approval.
- No standardized evaluation; model failures and local bugs are indistinguishable.

## Product surface (React frontend + FastAPI backend)

| View | What it does |
| --- | --- |
| Student chat | Continuous dialogue with an agent tutor; the agent only touches the self-built MCP boundary (question bank / knowledge base) — answers cite sources, never invent. |
| LeetCode bootcamp | 15-chapter learning path, ordered practice, code submission → verdict + detailed editorial; **Ebbinghaus** daily "review + new-question" queue. |
| Teacher dashboard | Per-knowledge-point mastery aggregation, at-risk students, one-click CSV, **appeal review** that auto-recomputes mastery after re-grade. |

## Key mechanisms

- **Replayable sessions**: sessions/attempts/agent events fully persisted; SSE + WebSocket resume by sequence.
- **Mastery as replayable memory**: each attempt is one weighted evidence; mastery is derived by a **pure, idempotent recompute** (incremental == recompute, guarded by tests). Re-grades replay the full evidence, no patching.
- **Appealable grading**: immutable evidence snapshots (stem / answer / cited knowledge points / score); teachers re-grade and the system recomputes the student's mastery.
- **Ebbinghaus review**: mastered items get due dates at days `1/2/4/7/15/30`; each day schedules due reviews first, then new questions from the current chapter.
- **Roles & approval**: teacher/student roles with self-built HMAC-SHA256 Bearer tokens + pbkdf2; teacher data isolated by ownership (403-esque cross-access returns 404); risky tool actions require human approval (auto-deny on timeout), fully audited.
- **Safety**: workspace path sandbox, MCP command allowlist, **student code is never executed server-side**.

## Architecture

```text
React (Student Chat / LeetCode / Teacher Dashboard)
        │  37× REST + WebSocket
        ▼
FastAPI application (api / application / domain / infrastructure)
        ├─ LeetCodeService   chapter progression + Ebbinghaus daily plan
        ├─ LearningService    attempts → evidence → mastery / appeals
        └─ RuntimeManager     one dialogue = one Agent turn (event bus + approval bridge)
                │  through the self-built MCP boundary
                ▼
    Self-built Agent runtime (MiniCode engine): layered memory / replay / approvals
                question_bank · knowledge_base
```

## Quickstart

Python 3.11+, Node 18+.

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install fastapi "uvicorn[standard]" sse-starlette pydantic-settings \
            "sqlalchemy[asyncio]" aiosqlite pytest pytest-asyncio httpx

python -m eduharness.scripts.seed_python_course    # idempotent demo course #1
python -m eduharness.scripts.seed_leetcode_course  # idempotent demo course #2

python -m eduharness.api.app                        # API @ http://127.0.0.1:8000

cd frontend && npm install && npm run dev           # Web @ http://localhost:5173 (/api proxied)
```

Demo accounts: teacher `demo` / `demo1234`; students `demo.stu01..03`, `demo.lc01..03`.

Config via `EDUHARNESS_*` env vars (e.g. `EDUHARNESS_DATABASE_URL` to switch SQLite ↔ PostgreSQL, `EDUHARNESS_AUTH_SECRET`). Secrets live in a local, git-ignored `.env`.

## Testing

```bash
python -m pytest tests/eduharness -q    # 40 layered tests, green locally
python -m pytest -q                      # full engine suite (Python 3.11+, dev deps)
```

- Self-built 3-condition memory eval (14 interrupted tasks × 28 goals): recovery **100% (28/28)** vs weak-session **29%** vs no-memory **0%**.
- Deterministic invariants guarded by tests: incremental == recompute, Ebbinghaus due dates, appeal re-grade monotonicity.
- 40 layered tests + engine 1300+ cross-platform CI; structure gate 0 violations.
- Everything runs without model credentials (grading via offline self-check); live agent chat needs a provider.

## Repository layout

| Path | Purpose |
| --- | --- |
| `eduharness/` | Main app: api / application / domain / infrastructure |
| `eduharness/scripts/` | Idempotent seed scripts for both courses |
| `minicode/` | Self-built agent runtime (sessions / memory / MCP / approvals) |
| `frontend/` | React 19 frontend (three views) |
| `tests/eduharness/` | Layered tests (pure functions / repository / HTTP e2e) |

## Honest boundaries

- Grading defaults to **offline self-check** against the bundled editorial; `reviewed_by=agent/teacher` slots are wired for LLM or human re-grading — code is never executed.
- Demo students use **synthetic attempt trajectories** to demonstrate due reviews / dashboards / re-grades.
- LeetCode items use editorial numbers only for course organization; all stems/solutions are self-written to avoid copyright issues.

## License

Open-source demo/education project; license TBD.
