import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { RemoteWorkflowsPage } from "./RemoteWorkflowsPage";

describe("RemoteWorkflowsPage", () => {
  beforeEach(() => {
    const storage = new Map<string, string>([["workbench_token", "demo-token"]]);
    vi.stubGlobal("localStorage", {
      getItem: (key: string) => storage.get(key) ?? null,
      setItem: (key: string, value: string) => {
        storage.set(key, value);
      },
      removeItem: (key: string) => {
        storage.delete(key);
      },
      clear: () => {
        storage.clear();
      },
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("loads workflows, submits a run, and renders the completed result", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;

      if (url.endsWith("/api/remote-workflows")) {
        return {
          ok: true,
          json: async () => ({
            workflows: [
              {
                id: "wf-portrait",
                name: "Portrait Workflow",
                run_count: 3,
              },
            ],
          }),
        };
      }

      if (url.endsWith("/api/remote-workflows/wf-portrait")) {
        return {
          ok: true,
          json: async () => ({
            workflow_id: "wf-portrait",
            workflow_template: {
              "12": {
                class_type: "CLIPTextEncode",
                inputs: {
                  text: "default prompt",
                },
              },
            },
            api_config: {
              enabledParams: {
                "12:text": true,
              },
              formValues: {},
              customLabels: {
                "12:text": "提示词",
              },
            },
          }),
        };
      }

      if (url.endsWith("/api/remote-workflows/wf-portrait/run")) {
        expect(init?.method).toBe("POST");
        return {
          ok: true,
          json: async () => ({ prompt_id: "prompt-1" }),
        };
      }

      if (url.endsWith("/api/remote-workflows/runs/prompt-1")) {
        return {
          ok: true,
          json: async () => ({
            prompt_id: "prompt-1",
            pending: false,
            results: [
              {
                type: "image",
                filename: "result.png",
                url: "/output/result.png",
                download_url: "https://zealman.example.com/output/result.png",
              },
            ],
          }),
        };
      }

      throw new Error(`Unhandled fetch: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<RemoteWorkflowsPage />);

    await waitFor(() => {
      expect(screen.getByText("Portrait Workflow")).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getByLabelText("提示词")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText("提示词"), { target: { value: "cinematic portrait" } });
    fireEvent.click(screen.getByRole("button", { name: "运行工作流" }));

    await waitFor(() => {
      expect(screen.getByText("prompt-1")).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getByText("result.png")).toBeInTheDocument();
    });
    expect(screen.getByAltText("result.png")).toHaveAttribute(
      "src",
      "https://zealman.example.com/output/result.png"
    );
  });
});
