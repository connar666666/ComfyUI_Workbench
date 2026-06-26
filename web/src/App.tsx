import { useEffect, useState } from "react";
import {
  Folder,
  HardDrive,
  History,
  Images,
  Layers,
  LogOut,
  Plus,
  Server,
  Sparkles,
  UserPlus,
  Users,
  Video,
  Workflow,
} from "lucide-react";
import { Navigate, NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { AssetsPage } from "./pages/AssetsPage";
import { JobsPage } from "./pages/JobsPage";
import { ComfyQueuePage } from "./pages/ComfyQueuePage";
import { VideosPage } from "./pages/VideosPage";
import { CanvasPage } from "./features/canvas/components/CanvasPage";
import { LoginPage } from "./pages/LoginPage";
import { JoinPage } from "./pages/JoinPage";
import { InvitePage } from "./pages/InvitePage";
import { ProjectsPage } from "./pages/ProjectsPage";
import { ProjectDetailPage } from "./pages/ProjectDetailPage";
import { AuthProvider, useAuth } from "./contexts/AuthContext";

const CURRENT_PROJECT_KEY = "workbench.currentProject";

type CurrentProjectSnapshot = {
  id: string;
  name: string;
  memberCount?: number;
};

function readCurrentProject(): CurrentProjectSnapshot | null {
  try {
    const raw = localStorage.getItem(CURRENT_PROJECT_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed.id !== "string" || typeof parsed.name !== "string") return null;
    return parsed;
  } catch {
    return null;
  }
}

function Sidebar() {
  const { user, isAuthenticated, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [currentProject, setCurrentProject] = useState<CurrentProjectSnapshot | null>(() => readCurrentProject());

  useEffect(() => {
    const handler = () => setCurrentProject(readCurrentProject());
    window.addEventListener("workbench:current-project-changed", handler);
    window.addEventListener("storage", handler);
    return () => {
      window.removeEventListener("workbench:current-project-changed", handler);
      window.removeEventListener("storage", handler);
    };
  }, []);

  const initial = (user?.display_name || user?.username || "?").slice(0, 1).toUpperCase();
  const insideProject = !!currentProject && location.pathname.startsWith("/projects/");
  const RENDER_QUEUE_BADGE = 1;

  return (
    <aside className="sidebar">
      <div className="brand">
        <span className="brand-mark">F</span>
        <span>FrameWeave</span>
      </div>

      <div
        className={`sidebar-project-card${insideProject ? " is-active" : ""}`}
        role="button"
        tabIndex={0}
        onClick={() => currentProject && navigate(`/projects/${currentProject.id}`)}
        onKeyDown={(event) => {
          if ((event.key === "Enter" || event.key === " ") && currentProject) {
            event.preventDefault();
            navigate(`/projects/${currentProject.id}`);
          }
        }}
      >
        <div className="sidebar-project-icon">
          <Sparkles size={16} />
        </div>
        <div className="sidebar-project-info">
          <div className="sidebar-project-kicker">当前项目</div>
          {currentProject ? (
            <div className="sidebar-project-name">
              <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {currentProject.name}
              </span>
            </div>
          ) : (
            <div className="sidebar-project-name sidebar-project-empty">未命名视频序列</div>
          )}
        </div>
      </div>

      {currentProject && (
        <nav className="sidebar-project-nav" aria-label="当前项目子导航">
          <NavLink to="/canvas" end className="sidebar-project-nav-item">
            <Workflow size={14} />
            <span>视频创作</span>
            <button
              type="button"
              className="sidebar-project-nav-add"
              title="在此项目中新建画布"
              onClick={(event) => {
                event.preventDefault();
                event.stopPropagation();
                navigate("/canvas", { state: { projectId: currentProject.id, action: "new" } });
              }}
            >
              <Plus size={11} />
            </button>
          </NavLink>
          <NavLink to="/assets" end className="sidebar-project-nav-item">
            <Images size={14} />
            <span>素材库</span>
          </NavLink>
          <NavLink
            to={`/projects/${currentProject.id}`}
            end
            className="sidebar-project-nav-item"
          >
            <Folder size={14} />
            <span>提示词助手</span>
          </NavLink>
          <NavLink to="/jobs" end className="sidebar-project-nav-item">
            <History size={14} />
            <span>历史记录</span>
          </NavLink>
          <NavLink to="/videos" end className="sidebar-project-nav-item">
            <Video size={14} />
            <span>视频库</span>
          </NavLink>
        </nav>
      )}

      {isAuthenticated ? (
        <>
          <div className="sidebar-section-divider" />

          <NavLink to="/comfyui" end className="sidebar-status-link">
            <span className="sidebar-status-link-row">
              <Layers size={15} />
              <span>渲染队列</span>
            </span>
            <span className="sidebar-status-badge">{RENDER_QUEUE_BADGE}</span>
          </NavLink>

          <NavLink to="/jobs" end className="sidebar-status-link">
            <span className="sidebar-status-link-row">
              <HardDrive size={15} />
              <span>存储空间</span>
            </span>
            <span className="sidebar-storage-inline">
              <span className="sidebar-storage-inline-text">842 GB</span>
              <span className="sidebar-storage-inline-track">
                <span className="sidebar-storage-inline-fill" style={{ width: "82%" }} />
              </span>
            </span>
          </NavLink>

          <div className="sidebar-section-divider" />

          <NavLink to="/projects" end className="sidebar-tool-link">
            <Server size={14} />
            <span>切换项目</span>
          </NavLink>

          {user?.role === "admin" && (
            <NavLink to="/invite" end className="sidebar-tool-link">
              <UserPlus size={14} />
              <span>邀请成员</span>
            </NavLink>
          )}

          <div className="sidebar-spacer" />

          <div className="sidebar-user">
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <div
                style={{
                  width: 32,
                  height: 32,
                  borderRadius: "50%",
                  background: "linear-gradient(135deg, #d0bcff, #4edea3)",
                  color: "#0b1326",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontWeight: 700,
                  fontSize: 13,
                  border: "1px solid rgba(208, 188, 255, 0.30)",
                }}
              >
                {initial}
              </div>
              <div className="sidebar-user-info">
                <span className="sidebar-user-name">{user?.display_name || user?.username}</span>
                <span className={`sidebar-user-role role-${user?.role}`}>
                  <Users size={9} style={{ display: "inline", marginRight: 4, verticalAlign: "-1px" }} />
                  {user?.role}
                </span>
              </div>
            </div>
            <button className="sidebar-logout" onClick={logout} title="退出登录">
              <LogOut size={14} />
            </button>
          </div>
        </>
      ) : (
        <div className="sidebar-guest">
          <span className="sidebar-muted">请登录以使用工作台</span>
        </div>
      )}
    </aside>
  );
}

function AppShell() {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <p style={{ textAlign: "center", color: "var(--main-muted)" }}>加载中...</p>
        </div>
      </div>
    );
  }

  // Public routes: login, join — render without sidebar
  const isPublicRoute = location.pathname === "/login" || location.pathname === "/join";

  if (isPublicRoute) {
    return (
      <Routes>
        <Route path="/login" element={isAuthenticated ? <Navigate to="/projects" /> : <LoginPage />} />
        <Route path="/join" element={<JoinPage />} />
      </Routes>
    );
  }

  return (
    <div className="app-shell">
      <Sidebar />

      <main className="main">
        <Routes>
          {/* Protected */}
          <Route path="/" element={isAuthenticated ? <Navigate to="/projects" /> : <Navigate to="/login" />} />
          <Route path="/projects" element={isAuthenticated ? <ProjectsPage /> : <Navigate to="/login" />} />
          <Route path="/projects/:projectId" element={isAuthenticated ? <ProjectDetailPage /> : <Navigate to="/login" />} />
          <Route path="/assets" element={isAuthenticated ? <AssetsPage /> : <Navigate to="/login" />} />
          <Route path="/canvas" element={isAuthenticated ? <CanvasPage /> : <Navigate to="/login" />} />
          <Route path="/jobs" element={isAuthenticated ? <JobsPage /> : <Navigate to="/login" />} />
          <Route path="/comfyui" element={isAuthenticated ? <ComfyQueuePage /> : <Navigate to="/login" />} />
          <Route path="/videos" element={isAuthenticated ? <VideosPage /> : <Navigate to="/login" />} />
          <Route path="/invite" element={isAuthenticated ? <InvitePage /> : <Navigate to="/login" />} />
        </Routes>
      </main>
    </div>
  );
}

export function App() {
  return (
    <AuthProvider>
      <AppShell />
    </AuthProvider>
  );
}