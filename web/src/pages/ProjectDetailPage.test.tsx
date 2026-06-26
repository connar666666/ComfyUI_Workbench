import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ProjectDetailPage } from "./ProjectDetailPage";

describe("ProjectDetailPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("renders project workflows, assets, history, and can run a workflow", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;

      if (url.endsWith("/api/projects/7")) {
        return {
          ok: true,
          json: async () => ({
            id: 7,
            name: "Campaign",
            description: "Launch work",
            current_user_role: "editor",
            members: [],
          }),
        };
      }
      if (url.endsWith("/api/projects/7/workflows")) {
        return {
          ok: true,
          json: async () => [
            {
              id: 3,
              workflow_id: "wf-portrait",
              display_name: "Portrait",
              defaults: { "12:prompt": "hello" },
              enabled: true,
            },
          ],
        };
      }
      if (url.endsWith("/api/projects/7/assets")) {
        return {
          ok: true,
          json: async () => [
            { id: 11, kind: "image", original_filename: "shot.png", size_bytes: 4, mime_type: "image/png", created_at: "2026-06-26T10:00:00Z" },
          ],
        };
      }
      if (url.endsWith("/api/projects/7/history")) {
        return {
          ok: true,
          json: async () => [
            { id: 99, type: "remote_workflow", status: "succeeded", title: "Portrait", created_at: "2026-06-26T10:00:00Z", result_asset_ids: [11] },
          ],
        };
      }
      if (url.endsWith("/api/projects/7/workflows/3/runs") && init?.method === "POST") {
        return {
          ok: true,
          json: async () => ({ id: 101, status: "running", prompt_id: "prompt-1", saved_asset_ids: [] }),
        };
      }
      if (url.endsWith("/api/projects/7/remote-runs/101/refresh")) {
        return {
          ok: true,
          json: async () => ({ id: 101, status: "succeeded", prompt_id: "prompt-1", saved_asset_ids: [11] }),
        };
      }

      throw new Error(`Unhandled fetch: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter initialEntries={["/projects/7"]}>
        <Routes>
          <Route path="/projects/:projectId" element={<ProjectDetailPage />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Campaign" })).toBeInTheDocument();
    });
    expect(screen.getByText("Portrait")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "素材" }));
    expect(screen.getByText("shot.png")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "历史" }));
    expect(screen.getByText("remote_workflow")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "工作流" }));

    fireEvent.click(screen.getByRole("button", { name: "运行" }));

    await waitFor(() => {
      expect(screen.getByText("最近运行 succeeded")).toBeInTheDocument();
    });
  });
});
