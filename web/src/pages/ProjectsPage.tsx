import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listProjects } from "../api/client";
import type { Project } from "../types";

export function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    listProjects()
      .then((data) => {
        setProjects(data);
        setError("");
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load projects"))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="page">
        <h1>项目</h1>
        <div className="empty-state">加载中...</div>
      </div>
    );
  }

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>项目</h1>
          <p className="page-subtitle">每个项目拥有自己的工作流面板、素材库和任务历史。</p>
        </div>
        <span className="page-count">{projects.length} projects</span>
      </div>

      {error && <div className="auth-error" style={{ marginBottom: 16 }}>{error}</div>}

      {projects.length === 0 ? (
        <div className="empty-state">暂无项目。</div>
      ) : (
        <table>
          <thead>
            <tr>
              <th>项目</th>
              <th style={{ width: 110 }}>角色</th>
              <th style={{ width: 120 }}>成员</th>
              <th style={{ width: 150 }}>更新</th>
            </tr>
          </thead>
          <tbody>
            {projects.map((project) => (
              <tr key={project.id}>
                <td>
                  <Link to={`/projects/${project.id}`} className="filename-cell">{project.name}</Link>
                  <div className="muted">{project.description || "无描述"}</div>
                </td>
                <td><span className="kind-tag">{project.current_user_role || "owner"}</span></td>
                <td className="muted">{project.member_count ?? project.members?.length ?? 0} members</td>
                <td className="muted">{project.updated_at ? new Date(project.updated_at).toLocaleString("zh-CN") : "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
