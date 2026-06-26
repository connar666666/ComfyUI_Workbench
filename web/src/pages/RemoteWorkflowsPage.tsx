import { useEffect, useMemo, useState } from "react";
import {
  getRemoteWorkflow,
  getRemoteWorkflowResult,
  listRemoteWorkflows,
  runRemoteWorkflow,
  uploadRemoteWorkflowFile,
} from "../api/client";
import type {
  RemoteWorkflowDetail,
  RemoteWorkflowResult,
  RemoteWorkflowResultItem,
  RemoteWorkflowSummary,
} from "../types";

type FieldKind = "text" | "textarea" | "number" | "boolean" | "file";

type WorkflowField = {
  key: string;
  label: string;
  kind: FieldKind;
  defaultValue: unknown;
  classType?: string;
  inputName: string;
};

function guessFieldKind(key: string, label: string, defaultValue: unknown): FieldKind {
  if (typeof defaultValue === "boolean") return "boolean";
  if (typeof defaultValue === "number") return "number";

  const hint = `${key} ${label}`.toLowerCase();
  if (/(image|audio|video|mask|file|upload)/.test(hint)) return "file";
  if (typeof defaultValue === "string" && defaultValue.length > 80) return "textarea";
  return "text";
}

function buildFields(detail: RemoteWorkflowDetail | null): WorkflowField[] {
  if (!detail) return [];

  const enabledParams = detail.api_config.enabledParams ?? {};
  const formValues = detail.api_config.formValues ?? {};
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

export function RemoteWorkflowsPage() {
  const [workflows, setWorkflows] = useState<RemoteWorkflowSummary[]>([]);
  const [selectedWorkflowId, setSelectedWorkflowId] = useState<string>("");
  const [detail, setDetail] = useState<RemoteWorkflowDetail | null>(null);
  const [formValues, setFormValues] = useState<Record<string, string | boolean>>({});
  const [search, setSearch] = useState("");
  const [error, setError] = useState("");
  const [loadingList, setLoadingList] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [currentRun, setCurrentRun] = useState<RemoteWorkflowResult | null>(null);
  const [activePromptId, setActivePromptId] = useState<string | null>(null);
  const [uploadingField, setUploadingField] = useState<string | null>(null);

  const fields = useMemo(() => buildFields(detail), [detail]);
  const filteredWorkflows = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    if (!keyword) return workflows;
    return workflows.filter((workflow) =>
      `${workflow.name} ${workflow.id}`.toLowerCase().includes(keyword)
    );
  }, [search, workflows]);

  const loadWorkflows = async () => {
    setLoadingList(true);
    try {
      const next = await listRemoteWorkflows();
      setWorkflows(next);
      setError("");
      setSelectedWorkflowId((current) => current || next[0]?.id || "");
    } catch (err) {
      setError(err instanceof Error ? err.message : "无法加载远程工作流");
    } finally {
      setLoadingList(false);
    }
  };

  useEffect(() => {
    loadWorkflows().catch(() => {});
  }, []);

  useEffect(() => {
    if (!selectedWorkflowId) {
      setDetail(null);
      setFormValues({});
      return;
    }

    let active = true;
    setLoadingDetail(true);
    getRemoteWorkflow(selectedWorkflowId)
      .then((data) => {
        if (!active) return;
        const nextFields = buildFields(data);
        setDetail(data);
        setFormValues(toInitialFormValues(nextFields));
        setError("");
      })
      .catch((err) => {
        if (active) {
          setError(err instanceof Error ? err.message : "无法加载工作流详情");
        }
      })
      .finally(() => {
        if (active) setLoadingDetail(false);
      });

    return () => {
      active = false;
    };
  }, [selectedWorkflowId]);

  useEffect(() => {
    if (!activePromptId) return;

    let cancelled = false;
    let timeoutId: number | undefined;

    const poll = async () => {
      try {
        const result = await getRemoteWorkflowResult(activePromptId);
        if (cancelled) return;
        setCurrentRun(result);
        setError("");
        if (result.pending) {
          timeoutId = window.setTimeout(poll, 2000);
        } else {
          setActivePromptId(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "无法轮询远程任务结果");
          setActivePromptId(null);
        }
      }
    };

    poll().catch(() => {});

    return () => {
      cancelled = true;
      if (timeoutId) window.clearTimeout(timeoutId);
    };
  }, [activePromptId]);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!selectedWorkflowId) return;

    setSubmitting(true);
    try {
      const payload = Object.fromEntries(
        fields.map((field) => [field.key, normalizeValue(field, formValues[field.key] ?? "")])
      );
      const run = await runRemoteWorkflow(selectedWorkflowId, payload);
      setCurrentRun({
        prompt_id: run.prompt_id,
        pending: true,
        results: [],
      });
      setActivePromptId(run.prompt_id);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "远程工作流运行失败");
    } finally {
      setSubmitting(false);
    }
  };

  const handleFileUpload = async (fieldKey: string, file: File | null) => {
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

  return (
    <div className="page remote-workflows-page">
      <div className="page-header">
        <div>
          <h1>远程工作流</h1>
          <p className="page-subtitle">读取 zealman 面板中的已保存工作流，填写参数并轮询远程结果。</p>
        </div>
        <button type="button" className="btn-secondary" onClick={() => loadWorkflows().catch(() => {})}>
          刷新工作流
        </button>
      </div>

      {error && <div className="auth-error remote-banner">{error}</div>}

      <div className="remote-layout">
        <section className="remote-panel remote-list-panel">
          <div className="remote-panel-header">
            <h2>工作流列表</h2>
            <span className="page-count">{workflows.length}</span>
          </div>
          <input
            type="text"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="搜索工作流"
          />
          {loadingList ? (
            <div className="empty-state">正在加载远程工作流...</div>
          ) : filteredWorkflows.length === 0 ? (
            <div className="empty-state">没有匹配的工作流</div>
          ) : (
            <div className="remote-workflow-list">
              {filteredWorkflows.map((workflow) => (
                <button
                  key={workflow.id}
                  type="button"
                  className={`remote-workflow-item ${workflow.id === selectedWorkflowId ? "active" : ""}`}
                  onClick={() => setSelectedWorkflowId(workflow.id)}
                >
                  <strong>{workflow.name}</strong>
                  <span>{workflow.id}</span>
                  <span>运行 {workflow.run_count ?? 0} 次</span>
                </button>
              ))}
            </div>
          )}
        </section>

        <section className="remote-panel remote-form-panel">
          <div className="remote-panel-header">
            <h2>参数表单</h2>
            {selectedWorkflowId && <span className="page-count">{selectedWorkflowId}</span>}
          </div>
          {!selectedWorkflowId ? (
            <div className="empty-state">请选择一个工作流</div>
          ) : loadingDetail ? (
            <div className="empty-state">正在加载工作流参数...</div>
          ) : (
            <form onSubmit={handleSubmit}>
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
                        onChange={(event) =>
                          setFormValues((current) => ({ ...current, [field.key]: event.target.value }))
                        }
                        rows={4}
                      />
                    ) : field.kind === "boolean" ? (
                      <label className="checkbox-row">
                        <input
                          id={field.key}
                          type="checkbox"
                          checked={Boolean(formValues[field.key])}
                          onChange={(event) =>
                            setFormValues((current) => ({ ...current, [field.key]: event.target.checked }))
                          }
                        />
                        <span>启用</span>
                      </label>
                    ) : (
                      <>
                        <input
                          id={field.key}
                          type={field.kind === "number" ? "number" : "text"}
                          value={String(formValues[field.key] ?? "")}
                          onChange={(event) =>
                            setFormValues((current) => ({ ...current, [field.key]: event.target.value }))
                          }
                        />
                        {field.kind === "file" && (
                          <div className="remote-upload-row">
                            <input
                              type="file"
                              onChange={(event) => handleFileUpload(field.key, event.target.files?.[0] ?? null)}
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

              <button type="submit" className="btn-primary" disabled={submitting || fields.length === 0}>
                {submitting ? "提交中..." : "运行工作流"}
              </button>
            </form>
          )}
        </section>

        <section className="remote-panel remote-result-panel">
          <div className="remote-panel-header">
            <h2>运行结果</h2>
            {currentRun && (
              <span className={`badge ${currentRun.pending ? "badge-running" : "badge-succeeded"}`}>
                {currentRun.pending ? "运行中" : "已完成"}
              </span>
            )}
          </div>
          {!currentRun ? (
            <div className="empty-state">提交工作流后，这里会显示 prompt_id 和输出文件。</div>
          ) : (
            <div className="remote-result-stack">
              <div className="remote-run-card">
                <div className="remote-run-key">Prompt ID</div>
                <div className="remote-run-value">{currentRun.prompt_id}</div>
              </div>

              {currentRun.results.length === 0 ? (
                <div className="empty-state">
                  {currentRun.pending ? "正在轮询远程输出..." : "任务完成，但没有返回输出文件"}
                </div>
              ) : (
                currentRun.results.map((item, index) => (
                  <div className="remote-result-card" key={`${item.filename || item.url || index}-${index}`}>
                    <div className="remote-result-header">
                      <strong>{item.filename || item.type || `结果 ${index + 1}`}</strong>
                      {item.type && <span className="badge badge-queued">{item.type}</span>}
                    </div>
                    {previewForResult(item)}
                    {item.text && <pre className="remote-text-result">{item.text}</pre>}
                    {(item.download_url || item.url) && (
                      <a
                        href={item.download_url || item.url}
                        target="_blank"
                        rel="noreferrer"
                        className="remote-result-link"
                      >
                        打开输出文件
                      </a>
                    )}
                  </div>
                ))
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
