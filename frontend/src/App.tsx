import { useState } from "react";
import { BookOpen, Code2, GraduationCap } from "lucide-react";
import LeetCodeApp from "./LeetCodeApp";
import StudentChat from "./StudentChat";
import TeacherApp from "./TeacherApp";

type View = "chat" | "teacher" | "leetcode";

export default function App() {
  const [view, setView] = useState<View>("leetcode");

  return (
    <div className="app-shell">
      <nav className="topnav">
        <div className="topnav-brand">
          <BookOpen size={18} />
          <strong>EduHarness</strong>
          <span className="muted">可审计 AI 助教</span>
        </div>
        <div className="topnav-tabs">
          <button
            className={`tabbtn ${view === "leetcode" ? "active" : ""}`}
            onClick={() => setView("leetcode")}
          >
            <Code2 size={15} /> LeetCode
          </button>
          <button
            className={`tabbtn ${view === "chat" ? "active" : ""}`}
            onClick={() => setView("chat")}
          >
            学生对话
          </button>
          <button
            className={`tabbtn ${view === "teacher" ? "active" : ""}`}
            onClick={() => setView("teacher")}
          >
            <GraduationCap size={15} /> 教师工作台
          </button>
        </div>
      </nav>

      <div className="view">
        {view === "chat" ? (
          <StudentChat />
        ) : view === "teacher" ? (
          <TeacherApp />
        ) : (
          <LeetCodeApp />
        )}
      </div>
    </div>
  );
}
