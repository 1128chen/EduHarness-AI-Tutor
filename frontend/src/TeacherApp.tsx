import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import {
  AlertTriangle, Check, Download, GraduationCap,
  LogOut, RefreshCw, Scale, ShieldCheck, UserRound, X,
} from "lucide-react";
import {
  AppealRow, Cockpit, CockpitPoint, Course, MasteryRow,
  StudentRow, clearToken, jcall, readToken, writeToken,
} from "./api";

type Flash = { kind: "ok" | "err"; text: string } | null;

function pct(value: number): number {
  return Math.round(Math.max(0, Math.min(1, value)) * 100);
}

export default function TeacherApp() {
  const [token, setToken] = useState(readToken());
  const [loggedIn, setLoggedIn] = useState(Boolean(readToken()));
  const [username, setUsername] = useState("demo");
  const [password, setPassword] = useState("demo1234");
  const [teacherName, setTeacherName] = useState("");
  const [busy, setBusy] = useState(false);
  const [flash, setFlash] = useState<Flash>(null);

  async function login(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setFlash(null);
    try {
      const result = await jcall<{
        access_token: string;
        teacher: { username: string; display_name: string | null };
      }>("/auth/teacher/login", {
        method: "POST",
        body: { username, password },
      });
      writeToken(result.access_token);
      setToken(result.access_token);
      setTeacherName(result.teacher.display_name ?? result.teacher.username);
      setLoggedIn(true);
    } catch (error) {
      setFlash({ kind: "err", text: errorMsg(error) });
    } finally {
      setBusy(false);
    }
  }

  function logout() {
    clearToken();
    setToken("");
    setLoggedIn(false);
    setCourse(null);
  }

  const [courses, setCourses] = useState<Course[]>([]);
  const [course, setCourse] = useState<Course | null>(null);
  const [students, setStudents] = useState<StudentRow[]>([]);
  const [cockpit, setCockpit] = useState<Cockpit | null>(null);
  const [pending, setPending] = useState<AppealRow[]>([]);
  const [student, setStudent] = useState<StudentRow | null>(null);
  const [mastery, setMastery] = useState<MasteryRow[]>([]);

  async function loadCourses() {
    setBusy(true);
    try {
      setCourses(await jcall<Course[]>("/teachers/courses", { token }));
    } catch (error) {
      setFlash({ kind: "err", text: errorMsg(error) });
    } finally {
      setBusy(false);
    }
  }

  async function loadPending() {
    try {
      setPending(await jcall<AppealRow[]>("/appeals/pending", { token }));
    } catch (error) {
      setFlash({ kind: "err", text: errorMsg(error) });
    }
  }

  useEffect(() => {
    if (loggedIn) void loadCourses();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loggedIn]);

  async function openCourse(item: Course) {
    setCourse(item);
    setStudent(null);
    setMastery([]);
    try {
      const [studentsResult, cockpitResult] = await Promise.all([
        jcall<{ students: StudentRow[] }>(`/courses/${item.id}/students`, {
          token,
        }),
        jcall<Cockpit>(`/courses/${item.id}/cockpit`, { token }),
      ]);
      setStudents(studentsResult.students);
      setCockpit(cockpitResult);
      void loadPending();
    } catch (error) {
      setFlash({ kind: "err", text: errorMsg(error) });
    }
  }

  async function refreshCourse() {
    if (!course) return;
    await openCourse(course);
  }

  async function selectStudent(row: StudentRow) {
    setStudent(row);
    setBusy(true);
    try {
      setMastery(
        await jcall<MasteryRow[]>(`/students/${row.id}/mastery`),
      );
    } catch (error) {
      setFlash({ kind: "err", text: errorMsg(error) });
    } finally {
      setBusy(false);
    }
  }

  async function enrollStudent(externalId: string) {
    if (!course) return;
    try {
      await jcall(`/courses/${course.id}/students`, {
        method: "POST",
        token,
        body: { student_external_id: externalId },
      });
      setFlash({ kind: "ok", text: `已报名 ${externalId}` });
      await openCourse(course);
    } catch (error) {
      setFlash({ kind: "err", text: errorMsg(error) });
    }
  }

  async function downloadCsv() {
    if (!course) return;
    try {
      const blob = await jcall<Blob>(`/courses/${course.id}/cockpit.csv`, {
        token,
        asBlob: true,
      });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `cockpit-${course.name}.csv`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      setFlash({ kind: "err", text: errorMsg(error) });
    }
  }

  async function resolveAppeal(
    appeal: AppealRow,
    decision: "sustain" | "reject",
    newScore: number | null,
    note: string,
  ) {
    try {
      const result = await jcall<{ status: string; mastery_deltas: unknown[] }>(
        `/appeals/${appeal.id}/resolve`,
        {
          method: "POST",
          token,
          body: { decision, new_score: newScore, teacher_note: note },
        },
      );
      const moved =
        result.mastery_deltas.length > 0
          ? `，已联动重算 ${result.mastery_deltas.length} 个知识点`
          : "";
      setFlash({
        kind: "ok",
        text: `申诉#${appeal.id.slice(0, 8)} → ${result.status}${moved}`,
      });
      setPending((list) => list.filter((item) => item.id !== appeal.id));
      if (course) await openCourse(course);
      if (student) await selectStudent(student);
    } catch (error) {
      setFlash({ kind: "err", text: errorMsg(error) });
    }
  }

  function errorMsg(error: unknown): string {
    return error instanceof Error ? error.message : String(error);
  }

  if (!loggedIn) {
    return (
      <div className="teach login-wrap">
        <form className="login-card" onSubmit={login}>
          <div className="login-icon">
            <GraduationCap size={26} />
          </div>
          <h1>教师工作台</h1>
          <p className="muted">登录后可管理班级驾驶舱与申诉复核</p>

          <label>
            账号
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
            />
          </label>
          <label>
            密码
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>

          {flash && <div className={`flash ${flash.kind}`}>{flash.text}</div>}

          <button className="primary" disabled={busy}>
            {busy ? "登录中..." : "登录"}
          </button>
          <small className="muted">演示账号：demo / demo1234</small>
        </form>
      </div>
    );
  }

  const weakCount = cockpit
    ? cockpit.knowledge_points.reduce(
        (sum, point) => sum + point.at_risk_students,
        0,
      )
    : 0;

  return (
    <div className="teach">
      <div className="teach-toolbar">
        <div className="teach-title">
          <GraduationCap size={20} />
          <strong>教师工作台</strong>
          <span className="muted">{teacherName}</span>
        </div>
        <div className="teach-actions">
          <button className="secondary icon-btn" onClick={loadCourses} title="刷新">
            <RefreshCw size={16} />
          </button>
          <button className="secondary icon-btn" onClick={logout} title="退出登录">
            <LogOut size={16} />
          </button>
        </div>
      </div>

      {flash && (
        <div className={`flash ${flash.kind}`}>
          {flash.kind === "ok" ? <Check size={15} /> : <X size={15} />}
          {flash.text}
        </div>
      )}

      <div className="teach-body">
        <aside className="course-list">
          <h2>我的课程</h2>
          {courses.length === 0 && <p className="muted">还没有课程</p>}
          {courses.map((item) => (
            <button
              key={item.id}
              className={`course-card ${course?.id === item.id ? "active" : ""}`}
              onClick={() => void openCourse(item)}
            >
              <strong>{item.name}</strong>
              <span className="muted">{item.subject}</span>
            </button>
          ))}

          <h2 className="section-gap">待复核申诉</h2>
          <div className="pending-badge">
            <Scale size={14} />
            <span>{pending.length} 条待处理</span>
          </div>
        </aside>

        <main className="course-main">
          {!course ? (
            <div className="placeholder">
              <GraduationCap size={40} />
              <h2>选择左侧课程查看班级驾驶舱</h2>
              <p className="muted">展示知识点掌握度聚合、高风险学生与申诉复核</p>
            </div>
          ) : (
            <>
              <header className="course-head">
                <div>
                  <h1>{course.name}</h1>
                  <span className="muted">{course.subject}</span>
                </div>
                <div className="course-actions">
                  <button className="secondary" onClick={() => void downloadCsv()}>
                    <Download size={15} /> 导出 CSV
                  </button>
                  <button className="secondary" onClick={() => void refreshCourse()}>
                    <RefreshCw size={15} /> 刷新
                  </button>
                </div>
              </header>

              <div className="stat-grid">
                <div className="stat">
                  <span>学生数</span>
                  <b>{cockpit?.student_count ?? 0}</b>
                </div>
                <div className="stat">
                  <span>已练知识点</span>
                  <b>{cockpit?.knowledge_points.length ?? 0}</b>
                </div>
                <div className="stat warn">
                  <span>高风险(人次)</span>
                  <b>{weakCount}</b>
                </div>
              </div>

              <section className="card">
                <h2>班级掌握度 · 弱项优先</h2>
                <table className="kp-table">
                  <thead>
                    <tr>
                      <th>知识点</th>
                      <th>练习人数</th>
                      <th>作答次数</th>
                      <th>平均掌握度</th>
                      <th>高风险</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(cockpit?.knowledge_points ?? []).map((point) => (
                      <CockpitRow key={point.knowledge_point_id} point={point} />
                    ))}
                  </tbody>
                </table>
                {(cockpit?.knowledge_points ?? []).length === 0 && (
                  <p className="muted">该课程还没有作答数据</p>
                )}
              </section>

              <section className="card">
                <h2>班级学生</h2>
                <div className="chip-row">
                  {students.map((row) => (
                    <button
                      key={row.id}
                      className={`chip ${student?.id === row.id ? "active" : ""}`}
                      onClick={() => void selectStudent(row)}
                    >
                      <UserRound size={14} />
                      {row.display_name ?? row.external_id}
                    </button>
                  ))}
                  {students.length === 0 && (
                    <p className="muted">暂无学生，先报名一名演示学生</p>
                  )}
                  <EnrollInput onEnroll={enrollStudent} />
                </div>

                {student && (
                  <div className="mastery-panel">
                    <h3>
                      {student.display_name ?? student.external_id} · 知识点掌握度
                    </h3>
                    {mastery.length === 0 && (
                      <p className="muted">该学生还没有作答记录</p>
                    )}
                    {mastery.map((row) => (
                      <div key={row.knowledge_point_id} className="bar-row">
                        <div className="bar-label">
                          <span title={row.code}>{row.name}</span>
                          <span className="muted">
                            作答 {row.attempts_count} · 置信{" "}
                            {pct(row.confidence)}%
                          </span>
                        </div>
                        <div className="bar">
                          <div
                            className={`bar-fill ${row.mastery < 0.5 ? "low" : ""}`}
                            style={{ width: `${pct(row.mastery)}%` }}
                          />
                        </div>
                        <b>{pct(row.mastery)}%</b>
                      </div>
                    ))}
                  </div>
                )}
              </section>

              <section className="card">
                <h2>
                  <Scale size={16} /> 申诉复核 · 可改判并联动重算掌握度
                </h2>
                {pending.length === 0 && (
                  <p className="muted">没有待处理的申诉</p>
                )}
                {pending.map((appeal) => (
                  <AppealCard
                    key={appeal.id}
                    appeal={appeal}
                    onResolve={resolveAppeal}
                  />
                ))}
              </section>
            </>
          )}
        </main>
      </div>
    </div>
  );
}

