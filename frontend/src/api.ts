const API = "/api/v1";

export async function jcall<T>(
  path: string,
  options: {
    method?: string;
    body?: unknown;
    token?: string;
    asBlob?: boolean;
  } = {},
): Promise<T> {
  const headers: Record<string, string> = {};
  if (options.token) headers["Authorization"] = `Bearer ${options.token}`;
  if (options.body !== undefined) headers["Content-Type"] = "application/json";

  const response = await fetch(`${API}${path}`, {
    method: options.method ?? "GET",
    headers,
    body:
      options.body !== undefined
        ? JSON.stringify(options.body)
        : undefined,
  });

  if (options.asBlob) {
    if (!response.ok) throw new Error(`请求失败：HTTP ${response.status}`);
    return (await response.blob()) as T;
  }

  const text = await response.text();
  if (!response.ok) {
    let message = text || `请求失败：HTTP ${response.status}`;
    try {
      const parsed = JSON.parse(text);
      if (typeof parsed.detail === "string") message = parsed.detail;
    } catch {
      /* 保持原始错误文本 */
    }
    throw new Error(message);
  }
  return text ? (JSON.parse(text) as T) : (undefined as T);
}

export function readToken(): string {
  return localStorage.getItem("eduharness_token") ?? "";
}

export function writeToken(token: string): void {
  localStorage.setItem("eduharness_token", token);
}

export function clearToken(): void {
  localStorage.removeItem("eduharness_token");
}

export type Course = {
  id: string;
  name: string;
  subject: string;
  description: string;
  created_at: string;
};

export type StudentRow = {
  id: string;
  external_id: string;
  display_name: string | null;
};

export type MasteryRow = {
  knowledge_point_id: string;
  code: string;
  name: string;
  subject: string;
  mastery: number;
  confidence: number;
  attempts_count: number;
  prerequisites: string[];
  last_practiced_at: string | null;
};

export type CockpitPoint = {
  knowledge_point_id: string;
  code: string;
  name: string;
  practiced_students: number;
  attempts: number;
  avg_mastery: number;
  avg_confidence: number;
  at_risk_students: number;
};

export type Cockpit = {
  course_id: string;
  name: string;
  subject: string;
  student_count: number;
  knowledge_points: CockpitPoint[];
};

export type AppealRow = {
  id: string;
  attempt_id: string;
  student_id: string;
  display_name: string | null;
  reason: string;
  status: "pending" | "sustained" | "rejected";
  evidence_snapshot: {
    question_stem: string | null;
    answer: Record<string, unknown>;
    score: number;
    max_score: number;
    created_at: string;
    knowledge_points: Array<{
      code: string;
      name: string;
      weight: number;
    }>;
  };
  new_score: number | null;
  teacher_note: string | null;
  created_at: string;
  resolved_at: string | null;
};
