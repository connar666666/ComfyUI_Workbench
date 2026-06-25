import { describe, expect, it } from "vitest";
import type { WorkbenchEdge, WorkbenchNode } from "../canvasTypes";
import { resolveNodeInputs } from "./resolveNodeInputs";

describe("resolveNodeInputs", () => {
  it("uses connected prompt and asset nodes as generation inputs", () => {
    const nodes: WorkbenchNode[] = [
      {
        id: "prompt-1",
        type: "prompt",
        position: { x: 0, y: 0 },
        data: { title: "Prompt", prompt: "rainy city" },
      },
      {
        id: "image-1",
        type: "asset",
        position: { x: 0, y: 120 },
        data: { title: "Image", assetId: 10, assetKind: "image" },
      },
      {
        id: "audio-1",
        type: "asset",
        position: { x: 0, y: 240 },
        data: { title: "Audio", assetId: 20, assetKind: "audio" },
      },
      {
        id: "vg-1",
        type: "videoGeneration",
        position: { x: 320, y: 0 },
        data: {
          title: "Generate",
          duration_sec: 5,
          resolution: "720x1280",
          audio_start_sec: 0,
        },
      },
    ];
    const edges: WorkbenchEdge[] = [
      { id: "e1", source: "prompt-1", target: "vg-1" },
      { id: "e2", source: "image-1", target: "vg-1" },
      { id: "e3", source: "audio-1", target: "vg-1" },
    ];

    const result = resolveNodeInputs(nodes, edges, "vg-1");

    expect(result.prompt).toBe("rainy city");
    expect(result.reference_image_asset_id).toBe(10);
    expect(result.reference_audio_asset_id).toBe(20);
  });
});
