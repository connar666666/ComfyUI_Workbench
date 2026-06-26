import { useCallback, useEffect, useState } from "react";
import type { ChangeEvent } from "react";
import { useParams } from "react-router-dom";
import {
  assetUrl,
  getProject,
  listProjectAssets,
  listProjectHistory,
  listProjectWorkflows,
  refreshProjectRemoteRun,
  runProjectWorkflow,
  uploadProjectAsset,
} from "../api/client";
import type { Asset, Project, ProjectHistoryItem, ProjectRemoteRun, ProjectWorkflow } from "../types";

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
        workflows.length === 0 ? (
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
        )
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
