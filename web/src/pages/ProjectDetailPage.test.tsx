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
      if (url.endsWith("/api/remote-workflows/wf-portrait")) {
        return {
          ok: true,
          json: async () => ({
            workflow_id: "wf-portrait",
            workflow_template: {
              "12": { class_type: "CLIPTextEncode", inputs: { text: "default prompt" } },
              "20": { class_type: "LoadImage", inputs: { image: "" } },
            },
            api_config: {
              enabledParams: { "12:text": true, "20:image": true },
              formValues: {},
              customLabels: { "12:text": "提示词", "20:image": "参考图" },
            },
          }),
        };
      }
      if (url.endsWith("/api/remote-workflows/wf-new")) {
        return {
          ok: true,
          json: async () => ({
            workflow_id: "wf-new",
            workflow_template: {
              "12": { class_type: "CLIPTextEncode", inputs: { text: "hello" } },
            },
            api_config: {
              enabledParams: { "12:text": true },
              formValues: {},
              customLabels: { "12:text": "提示词" },
            },
          }),
        };
      }
      if (url.endsWith("/api/remote-workflows/uploads") && init?.method === "POST") {
        return {
          ok: true,
          json: async () => ({ name: "uploaded-reference.png" }),
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
        expect(String(init.body)).toContain("cinematic closeup");
        expect(String(init.body)).toContain("uploaded-reference.png");
        return {
          ok: true,
          json: async () => ({ id: 101, status: "running", prompt_id: "prompt-1", saved_asset_ids: [], results: [] }),
        };
      }
      if (url.endsWith("/api/projects/7/remote-runs/101/refresh")) {
        return {
          ok: true,
          json: async () => ({
            id: 101,
            status: "succeeded",
            prompt_id: "prompt-1",
            saved_asset_ids: [11],
            results: [{ type: "image", filename: "result.png", download_url: "https://zealman.example.com/result.png" }],
          }),
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
    await waitFor(() => {
      expect(screen.getByLabelText("提示词")).toBeInTheDocument();
    });

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

    fireEvent.click(screen.getByRole("button", { name: /Portrait wf-portrait/ }));
    await waitFor(() => {
      expect(screen.getByLabelText("提示词")).toBeInTheDocument();
    });
    fireEvent.change(screen.getByLabelText("提示词"), { target: { value: "cinematic closeup" } });
    fireEvent.change(screen.getByLabelText("参考图 上传"), {
      target: { files: [new File(["demo"], "reference.png", { type: "image/png" })] },
    });

    await waitFor(() => {
      expect(screen.getByDisplayValue("uploaded-reference.png")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "运行工作流" }));

    await waitFor(() => {
      expect(screen.getByText("最近运行 succeeded")).toBeInTheDocument();
    });
    expect(screen.getByText("result.png")).toBeInTheDocument();
  });
});
