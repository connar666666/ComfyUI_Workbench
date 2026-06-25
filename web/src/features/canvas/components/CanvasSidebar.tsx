import { FilePlus, ImagePlus, PlusCircle, Upload } from "lucide-react";
import type { Asset } from "../../../types";

type CanvasSidebarProps = {
  assets: Asset[];
  kindFilter: string;
  setKindFilter: (kind: string) => void;
  isLoading: boolean;
  isUploading: boolean;
  error: string;
  onAddPrompt: () => void;
  onAddGeneration: () => void;
  onAddAsset: (asset: Asset) => void;
  onUpload: (file: File) => void;
};

const KIND_OPTIONS = [
  { value: "", label: "全部素材" },
  { value: "image", label: "图片" },
  { value: "audio", label: "音频" },
  { value: "video", label: "视频" },
];

export function CanvasSidebar({
  assets,
  kindFilter,
  setKindFilter,
  isLoading,
  isUploading,
  error,
  onAddPrompt,
  onAddGeneration,
  onAddAsset,
  onUpload,
}: CanvasSidebarProps) {
  return (
    <aside className="canvas-panel canvas-left-panel">
      <section>
        <h2>节点库</h2>
        <button type="button" className="btn-secondary canvas-panel-button" onClick={onAddPrompt}>
          <FilePlus size={16} />
          Prompt Node
        </button>
        <button type="button" className="btn-primary canvas-panel-button" onClick={onAddGeneration}>
          <PlusCircle size={16} />
          Video Generation
        </button>
      </section>

      <section>
        <h2>素材</h2>
        <select value={kindFilter} onChange={(event) => setKindFilter(event.target.value)}>
          {KIND_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
        <label className="btn-secondary canvas-panel-button canvas-upload-button">
          <Upload size={16} />
          {isUploading ? "上传中..." : "上传到画布"}
          <input
            type="file"
            disabled={isUploading}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) onUpload(file);
              event.target.value = "";
            }}
          />
        </label>
        {error && <div className="auth-error">{error}</div>}
        <div className="canvas-asset-list">
          {isLoading ? (
            <div className="muted">加载素材...</div>
          ) : assets.length === 0 ? (
            <div className="muted">暂无素材</div>
          ) : (
            assets.slice(0, 40).map((asset) => (
              <button
                key={asset.id}
                type="button"
                className="canvas-asset-item"
                onClick={() => onAddAsset(asset)}
              >
                <ImagePlus size={15} />
                <span>{asset.original_filename}</span>
              </button>
            ))
          )}
        </div>
      </section>
    </aside>
  );
}
