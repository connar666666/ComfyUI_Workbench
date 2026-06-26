import type { Edge, Node } from "@xyflow/react";

export type WorkbenchNodeType = "prompt" | "asset" | "videoGeneration";

export type WorkbenchStatus =
  | "idle"
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "canceled";

export type WorkbenchNodeData = {
  title: string;
  createdBy?: string;
  updatedBy?: string;
  status?: WorkbenchStatus;
  currentJobId?: string;
  currentVersionId?: string;
  thumbnailUrl?: string;
  errorMessage?: string;
};

export type PromptNodeData = WorkbenchNodeData & {
  prompt: string;
  negativePrompt?: string;
};

export type AssetNodeData = WorkbenchNodeData & {
  assetId: string;
  assetKind: "image" | "audio" | "video" | "document";
  fileName?: string;
  mimeType?: string;
};

export type VideoGenerationNodeData = WorkbenchNodeData & {
  prompt?: string;
  negativePrompt?: string;
  duration_sec: number;
  resolution: "720x1280" | "1280x720" | "1024x1024";
  audio_start_sec: number;
  reference_image_asset_id?: string | null;
  reference_audio_asset_id?: string | null;
};

export type PromptNode = Node<PromptNodeData, "prompt">;
export type AssetNode = Node<AssetNodeData, "asset">;
export type VideoGenerationNode = Node<VideoGenerationNodeData, "videoGeneration">;

export type WorkbenchNode = PromptNode | AssetNode | VideoGenerationNode;

export type WorkbenchEdge = Edge<{
  inputType?: "prompt" | "image" | "audio" | "reference";
}>;

export type ResolvedGenerationInputs = {
  prompt?: string;
  negativePrompt?: string;
  reference_image_asset_id?: string | null;
  reference_audio_asset_id?: string | null;
};

export type CanvasJobPayload = {
  prompt: string;
  duration_sec: number;
  resolution: "720x1280" | "1280x720" | "1024x1024";
  audio_start_sec: number;
  reference_image_asset_id?: string | null;
  reference_audio_asset_id?: string | null;
  canvas_id: string;
  canvas_node_id: string;
};
