import { useCallback, useEffect, useState } from "react";
import type { ChangeEvent, FormEvent } from "react";
import { useParams } from "react-router-dom";
import {
  addProjectWorkflow,
  assetUrl,
  getProject,
  getRemoteWorkflow,
  listProjectAssets,
  listProjectHistory,
  listProjectWorkflows,
  listRemoteWorkflows,
  refreshProjectRemoteRun,
  runProjectWorkflow,
  uploadRemoteWorkflowFile,
  uploadProjectAsset,
} from "../api/client";
import type {
  Asset,
  Project,
  ProjectHistoryItem,
  ProjectRemoteRun,
  ProjectWorkflow,
  RemoteWorkflowDetail,
  RemoteWorkflowResultItem,
  RemoteWorkflowSummary,
} from "../types";

const KIND_LABELS: Record<string, string> = { image: "图片", audio: "音频", video: "视频", document: "文档" };
type FieldKind = "text" | "textarea" | "number" | "boolean" | "file";
type WorkflowField = {
  key: string;
  label: string;
  kind: FieldKind;
  defaultValue: unknown;
  classType?: string;
  inputName: string;
};

function guessKind(file: File): string {
  if (file.type.startsWith("image/")) return "image";
  if (file.type.startsWith("audio/")) return "audio";
  if (file.type.startsWith("video/")) return "video";
  return "document";
}

function guessFieldKind(key: string, label: string, defaultValue: unknown): FieldKind {
  if (typeof defaultValue === "boolean") return "boolean";
  if (typeof defaultValue === "number") return "number";
  const hint = `${key} ${label}`.toLowerCase();
  if (/(image|audio|video|mask|file|upload)/.test(hint)) return "file";
  if (typeof defaultValue === "string" && defaultValue.length > 80) return "textarea";
  return "text";
}

function buildFields(detail: RemoteWorkflowDetail | null, defaults: Record<string, unknown>): WorkflowField[] {
  if (!detail) return [];
  const enabledParams = detail.api_config.enabledParams ?? {};
  const formValues = { ...(detail.api_config.formValues ?? {}), ...defaults };
  const customLabels = detail.api_config.customLabels ?? {};

  return Object.entries(enabledParams)
    .filter(([, enabled]) => enabled)
    .map(([key]) => {
      const [nodeId, inputName] = key.split(":");
      const node = detail.workflow_template[nodeId];
      const templateValue = node?.inputs?.[inputName];
      const defaultValue = formValues[key] ?? templateValue ?? "";
      const label = customLabels[key] ?? inputName ?? key;
      return {
        key,
        label,
        kind: guessFieldKind(key, label, defaultValue),
        defaultValue,
        classType: node?.class_type,
        inputName: inputName ?? key,
      };
    })
    .sort((a, b) => a.label.localeCompare(b.label, "zh-CN"));
}

function toInitialFormValues(fields: WorkflowField[]): Record<string, string | boolean> {
  return Object.fromEntries(
    fields.map((field) => [
      field.key,
      field.kind === "boolean" ? Boolean(field.defaultValue) : String(field.defaultValue ?? ""),
    ])
  );
}

function normalizeValue(field: WorkflowField, value: string | boolean): unknown {
  if (field.kind === "boolean") return Boolean(value);
  if (field.kind === "number") {
    const num = Number(value);
    return Number.isFinite(num) ? num : value;
  }
  return String(value);
}

