import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { PromptNode as PromptNodeType } from "../canvasTypes";

export function PromptNode({ data }: NodeProps<PromptNodeType>) {
  return (
    <div className="canvas-node canvas-node-prompt">
      <Handle type="target" position={Position.Left} />
      <div className="canvas-node-kicker">Prompt</div>
      <div className="canvas-node-title">{data.title}</div>
      <p className="canvas-node-text">{data.prompt || "空提示词"}</p>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
