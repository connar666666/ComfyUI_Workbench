import { Bell, GitBranch, Rocket, Search } from "lucide-react";
import { useAuth } from "../../../contexts/AuthContext";

const CANVAS_VERSION = "v1.4.0-alpha";

export function CanvasTopbar() {
  const { user } = useAuth();
  const initial = (user?.display_name || user?.username || "?").slice(0, 1).toUpperCase();

  return (
    <header className="canvas-topbar">
      <div className="canvas-topbar-brand">
        <span className="brand-mark">F</span>
        <span className="canvas-topbar-title">FrameWeave AIGC 工作室</span>
        <span className="canvas-topbar-version">{CANVAS_VERSION}</span>
      </div>

      <div className="canvas-topbar-search">
        <Search size={15} />
        <input
          type="text"
          placeholder="搜索工作流节点、提示词、资产…"
          aria-label="搜索画布内容"
        />
        <kbd>⌘K</kbd>
      </div>

      <div className="canvas-topbar-actions">
        <button type="button" className="btn-primary canvas-topbar-cta">
          <Rocket size={14} />
          创建发布
        </button>
        <button type="button" className="canvas-topbar-icon" title="版本树">
          <GitBranch size={16} />
        </button>
        <button type="button" className="canvas-topbar-icon" title="通知">
          <Bell size={16} />
        </button>
        <div className="canvas-topbar-avatar" title={user?.display_name || user?.username || ""}>
          {initial}
        </div>
      </div>
    </header>
  );
}