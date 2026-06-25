import { ReactFlowProvider } from "@xyflow/react";
import { CollaborativeCanvas } from "./CollaborativeCanvas";
import { CanvasRoom } from "./CanvasRoom";

export function CanvasPage() {
  return (
    <CanvasRoom canvasId="default">
      <ReactFlowProvider>
        <div className="canvas-page">
          <CollaborativeCanvas canvasId="default" />
        </div>
      </ReactFlowProvider>
    </CanvasRoom>
  );
}
