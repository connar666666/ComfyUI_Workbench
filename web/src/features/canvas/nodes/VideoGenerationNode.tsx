import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Play } from "lucide-react";
import type { VideoGenerationNode as VideoGenerationNodeType } from "../canvasTypes";

type VideoGenerationNodeProps = NodeProps<VideoGenerationNodeType> & {
  data: VideoGenerationNodeType["data"] & {
    onGenerate?: (nodeId: string) => void;
  };
};

export function VideoGenerationNode({ id, data }: VideoGenerationNodeProps) {
  const isBusy = data.status === "queued" || data.status === "running";

  return (
    <div className="canvas-node canvas-node-generation">
      <Handle type="target" position={Position.Left} />
      <div className="canvas-node-kicker">Video Generation</div>
      <div className="canvas-node-title">{data.title}</div>
      <p className="canvas-node-text">{data.prompt || "连接 PromptNode 或在右侧填写提示词"}</p>
      <div className="canvas-node-meta">
        <span>{data.duration_sec}s</span>
        <span>{data.resolution}</span>
        <span className={`canvas-status canvas-status-${data.status || "idle"}`}>{data.status || "idle"}</span>
      </div>
      {data.errorMessage && <div className="canvas-node-error">{data.errorMessage}</div>}
      <button
        type="button"
        className="btn-primary btn-sm canvas-node-action"
        disabled={isBusy}
        onClick={() => data.onGenerate?.(id)}
      >
        <Play size={14} />
        Generate
      </button>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
