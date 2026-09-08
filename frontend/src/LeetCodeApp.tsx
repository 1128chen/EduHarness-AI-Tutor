import { useEffect, useState } from "react";
import {
  BookOpen, CalendarCheck, CheckCircle2, Code2, Lock,
  Play, RefreshCw, Send, Sparkles, X,
} from "lucide-react";
import { jcall } from "./api";

type Editorial = { editorial?: number; title?: string };
type Question = {
  id: string;
  stem: string;
  difficulty: number;
  editorial: Editorial;
  attempted?: boolean;
  attempts?: number;
  ac?: boolean;
  mastery?: number;
};
type Chapter = {
  code: string;
  name: string;
  description: string;
  status: "locked" | "open" | "done";
  current: boolean;
  ac_count: number;
  total_questions: number;
  questions: Question[];
};
type PlanTask = {
  id: string;
  kind: "learn" | "review";
  status: string;
  reason?: Record<string, any>;
  question?: Question;
};

const STATUS_LABEL: Record<string, string> = {
  locked: "未解锁",
  open: "进行中",
  done: "已完成",
};

function pctDifficulty(difficulty: number): string {
  return `${Math.round(difficulty * 100)}`;
}

export default function LeetCodeApp() {
  const [externalId, setExternalId] = useState("demo.lc01");
  const [studentId, setStudentId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [chapters, setChapters] = useState<Chapter[]>([]);

  const [plan, setPlan] = useState<{ learn: PlanTask[]; review: PlanTask[] }>({
    learn: [],
    review: [],
  });

  // 选中的章节(含知识点串讲)与正在练习的题
  const [chapterCode, setChapterCode] = useState<string | null>(null);
  const [chapterNotes, setChapterNotes] = useState("");
  const [practice, setPractice] = useState<Question | null>(null);
  const [code, setCode] = useState("");
  const [verdict, setVerdict] = useState("ac");
  const [notes, setNotes] = useState("");
  const [outcome, setOutcome] = useState<Record<string, any> | null>(null);
  const [solution, setSolution] = useState("");

  function fail(value: unknown) {
    setError(value instanceof Error ? value.message : String(value));
  }

  async function resolveStudent() {
    setBusy(true);
    setError("");
    try {
      const result = await jcall<{ id: string }>(
        `/students/by-external/${encodeURIComponent(externalId)}`,
      );
      setStudentId(result.id);
      const [curriculum] = await Promise.all([
        jcall<{ chapters: Chapter[] }>(
          `/leetcode/curriculum?student_id=${result.id}`,
        ),
      ]);
      setChapters(curriculum.chapters);
      await loadPlan(result.id);
    } catch (value) {
      fail(value);
    } finally {
      setBusy(false);
    }
  }

  async function loadPlan(sid: string) {
    try {
      const result = await jcall<{ learn: PlanTask[]; review: PlanTask[] }>(
        `/students/${sid}/leetcode/today`,
        { method: "POST", body: {} },
      );
      setPlan({ learn: result.learn, review: result.review });
    } catch (value) {
      fail(value);
    }
  }

  useEffect(() => {
    if (studentId) void loadPlan(studentId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [studentId]);

  async function openChapter(chapter: Chapter) {
    setChapterCode(chapter.code);
    setChapterNotes("");
    try {
      const doc = await jcall<{ chunks: Array<{ text: string }> }>(
        `/leetcode/curriculum/${chapter.code}/knowledge`,
      );
      setChapterNotes((doc.chunks ?? []).map((c) => c.text).join("\n"));
    } catch {
      setChapterNotes("（本章暂未提供知识点文档）");
    }
  }

  async function beginPractice(question: Question) {
    setPractice(question);
    setCode("");
    setNotes("");
    setVerdict("ac");
    setOutcome(null);
    setSolution("");
  }

  async function submitCoding() {
    if (!practice || !studentId) return;
    setBusy(true);
    setError("");
    try {
      const result = await jcall<Record<string, any>>(
        `/students/${studentId}/attempts/coding`,
        {
          method: "POST",
          body: {
            question_id: practice.id,
            subject: "leetcode",
            code,
            language: "python",
            verdict,
            notes: notes || null,
            reviewed_by: "self",
          },
        },
      );
      setOutcome(result);
      try {
        const doc = await jcall<{ chunks: Array<{ text: string }> }>(
          `/questions/${practice.id}/solution`,
        );
        setSolution((doc.chunks ?? []).map((c) => c.text).join("\n"));
      } catch {
        setSolution("（暂无题解文档）");
      }
      if (studentId) {
        const curriculum = await jcall<{ chapters: Chapter[] }>(
          `/leetcode/curriculum?student_id=${studentId}`,
        );
        setChapters(curriculum.chapters);
        await loadPlan(studentId);
      }
    } catch (value) {
      fail(value);
    } finally {
      setBusy(false);
    }
  }

  async function finishTask(task: PlanTask) {
    if (!studentId) return;
    try {
      await jcall(`/leetcode/tasks/${task.id}/done`, { method: "POST" });
      await loadPlan(studentId);
    } catch (value) {
      fail(value);
    }
  }

  const verdictLabel: Record<string, string> = {
    ac: "AC · 通过",
    partial: "部分通过",
    wrong: "错误",
  };

  return (
    <div className="teach lc">
      <div className="teach-toolbar">
        <div className="teach-title">
          <Code2 size={20} />
          <strong>LeetCode Hot100 训练营</strong>
          <span className="muted">章节学习 → 刷题 → 艾宾浩斯复习</span>
        </div>
        <div className="lc-identity">
          <label>
            学员编号
            <input
              value={externalId}
              onChange={(e) => setExternalId(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void resolveStudent();
              }}
            />
          </label>
          <button className="primary" disabled={busy} onClick={resolveStudent}>
            <RefreshCw size={15} /> 载入
          </button>
        </div>
      </div>

      {error && <div className="flash err"><X size={15} />{error}</div>}
      {!studentId && (
        <div className="placeholder lc-placeholder">
          <Code2 size={40} />
          <h2>输入演示学员编号开始</h2>
          <p className="muted">可用：demo.lc01 / demo.lc02 / demo.lc03</p>
        </div>
      )}

      {studentId && (
        <div className="lc-body">
          <aside className="course-list lc-chapters">
            <h2>学习路径（15 章）</h2>
            {chapters.map((chapter) => (
              <div
                key={chapter.code}
                className={`course-card lc-chapter ${chapterCode === chapter.code ? "active" : ""}`}
              >
                <button
                  className="lc-chapter-head"
                  onClick={() => void openChapter(chapter)}
                >
                  {chapter.status === "locked" ? (
                    <Lock size={13} />
                  ) : chapter.status === "done" ? (
                    <CheckCircle2 size={13} />
                  ) : (
                    <Sparkles size={13} />
                  )}
                  <strong>{chapter.name}</strong>
                  <span className="muted">
                    {STATUS_LABEL[chapter.status]}
                  </span>
                  <span className="muted">
                    {chapter.ac_count}/{chapter.total_questions}
                  </span>
                </button>
              </div>
            ))}
          </aside>

          <main className="course-main">
            <section className="card">
              <h2>
                <CalendarCheck size={16} /> 今日计划 · 先复习到期题，再刷当前章新题
              </h2>
              <div className="plan-columns">
                <div className="plan-col">
                  <h3>复习队列（艾宾浩斯到期）</h3>
                  {plan.review.length === 0 && (
                    <p className="muted">今天没有到期复习题</p>
                  )}
                  {plan.review.map((task) => (
                    <TaskCard
                      key={task.id}
                      task={task}
                      onPractice={() =>
                        task.question && void beginPractice(task.question)
                      }
                      onDone={() => void finishTask(task)}
                    />
                  ))}
                </div>
                <div className="plan-col">
                  <h3>新题队列（当前章）</h3>
                  {plan.learn.length === 0 && (
                    <p className="muted">当前章已刷完，继续下一章吧</p>
                  )}
                  {plan.learn.map((task) => (
                    <TaskCard
                      key={task.id}
                      task={task}
                      onPractice={() =>
                        task.question && void beginPractice(task.question)
                      }
                      onDone={() => void finishTask(task)}
                    />
                  ))}
                </div>
              </div>
            </section>

            {chapterCode && (
              <section className="card">
                <h2>
                  <BookOpen size={16} /> 章节知识点 ·{" "}
                  {chapters.find((c) => c.code === chapterCode)?.name}
                </h2>
                <pre className="chapter-notes">{chapterNotes}</pre>
                <div className="chip-row">
                  {(
                    chapters.find((c) => c.code === chapterCode)?.questions ??
                    []
                  ).map((question) => (
                    <button
                      key={question.id}
                      className={`chip ${practice?.id === question.id ? "active" : ""}`}
                      onClick={() => void beginPractice(question)}
                    >
                      #{question.editorial.editorial}{" "}
                      {question.editorial.title}
                      {question.ac ? " ✓" : question.attempted ? " ·重刷" : ""}
                    </button>
                  ))}
                </div>
              </section>
            )}

            {practice && (
              <section className="card lc-practice">
                <div className="practice-head">
                  <h2>
                    练习 · #{practice.editorial.editorial}{" "}
                    {practice.editorial.title}
                  </h2>
                  <span className="muted">
                    难度 {pctDifficulty(practice.difficulty)} · Python
                  </span>
                </div>
                <p className="practice-stem">{practice.stem}</p>

                <label>
                  你的解法
                  <textarea
                    className="code-area"
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                    placeholder={'def solve(nums):\n    ...'}
                    spellCheck={false}
                  />
                </label>
                <div className="practice-actions">
                  <label>
                    自查结论
                    <select
                      value={verdict}
                      onChange={(e) => setVerdict(e.target.value)}
                    >
                      <option value="ac">AC · 通过</option>
                      <option value="partial">部分通过</option>
                      <option value="wrong">错误</option>
                    </select>
                  </label>
                  <input
                    placeholder="备注（哪里卡住/思路）"
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                  />
                  <button
                    className="primary"
                    disabled={busy || !code.trim()}
                    onClick={() => void submitCoding()}
                  >
                    <Send size={15} /> 提交批改
                  </button>
                </div>

                {outcome && (
                  <div className={`review-verdict ${outcome.verdict}`}>
                    <b>
                      {verdictLabel[String(outcome.verdict)] ?? outcome.verdict}
                    </b>
                    <span className="muted">
                      · 判分 {outcome.score} / 1.0 · 记录
                      #{String(outcome.attempt_id).slice(0, 8)}
                    </span>
                  </div>
                )}

                {solution && (
                  <details className="solution-box" open>
                    <summary>
                      <Play size={14} /> 详细题解
                    </summary>
                    <pre>{solution}</pre>
                  </details>
                )}
              </section>
            )}
          </main>
        </div>
      )}
    </div>
  );
}

function TaskCard({
  task,
  onPractice,
  onDone,
}: {
  task: PlanTask;
  onPractice: () => void;
  onDone: () => void;
}) {
  const question = task.question;
  return (
    <div className={`plan-task ${task.status}`}>
      <div className="plan-task-main">
        <span className={`kind-pill ${task.kind}`}>
          {task.kind === "review" ? "复习" : "新题"}
        </span>
        {question && (
          <span>
            #{question.editorial.editorial} {question.editorial.title}
          </span>
        )}
        {task.reason?.chapter_name && (
          <span className="muted">({task.reason.chapter_name})</span>
        )}
      </div>
      <div className="plan-task-actions">
        <button className="secondary small" onClick={onPractice}>
          去做
        </button>
        <button className="primary small" onClick={onDone}>
          标记完成
        </button>
      </div>
    </div>
  );
}
