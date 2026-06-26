import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ChevronRight,
  CirclePlay,
  Clock,
  FileText,
  Folder,
  FolderOpen,
  FolderPlus,
  Music,
  Plus,
  Sparkles,
  Trash2,
  Upload,
  Video,
  X,
} from "lucide-react";
import {
  assetUrl,
  createAssetFolder,
  deleteAssetFolder,
  listAssetFolders,
  listAssets,
  uploadAsset,
} from "../api/client";
import { useSSE } from "../hooks/useSSE";
import type { Asset, AssetFolder, SSEEvent } from "../types";

const KIND_META: Record<string, { label: string; chip: string }> = {
  image: { label: "图片", chip: "Image" },
  audio: { label: "音频", chip: "Audio" },
  video: { label: "视频", chip: "Video" },
  document: { label: "文档", chip: "Doc" },
};

export function AssetsPage() {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [folders, setFolders] = useState<AssetFolder[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [uploading, setUploading] = useState(false);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [folderFilter, setFolderFilter] = useState<number | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [newFolderName, setNewFolderName] = useState("");
  const [creatingFolder, setCreatingFolder] = useState(false);
  const [createError, setCreateError] = useState("");

  const fetchAssets = useCallback(async () => {
    try {
      const data = await listAssets(undefined, folderFilter);
      setAssets(data);
      setError("");
    } catch {
      setError("加载素材失败");
    } finally {
      setLoading(false);
    }
  }, [folderFilter]);

  const fetchFolders = useCallback(async () => {
    try {
      const data = await listAssetFolders();
      setFolders(data);
    } catch {
      setFolders([]);
    }
  }, []);

  useEffect(() => {
    fetchAssets();
  }, [fetchAssets]);

  useEffect(() => {
    fetchFolders();
  }, [fetchFolders]);

  useSSE((event: SSEEvent) => {
    if (event.type === "asset_uploaded") {
      const newAsset = (event.data as { asset: Asset }).asset;
      if (folderFilter == null || newAsset.folder_id === folderFilter) {
        setAssets((prev) => (prev.some((a) => a.id === newAsset.id) ? prev : [newAsset, ...prev]));
      }
    }
  });

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    let kind = "document";
    if (file.type.startsWith("image/")) kind = "image";
    else if (file.type.startsWith("audio/")) kind = "audio";
    else if (file.type.startsWith("video/")) kind = "video";
    setUploading(true);
    try {
      await uploadAsset(kind, file, folderFilter);
      await fetchAssets();
    } catch (err) {
      setError(err instanceof Error ? err.message : "上传失败");
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  };

  const handleCreateFolder = async (event: React.FormEvent) => {
    event.preventDefault();
    const trimmed = newFolderName.trim();
    if (!trimmed) {
      setCreateError("请输入文件夹名称");
      return;
    }
    setCreatingFolder(true);
    setCreateError("");
    try {
      const created = await createAssetFolder(trimmed);
      setFolders((prev) => [...prev, created].sort((a, b) => a.name.localeCompare(b.name, "zh-Hans-CN")));
      setFolderFilter(created.id);
      setShowCreate(false);
      setNewFolderName("");
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "创建文件夹失败");
    } finally {
      setCreatingFolder(false);
    }
  };

  const handleDeleteFolder = async (folder: AssetFolder, event: React.MouseEvent) => {
    event.stopPropagation();
    if (!window.confirm(`确定删除文件夹「${folder.name}」？`)) return;
    try {
      await deleteAssetFolder(folder.id);
      setFolders((prev) => prev.filter((f) => f.id !== folder.id));
      if (folderFilter === folder.id) setFolderFilter(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除文件夹失败");
    }
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes}B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)}GB`;
  };

  const formatDate = (iso: string) =>
    new Date(iso).toLocaleString("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });

  const selectedAsset = useMemo(
    () => (selectedId == null ? null : assets.find((a) => a.id === selectedId) || null),
    [assets, selectedId]
  );

  const selectedFolder = useMemo(
    () => folders.find((f) => f.id === folderFilter) || null,
    [folders, folderFilter]
  );

  if (loading) {
    return (
      <div className="page">
        <h1>素材库</h1>
        <div className="empty-state">加载中...</div>
      </div>
    );
  }

  return (
    <div className={`assets-page${selectedAsset ? " has-inspector" : ""}`}>
      <div className="assets-toolbar">
        <div className="assets-breadcrumb">
          <button type="button" onClick={() => setFolderFilter(null)}>全部素材</button>
          <ChevronRight size={14} />
          <span className="assets-breadcrumb-current">
            {selectedFolder ? selectedFolder.name : "未分类"}
          </span>
        </div>
        <div className="assets-toolbar-actions">
          <button
            type="button"
            className="btn btn-outline"
            onClick={() => setShowCreate((prev) => !prev)}
          >
            <FolderPlus size={15} />
            新建文件夹
          </button>
          <label className="btn btn-primary btn-upload">
            <Upload size={15} />
            {uploading ? "上传中..." : "上传文件"}
            <input type="file" onChange={handleUpload} style={{ display: "none" }} disabled={uploading} />
          </label>
        </div>
      </div>

      {showCreate && (
        <form className="project-create-form assets-create-form" onSubmit={handleCreateFolder}>
          <label>
            文件夹名称
            <input
              value={newFolderName}
              onChange={(event) => setNewFolderName(event.target.value)}
              placeholder="例如：角色设定 / 镜头脚本"
              autoFocus
              maxLength={64}
            />
          </label>
          {createError && <div className="auth-error">{createError}</div>}
          <div className="page-toolbar">
            <button className="btn btn-primary" type="submit" disabled={creatingFolder}>
              {creatingFolder ? "创建中..." : "创建文件夹"}
            </button>
            <button
              className="btn btn-secondary"
              type="button"
              onClick={() => {
                setShowCreate(false);
                setNewFolderName("");
                setCreateError("");
              }}
            >
              取消
            </button>
          </div>
        </form>
      )}

      {error && <div className="auth-error" style={{ marginBottom: 16 }}>{error}</div>}

      <section className="assets-section">
        <h2 className="assets-section-title">
          <span className="assets-section-bar" />
          文件夹
        </h2>
        {folders.length === 0 ? (
          <button
            type="button"
            className="assets-folder-empty glass-card"
            onClick={() => setShowCreate(true)}
          >
            <div className="assets-folder-icon is-secondary">
              <Folder size={26} strokeWidth={1.6} />
            </div>
            <div className="assets-folder-info">
              <h3>创建第一个文件夹</h3>
              <p>为素材建立分类，例如「角色设定」「镜头脚本」「成片归档」</p>
            </div>
            <span className="assets-folder-more">+</span>
          </button>
        ) : (
          <div className="assets-folder-grid">
            <button
              type="button"
              className={`assets-folder-card glass-card${folderFilter == null ? " is-selected" : ""}`}
              onClick={() => setFolderFilter(null)}
            >
              <div className="assets-folder-icon is-primary">
                <FolderOpen size={26} strokeWidth={1.6} />
              </div>
              <div className="assets-folder-info">
                <h3>全部素材</h3>
                <p>查看所有未归档的素材</p>
              </div>
            </button>
            {folders.map((folder, idx) => (
              <FolderCard
                key={folder.id}
                folder={folder}
                index={idx}
                selected={folder.id === folderFilter}
                onSelect={() => setFolderFilter(folder.id)}
                onDelete={(event) => handleDeleteFolder(folder, event)}
              />
            ))}
          </div>
        )}
      </section>

      <section className="assets-section">
        <h2 className="assets-section-title">
          <span className="assets-section-bar" />
          {selectedFolder ? `${selectedFolder.name} · 素材概览` : "素材概览"}
        </h2>
        {assets.length === 0 ? (
          <div className="empty-state">
            {selectedFolder
              ? `「${selectedFolder.name}」中暂无素材，请上传文件。`
              : "暂无素材，请上传文件。"}
          </div>
        ) : (
          <div className="assets-grid">
            {assets.map((asset) => (
              <AssetCard
                key={asset.id}
                asset={asset}
                formatSize={formatSize}
                selected={asset.id === selectedId}
                onSelect={() => setSelectedId(asset.id)}
              />
            ))}
          </div>
        )}
      </section>

      {selectedAsset && (
        <AssetInspector
          asset={selectedAsset}
          formatSize={formatSize}
          formatDate={formatDate}
          onClose={() => setSelectedId(null)}
        />
      )}
    </div>
  );
}

type FolderCardProps = {
  folder: AssetFolder;
  index: number;
  selected: boolean;
  onSelect: () => void;
  onDelete: (event: React.MouseEvent) => void;
};

function FolderCard({ folder, index, selected, onSelect, onDelete }: FolderCardProps) {
  const Icon = index % 2 === 0 ? Folder : FolderOpen;
  return (
    <div
      className={`assets-folder-card glass-card${selected ? " is-selected" : ""}`}
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onSelect();
        }
      }}
    >
      <button type="button" className="assets-folder-card-body" onClick={onSelect}>
        <div className="assets-folder-icon is-secondary">
          <Icon size={26} strokeWidth={1.6} />
        </div>
        <div className="assets-folder-info">
          <h3>{folder.name}</h3>
          <p>{folder.asset_count} 个项目</p>
        </div>
      </button>
      <button
        type="button"
        className="assets-folder-delete"
        title="删除文件夹"
        aria-label={`删除文件夹 ${folder.name}`}
        onClick={onDelete}
      >
        <Trash2 size={14} />
      </button>
    </div>
  );
}

type AssetCardProps = {
  asset: Asset;
  formatSize: (bytes: number) => string;
  selected: boolean;
  onSelect: () => void;
};

function AssetCard({ asset, formatSize, selected, onSelect }: AssetCardProps) {
  const meta = KIND_META[asset.kind] || { label: asset.kind, chip: asset.kind };
  const isImage = asset.kind === "image";
  const isVideo = asset.kind === "video";
  const isAudio = asset.kind === "audio";

  return (
    <div
      className={`assets-card glass-card${selected ? " is-selected" : ""}`}
      onClick={onSelect}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect();
        }
      }}
    >
      <div className="assets-card-preview">
        {isImage && (
          <img
            src={assetUrl(asset.id)}
            alt={asset.original_filename}
            loading="lazy"
            className="assets-card-media"
          />
        )}
        {isVideo && (
          <>
            <img
              src={assetUrl(asset.id)}
              alt={asset.original_filename}
              loading="lazy"
              className="assets-card-media assets-card-media-blur"
            />
            <span className="assets-card-play">
              <CirclePlay size={22} fill="currentColor" />
            </span>
            <span className="assets-card-duration">00:15</span>
          </>
        )}
        {isAudio && (
          <div className="assets-card-audio">
            <div className="assets-card-waveform">
              <span style={{ animationDelay: "0.1s" }} />
              <span style={{ animationDelay: "0.2s" }} />
              <span style={{ animationDelay: "0.3s" }} />
              <span style={{ animationDelay: "0.4s" }} />
              <span style={{ animationDelay: "0.5s" }} />
              <span style={{ animationDelay: "0.6s" }} />
              <span style={{ animationDelay: "0.7s" }} />
            </div>
            <button type="button" className="assets-card-play-btn" onClick={(e) => e.stopPropagation()}>
              <CirclePlay size={18} fill="currentColor" />
            </button>
          </div>
        )}
        {!isImage && !isVideo && !isAudio && (
          <div className="assets-card-doc">
            <FileText size={56} strokeWidth={1.2} />
            <p className="mono">{asset.original_filename}</p>
          </div>
        )}
        {isImage && (
          <div className="assets-card-hover-overlay">
            <button type="button" className="assets-card-add-btn" onClick={(e) => e.stopPropagation()}>
              <Plus size={16} strokeWidth={2.4} />
            </button>
          </div>
        )}
      </div>
      <div className="assets-card-body">
        <div className="assets-card-title-row">
          <h4 className="assets-card-title">{asset.original_filename}</h4>
          <span className="assets-card-chip">{meta.chip}</span>
        </div>
        <p className="assets-card-meta">
          {formatSize(asset.size_bytes)} · {asset.uploaded_by_username || "—"}
        </p>
      </div>
    </div>
  );
}

type InspectorProps = {
  asset: Asset;
  formatSize: (bytes: number) => string;
  formatDate: (iso: string) => string;
  onClose: () => void;
};

function AssetInspector({ asset, formatSize, formatDate, onClose }: InspectorProps) {
  const meta = KIND_META[asset.kind] || { label: asset.kind, chip: asset.kind };
  const isImage = asset.kind === "image";

  return (
    <aside className="assets-inspector">
      <header className="assets-inspector-header">
        <h3>文件详情</h3>
        <button type="button" className="assets-inspector-close" onClick={onClose} aria-label="关闭">
          <X size={18} />
        </button>
      </header>

      <div className="assets-inspector-body">
        <div className="assets-inspector-preview">
          {isImage ? (
            <img src={assetUrl(asset.id)} alt={asset.original_filename} className="assets-inspector-image" />
          ) : (
            <div className="assets-inspector-preview-fallback">
              {asset.kind === "video" && <Video size={48} strokeWidth={1.2} />}
              {asset.kind === "audio" && <Music size={48} strokeWidth={1.2} />}
              {asset.kind === "document" && <FileText size={48} strokeWidth={1.2} />}
            </div>
          )}
        </div>

        <div className="assets-inspector-block">
          <h4 className="assets-inspector-block-title">核心元数据</h4>
          <div className="assets-inspector-list">
            <InspectorRow label="文件名" value={asset.original_filename} mono />
            <InspectorRow label="类型" value={meta.label} />
            <InspectorRow label="大小" value={formatSize(asset.size_bytes)} mono />
            <InspectorRow
              label="MIME"
              value={asset.mime_type}
              mono
              truncate
            />
            <InspectorRow
              label="上传者"
              value={asset.uploaded_by_username || "未知"}
            />
            <InspectorRow
              label="创建时间"
              value={formatDate(asset.created_at)}
              mono
            />
          </div>
        </div>

        <div className="assets-inspector-block">
          <h4 className="assets-inspector-block-title">版本历史</h4>
          <div className="assets-inspector-versions">
            <div className="assets-version-row is-current">
              <div className="assets-version-badge">
                <Sparkles size={13} />
              </div>
              <div className="assets-version-info">
                <p className="assets-version-title">当前版本</p>
                <p className="assets-version-meta">
                  <Clock size={10} />
                  {formatDate(asset.created_at)} · {asset.uploaded_by_username || "系统"}
                </p>
              </div>
            </div>
            <div className="assets-version-row is-dimmed">
              <div className="assets-version-badge">V1</div>
              <div className="assets-version-info">
                <p className="assets-version-title">初始草案</p>
                <p className="assets-version-meta">—</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <footer className="assets-inspector-footer">
        <button type="button" className="btn btn-primary btn-full">
          <Plus size={15} />
          添加到画布
        </button>
        <div className="assets-inspector-footer-row">
          <a href={assetUrl(asset.id)} download className="btn btn-secondary assets-inspector-action">
            下载
          </a>
          <button type="button" className="btn btn-danger-soft assets-inspector-action">
            删除
          </button>
        </div>
      </footer>
    </aside>
  );
}

function InspectorRow({
  label,
  value,
  mono,
  truncate,
}: {
  label: string;
  value: string;
  mono?: boolean;
  truncate?: boolean;
}) {
  return (
    <div className="assets-inspector-row">
      <span className="assets-inspector-row-label">{label}</span>
      <span
        className={`assets-inspector-row-value${mono ? " mono" : ""}${truncate ? " assets-inspector-row-truncate" : ""}`}
        title={value}
      >
        {value}
      </span>
    </div>
  );
}