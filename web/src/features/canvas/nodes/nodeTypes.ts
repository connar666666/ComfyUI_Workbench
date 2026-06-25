import { AssetNode } from "./AssetNode";
import { PromptNode } from "./PromptNode";
import { VideoGenerationNode } from "./VideoGenerationNode";

export const nodeTypes = {
  prompt: PromptNode,
  asset: AssetNode,
  videoGeneration: VideoGenerationNode,
};
