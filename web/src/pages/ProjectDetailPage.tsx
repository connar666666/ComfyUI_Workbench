import { useCallback, useEffect, useState } from "react";
import type { ChangeEvent, FormEvent } from "react";
import { useParams } from "react-router-dom";
import {
  addProjectWorkflow,
  assetUrl,
  getProject,
  listProjectAssets,
  listProjectHistory,
  listProjectWorkflows,
  listRemoteWorkflows,
  refreshProjectRemoteRun,
  runProjectWorkflow,
  uploadProjectAsset,
} from "../api/client";
import type { Asset, Project, ProjectHistoryItem, ProjectRemoteRun, ProjectWorkflow, RemoteWorkflowSummary } from "../types";

const KIND_LABELS: Record<string, string> = { image: "图片", audio: "音频", video: "视频", document: "文档" };

function guessKind(file: File): string {
  if (file.type.startsWith("image/")) return "image";
  if (file.type.startsWith("audio/")) return "audio";
  if (file.type.startsWith("video/")) return "video";
  return "document";
}

export function ProjectDetailPage() {
  const { projectId } = useParams();
  const id = Number(projectId);
  const [project, setProject] = useState<Project | null>(null);
  const [workflows, setWorkflows] = useState<ProjectWorkflow[]>([]);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [history, setHistory] = useState<ProjectHistoryItem[]>([]);
  const [activeTab, setActiveTab] = useState<"workflows" | "assets" | "history">("workflows");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [runningId, setRunningId] = useState<number | null>(null);
  const [lastRun, setLastRun] = useState<ProjectRemoteRun | null>(null);
  const [uploading, setUploading] = useState(false);
  const [catalog, setCatalog] = useState<RemoteWorkflowSummary[]>([]);
  const [showAddWorkflow, setShowAddWorkflow] = useState(false);
  const [selectedWorkflowId, setSelectedWorkflowId] = useState("");
  const [addingWorkflow, setAddingWorkflow] = useState(false);

  const canEdit = project?.current_user_role === "owner" || project?.current_user_role === "editor";

  const loadProjectData = useCallback(async () => {
    if (!Number.isFinite(id)) return;
    const [projectData, workflowData, assetData, historyData] = await Promise.all([
      getProject(id),
      listProjectWorkflows(id),
      listProjectAssets(id),
      listProjectHistory(id),
    ]);
    setProject(projectData);
    setWorkflows(workflowData);
    setAssets(assetData);
    setHistory(historyData);
  }, [id]);

  useEffect(() => {
    setLoading(true);
    loadProjectData()
      .then(() => setError(""))
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load project"))
      .finally(() => setLoading(false));
  }, [loadProjectData]);

  const handleRun = async (workflow: ProjectWorkflow) => {
    setRunningId(workflow.id);
    try {
      const run = await runProjectWorkflow(id, workflow.id, workflow.defaults || {});
      const refreshed = await refreshProjectRemoteRun(id, run.id);
      setLastRun(refreshed);
      await loadProjectData();
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Workflow run failed");
    } finally {
      setRunningId(null);
    }
  };

  const handleUpload = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      await uploadProjectAsset(id, guessKind(file), file);
      setAssets(await listProjectAssets(id));
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
      event.target.value = "";
    }
  };

  const handleAddWorkflow = async (event: FormEvent) => {
    event.preventDefault();
    if (!selectedWorkflowId) {
      setError("请选择一个远程工作流");
      return;
    }
    setAddingWorkflow(true);
    try {
      await addProjectWorkflow(id, { workflow_id: selectedWorkflowId });
      setSelectedWorkflowId("");
      setShowAddWorkflow(false);
      setWorkflows(await listProjectWorkflows(id));
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add workflow");
    } finally {
      setAddingWorkflow(false);
    }
  };

  const openAddWorkflow = async () => {
    try {
      const remoteWorkflows = await listRemoteWorkflows();
      const existingIds = new Set(workflows.map((workflow) => workflow.workflow_id));
      const available = remoteWorkflows.filter((workflow) => !existingIds.has(workflow.id));
      setCatalog(available);
      setSelectedWorkflowId(available[0]?.id ?? "");
      setShowAddWorkflow(true);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load remote workflow catalog");
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

  if (!project) {
    return (
      <div className="page">
        <h1>项目</h1>
        <div className="empty-state">项目不存在。</div>
      </div>
    );
  }

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>{project.name}</h1>
          <p className="page-subtitle">{project.description || "无描述"}</p>
        </div>
        <span className="kind-tag">{project.current_user_role}</span>
      </div>

      {error && <div className="auth-error" style={{ marginBottom: 16 }}>{error}</div>}
      {lastRun && <div className="empty-state" style={{ marginBottom: 16 }}>最近运行 {lastRun.status}</div>}

      <div className="page-toolbar" style={{ marginBottom: 16 }}>
        <button className={activeTab === "workflows" ? "btn-primary" : "btn-secondary"} onClick={() => setActiveTab("workflows")}>工作流</button>
        <button className={activeTab === "assets" ? "btn-primary" : "btn-secondary"} onClick={() => setActiveTab("assets")}>素材</button>
        <button className={activeTab === "history" ? "btn-primary" : "btn-secondary"} onClick={() => setActiveTab("history")}>历史</button>
      </div>

      {activeTab === "workflows" && (
        <>
          {canEdit && (
            <div className="page-toolbar" style={{ marginBottom: 16 }}>
              <button className="btn-secondary" type="button" onClick={() => openAddWorkflow()}>
                添加工作流
              </button>
            </div>
          )}
          {showAddWorkflow && (
            <form className="auth-card" style={{ marginBottom: 16, maxWidth: 560 }} onSubmit={handleAddWorkflow}>
              <label>
                选择远程工作流
                <select value={selectedWorkflowId} onChange={(event) => setSelectedWorkflowId(event.target.value)}>
                  <option value="">请选择</option>
                  {catalog.map((workflow) => (
                    <option key={workflow.id} value={workflow.id}>
                      {workflow.name}
                    </option>
                  ))}
                </select>
              </label>
              <div className="page-toolbar">
                <button className="btn-primary" type="submit" disabled={addingWorkflow || !selectedWorkflowId}>
                  {addingWorkflow ? "加入中..." : "加入项目"}
                </button>
                <button className="btn-secondary" type="button" onClick={() => setShowAddWorkflow(false)}>
                  取消
                </button>
              </div>
            </form>
          )}
          {workflows.length === 0 ? (
            <div className="empty-state">这个项目还没有收藏工作流。</div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>工作流</th>
                  <th>Workflow ID</th>
                  <th style={{ width: 120 }}>状态</th>
                  <th style={{ width: 90 }}></th>
                </tr>
              </thead>
              <tbody>
                {workflows.map((workflow) => (
                  <tr key={workflow.id}>
                    <td>{workflow.display_name || workflow.workflow_id}</td>
                    <td className="muted">{workflow.workflow_id}</td>
                    <td><span className="kind-tag">{workflow.enabled ? "enabled" : "disabled"}</span></td>
                    <td>
                      {canEdit && workflow.enabled && (
                        <button className="btn-primary btn-sm" disabled={runningId === workflow.id} onClick={() => handleRun(workflow)}>
                          {runningId === workflow.id ? "运行中" : "运行"}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}

      {activeTab === "assets" && (
        <>
          {canEdit && (
            <div className="page-toolbar" style={{ marginBottom: 16 }}>
              <label className="btn-primary btn-upload">
                {uploading ? "上传中..." : "上传素材"}
                <input type="file" onChange={handleUpload} style={{ display: "none" }} disabled={uploading} />
              </label>
            </div>
          )}
          {assets.length === 0 ? (
            <div className="empty-state">暂无项目素材。</div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th style={{ width: 60 }}>ID</th>
                  <th>文件名</th>
                  <th style={{ width: 100 }}>类型</th>
                  <th style={{ width: 80 }}></th>
                </tr>
              </thead>
              <tbody>
                {assets.map((asset) => (
                  <tr key={asset.id}>
                    <td>{asset.id}</td>
                    <td>{asset.original_filename}</td>
                    <td><span className="kind-tag">{KIND_LABELS[asset.kind] || asset.kind}</span></td>
                    <td><a className="btn-secondary btn-sm" href={assetUrl(asset.id)} download>下载</a></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}

      {activeTab === "history" && (
        history.length === 0 ? (
          <div className="empty-state">暂无项目历史。</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>标题</th>
                <th style={{ width: 140 }}>类型</th>
                <th style={{ width: 100 }}>状态</th>
                <th style={{ width: 130 }}>结果素材</th>
              </tr>
            </thead>
            <tbody>
              {history.map((item) => (
                <tr key={`${item.type}-${item.id}`}>
                  <td>{item.title}</td>
                  <td><span className="kind-tag">{item.type}</span></td>
                  <td>{item.status}</td>
                  <td className="muted">{item.result_asset_ids?.length ?? 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      )}
    </div>
  );
}
