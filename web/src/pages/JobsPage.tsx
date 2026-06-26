import { useCallback, useEffect, useState } from "react";
import { cancelJob, listJobs } from "../api/client";
import { useSSE } from "../hooks/useSSE";
import { useAuth } from "../contexts/AuthContext";
import { StatusBadge } from "../components/StatusBadge";
import type { Job, SSEEvent } from "../types";

export function JobsPage() {
  const { user } = useAuth();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const fetchJobs = useCallback(async () => {
    try {
      const data = await listJobs();
      setJobs(data);
      setError("");
    } catch (err) {
      setError("Failed to load jobs");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchJobs(); }, [fetchJobs]);

  useSSE((event: SSEEvent) => {
    if (event.type === "job_created") {
      const newJob = (event.data as { job: Job }).job;
      setJobs((prev) => prev.some((j) => j.id === newJob.id) ? prev : [newJob, ...prev]);
    } else if (event.type === "job_status_changed") {
      const updated = (event.data as { job: Job }).job;
      setJobs((prev) => prev.map((j) => (j.id === updated.id ? updated : j)));
    }
  });

  const handleCancel = async (jobId: string) => {
    try { await cancelJob(jobId); fetchJobs(); }
    catch (err) { setError(err instanceof Error ? err.message : "Cancel failed"); }
  };

  const formatDate = (iso: string) => new Date(iso).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });

  if (loading) return <div className="page"><h1>任务队列</h1><div className="empty-state">加载中...</div></div>;

  return (
    <div className="page">
      <div className="page-header">
        <h1>任务队列</h1>
        <span className="page-count">{jobs.length} tasks</span>
      </div>
      {error && <div className="auth-error" style={{ marginBottom: 16 }}>{error}</div>}
      {jobs.length === 0 ? (
        <div className="empty-state">暂无任务。去创建你的第一个生成任务吧！</div>
      ) : (
        <table>
          <thead>
            <tr>
              <th style={{ width: 60 }}>ID</th>
              <th>Prompt</th>
              <th style={{ width: 80 }}>Status</th>
              <th style={{ width: 100 }}>By</th>
              <th style={{ width: 80 }}>Resolution</th>
              <th style={{ width: 50 }}>Dur</th>
              <th style={{ width: 130 }}>Created</th>
              <th style={{ width: 70 }}></th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((job) => (
              <>
                <tr key={job.id} onClick={() => setExpandedId(expandedId === job.id ? null : job.id)} style={{ cursor: "pointer" }}>
                  <td>{job.id}</td>
                  <td className="prompt-cell" title={job.prompt}>{job.prompt}</td>
                  <td><StatusBadge status={job.status} /></td>
                  <td className="muted">{job.created_by_username || `user#${job.created_by}`}</td>
                  <td>{job.resolution}</td>
                  <td>{job.duration_sec}s</td>
                  <td className="muted">{formatDate(job.created_at)}</td>
                  <td>
                    {job.status === "queued" && (
                      <button className="btn-secondary btn-sm" onClick={(e) => { e.stopPropagation(); handleCancel(job.id); }}>取消</button>
                    )}
                  </td>
                </tr>
                {expandedId === job.id && (
                  <tr key={`${job.id}-detail`} className="job-detail-row">
                    <td colSpan={8}>
                      <div className="job-detail">
                        <div className="job-detail-grid">
                          <div><strong>Prompt:</strong> {job.prompt}</div>
                          <div><strong>Status:</strong> <StatusBadge status={job.status} /></div>
                          <div><strong>Created:</strong> {formatDate(job.created_at)}</div>
                          {job.started_at && <div><strong>Started:</strong> {formatDate(job.started_at)}</div>}
                          {job.completed_at && <div><strong>Completed:</strong> {formatDate(job.completed_at)}</div>}
                        </div>
                        {job.error_message && <div className="job-error"><strong>Error:</strong> {job.error_message}</div>}
                      </div>
                    </td>
                  </tr>
                )}
              </>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