function previewForResult(item: RemoteWorkflowResultItem) {
  const url = item.download_url ?? item.url;
  if (!url) return null;
  if (item.type === "image") {
    return <img src={url} alt={item.filename || "remote result"} className="remote-preview-image" />;
  }
  if (item.type === "video") {
    return <video src={url} controls className="remote-preview-video" />;
  }
  if (item.type === "audio") {
    return <audio src={url} controls className="remote-preview-audio" />;
  }
  return null;
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
  const [selectedProjectWorkflowId, setSelectedProjectWorkflowId] = useState<number | null>(null);
  const [workflowDetail, setWorkflowDetail] = useState<RemoteWorkflowDetail | null>(null);
  const [formValues, setFormValues] = useState<Record<string, string | boolean>>({});
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [uploadingField, setUploadingField] = useState<string | null>(null);
  const [catalog, setCatalog] = useState<RemoteWorkflowSummary[]>([]);
  const [showAddWorkflow, setShowAddWorkflow] = useState(false);
  const [selectedWorkflowId, setSelectedWorkflowId] = useState("");
  const [addingWorkflow, setAddingWorkflow] = useState(false);

  const canEdit = project?.current_user_role === "owner" || project?.current_user_role === "editor";
  const selectedWorkflow = workflows.find((workflow) => workflow.id === selectedProjectWorkflowId) ?? workflows[0] ?? null;
  const fields = buildFields(workflowDetail, selectedWorkflow?.defaults ?? {});

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

  useEffect(() => {
    if (!project) return;
    try {
      localStorage.setItem(
        "workbench.currentProject",
        JSON.stringify({
          id: String(project.id),
          name: project.name,
          memberCount: project.member_count ?? project.members?.length ?? 0,
        }),
      );
      window.dispatchEvent(new Event("workbench:current-project-changed"));
    } catch {
      // localStorage unavailable; skip.
    }
  }, [project]);

  useEffect(() => {
    if (!workflows.length) {
      setSelectedProjectWorkflowId(null);
      return;
    }
    setSelectedProjectWorkflowId((current) => {
      if (current && workflows.some((workflow) => workflow.id === current)) return current;
      return workflows[0].id;
    });
  }, [workflows]);

  useEffect(() => {
    if (!selectedWorkflow) {
      setWorkflowDetail(null);
      setFormValues({});
      return;
    }
    let active = true;
    setLoadingDetail(true);
    getRemoteWorkflow(selectedWorkflow.workflow_id)
      .then((data) => {
        if (!active) return;
        const nextFields = buildFields(data, selectedWorkflow.defaults ?? {});
        setWorkflowDetail(data);
        setFormValues(toInitialFormValues(nextFields));
        setError("");
      })
      .catch((err) => {
        if (active) setError(err instanceof Error ? err.message : "Failed to load workflow detail");
      })
      .finally(() => {
        if (active) setLoadingDetail(false);
      });
    return () => {
      active = false;
    };
  }, [selectedWorkflow]);

  const handleRun = async (workflow: ProjectWorkflow) => {
    setRunningId(workflow.id);
    try {
      const payload = Object.fromEntries(
        fields.map((field) => [field.key, normalizeValue(field, formValues[field.key] ?? "")])
      );
      const run = await runProjectWorkflow(id, workflow.id, payload);
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
      const nextWorkflows = await listProjectWorkflows(id);
      setWorkflows(nextWorkflows);
      setSelectedProjectWorkflowId(nextWorkflows[nextWorkflows.length - 1]?.id ?? null);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add workflow");
    } finally {
      setAddingWorkflow(false);
    }
  };

  const handleFieldUpload = async (fieldKey: string, file: File | null) => {
    if (!file) return;
    setUploadingField(fieldKey);
    try {
      const uploaded = await uploadRemoteWorkflowFile(file);
      setFormValues((current) => ({ ...current, [fieldKey]: uploaded.name }));
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "文件上传失败");
    } finally {
      setUploadingField(null);
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
            <div className="remote-layout">
              <section className="remote-panel remote-list-panel">
                <div className="remote-panel-header">
                  <h2>项目工作流</h2>
                  <span className="page-count">{workflows.length}</span>
                </div>
                <div className="remote-workflow-list">
                  {workflows.map((workflow) => (
                    <button
                      key={workflow.id}
                      type="button"
                      className={`remote-workflow-item ${workflow.id === selectedWorkflow?.id ? "active" : ""}`}
                      onClick={() => setSelectedProjectWorkflowId(workflow.id)}
                    >
                      <strong>{workflow.display_name || workflow.workflow_id}</strong>
                      <span>{workflow.workflow_id}</span>
                      <span>{workflow.enabled ? "已启用" : "已停用"}</span>
                    </button>
                  ))}
                </div>
              </section>

              <section className="remote-panel remote-form-panel">
                <div className="remote-panel-header">
                  <h2>参数表单</h2>
                  {selectedWorkflow && <span className="page-count">{selectedWorkflow.workflow_id}</span>}
                </div>
                {!selectedWorkflow ? (
                  <div className="empty-state">请选择一个项目工作流</div>
                ) : loadingDetail ? (
                  <div className="empty-state">正在加载工作流参数...</div>
                ) : (
                  <form
                    onSubmit={(event) => {
                      event.preventDefault();
                      void handleRun(selectedWorkflow);
                    }}
                  >
                    {fields.length === 0 ? (
                      <div className="empty-state">当前工作流没有启用参数</div>
                    ) : (
                      fields.map((field) => (
                        <div className="form-group" key={field.key}>
                          <label htmlFor={field.key}>{field.label}</label>
                          {field.kind === "textarea" ? (
                            <textarea
                              id={field.key}
                              value={String(formValues[field.key] ?? "")}
                              onChange={(event) => setFormValues((current) => ({ ...current, [field.key]: event.target.value }))}
                              rows={4}
                            />
                          ) : field.kind === "boolean" ? (
                            <label className="checkbox-row">
                              <input
                                id={field.key}
                                type="checkbox"
                                checked={Boolean(formValues[field.key])}
                                onChange={(event) => setFormValues((current) => ({ ...current, [field.key]: event.target.checked }))}
                              />
                              <span>启用</span>
                            </label>
                          ) : (
                            <>
                              <input
                                id={field.key}
                                type={field.kind === "number" ? "number" : "text"}
                                value={String(formValues[field.key] ?? "")}
                                onChange={(event) => setFormValues((current) => ({ ...current, [field.key]: event.target.value }))}
                              />
                              {field.kind === "file" && (
                                <div className="remote-upload-row">
                                  <input
                                    type="file"
                                    onChange={(event) => handleFieldUpload(field.key, event.target.files?.[0] ?? null)}
                                    aria-label={`${field.label} 上传`}
                                  />
                                  <span className="sidebar-muted">
                                    {uploadingField === field.key ? "上传中..." : "上传后会自动回填文件名"}
                                  </span>
                                </div>
                              )}
                            </>
                          )}
                          <div className="remote-field-meta">
                            <span>{field.key}</span>
                            {field.classType && <span>{field.classType}</span>}
                          </div>
                        </div>
                      ))
                    )}
                    <button
                      type="submit"
                      className="btn-primary"
                      disabled={!canEdit || !selectedWorkflow.enabled || runningId === selectedWorkflow.id || fields.length === 0}
                    >
                      {runningId === selectedWorkflow.id ? "运行中..." : "运行工作流"}
                    </button>
                  </form>
                )}
              </section>

              <section className="remote-panel remote-result-panel">
                <div className="remote-panel-header">
                  <h2>运行结果</h2>
                  {lastRun && <span className={`badge ${lastRun.status === "running" ? "badge-running" : "badge-succeeded"}`}>{lastRun.status}</span>}
                </div>
                {!lastRun ? (
                  <div className="empty-state">运行后这里会显示本次项目工作流结果。</div>
                ) : (
                  <div className="remote-result-stack">
                    {lastRun.prompt_id && (
                      <div className="remote-run-card">
                        <div className="remote-run-key">Prompt ID</div>
                        <div className="remote-run-value">{lastRun.prompt_id}</div>
                      </div>
                    )}
                    {lastRun.results?.length ? (
                      lastRun.results.map((item, index) => (
                        <div className="remote-result-card" key={`${item.filename || item.url || index}-${index}`}>
                          <div className="remote-result-header">
                            <strong>{item.filename || item.type || `结果 ${index + 1}`}</strong>
                            {item.type && <span className="badge badge-queued">{item.type}</span>}
                          </div>
                          {previewForResult(item)}
                          {(item.download_url || item.url) && (
                            <a href={item.download_url || item.url} target="_blank" rel="noreferrer" className="remote-result-link">
                              打开输出文件
                            </a>
                          )}
                        </div>
                      ))
                    ) : (
                      <div className="empty-state">当前运行还没有输出文件。</div>
                    )}
                  </div>
                )}
              </section>
            </div>
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
