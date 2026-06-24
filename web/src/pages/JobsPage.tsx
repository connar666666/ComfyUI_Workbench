import { useEffect, useState } from "react";
import { listJobs } from "../api/client";
import { StatusBadge } from "../components/StatusBadge";
import type { Job } from "../types";

export function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listJobs()
      .then(setJobs)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="page"><h1>任务队列</h1><p>加载中...</p></div>;

  return (
    <div className="page">
      <h1>任务队列</h1>
      {jobs.length === 0 ? (
        <p className="empty-state">暂无任务。</p>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>提示词</th>
              <th>状态</th>
              <th>分辨率</th>
              <th>时长</th>
              <th>创建时间</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((j) => (
              <tr key={j.id}>
                <td>{j.id}</td>
                <td className="prompt-cell">{j.prompt}</td>
                <td><StatusBadge status={j.status} /></td>
                <td>{j.resolution}</td>
                <td>{j.duration_sec}s</td>
                <td>{new Date(j.created_at).toLocaleString("zh-CN")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
