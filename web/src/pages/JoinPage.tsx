import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";

export function JoinPage() {
  const [inviteLink, setInviteLink] = useState("");
  const [error, setError] = useState("");
  const navigate = useNavigate();

  const handlePaste = async () => {
    setError("");
    try {
      const text = await navigator.clipboard.readText();
      setInviteLink(text);
    } catch {
      // clipboard access denied — user can paste manually
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    // Extract token from full invite URL or raw token
    let token = inviteLink.trim();
    try {
      const url = new URL(token);
      token = url.searchParams.get("token") || token;
    } catch {
      // not a URL, treat as raw token
    }

    if (!token) {
      setError("Please paste your invite link or token");
      return;
    }

    navigate(`/login?token=${encodeURIComponent(token)}`);
  };

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-header">
          <h1>Join Workspace</h1>
          <p>Paste your invite link to join the shared workbench.</p>
        </div>

        <form onSubmit={handleSubmit} className="auth-form">
          {error && <div className="auth-error">{error}</div>}

          <div className="form-group">
            <label htmlFor="invite">Invite Link or Token</label>
            <textarea
              id="invite"
              value={inviteLink}
              onChange={(e) => setInviteLink(e.target.value)}
              placeholder="https://.../join?token=..."
              rows={3}
              autoFocus
            />
            <button type="button" className="btn-secondary btn-sm" onClick={handlePaste} style={{ marginTop: 8 }}>
              Paste from Clipboard
            </button>
          </div>

          <button type="submit" className="btn-primary btn-full">
            Continue
          </button>
        </form>
      </div>
    </div>
  );
}
