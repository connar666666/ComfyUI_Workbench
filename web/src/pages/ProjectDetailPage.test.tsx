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
    const projectWorkflows = [
      {
        id: 3,
        workflow_id: "wf-portrait",
        display_name: "Portrait",
        defaults: { "12:prompt": "hello" },
        enabled: true,
      },
    ] as Array<Record<string, unknown>>;

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
        if (init?.method === "POST") {
          projectWorkflows.push({
            id: 5,
            workflow_id: "wf-new",
            display_name: "New Workflow",
            defaults: {},
            enabled: true,
          });
          return {
            ok: true,
            json: async () => projectWorkflows[projectWorkflows.length - 1],
          };
        }
        return {
          ok: true,
          json: async () => projectWorkflows,
        };
      }
      if (url.endsWith("/api/remote-workflows")) {
        return {
          ok: true,
          json: async () => ({
            workflows: [{ id: "wf-new", name: "New Workflow" }],
          }),
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
      if (/\/api\/projects\/7\/workflows\/\d+\/runs$/.test(url) && init?.method === "POST") {
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
    fireEvent.click(screen.getByRole("button", { name: "添加工作流" }));
    await waitFor(() => {
      expect(screen.getByLabelText("选择远程工作流")).toBeInTheDocument();
    });
    fireEvent.change(screen.getByLabelText("选择远程工作流"), { target: { value: "wf-new" } });
    fireEvent.click(screen.getByRole("button", { name: "加入项目" }));

    await waitFor(() => {
      expect(screen.getByText("New Workflow")).toBeInTheDocument();
    });

    fireEvent.click(screen.getAllByRole("button", { name: "运行" })[1]);

    await waitFor(() => {
      expect(screen.getByText("最近运行 succeeded")).toBeInTheDocument();
    });
  });
});
