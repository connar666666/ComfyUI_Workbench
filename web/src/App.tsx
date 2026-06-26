import { Navigate, NavLink, Route, Routes } from "react-router-dom";
import { Briefcase, Cloud, Images, ListVideo, LogOut, PlusCircle, Server, UserPlus, Video, Workflow } from "lucide-react";
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

function AppShell() {
  const { user, isAuthenticated, isLoading, logout } = useAuth();

  if (isLoading) {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <p style={{ textAlign: "center", color: "var(--main-muted)" }}>加载中...</p>
        </div>
      </div>
    );
  }

  // Public routes: login, join
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">ComfyUI Workbench</div>

        {isAuthenticated ? (
          <>
            <NavLink to="/projects"><Briefcase size={18} />项目</NavLink>
            <NavLink to="/assets"><Images size={18} />素材库</NavLink>
            <NavLink to="/canvas"><Workflow size={18} />创作画布</NavLink>
            <NavLink to="/jobs/new"><PlusCircle size={18} />创建任务</NavLink>
            <NavLink to="/jobs"><ListVideo size={18} />任务队列</NavLink>
            <NavLink to="/comfyui"><Server size={18} />ComfyUI 队列</NavLink>
            <NavLink to="/remote-workflows"><Cloud size={18} />远程工作流</NavLink>
            <NavLink to="/videos"><Video size={18} />视频库</NavLink>
            {user?.role === "admin" && (
              <NavLink to="/invite"><UserPlus size={18} />邀请成员</NavLink>
            )}

            <div className="sidebar-spacer" />

            <div className="sidebar-user">
              <div className="sidebar-user-info">
                <span className="sidebar-user-name">{user?.display_name || user?.username}</span>
                <span className={`sidebar-user-role role-${user?.role}`}>{user?.role}</span>
              </div>
              <button className="sidebar-logout" onClick={logout} title="退出登录">
                <LogOut size={16} />
              </button>
            </div>
          </>
        ) : (
          <div className="sidebar-guest">
            <span className="sidebar-muted">请登录以使用工作台</span>
          </div>
        )}
      </aside>

      <main className="main">
        <Routes>
          {/* Public */}
          <Route path="/login" element={isAuthenticated ? <Navigate to="/projects" /> : <LoginPage />} />
          <Route path="/join" element={<JoinPage />} />

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
