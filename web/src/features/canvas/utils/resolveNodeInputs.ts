import type {
  AssetNode,
  PromptNode,
  ResolvedGenerationInputs,
  WorkbenchEdge,
  WorkbenchNode,
} from "../canvasTypes";

function isPromptNode(node: WorkbenchNode): node is PromptNode {
  return node.type === "prompt";
}

function isAssetNode(node: WorkbenchNode): node is AssetNode {
  return node.type === "asset";
}

export function resolveNodeInputs(
  nodes: WorkbenchNode[],
  edges: WorkbenchEdge[],
  targetNodeId: string
): ResolvedGenerationInputs {
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const incomingNodes = edges
    .filter((edge) => edge.target === targetNodeId)
    .map((edge) => byId.get(edge.source))
    .filter((node): node is WorkbenchNode => Boolean(node));

  const promptNode = incomingNodes.find(isPromptNode);
  const imageAssetNode = incomingNodes.find(
    (node): node is AssetNode => isAssetNode(node) && node.data.assetKind === "image"
  );
  const audioAssetNode = incomingNodes.find(
    (node): node is AssetNode => isAssetNode(node) && node.data.assetKind === "audio"
  );

  return {
    prompt: promptNode?.data.prompt,
    negativePrompt: promptNode?.data.negativePrompt,
    reference_image_asset_id: imageAssetNode?.data.assetId ?? null,
    reference_audio_asset_id: audioAssetNode?.data.assetId ?? null,
  };
}
