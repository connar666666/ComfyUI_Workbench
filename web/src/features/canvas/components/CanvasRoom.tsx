import { ClientSideSuspense, LiveblocksProvider, RoomProvider } from "@liveblocks/react/suspense";
import type { ReactNode } from "react";
import { getAuthToken } from "../../../api/client";
import { resolveCanvasUsers } from "../api/canvasApi";

type CanvasRoomProps = {
  canvasId: string;
  children: ReactNode;
};

export function CanvasRoom({ canvasId, children }: CanvasRoomProps) {
  return (
    <LiveblocksProvider
      authEndpoint={async (room) => {
        const token = getAuthToken();
        const response = await fetch("/api/liveblocks-auth", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({ room }),
        });
        return response.json();
      }}
      resolveUsers={async ({ userIds }) => resolveCanvasUsers(userIds)}
    >
      <RoomProvider id={`canvas:${canvasId}`}>
        <ClientSideSuspense fallback={<div className="empty-state">加载画布...</div>}>
          {children}
        </ClientSideSuspense>
      </RoomProvider>
    </LiveblocksProvider>
  );
}
