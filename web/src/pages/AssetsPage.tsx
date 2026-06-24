import { useEffect, useState } from "react";
import { listAssets } from "../api/client";
import type { Asset } from "../types";

export function AssetsPage() {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listAssets()
      .then(setAssets)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="page"><h1>素材库</h1><p>加载中...</p></div>;

  return (
    <div className="page">
      <h1>素材库</h1>
      {assets.length === 0 ? (
        <p className="empty-state">暂无素材，请上传文件。</p>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>文件名</th>
              <th>类型</th>
              <th>大小</th>
              <th>上传时间</th>
            </tr>
          </thead>
          <tbody>
            {assets.map((a) => (
              <tr key={a.id}>
                <td>{a.id}</td>
                <td>{a.original_filename}</td>
                <td>{a.kind}</td>
                <td>{formatSize(a.size_bytes)}</td>
                <td>{new Date(a.created_at).toLocaleString("zh-CN")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
