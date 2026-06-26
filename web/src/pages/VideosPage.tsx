import { useEffect, useState } from "react";
import { listVideos, videoUrl } from "../api/client";
import type { Video } from "../types";

export function VideosPage() {
  const [videos, setVideos] = useState<Video[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [playingId, setPlayingId] = useState<string | null>(null);

  useEffect(() => {
    listVideos().then(setVideos).catch(() => setError("Failed to load videos")).finally(() => setLoading(false));
  }, []);

  const formatDate = (iso: string) => new Date(iso).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
  const formatDuration = (sec?: number | null) => { if (!sec) return "-"; const m = Math.floor(sec / 60); const s = Math.floor(sec % 60); return `${m}:${s.toString().padStart(2, "0")}`; };
  const formatSize = (bytes: number) => { if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`; return `${(bytes / (1024 * 1024)).toFixed(1)}MB`; };

  if (loading) return <div className="page"><h1>视频库</h1><div className="empty-state">加载中...</div></div>;

  return (
    <div className="page">
      <div className="page-header">
        <h1>视频库</h1>
        <span className="page-count">{videos.length} videos</span>
      </div>
      {error && <div className="auth-error" style={{ marginBottom: 16 }}>{error}</div>}
      {videos.length === 0 ? (
        <div className="empty-state">暂无已生成的视频。创建任务生成你的第一个视频！</div>
      ) : (
        <div className="video-grid">
          {videos.map((video) => (
            <div key={video.id} className={`video-card ${playingId === video.id ? "playing" : ""}`}>
              <div className="video-card-preview">
                {playingId === video.id ? (
                  <video controls autoPlay src={videoUrl(video.id)} onEnded={() => setPlayingId(null)} className="video-player" />
                ) : (
                  <div className="video-placeholder" onClick={() => setPlayingId(video.id)}>
                    <span className="play-icon">▶</span>
                  </div>
                )}
              </div>
              <div className="video-card-info">
                <h3 className="video-title" title={video.title}>{video.title}</h3>
                <div className="video-meta">
                  <span>{formatDuration(video.duration_sec)}</span>
                  <span>{video.width && video.height ? `${video.width}x${video.height}` : "-"}</span>
                  <span>{formatSize(video.size_bytes)}</span>
                </div>
                <div className="video-meta muted">
                  <span>{video.created_by_username || `user#${video.created_by}`}</span>
                  <span>{formatDate(video.created_at)}</span>
                </div>
                <a href={videoUrl(video.id)} download className="btn-secondary btn-sm" style={{ marginTop: 8 }}>下载</a>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
