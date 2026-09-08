import { useRef, useState } from "react";
import type { FormEvent } from "react";
import { fetchEventSource } from "@microsoft/fetch-event-source";
import {
  BookOpen, Check, CircleStop, LoaderCircle,
  Send, ShieldAlert, Wrench, X,
} from "lucide-react";

type Session = {
  id: string;
  student_id: string;
};

type Message = {
  id: string;
  role: "user" | "assistant";
  text: string;
  turnId?: string;
  pending?: boolean;
  error?: boolean;
};

type ToolLog = {
  id: string;
  name: string;
  status: string;
  content: unknown;
};

type Approval = {
  approvalId: string;
  request: Record<string, any>;
};

const API = "/api/v1";
const API_KEY = import.meta.env.VITE_API_KEY ?? "";

function formatPlainMath(text: string): string {
  return text
    // 删除数学分隔符
    .replace(/\$\$/g, "")
    .replace(/\$/g, "")
    .replace(/\\\(/g, "")
    .replace(/\\\)/g, "")
    .replace(/\\\[/g, "")
    .replace(/\\\]/g, "")

    // 删除 aligned、equation 等环境
    .replace(
      /\\begin\{(?:aligned|align\*?|equation\*?)\}/g,
      "",
    )
    .replace(
      /\\end\{(?:aligned|align\*?|equation\*?)\}/g,
      "",
    )

    // 将 LaTeX 换行变成普通换行
    .replace(/\\\\/g, "\n")

    // 删除对齐符号
    .replace(/&/g, "")

    // 转换常用命令
    .replace(/\\quad/g, " ")
    .replace(/\\qquad/g, " ")
    .replace(/\\times/g, "×")
    .replace(/\\div/g, "÷")
    .replace(/\\cdot/g, "·")
    .replace(/\\neq/g, "≠")
    .replace(/\\leq?/g, "≤")
    .replace(/\\geq?/g, "≥")
    .replace(/\\pm/g, "±")

    // 转换文字、分数、根号
    .replace(/\\text\{([^{}]*)\}/g, "$1")
    .replace(
      /\\frac\{([^{}]+)\}\{([^{}]+)\}/g,
      "($1)/($2)",
    )
    .replace(
      /\\sqrt\{([^{}]+)\}/g,
      "√($1)",
    )

    // 转换上下标
    .replace(/\^\{([^{}]+)\}/g, "^$1")
    .replace(/_\{([^{}]+)\}/g, "_$1")

    // 删除 Markdown 加粗和分隔线
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/^\s*---\s*$/gm, "")

    // 整理多余空白
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function headers(
  json = false,
): Record<string, string> {
  const result: Record<string, string> = {};

  if (json) {
    result["Content-Type"] = "application/json";
  }

  if (API_KEY) {
    result["X-API-Key"] = API_KEY;
  }

  return result;
}

async function request<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    ...init,
    headers: {
      ...headers(Boolean(init?.body)),
      ...init?.headers,
    },
  });

  const responseText = await response.text();

  if (!response.ok) {
    throw new Error(
      responseText ||
      `请求失败：HTTP ${response.status}`,
    );
  }

  if (!responseText.trim()) {
    return undefined as T;
  }

  try {
    return JSON.parse(responseText) as T;
  } catch {
    throw new Error(
      `服务器返回了非 JSON 内容：${
        responseText.slice(0, 300)
      }`,
    );
  }
}

