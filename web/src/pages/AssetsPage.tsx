import { useCallback, useEffect, useState } from "react";
import { assetUrl, listAssets, uploadAsset } from "../api/client";
import { useSSE } from "../hooks/useSSE";
import type { Asset, SSEEvent } from "../types";

const KIND_LABELS: Record<string, string> = { image: "图片", audio: "音频", video: "视频", document: "文档" };

export function AssetsPage() {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [kindFilter, setKindFilter] = useState("");
  const [uploading, setUploading] = useState(false);

  const fetchAssets = useCallback(async () => {
    try {
      const data = await listAssets(kindFilter || undefined);
      setAssets(data); setError("");
    } catch (err) { setError("Failed to load assets"); }
    finally { setLoading(false); }
  }, [kindFilter]);

  useEffect(() => { fetchAssets(); }, [fetchAssets]);

  useSSE((event: SSEEvent) => {
    if (event.type === "asset_uploaded") {
      const newAsset = (event.data as { asset: Asset }).asset;
      setAssets((prev) => prev.some((a) => a.id === newAsset.id) ? prev : [newAsset, ...prev]);
    }
  });

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]; if (!file) return;
    let kind = "document";
    if (file.type.startsWith("image/")) kind = "image";
    else if (file.type.startsWith("audio/")) kind = "audio";
    else if (file.type.startsWith("video/")) kind = "video";
    setUploading(true);
    try { await uploadAsset(kind, file); fetchAssets(); }
    catch (err) { setError(err instanceof Error ? err.message : "Upload failed"); }
    finally { setUploading(false); e.target.value = ""; }
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes}B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
  };

  const formatDate = (iso: string) => new Date(iso).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });

  if (loading) return <div className="page"><h1>素材库</h1><div className="empty-state">加载中...</div></div>;

  return (
    <div className="page">
      <div className="page-header">
        <h1>素材库</h1>
        <div className="page-toolbar">
          <select value={kindFilter} onChange={(e) => setKindFilter(e.target.value)}>
            <option value="">全部类型</option>
            <option value="image">图片</option>
            <option value="audio">音频</option>
            <option value="video">视频</option>
            <option value="document">文档</option>
          </select>
          <label className="btn-primary btn-upload">
            {uploading ? "上传中..." : "上传文件"}
            <input type="file" onChange={handleUpload} style={{ display: "none" }} disabled={uploading} />
          </label>
        </div>
      </div>
      {error && <div className="auth-error" style={{ marginBottom: 16 }}>{error}</div>}
      {assets.length === 0 ? (
        <div className="empty-state">暂无素材，请上传文件。</div>
      ) : (
        <table>
          <thead>
            <tr>
              <th style={{ width: 50 }}>ID</th>
              <th style={{ width: 80 }}>Preview</th>
              <th>Filename</th>
              <th style={{ width: 80 }}>Kind</th>
              <th style={{ width: 80 }}>Size</th>
              <th style={{ width: 100 }}>Uploaded By</th>
              <th style={{ width: 130 }}>Created</th>
              <th style={{ width: 80 }}></th>
            </tr>
          </thead>
          <tbody>
            {assets.map((asset) => (
              <tr key={asset.id}>
                <td>{asset.id}</td>
                <td>
                  {asset.kind === "image" ? (
                    <img src={assetUrl(asset.id)} alt={asset.original_filename} className="asset-thumb" loading="lazy" />
                  ) : (
                    <span className="asset-type-icon">{asset.kind === "audio" ? "🎵" : asset.kind === "video" ? "🎬" : "📄"}</span>
                  )}
                </td>
                <td className="filename-cell" title={asset.original_filename}>{asset.original_filename}</td>
                <td><span className="kind-tag">{KIND_LABELS[asset.kind] || asset.kind}</span></td>
                <td className="muted">{formatSize(asset.size_bytes)}</td>
                <td className="muted">{asset.uploaded_by_username || "-"}</td>
                <td className="muted">{formatDate(asset.created_at)}</td>
                <td><a href={assetUrl(asset.id)} download className="btn-secondary btn-sm">下载</a></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
