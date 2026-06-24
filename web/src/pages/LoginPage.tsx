import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";

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
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-header">
          <h1>ComfyUI Workbench</h1>
          <p>
            {inviteToken
              ? "You've been invited! Choose a username to join."
              : mode === "login"
              ? "Sign in to your workspace"
              : "Create a new account"}
          </p>
        </div>

        <form onSubmit={handleSubmit} className="auth-form">
          {error && <div className="auth-error">{error}</div>}

          <div className="form-group">
            <label htmlFor="username">Username</label>
            <input
              id="username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="your-username"
              required
              minLength={2}
              autoFocus
            />
          </div>

          {(mode === "register" || inviteToken) && (
            <div className="form-group">
              <label htmlFor="displayName">Display Name (optional)</label>
              <input
                id="displayName"
                type="text"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder="Your Name"
              />
            </div>
          )}

          {!inviteToken && (
            <div className="form-group">
              <label htmlFor="password">Password</label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                required={!inviteToken}
                minLength={4}
              />
            </div>
          )}

          <button type="submit" className="btn-primary btn-full" disabled={loading}>
            {loading ? "Loading..." : inviteToken ? "Join Workspace" : mode === "login" ? "Sign In" : "Create Account"}
          </button>
        </form>

        {!inviteToken && (
          <div className="auth-toggle">
            {mode === "login" ? (
              <span>
                No account?{" "}
                <button className="link-btn" onClick={() => setMode("register")}>
                  Register
                </button>
              </span>
            ) : (
              <span>
                Have an account?{" "}
                <button className="link-btn" onClick={() => setMode("login")}>
                  Sign In
                </button>
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
