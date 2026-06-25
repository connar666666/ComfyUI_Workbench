import { PanelTopClose, Redo2, Undo2 } from "lucide-react";

type CanvasToolbarProps = {
  onFitView: () => void;
};

export function CanvasToolbar({ onFitView }: CanvasToolbarProps) {
  return (
    <div className="canvas-toolbar">
      <div>
        <h1>创作画布</h1>
        <span>Liveblocks collaborative room: canvas:default</span>
      </div>
      <div className="canvas-toolbar-actions">
        <button type="button" className="btn-secondary btn-sm" title="Undo">
          <Undo2 size={14} />
        </button>
        <button type="button" className="btn-secondary btn-sm" title="Redo">
          <Redo2 size={14} />
        </button>
        <button type="button" className="btn-secondary btn-sm" onClick={onFitView}>
          <PanelTopClose size={14} />
          Fit
        </button>
      </div>
    </div>
  );
}
