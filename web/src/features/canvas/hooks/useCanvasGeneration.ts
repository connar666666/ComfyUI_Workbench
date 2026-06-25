import { useCallback } from "react";
import type { OnNodesChange } from "@xyflow/react";
import { createCanvasJob } from "../api/canvasApi";
import type { WorkbenchEdge, WorkbenchNode } from "../canvasTypes";
import { buildGenerationPayload } from "../utils/buildGenerationPayload";
import { resolveNodeInputs } from "../utils/resolveNodeInputs";

export function useCanvasGeneration(
  canvasId: string,
  nodes: WorkbenchNode[],
  edges: WorkbenchEdge[],
  onNodesChange: OnNodesChange<WorkbenchNode>
) {
  const replaceNode = useCallback(
    (node: WorkbenchNode) => {
      onNodesChange([{ id: node.id, type: "replace", item: node }]);
    },
    [onNodesChange]
  );

  return useCallback(
    async (nodeId: string) => {
      const node = nodes.find((item) => item.id === nodeId);
      if (!node || node.type !== "videoGeneration") return;

      try {
        const payload = buildGenerationPayload({
          canvasId,
          node,
          resolvedInputs: resolveNodeInputs(nodes, edges, nodeId),
        });
        replaceNode({ ...node, data: { ...node.data, status: "queued", errorMessage: undefined } });
        const job = await createCanvasJob(payload);
        replaceNode({
          ...node,
          data: {
            ...node.data,
            status: job.status,
            currentJobId: job.id,
            currentVersionId: job.canvas_version_id ?? undefined,
            errorMessage: job.error_message ?? undefined,
          },
        });
      } catch (err) {
        replaceNode({
          ...node,
          data: {
            ...node.data,
            status: "failed",
            errorMessage: err instanceof Error ? err.message : "Failed to create job",
          },
        });
      }
    },
    [canvasId, edges, nodes, replaceNode]
  );
}
