import { Handle, Position, type NodeProps } from "@xyflow/react";
import { FileAudio, FileImage, FileVideo, FileText } from "lucide-react";
import { assetUrl } from "../../../api/client";
import type { AssetNode as AssetNodeType } from "../canvasTypes";

function AssetIcon({ kind }: { kind: AssetNodeType["data"]["assetKind"] }) {
  if (kind === "image") return <FileImage size={18} />;
  if (kind === "audio") return <FileAudio size={18} />;
  if (kind === "video") return <FileVideo size={18} />;
  return <FileText size={18} />;
}

export function AssetNode({ data }: NodeProps<AssetNodeType>) {
  return (
    <div className="canvas-node canvas-node-asset">
      <Handle type="target" position={Position.Left} />
      <div className="canvas-node-row">
        <span className="canvas-node-icon"><AssetIcon kind={data.assetKind} /></span>
        <div>
          <div className="canvas-node-kicker">{data.assetKind}</div>
          <div className="canvas-node-title">{data.title}</div>
        </div>
      </div>
      {data.assetKind === "image" ? (
        <img className="canvas-node-preview" src={assetUrl(data.assetId)} alt={data.fileName || data.title} />
      ) : (
        <p className="canvas-node-text">{data.fileName || `Asset #${data.assetId}`}</p>
      )}
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
