import { NavLink, Route, Routes } from "react-router-dom";
import { Images, ListVideo, PlusCircle, Server, Video } from "lucide-react";
import { AssetsPage } from "./pages/AssetsPage";
import { NewJobPage } from "./pages/NewJobPage";
import { JobsPage } from "./pages/JobsPage";
import { ComfyQueuePage } from "./pages/ComfyQueuePage";
import { VideosPage } from "./pages/VideosPage";

export function App() {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">OpenClaw Workbench</div>
        <NavLink to="/assets"><Images size={18} />素材库</NavLink>
        <NavLink to="/jobs/new"><PlusCircle size={18} />创建任务</NavLink>
        <NavLink to="/jobs"><ListVideo size={18} />任务队列</NavLink>
        <NavLink to="/comfyui"><Server size={18} />ComfyUI 队列</NavLink>
        <NavLink to="/videos"><Video size={18} />视频库</NavLink>
      </aside>
      <main className="main">
        <Routes>
          <Route path="/" element={<AssetsPage />} />
          <Route path="/assets" element={<AssetsPage />} />
          <Route path="/jobs/new" element={<NewJobPage />} />
          <Route path="/jobs" element={<JobsPage />} />
          <Route path="/comfyui" element={<ComfyQueuePage />} />
          <Route path="/videos" element={<VideosPage />} />
        </Routes>
      </main>
    </div>
  );
}
