import { useEffect, useState } from "react";
import type { OnNodesChange } from "@xyflow/react";
import { CheckCircle2, Info, Trash2 } from "lucide-react";
import type { NodeVersion } from "../../../types";
import { listCanvasNodeVersions } from "../api/canvasApi";
import type { WorkbenchEdge, WorkbenchNode } from "../canvasTypes";

type CanvasRightPanelProps = {
  canvasId: string;
  selectedNode: WorkbenchNode | null;
  onNodesChange: OnNodesChange<WorkbenchNode>;
  onGenerate: (nodeId: string) => void;
  incomingEdges?: WorkbenchEdge[];
};

export function CanvasRightPanel({
  canvasId,
  selectedNode,
  onNodesChange,
  onGenerate,
  incomingEdges = [],
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
        <header className="canvas-right-header">
          <h2>节点属性</h2>
          <p className="canvas-right-hint">点击画布中的节点查看属性</p>
        </header>
        <div className="empty-state">未选中任何节点</div>
      </aside>
    );
  }

  const typeLabel: Record<string, string> = {
    prompt: "Prompt 节点",
    asset: "资产节点",
    videoGeneration: "视频生成节点",
  };

  return (
    <aside className="canvas-panel canvas-right-panel">
      <header className="canvas-right-header">
        <h2>节点属性</h2>
        <p className="canvas-right-hint">
          当前选择:{" "}
          <span className="canvas-right-selected">
            {typeLabel[selectedNode.type] || selectedNode.type} · v2.1
          </span>
        </p>
      </header>

      <section className="canvas-right-section">
        <div className="canvas-right-section-header">
          <h3>输入依赖</h3>
          <Info size={13} />
        </div>
        {incomingEdges.length === 0 ? (
          <div className="muted">暂无输入</div>
        ) : (
          <div className="canvas-right-deps">
            {incomingEdges.map((edge) => (
              <div key={edge.id} className="canvas-right-dep-item">
                <span>{edge.source}</span>
                <CheckCircle2 size={14} className="ok" />
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="canvas-right-section">
        <h3>基本参数</h3>
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
                <label>持续时长</label>
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
              立即生成
            </button>
          </>
        )}
      </section>

      {selectedNode.type === "videoGeneration" && (
        <>
          <section className="canvas-right-section">
            <h3>输出候选</h3>
            <div className="canvas-right-output-grid">
              <div className="canvas-right-output-cell" style={{ background: "linear-gradient(135deg, #d0bcff, #4edea3)" }} />
              <div className="canvas-right-output-cell" style={{ background: "linear-gradient(135deg, #ffb95f, #d0bcff)" }} />
            </div>
          </section>

          <section className="canvas-right-section canvas-versions">
            <h3>版本历史</h3>
            {versions.length === 0 ? (
              <div className="muted">暂无版本</div>
            ) : (
              versions.map((version) => (
                <div key={version.id} className="canvas-version-item">
                  <span className="canvas-version-id">v{version.version_number}.0</span>
                  <span className="canvas-version-status">{version.status === "succeeded" ? "当前激活" : "回滚"}</span>
                </div>
              ))
            )}
          </section>
        </>
      )}

      <footer className="canvas-right-footer">
        <button type="button" className="canvas-right-delete">
          <Trash2 size={15} />
          删除节点
        </button>
      </footer>
    </aside>
  );
}