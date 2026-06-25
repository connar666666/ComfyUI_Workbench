import type {
  CanvasJobPayload,
  ResolvedGenerationInputs,
  VideoGenerationNode,
  WorkbenchNode,
} from "../canvasTypes";

type BuildGenerationPayloadInput = {
  canvasId: string;
  node: WorkbenchNode;
  resolvedInputs: ResolvedGenerationInputs;
};

function isVideoGenerationNode(node: WorkbenchNode): node is VideoGenerationNode {
  return node.type === "videoGeneration";
}

export function buildGenerationPayload({
  canvasId,
  node,
  resolvedInputs,
}: BuildGenerationPayloadInput): CanvasJobPayload {
  if (!isVideoGenerationNode(node)) {
    throw new Error("video generation node is required");
  }

  const prompt = (node.data.prompt || resolvedInputs.prompt || "").trim();
  if (!prompt) {
    throw new Error("prompt is required");
  }

  return {
    prompt,
    duration_sec: node.data.duration_sec,
    resolution: node.data.resolution,
    audio_start_sec: node.data.audio_start_sec,
    reference_image_asset_id:
      node.data.reference_image_asset_id ?? resolvedInputs.reference_image_asset_id ?? null,
    reference_audio_asset_id:
      node.data.reference_audio_asset_id ?? resolvedInputs.reference_audio_asset_id ?? null,
    canvas_id: canvasId,
    canvas_node_id: node.id,
  };
}
