import { describe, expect, it } from "vitest";
import type { WorkbenchNode } from "../canvasTypes";
import { buildGenerationPayload } from "./buildGenerationPayload";

describe("buildGenerationPayload", () => {
  it("builds a /api/jobs-compatible payload with canvas ids", () => {
    const node: WorkbenchNode = {
      id: "vg-1",
      type: "videoGeneration",
      position: { x: 0, y: 0 },
      data: {
        title: "Generate",
        prompt: "rainy city",
        duration_sec: 5,
        resolution: "720x1280",
        audio_start_sec: 0,
      },
    };

    const payload = buildGenerationPayload({
      canvasId: "default",
      node,
      resolvedInputs: {},
    });

    expect(payload).toMatchObject({
      canvas_id: "default",
      canvas_node_id: "vg-1",
      prompt: "rainy city",
      duration_sec: 5,
      resolution: "720x1280",
      audio_start_sec: 0,
    });
  });

  it("rejects generation payloads without a prompt", () => {
    const node: WorkbenchNode = {
      id: "vg-1",
      type: "videoGeneration",
      position: { x: 0, y: 0 },
      data: {
        title: "Generate",
        duration_sec: 5,
        resolution: "720x1280",
        audio_start_sec: 0,
      },
    };

    expect(() =>
      buildGenerationPayload({
        canvasId: "default",
        node,
        resolvedInputs: {},
      })
    ).toThrow("prompt is required");
  });
});
