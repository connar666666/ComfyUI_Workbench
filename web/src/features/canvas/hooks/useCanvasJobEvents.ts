import { useCallback } from "react";
import type { OnNodesChange } from "@xyflow/react";
import { useSSE } from "../../../hooks/useSSE";
import type { Job, SSEEvent } from "../../../types";
import type { WorkbenchNode } from "../canvasTypes";

export function useCanvasJobEvents(
  canvasId: string,
  nodes: WorkbenchNode[],
  onNodesChange: OnNodesChange<WorkbenchNode>
) {
  const replaceNode = useCallback(
    (node: WorkbenchNode) => {
      onNodesChange([{ id: node.id, type: "replace", item: node }]);
    },
    [onNodesChange]
  );

  useSSE((event: SSEEvent) => {
    if (event.type !== "job_created" && event.type !== "job_status_changed") return;
    const job = (event.data as { job?: Job }).job;
    if (!job || job.canvas_id !== canvasId || !job.canvas_node_id) return;

    const node = nodes.find((item) => item.id === job.canvas_node_id);
    if (!node || node.type !== "videoGeneration") return;

    replaceNode({
      ...node,
      data: {
        ...node.data,
        status: job.status,
        currentJobId: job.id,
        currentVersionId: job.canvas_version_id ?? node.data.currentVersionId,
        errorMessage: job.error_message ?? undefined,
      },
    });
  });
}
