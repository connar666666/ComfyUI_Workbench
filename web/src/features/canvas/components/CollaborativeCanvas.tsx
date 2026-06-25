import { useMemo, useState } from "react";
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  useReactFlow,
  type OnNodesChange,
} from "@xyflow/react";
import { Cursors, useLiveblocksFlow } from "@liveblocks/react-flow";
import "@xyflow/react/dist/style.css";
import "@liveblocks/react-flow/styles.css";
import "@liveblocks/react-ui/styles.css";
import type { Asset } from "../../../types";
import type { WorkbenchEdge, WorkbenchNode } from "../canvasTypes";
import { useCanvasAssets } from "../hooks/useCanvasAssets";
import { useCanvasGeneration } from "../hooks/useCanvasGeneration";
import { useCanvasJobEvents } from "../hooks/useCanvasJobEvents";
import { nodeTypes } from "../nodes/nodeTypes";
import { CanvasRightPanel } from "./CanvasRightPanel";
import { CanvasSidebar } from "./CanvasSidebar";
import { CanvasToolbar } from "./CanvasToolbar";

type CollaborativeCanvasProps = {
  canvasId: string;
};

function newNodeId(prefix: string) {
  return `${prefix}-${crypto.randomUUID()}`;
}

export function CollaborativeCanvas({ canvasId }: CollaborativeCanvasProps) {
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const reactFlow = useReactFlow<WorkbenchNode, WorkbenchEdge>();
  const { assets, kindFilter, setKindFilter, isLoading, isUploading, error, upload } = useCanvasAssets();
  const {
    nodes,
    edges,
    onNodesChange,
    onEdgesChange,
    onConnect,
    onDelete,
  } = useLiveblocksFlow<WorkbenchNode, WorkbenchEdge>({
    suspense: true,
    storageKey: "workbenchFlow",
    nodes: {
      initial: [],
      sync: {
        "*": {
          thumbnailUrl: "atomic",
          errorMessage: "atomic",
        },
      },
    },
    edges: {
      initial: [],
    },
  });

  const generate = useCanvasGeneration(canvasId, nodes, edges, onNodesChange);
  useCanvasJobEvents(canvasId, nodes, onNodesChange);

  const selectedNode = useMemo(
    () => nodes.find((node) => node.id === selectedNodeId) || null,
    [nodes, selectedNodeId]
  );

  const nodesWithActions = useMemo(
    () =>
      nodes.map((node) =>
        node.type === "videoGeneration"
          ? { ...node, data: { ...node.data, onGenerate: generate } }
          : node
      ),
    [generate, nodes]
  );

  const addNode = (node: WorkbenchNode) => {
    onNodesChange([{ type: "add", item: node }]);
    setSelectedNodeId(node.id);
  };

  const addPromptNode = () => {
    addNode({
      id: newNodeId("prompt"),
      type: "prompt",
      position: { x: 120, y: 120 },
      data: { title: "Prompt", prompt: "" },
    });
  };

  const addGenerationNode = () => {
    addNode({
      id: newNodeId("generation"),
      type: "videoGeneration",
      position: { x: 480, y: 180 },
      data: {
        title: "Video Generation",
        duration_sec: 5,
        resolution: "720x1280",
        audio_start_sec: 0,
        status: "idle",
      },
    });
  };

  const addAssetNode = (asset: Asset) => {
    addNode({
      id: newNodeId("asset"),
      type: "asset",
      position: { x: 140, y: 320 },
      data: {
        title: asset.original_filename,
        assetId: asset.id,
        assetKind: asset.kind,
        fileName: asset.original_filename,
        mimeType: asset.mime_type,
      },
    });
  };

  const uploadToCanvas = async (file: File) => {
    const asset = await upload(file);
    addAssetNode(asset);
  };

  const handleNodesChange: OnNodesChange<WorkbenchNode> = (changes) => {
    const removedIds = new Set(changes.filter((change) => change.type === "remove").map((change) => change.id));
    if (selectedNodeId && removedIds.has(selectedNodeId)) {
      setSelectedNodeId(null);
    }
    onNodesChange(changes);
  };

  return (
    <div className="canvas-workspace">
      <CanvasSidebar
        assets={assets}
        kindFilter={kindFilter}
        setKindFilter={setKindFilter}
        isLoading={isLoading}
        isUploading={isUploading}
        error={error}
        onAddPrompt={addPromptNode}
        onAddGeneration={addGenerationNode}
        onAddAsset={addAssetNode}
        onUpload={uploadToCanvas}
      />
      <section className="canvas-main">
        <CanvasToolbar onFitView={() => reactFlow.fitView()} />
        <div className="canvas-surface">
          <ReactFlow
            nodes={nodesWithActions}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodesChange={handleNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onDelete={onDelete}
            onNodeClick={(_, node) => setSelectedNodeId(node.id)}
            fitView
          >
            <Background />
            <Controls />
            <MiniMap />
            <Cursors />
          </ReactFlow>
        </div>
      </section>
      <CanvasRightPanel
        canvasId={canvasId}
        selectedNode={selectedNode}
        onNodesChange={onNodesChange}
        onGenerate={generate}
      />
    </div>
  );
}
