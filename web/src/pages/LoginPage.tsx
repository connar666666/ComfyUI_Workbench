import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";

function normalizeAuthErrorMessage(mode: "login" | "register", err: unknown): string {
  const message = err instanceof Error ? err.message.trim() : "";
  const lower = message.toLowerCase();
  const status =
    typeof err === "object" && err !== null && "status" in err && typeof (err as { status?: unknown }).status === "number"
      ? (err as { status: number }).status
      : undefined;

  if (mode === "login") {
    if (status === 403) {
      return "账户不存在或密码错误";
    }
    if (
      lower.includes("invalid username or password") ||
      lower.includes("login failed") ||
      lower.includes("not authenticated")
    ) {
      return "账户不存在或密码错误";
    }
    if (lower.includes("invite-only")) {
      return "该账户只能通过邀请链接登录";
    }
    return message || "登录失败，请稍后重试";
  }

  if (status === 409) {
    return "用户名已存在";
  }
  if (lower.includes("already taken") || lower.includes("already exists") || lower.includes("registration failed")) {
    return "用户名已存在";
  }
  return message || "注册失败，请稍后重试";
}

export function LoginPage() {
  const [searchParams] = useSearchParams();
  const inviteToken = searchParams.get("token");
  const isJoin = Boolean(inviteToken);

  const [mode, setMode] = useState<"login" | "register">(isJoin ? "register" : "login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const { login, register, joinWithInvite } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      if (inviteToken) {
        await joinWithInvite(inviteToken, username, displayName || undefined);
      } else if (mode === "login") {
        await login(username, password);
      } else {
        await register(username, password, displayName || undefined);
      }
      navigate("/jobs");
    } catch (err) {
      setError(inviteToken ? (err instanceof Error ? err.message : "加入失败，请稍后重试") : normalizeAuthErrorMessage(mode, err));
    } finally {
      setLoading(false);
    }
  };

  const switchMode = (nextMode: "login" | "register") => {
    setMode(nextMode);
    setError("");
  };

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-header">
          <h1>
            {inviteToken
              ? "加入共享工作台"
              : mode === "login"
              ? "登录"
              : "注册"}
          </h1>
          <p>
            {inviteToken
              ? "你收到了一个邀请，请设置用户名后加入。"
              : mode === "login"
              ? "登录你的工作台"
              : "创建新账户"}
          </p>
        </div>

        <form onSubmit={handleSubmit} className="auth-form">
          {error && (
            <div className="auth-error" role="alert" aria-live="polite">
              {error}
            </div>
          )}

          <div className="form-group">
            <label htmlFor="username">用户名</label>
            <input
              className="auth-input"
              id="username"
              type="text"
              value={username}
              onChange={(e) => {
                setUsername(e.target.value);
                if (error) setError("");
              }}
              placeholder="请输入用户名"
              required
              minLength={2}
              autoFocus
            />
          </div>

          {(mode === "register" || inviteToken) && (
            <div className="form-group">
              <label htmlFor="displayName">显示名称（可选）</label>
              <input
                className="auth-input"
                id="displayName"
                type="text"
                value={displayName}
                onChange={(e) => {
                  setDisplayName(e.target.value);
                  if (error) setError("");
                }}
                placeholder="用于展示的名称"
              />
            </div>
          )}

          {!inviteToken && (
            <div className="form-group">
              <label htmlFor="password">密码</label>
              <input
                className="auth-input"
                id="password"
                type="password"
                value={password}
                onChange={(e) => {
                  setPassword(e.target.value);
                  if (error) setError("");
                }}
                placeholder="请输入密码"
                required={!inviteToken}
                minLength={4}
              />
            </div>
          )}

          <button type="submit" className="btn-primary btn-full" disabled={loading}>
            {loading ? "处理中..." : inviteToken ? "加入工作台" : mode === "login" ? "登录" : "注册并进入"}
          </button>
        </form>

        {!inviteToken && (
          <div className="auth-toggle">
            {mode === "login" ? (
              <span>
                还没有账户？{" "}
                <button type="button" className="link-btn" onClick={() => switchMode("register")}>
                  去注册
                </button>
              </span>
            ) : (
              <span>
                已有账户？{" "}
                <button type="button" className="link-btn" onClick={() => switchMode("login")}>
                  去登录
                </button>
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
