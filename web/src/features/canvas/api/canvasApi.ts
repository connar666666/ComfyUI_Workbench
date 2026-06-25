import { createJob, listNodeVersions, resolveLiveblocksUsers } from "../../../api/client";
import type { CanvasJobPayload } from "../canvasTypes";

export function createCanvasJob(payload: CanvasJobPayload) {
  return createJob(payload);
}

export function listCanvasNodeVersions(canvasId: string, nodeId: string) {
  return listNodeVersions(canvasId, nodeId);
}

export function resolveCanvasUsers(userIds: string[]) {
  return resolveLiveblocksUsers(userIds);
}