function CockpitRow({ point }: { point: CockpitPoint }) {
  return (
    <tr>
      <td>
        <b>{point.name}</b>
        <span className="muted block" title={point.code}>
          {point.code}
        </span>
      </td>
      <td>{point.practiced_students}</td>
      <td>{point.attempts}</td>
      <td>
        <div className="cell-mastery">
          <div className="bar small">
            <div
              className={`bar-fill ${point.avg_mastery < 0.5 ? "low" : ""}`}
              style={{ width: `${pct(point.avg_mastery)}%` }}
            />
          </div>
          <span>{pct(point.avg_mastery)}%</span>
        </div>
      </td>
      <td>
        {point.at_risk_students > 0 ? (
          <span className="risk-badge">
            <AlertTriangle size={13} /> {point.at_risk_students}
          </span>
        ) : (
          <span className="ok-text">-</span>
        )}
      </td>
    </tr>
  );
}

function EnrollInput({ onEnroll }: { onEnroll: (externalId: string) => void }) {
  const [value, setValue] = useState("");
  return (
    <form
      className="enroll-form"
      onSubmit={(event) => {
        event.preventDefault();
        if (value.trim()) {
          onEnroll(value.trim());
          setValue("");
        }
      }}
    >
      <input
        placeholder="输入 external_id 报名（如 demo.stu01）"
        value={value}
        onChange={(e) => setValue(e.target.value)}
      />
      <button className="primary" disabled={!value.trim()}>
        报名
      </button>
    </form>
  );
}

