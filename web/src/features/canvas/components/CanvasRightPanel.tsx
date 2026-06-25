import { useEffect, useState } from "react";
import type { OnNodesChange } from "@xyflow/react";
import type { NodeVersion } from "../../../types";
import { listCanvasNodeVersions } from "../api/canvasApi";
import type { WorkbenchNode } from "../canvasTypes";

type CanvasRightPanelProps = {
  canvasId: string;
  selectedNode: WorkbenchNode | null;
  onNodesChange: OnNodesChange<WorkbenchNode>;
  onGenerate: (nodeId: string) => void;
};

export function CanvasRightPanel({
  canvasId,
  selectedNode,
  onNodesChange,
  onGenerate,
}: CanvasRightPanelProps) {
  const [versions, setVersions] = useState<NodeVersion[]>([]);

  useEffect(() => {
    if (selectedNode?.type !== "videoGeneration") {
      setVersions([]);
      return;
    }
    listCanvasNodeVersions(canvasId, selectedNode.id).then(setVersions).catch(() => setVersions([]));
  }, [canvasId, selectedNode?.id, selectedNode?.type]);

  const updateNode = (node: WorkbenchNode) => {
    onNodesChange([{ id: node.id, type: "replace", item: node }]);
  };

  if (!selectedNode) {
    return (
      <aside className="canvas-panel canvas-right-panel">
        <h2>属性</h2>
        <div className="empty-state">选择一个节点查看属性。</div>
      </aside>
    );
  }

  return (
    <aside className="canvas-panel canvas-right-panel">
      <h2>属性</h2>
      <div className="form-group">
        <label>标题</label>
        <input
          type="text"
          value={selectedNode.data.title}
          onChange={(event) =>
            updateNode({ ...selectedNode, data: { ...selectedNode.data, title: event.target.value } } as WorkbenchNode)
          }
        />
      </div>

      {selectedNode.type === "prompt" && (
        <>
          <div className="form-group">
            <label>Prompt</label>
            <textarea
              value={selectedNode.data.prompt}
              onChange={(event) => updateNode({ ...selectedNode, data: { ...selectedNode.data, prompt: event.target.value } })}
            />
          </div>
          <div className="form-group">
            <label>Negative Prompt</label>
            <textarea
              value={selectedNode.data.negativePrompt || ""}
              onChange={(event) => updateNode({ ...selectedNode, data: { ...selectedNode.data, negativePrompt: event.target.value } })}
            />
          </div>
        </>
      )}

      {selectedNode.type === "asset" && (
        <div className="canvas-node-detail-list">
          <div><strong>Asset ID:</strong> {selectedNode.data.assetId}</div>
          <div><strong>Type:</strong> {selectedNode.data.assetKind}</div>
          <div><strong>Filename:</strong> {selectedNode.data.fileName || "-"}</div>
        </div>
      )}

      {selectedNode.type === "videoGeneration" && (
        <>
          <div className="form-group">
            <label>Prompt</label>
            <textarea
              value={selectedNode.data.prompt || ""}
              onChange={(event) => updateNode({ ...selectedNode, data: { ...selectedNode.data, prompt: event.target.value } })}
            />
          </div>
          <div className="form-row">
            <div className="form-group">
              <label>时长</label>
              <input
                type="number"
                min={1}
                max={60}
                value={selectedNode.data.duration_sec}
                onChange={(event) => updateNode({ ...selectedNode, data: { ...selectedNode.data, duration_sec: Number(event.target.value) } })}
              />
            </div>
            <div className="form-group">
              <label>音频偏移</label>
              <input
                type="number"
                min={0}
                step={0.1}
                value={selectedNode.data.audio_start_sec}
                onChange={(event) => updateNode({ ...selectedNode, data: { ...selectedNode.data, audio_start_sec: Number(event.target.value) } })}
              />
            </div>
          </div>
          <div className="form-group">
            <label>分辨率</label>
            <select
              value={selectedNode.data.resolution}
              onChange={(event) =>
                updateNode({
                  ...selectedNode,
                  data: {
                    ...selectedNode.data,
                    resolution: event.target.value as "720x1280" | "1280x720" | "1024x1024",
                  },
                })
              }
            >
              <option value="720x1280">720x1280</option>
              <option value="1280x720">1280x720</option>
              <option value="1024x1024">1024x1024</option>
            </select>
          </div>
          <button type="button" className="btn-primary btn-full" onClick={() => onGenerate(selectedNode.id)}>
            Generate
          </button>
          <section className="canvas-versions">
            <h3>版本历史</h3>
            {versions.length === 0 ? (
              <div className="muted">暂无版本</div>
            ) : (
              versions.map((version) => (
                <div key={version.id} className="canvas-version-item">
                  <strong>v{version.version_number}</strong>
                  <span>{version.status}</span>
                  <p>{version.prompt}</p>
                  {version.output_video_id && <span>video #{version.output_video_id}</span>}
                </div>
              ))
            )}
          </section>
        </>
      )}
    </aside>
  );
}
