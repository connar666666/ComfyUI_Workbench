import { useState } from "react";
import { createInvite } from "../api/client";
import { useAuth } from "../contexts/AuthContext";
import { Copy, Check } from "lucide-react";

export function InvitePage() {
  const { user } = useAuth();
  const [role, setRole] = useState("member");
  const [maxUses, setMaxUses] = useState<number | null>(null);
  const [expiresInDays, setExpiresInDays] = useState(7);
  const [inviteLink, setInviteLink] = useState("");
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);

  const handleCreate = async () => {
    setError("");
    setInviteLink("");
    try {
      const result = await createInvite(role, maxUses, expiresInDays);
      setInviteLink(result.invite_link);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create invite");
    }
  };

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(inviteLink);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // fallback: select the text
    }
  };

  if (user?.role !== "admin") {
    return (
      <div className="page">
        <h1>邀请成员</h1>
        <div className="empty-state">只有管理员可以创建邀请链接。</div>
      </div>
    );
  }

  return (
    <div className="page">
      <div className="page-header">
        <h1>邀请成员</h1>
      </div>

      <div className="invite-panel" style={{ maxWidth: 560 }}>
        <p style={{ color: "var(--main-muted)", marginBottom: 20 }}>
          生成一个邀请链接，分享给团队成员即可加入工作空间。
        </p>

        {error && <div className="auth-error">{error}</div>}

        <div className="form-row">
          <div className="form-group">
            <label htmlFor="inviteRole">角色</label>
            <select id="inviteRole" value={role} onChange={(e) => setRole(e.target.value)}>
              <option value="member">Member</option>
              <option value="admin">Admin</option>
            </select>
          </div>

          <div className="form-group">
            <label htmlFor="inviteExpiry">有效期 (天)</label>
            <input
              id="inviteExpiry"
              type="number"
              value={expiresInDays}
              onChange={(e) => setExpiresInDays(Number(e.target.value))}
              min={1}
              max={90}
            />
          </div>

          <div className="form-group">
            <label htmlFor="inviteMaxUses">最大使用次数 (可选)</label>
            <input
              id="inviteMaxUses"
              type="number"
              value={maxUses ?? ""}
              onChange={(e) => setMaxUses(e.target.value ? Number(e.target.value) : null)}
              min={1}
              placeholder="无限制"
            />
          </div>
        </div>

        <button className="btn-primary" onClick={handleCreate}>
          生成邀请链接
        </button>

        {inviteLink && (
          <div className="invite-result">
            <label>邀请链接</label>
            <div className="invite-link-row">
              <input
                type="text"
                value={inviteLink}
                readOnly
                onClick={(e) => (e.target as HTMLInputElement).select()}
                className="invite-link-input"
              />
              <button className="btn-secondary" onClick={handleCopy} title="复制">
                {copied ? <Check size={16} /> : <Copy size={16} />}
              </button>
            </div>
            <p className="muted" style={{ fontSize: 12, marginTop: 8 }}>
              将此链接发送给团队成员，他们点击即可加入。
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
