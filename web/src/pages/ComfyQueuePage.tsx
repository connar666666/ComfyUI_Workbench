import { useEffect, useState } from "react";
import { getQueueStatus } from "../api/client";
import type { QueueStatus } from "../types";

export function ComfyQueuePage() {
  const [queue, setQueue] = useState<QueueStatus | null>(null);
  const [error, setError] = useState("");
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);

  useEffect(() => {
    let active = true;
    const poll = async () => {
      try {
        const data = await getQueueStatus();
        if (active) { setQueue(data); setLastUpdate(new Date()); setError(""); }
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : "无法连接到 ComfyUI 队列");
        }
      }
    };
    poll();
    const interval = setInterval(poll, 3000);
    return () => { active = false; clearInterval(interval); };
  }, []);

  const formatTime = (d: Date) => d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });

  return (
    <div className="page">
      <div className="page-header">
        <h1>ComfyUI 队列</h1>
        {lastUpdate && <span className="page-count muted" style={{ fontSize: 12 }}>最后更新: {formatTime(lastUpdate)}</span>}
      </div>
      {error && <div className="auth-error" style={{ marginBottom: 16 }}>{error}</div>}
      {queue === null ? (
        <div className="empty-state">正在加载队列状态...</div>
      ) : (
        <div className="queue-sections">
          <div className="queue-section">
            <h2 className="queue-section-title running">🔄 运行中 ({queue.running.length})</h2>
            {queue.running.length === 0 ? (
              <div className="empty-state" style={{ padding: "12px 0" }}>无运行中的任务</div>
            ) : (
              <div className="queue-cards">
                {queue.running.map((entry) => (
                  <div key={entry.prompt_id} className="queue-card running">
                    <div className="queue-card-header">
                      <span className="queue-prompt-id">{entry.prompt_id}</span>
                      <span className="badge badge-running">Running</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
          <div className="queue-section">
            <h2 className="queue-section-title pending">⏳ 等待中 ({queue.pending.length})</h2>
            {queue.pending.length === 0 ? (
              <div className="empty-state" style={{ padding: "12px 0" }}>无等待中的任务</div>
            ) : (
              <div className="queue-cards">
                {queue.pending.map((entry, i) => (
                  <div key={entry.prompt_id || i} className="queue-card pending">
                    <div className="queue-card-header">
                      <span className="queue-prompt-id">{entry.prompt_id || `pending-${i}`}</span>
                      <span className="badge badge-queued">Position #{entry.queue_position + 1}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