function AppealCard({
  appeal,
  onResolve,
}: {
  appeal: AppealRow;
  onResolve: (
    appeal: AppealRow,
    decision: "sustain" | "reject",
    newScore: number | null,
    note: string,
  ) => void;
}) {
  const [open, setOpen] = useState(false);
  const [newScore, setNewScore] = useState(
    String(appeal.evidence_snapshot.max_score || 1),
  );
  const [note, setNote] = useState("");

  const snapshot = appeal.evidence_snapshot;
  const rawAnswer = String(snapshot.answer?.value ?? "");

  return (
    <div className="appeal-card">
      <div className="appeal-head">
        <span className="pending-pill">待复核</span>
        <strong>{appeal.display_name ?? appeal.student_id.slice(0, 8)}</strong>
        <span className="muted">
          题干：{snapshot.question_stem ?? "(题目已删除)"}
        </span>
        <button className="secondary small" onClick={() => setOpen(!open)}>
          {open ? "收起证据" : "查看证据链"}
        </button>
      </div>

      {open && (
        <div className="appeal-evidence">
          <p>
            <b>学生答案：</b>
            <code>{rawAnswer || "(空)"}</code>
            <span className="muted">
              · 原得分 {snapshot.score}/{snapshot.max_score} ·{" "}
              {snapshot.created_at.slice(0, 10)}
            </span>
          </p>
          <p className="appeal-reason">
            <b>申诉理由：</b>
            {appeal.reason}
          </p>
          <div className="muted">引用的知识点：</div>
          <div className="chip-row">
            {snapshot.knowledge_points.map((point) => (
              <span key={point.code} className="chip static">
                {point.name}（{point.weight}）
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="appeal-actions">
        <label>
          改判得分
          <input
            type="number"
            min={0}
            step="0.5"
            value={newScore}
            onChange={(e) => setNewScore(e.target.value)}
          />
        </label>
        <input
          placeholder="复核意见（可选）"
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
        <button
          className="primary"
          onClick={() =>
            onResolve(appeal, "sustain", Number(newScore) || null, note)
          }
        >
          <ShieldCheck size={15} /> 支持并改判
        </button>
        <button
          className="secondary"
          onClick={() => onResolve(appeal, "reject", null, note)}
        >
          <X size={15} /> 驳回
        </button>
      </div>
    </div>
  );
}