export default function StudentChat() {
  const [session, setSession] = useState<Session | null>(null);
  const [externalId, setExternalId] = useState("student-web-001");
  const [displayName, setDisplayName] = useState("体验学生");
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [tools, setTools] = useState<ToolLog[]>([]);
  const [approval, setApproval] = useState<Approval | null>(null);
  const [activeTurn, setActiveTurn] = useState<string | null>(null);
  const [error, setError] = useState("");
  const controller = useRef<AbortController | null>(null);

  async function createLearningSession() {
    try {
      setError("");
      const result = await request<Session>("/sessions", {
        method: "POST",
        body: JSON.stringify({
          student_external_id: externalId,
          student_display_name: displayName,
          workspace_id: "default",
          title: "React 学习会话",
        }),
      });

      setSession(result);
      setMessages([]);
      setTools([]);
      localStorage.setItem("eduharness_session_id", result.id);
    } catch (value) {
      setError(value instanceof Error ? value.message : "创建会话失败");
    }
  }

  function updateAssistant(
    turnId: string,
    updater: (message: Message) => Message,
  ) {
    setMessages((current) =>
      current.map((message) =>
        message.turnId === turnId ? updater(message) : message,
      ),
    );
  }

async function consumeEvents(turnId: string) {
  // 停止可能残留的旧连接。
  controller.current?.abort();

  // 使用局部常量，TypeScript 可以确定它不为 null。
  const streamController = new AbortController();
  controller.current = streamController;

  await fetchEventSource(
    `${API}/turns/${turnId}/events`,
    {
      headers: headers(),
      signal: streamController.signal,

      async onopen(response) {
        if (!response.ok) {
          throw new Error(await response.text());
        }
      },

      onmessage(message) {
  const eventName = message.event;
  const rawData = message.data?.trim();

  // SSE 心跳或空结束帧没有 JSON 数据。
  if (!rawData) {
    return;
  }

  let payload: any;

  try {
    payload = JSON.parse(rawData);
  } catch (error) {
    console.warn(
      "忽略无法解析的 SSE 消息：",
      eventName,
      rawData,
      error,
    );
    return;
  }

  // 普通 HarnessEvent 使用 payload.data；
  // stream.error、stream.closed 可能直接返回数据。
  const data = payload.data ?? payload;

        if (eventName === "model.delta") {
          updateAssistant(turnId, (item) => ({
            ...item,
            text: item.text + String(data.text ?? ""),
          }));
        }

        if (eventName === "assistant.completed") {
          updateAssistant(turnId, (item) => ({
            ...item,
            text: String(data.text ?? item.text),
            pending: false,
          }));
        }

        if (eventName === "tool.started") {
          setTools((items) => [
            ...items,
            {
              id: `${turnId}-${payload.sequence}`,
              name: String(data.tool_name),
              status: "运行中",
              content: data.input,
            },
          ]);
        }

        if (eventName === "tool.completed") {
          setTools((items) => [
            ...items,
            {
              id: `${turnId}-${payload.sequence}`,
              name: String(data.tool_name),
              status: data.is_error ? "失败" : "完成",
              content: data.output,
            },
          ]);
        }

        if (eventName === "approval.required") {
          setApproval({
            approvalId: String(data.approval_id),
            request: data.request ?? {},
          });
        }

        if (eventName === "turn.failed" ||
            eventName === "stream.error") {
          const text = String(
            data.message ?? data.error_message ?? "Agent 执行失败",
          );
          updateAssistant(turnId, (item) => ({
            ...item,
            text,
            pending: false,
            error: true,
          }));
          setError(text);
          setActiveTurn(null);
        }

        if (eventName === "turn.completed" ||
            eventName === "stream.closed") {
          setActiveTurn(null);
          controller.current?.abort();
        }
      },

      onerror(value) {
        throw value;
      },
    });
  }

  async function send(event: FormEvent) {
    event.preventDefault();
    const content = input.trim();

    if (!session || !content || activeTurn) return;

    setInput("");
    setError("");
    setMessages((items) => [
      ...items,
      {
        id: crypto.randomUUID(),
        role: "user",
        text: content,
      },
    ]);

    try {
      const turn = await request<{ turn_id: string }>(
        `/sessions/${session.id}/turns`,
        {
          method: "POST",
          body: JSON.stringify({ content }),
        },
      );

      setActiveTurn(turn.turn_id);
      setMessages((items) => [
        ...items,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          turnId: turn.turn_id,
          text: "",
          pending: true,
        },
      ]);

      void consumeEvents(turn.turn_id).catch((value) => {
        if (!controller.current?.signal.aborted) {
          setError(
            value instanceof Error ? value.message : "SSE 连接失败",
          );
          setActiveTurn(null);
        }
      });
    } catch (value) {
      setError(value instanceof Error ? value.message : "发送失败");
    }
  }

  async function cancel() {
    if (!activeTurn) return;
    await request(`/turns/${activeTurn}/cancel`, {
      method: "POST",
    });
  }

  async function decide(decision: string) {
    if (!approval) return;

    await request(`/approvals/${approval.approvalId}`, {
      method: "POST",
      body: JSON.stringify({
        decision,
        feedback: null,
        resolved_by: "react-web",
      }),
    });

    setApproval(null);
  }

  const choices = approval?.request.choices ?? [
    { decision: "allow_once", label: "本次允许" },
    { decision: "deny_once", label: "拒绝" },
  ];

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="brand">
          <BookOpen size={22} />
          <strong>EduHarness</strong>
        </div>

        <label>
          学生编号
          <input
            value={externalId}
            onChange={(e) => setExternalId(e.target.value)}
          />
        </label>

        <label>
          学生姓名
          <input
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
          />
        </label>

        <button className="secondary" onClick={createLearningSession}>
          新建学习会话
        </button>

        {session && (
          <div className="session-info">
            <span>Session ID</span>
            <code>{session.id}</code>
            <span>Student ID</span>
            <code>{session.student_id}</code>
          </div>
        )}
      </aside>

      <main className="chat">
        <header>
          <div>
            <h1>学习对话</h1>
            <small>{session ? "会话已连接" : "请先创建会话"}</small>
          </div>

          {activeTurn && (
            <button
              className="icon danger"
              title="停止回答"
              onClick={cancel}
            >
              <CircleStop size={20} />
            </button>
          )}
        </header>

        <section className="messages">
          {!messages.length && (
            <div className="empty">
              <BookOpen size={36} />
              <h2>开始一次学习对话</h2>
              <p>可以提问、检索题库或请求自适应练习。</p>
            </div>
          )}

          {messages.map((message) => (
            <article
              key={message.id}
              className={`message ${message.role} ${
                message.error ? "message-error" : ""
              }`}
            >
              <b>{message.role === "user" ? "你" : "EduHarness"}</b>
              <div>
                {(
                    message.role === "assistant"
                        ? formatPlainMath(message.text)
                        : message.text
                ) || (
                    message.pending
                        ? "正在思考..."
                        : ""
                )}
              </div>
              {message.pending && (
                  <LoaderCircle className="spin" size={15}/>
              )}
            </article>
          ))}
        </section>

        {error && <div className="error"><X size={16} />{error}</div>}

        <form className="composer" onSubmit={send}>
          <textarea
            value={input}
            disabled={!session || Boolean(activeTurn)}
            placeholder={session ? "输入你的问题" : "请先创建会话"}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                e.currentTarget.form?.requestSubmit();
              }
            }}
          />
          <button
            className="send"
            title="发送"
            disabled={!session || !input.trim() || Boolean(activeTurn)}
          >
            <Send size={20} />
          </button>
        </form>
      </main>

      <aside className="activity">
        <h2><Wrench size={18} />Agent 活动</h2>
        {!tools.length && <p>等待工具调用</p>}

        {tools.map((tool) => (
          <details key={tool.id}>
            <summary>
              {tool.status === "完成"
                ? <Check size={14} />
                : <LoaderCircle size={14} />}
              {tool.name} · {tool.status}
            </summary>
            <pre>{JSON.stringify(tool.content, null, 2)}</pre>
          </details>
        ))}
      </aside>

      {approval && (
        <div className="backdrop">
          <div className="approval">
            <ShieldAlert size={28} />
            <h2>需要授权</h2>
            <pre>{JSON.stringify(approval.request, null, 2)}</pre>
            <div className="approval-actions">
              {choices.map((choice: any) => (
                <button
                  key={choice.decision}
                  className={
                    String(choice.decision).startsWith("allow")
                      ? "primary"
                      : "secondary"
                  }
                  onClick={() => void decide(choice.decision)}
                >
                  {choice.label ?? choice.decision}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}