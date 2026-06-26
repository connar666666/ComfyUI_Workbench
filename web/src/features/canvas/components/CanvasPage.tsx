import { ReactFlowProvider } from "@xyflow/react";
import { useEffect, useState } from "react";
import { getAuthToken, readApiError } from "../../../api/client";
import { CollaborativeCanvas } from "./CollaborativeCanvas";
import { CanvasRoom } from "./CanvasRoom";
import { LocalCanvas } from "./LocalCanvas";

export function CanvasPage() {
  const canvasId = "default";
  const [collaborationState, setCollaborationState] = useState<"checking" | "ready" | "fallback">("checking");
  const [collaborationError, setCollaborationError] = useState("");

  useEffect(() => {
    let cancelled = false;

    const checkCollaboration = async () => {
      try {
        const token = getAuthToken();
        const response = await fetch("/api/liveblocks-auth", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({ room: `canvas:${canvasId}` }),
        });

        if (!response.ok) {
          throw await readApiError(response, "Live collaboration is unavailable");
        }

        if (!cancelled) {
          setCollaborationError("");
          setCollaborationState("ready");
        }
      } catch (err) {
        if (!cancelled) {
          setCollaborationError(err instanceof Error ? err.message : "Live collaboration is unavailable");
          setCollaborationState("fallback");
        }
      }
    };

    void checkCollaboration();

    return () => {
      cancelled = true;
    };
  }, [canvasId]);

  if (collaborationState === "checking") {
    return <div className="empty-state">正在检查协作画布服务...</div>;
  }

  if (collaborationState === "ready") {
    return (
      <CanvasRoom canvasId={canvasId}>
        <ReactFlowProvider>
          <div className="canvas-page">
            <CollaborativeCanvas canvasId={canvasId} />
          </div>
        </ReactFlowProvider>
      </CanvasRoom>
    );
  }

  return (
    <ReactFlowProvider>
      <div className="canvas-page">
        <div className="auth-error" role="alert" aria-live="polite" style={{ margin: "16px" }}>
          协作画布当前不可用，已切换到本地模式：{collaborationError}
        </div>
        <LocalCanvas canvasId={canvasId} />
      </div>
    </ReactFlowProvider>
  );
}
