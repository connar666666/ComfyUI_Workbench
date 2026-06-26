import { useEffect, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  Cloud,
  Folder,
  Images,
  Layers,
  ListVideo,
  LogOut,
  Plus,
  PlusCircle,
  Server,
  UserPlus,
  Video,
  Workflow,
  Users,
} from "lucide-react";
import { Navigate, NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { AssetsPage } from "./pages/AssetsPage";
import { NewJobPage } from "./pages/NewJobPage";
import { JobsPage } from "./pages/JobsPage";
import { ComfyQueuePage } from "./pages/ComfyQueuePage";
import { VideosPage } from "./pages/VideosPage";
import { CanvasPage } from "./features/canvas/components/CanvasPage";
import { LoginPage } from "./pages/LoginPage";
import { JoinPage } from "./pages/JoinPage";
import { InvitePage } from "./pages/InvitePage";
import { RemoteWorkflowsPage } from "./pages/RemoteWorkflowsPage";
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
        <div className="sidebar-project-kicker">当前项目</div>
        {currentProject ? (
          <>
            <div className="sidebar-project-name">
              <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {currentProject.name}
              </span>
              <ChevronRight size={14} color="var(--sidebar-muted)" />
            </div>
            <div className="sidebar-project-meta">
              {currentProject.memberCount != null
                ? `${currentProject.memberCount} 名成员 · 工作区`
                : "项目工作区"}
            </div>
          </>
        ) : (
          <>
            <div className="sidebar-project-name sidebar-project-empty">选择项目</div>
            <div className="sidebar-project-meta">前往项目空间开始</div>
          </>
        )}
      </div>

      {currentProject && (
        <nav className="sidebar-project-nav" aria-label="当前项目子导航">
          <NavLink
            to={`/projects/${currentProject.id}`}
            end
            className="sidebar-project-nav-item"
          >
            <Folder size={13} />
            <span>项目空间</span>
          </NavLink>
          <NavLink to="/assets" className="sidebar-project-nav-item">
            <Images size={13} />
            <span>素材库</span>
          </NavLink>
          <NavLink to="/canvas" className="sidebar-project-nav-item">
            <Workflow size={13} />
            <span>创作画布</span>
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
          <NavLink to="/videos" className="sidebar-project-nav-item">
            <Video size={13} />
            <span>视频库</span>
          </NavLink>
        </nav>
      )}

      {isAuthenticated ? (
        <>
          <div className="sidebar-group-label">导航</div>
          <NavLink to="/projects" end>
            <Layers size={15} />
            项目列表
          </NavLink>

          <div className="sidebar-group-label">工具</div>
          <NavLink to="/jobs/new"><PlusCircle size={15} />创建任务</NavLink>
          <NavLink to="/jobs"><ListVideo size={15} />任务队列</NavLink>
          <NavLink to="/comfyui"><Server size={15} />ComfyUI 队列</NavLink>
          <NavLink to="/remote-workflows"><Cloud size={15} />远程工作流</NavLink>

          {user?.role === "admin" && (
            <>
              <div className="sidebar-group-label">管理</div>
              <NavLink to="/invite"><UserPlus size={15} />邀请成员</NavLink>
            </>
          )}

          <div className="sidebar-status-card">
            <div className="sidebar-status-row">
              <span>渲染队列</span>
              <strong style={{ color: "var(--accent)" }}>3 进行中</strong>
            </div>
            <div className="sidebar-status-row">
              <span>存储使用</span>
              <strong>842 GB / 1 TB</strong>
            </div>
            <div className="sidebar-storage-bar">
              <div />
            </div>
          </div>

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
          <Route path="/jobs/new" element={isAuthenticated ? <NewJobPage /> : <Navigate to="/login" />} />
          <Route path="/jobs" element={isAuthenticated ? <JobsPage /> : <Navigate to="/login" />} />
          <Route path="/comfyui" element={isAuthenticated ? <ComfyQueuePage /> : <Navigate to="/login" />} />
          <Route path="/remote-workflows" element={isAuthenticated ? <RemoteWorkflowsPage /> : <Navigate to="/login" />} />
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