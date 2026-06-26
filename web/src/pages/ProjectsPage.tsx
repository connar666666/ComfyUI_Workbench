import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, Database, Layers, Plus, Rocket, Users } from "lucide-react";
import { createProject, listProjects } from "../api/client";
import type { Project } from "../types";

const CURRENT_PROJECT_KEY = "workbench.currentProject";

const COVER_GRADIENTS = [
  "linear-gradient(135deg, #6d3bd7 0%, #4edea3 100%)",
  "linear-gradient(135deg, #d0bcff 0%, #6d3bd7 100%)",
  "linear-gradient(135deg, #ffb95f 0%, #d0bcff 100%)",
  "linear-gradient(135deg, #4edea3 0%, #0b1326 100%)",
  "linear-gradient(135deg, #6d3bd7 0%, #ffb95f 100%)",
  "linear-gradient(135deg, #1c1b1c 0%, #d0bcff 100%)",
  "linear-gradient(135deg, #00a572 0%, #6d3bd7 100%)",
  "linear-gradient(135deg, #ca8100 0%, #4edea3 100%)",
];

function pickGradient(seed: number): string {
  const idx = Math.abs(Math.floor(seed)) % COVER_GRADIENTS.length;
  return COVER_GRADIENTS[idx];
}

function pickInitial(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) return "?";
  return trimmed[0].toUpperCase();
}

function relativeTime(iso?: string): string {
  if (!iso) return "未更新";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "未更新";
  const now = Date.now();
  const diff = Math.max(0, now - then);
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "刚刚";
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days} 天前`;
  return new Date(iso).toLocaleDateString("zh-CN");
}

function memberCount(project: Project): number {
  return project.member_count ?? project.members?.length ?? 0;
}

function setCurrentProject(project: Project) {
  try {
    localStorage.setItem(
      CURRENT_PROJECT_KEY,
      JSON.stringify({
        id: String(project.id),
        name: project.name,
        memberCount: memberCount(project),
      }),
    );
    window.dispatchEvent(new Event("workbench:current-project-changed"));
  } catch {
    // localStorage may be unavailable; silently skip.
  }
}

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
      .catch((err) => setError(err instanceof Error ? err.message : "加载项目失败"))
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
      setError(err instanceof Error ? err.message : "创建项目失败");
    } finally {
      setCreating(false);
    }
  };

  const handleOpen = (project: Project) => {
    setCurrentProject(project);
    navigate(`/projects/${project.id}`);
  };

  const totalMembers = projects.reduce((sum, p) => sum + memberCount(p), 0);
  const recentCount = projects.filter((p) => {
    if (!p.updated_at) return false;
    const diff = Date.now() - new Date(p.updated_at).getTime();
    return diff < 7 * 24 * 60 * 60 * 1000;
  }).length;

  if (loading) {
    return (
      <div className="page">
        <div className="page-header">
          <div>
            <h1>项目空间</h1>
            <p className="page-subtitle">欢迎回到 FrameWeave AIGC 工作区。在这里管理生成式项目、训练模型与创意资产。</p>
          </div>
        </div>
        <div className="empty-state">加载中...</div>
      </div>
    );
  }

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>项目空间</h1>
          <p className="page-subtitle">欢迎回到 FrameWeave AIGC 工作区。在这里管理生成式项目、训练模型与创意资产。</p>
        </div>
        <div className="page-toolbar">
          <button className="btn-primary" type="button" onClick={() => setShowCreate((current) => !current)}>
            <Plus size={16} />
            创建新项目
          </button>
        </div>
      </div>

      {error && <div className="auth-error" style={{ marginBottom: 16 }}>{error}</div>}

      {showCreate && (
        <form className="project-create-form" onSubmit={handleCreate}>
          <label>
            项目名称
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="例如：品牌短片 A"
              autoFocus
            />
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

      {projects.length > 0 && (
        <div className="project-bento">
          <div className="project-bento-card glass-card">
            <div className="project-bento-icon"><Layers size={20} /></div>
            <div>
              <div className="project-bento-label">项目数</div>
              <div className="project-bento-value">
                {projects.length} <small>个项目</small>
              </div>
            </div>
          </div>
          <div className="project-bento-card glass-card">
            <div className="project-bento-icon green"><Rocket size={20} /></div>
            <div>
              <div className="project-bento-label">本周更新</div>
              <div className="project-bento-value">
                {recentCount} <small className="delta">活跃</small>
              </div>
            </div>
          </div>
          <div className="project-bento-card glass-card">
            <div className="project-bento-icon amber"><Users size={20} /></div>
            <div>
              <div className="project-bento-label">团队成员</div>
              <div className="project-bento-value">
                {totalMembers} <small>人次</small>
              </div>
            </div>
          </div>
          <div className="project-bento-card glass-card">
            <div className="project-bento-icon"><Database size={20} /></div>
            <div>
              <div className="project-bento-label">素材占用</div>
              <div className="project-bento-value">
                842 GB <small>/ 1 TB</small>
              </div>
            </div>
          </div>
        </div>
      )}

      {projects.length === 0 ? (
        <div className="empty-state">暂无项目。点击「创建新项目」开始。</div>
      ) : (
        <>
          <div className="project-section-header">
            <h2>最近项目</h2>
            <span className="section-count">{projects.length} 个项目</span>
          </div>

          <div className="project-grid">
            {projects.map((project) => (
              <article
                key={project.id}
                className="project-card"
                onClick={() => handleOpen(project)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    handleOpen(project);
                  }
                }}
                tabIndex={0}
                role="button"
                aria-label={`打开项目 ${project.name}`}
              >
                <div
                  className="project-card-cover"
                  style={{ background: pickGradient(project.id) }}
                >
                  <span className="project-card-chip">
                    {project.current_user_role?.toUpperCase() || "OWNER"}
                  </span>
                  <div className="project-card-cover-art">{pickInitial(project.name)}</div>
                  <div className="project-card-overlay">
                    <span className="project-card-overlay-pill">
                      进入工作区
                      <ArrowRight size={14} />
                    </span>
                  </div>
                </div>
                <div className="project-card-body">
                  <h3 className="project-card-title">{project.name}</h3>
                  <p className="project-card-description">
                    {project.description || "暂无描述"}
                  </p>
                  <div className="project-card-footer">
                    <span className="project-card-footer-members">
                      <span className="avatars">
                        {Array.from({ length: Math.min(3, memberCount(project) || 1) }).map((_, idx) => (
                          <span key={idx} className="avatar">
                            {(project.name || "?").charAt((idx * 3) % (project.name.length || 1)).toUpperCase()}
                          </span>
                        ))}
                      </span>
                      <span>{memberCount(project) || 1} 成员</span>
                    </span>
                    <span>更新 · {relativeTime(project.updated_at)}</span>
                  </div>
                </div>
              </article>
            ))}

            <button
              type="button"
              className="project-card-create"
              onClick={() => setShowCreate(true)}
            >
              <span className="plus"><Plus size={26} /></span>
              <h3>开始新创意</h3>
              <p>从空白项目或预设工作流开始生成</p>
            </button>
          </div>
        </>
      )}
    </div>
  );
}