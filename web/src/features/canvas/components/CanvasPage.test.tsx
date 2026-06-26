import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CanvasPage } from "./CanvasPage";

vi.mock("./CanvasRoom", () => ({
  CanvasRoom: ({ children }: { children: React.ReactNode }) => <div data-testid="canvas-room">{children}</div>,
}));

vi.mock("./CollaborativeCanvas", () => ({
  CollaborativeCanvas: ({ canvasId }: { canvasId: string }) => <div>Collaborative canvas: {canvasId}</div>,
}));

vi.mock("./LocalCanvas", () => ({
  LocalCanvas: ({ canvasId }: { canvasId: string }) => <div>Local canvas: {canvasId}</div>,
}));

vi.mock("../../../api/client", async () => {
  return {
    getAuthToken: () => "test-token",
    readApiError: async (response: Response, fallbackMessage: string) => {
      const payload = await response.json().catch(() => null);
      const message =
        payload && typeof payload === "object" && "message" in payload && typeof payload.message === "string"
          ? payload.message
          : fallbackMessage;
      return new Error(message);
    },
  };
});

describe("CanvasPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("falls back to local canvas when collaboration auth is unavailable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 400,
        headers: new Headers({ "Content-Type": "application/json" }),
        json: async () => ({ message: "LIVEBLOCKS_SECRET_KEY is not configured" }),
        text: async () => JSON.stringify({ message: "LIVEBLOCKS_SECRET_KEY is not configured" }),
      })
    );

    render(<CanvasPage />);

    await waitFor(() => {
      expect(screen.getByText("Local canvas: default")).toBeInTheDocument();
    });
    expect(screen.getByText(/LIVEBLOCKS_SECRET_KEY is not configured/)).toBeInTheDocument();
  });

  it("uses collaborative mode when auth preflight succeeds", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ "Content-Type": "application/json" }),
        json: async () => ({ token: "liveblocks-token" }),
        text: async () => JSON.stringify({ token: "liveblocks-token" }),
      })
    );

    render(<CanvasPage />);

    await waitFor(() => {
      expect(screen.getByText("Collaborative canvas: default")).toBeInTheDocument();
    });
  });
});
