import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { createProject, listProjects } from "../api/client";
import type { Project } from "../types";

export function ProjectsPage() {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [creating, setCreating] = useState(false);

  const loadProjects = () =>
    listProjects()
      .then((data) => {
        setProjects(data);
        setError("");
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load projects"))
      .finally(() => setLoading(false));

  useEffect(() => {
    loadProjects();
  }, []);

  const handleCreate = async (event: FormEvent) => {
    event.preventDefault();
    const trimmedName = name.trim();
    if (!trimmedName) {
      setError("项目名称不能为空");
      return;
    }
    setCreating(true);
    try {
      await createProject({ name: trimmedName, description: description.trim(), members: [] });
      setName("");
      setDescription("");
      setShowCreate(false);
      setLoading(true);
      await loadProjects();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create project");
    } finally {
      setCreating(false);
    }
  };

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
        <div className="page-toolbar">
          <span className="page-count">{projects.length} projects</span>
          <button className="btn-primary" type="button" onClick={() => setShowCreate((current) => !current)}>
            新建项目
          </button>
        </div>
      </div>

      {error && <div className="auth-error" style={{ marginBottom: 16 }}>{error}</div>}

      {showCreate && (
        <form className="auth-card" style={{ marginBottom: 16, maxWidth: 560 }} onSubmit={handleCreate}>
          <label>
            项目名称
            <input value={name} onChange={(event) => setName(event.target.value)} placeholder="例如：品牌短片 A" />
          </label>
          <label>
            项目描述
            <textarea
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="这个项目的目标、素材范围或交付说明"
              rows={3}
            />
          </label>
          <div className="page-toolbar">
            <button className="btn-primary" type="submit" disabled={creating}>
              {creating ? "创建中..." : "创建项目"}
            </button>
            <button className="btn-secondary" type="button" onClick={() => setShowCreate(false)}>
              取消
            </button>
          </div>
        </form>
      )}

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
              <th style={{ width: 96 }}></th>
            </tr>
          </thead>
          <tbody>
            {projects.map((project) => (
              <tr key={project.id} onClick={() => navigate(`/projects/${project.id}`)} style={{ cursor: "pointer" }}>
                <td>
                  <Link to={`/projects/${project.id}`} className="filename-cell" onClick={(event) => event.stopPropagation()}>{project.name}</Link>
                  <div className="muted">{project.description || "无描述"}</div>
                </td>
                <td><span className="kind-tag">{project.current_user_role || "owner"}</span></td>
                <td className="muted">{project.member_count ?? project.members?.length ?? 0} members</td>
                <td className="muted">{project.updated_at ? new Date(project.updated_at).toLocaleString("zh-CN") : "-"}</td>
                <td style={{ width: 96 }}>
                  <button
                    className="btn-secondary btn-sm"
                    type="button"
                    onClick={(event) => {
                      event.stopPropagation();
                      navigate(`/projects/${project.id}`);
                    }}
                    aria-label={`打开项目 ${project.name}`}
                  >
                    打开
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
