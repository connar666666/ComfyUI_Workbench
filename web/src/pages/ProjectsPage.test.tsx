import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ProjectsPage } from "./ProjectsPage";

describe("ProjectsPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("renders visible projects with the current user's project role", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
        if (url.endsWith("/api/projects")) {
          return {
            ok: true,
            json: async () => [
              {
                id: 7,
                name: "Campaign",
                description: "Launch work",
                current_user_role: "owner",
                member_count: 3,
                updated_at: "2026-06-26T10:00:00Z",
              },
            ],
          };
        }
        throw new Error(`Unhandled fetch: ${url}`);
      })
    );

    render(
      <MemoryRouter>
        <ProjectsPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText("Campaign")).toBeInTheDocument();
    });
    expect(screen.getByText("Launch work")).toBeInTheDocument();
    expect(screen.getByText("OWNER")).toBeInTheDocument();
    expect(screen.getByText("3 成员")).toBeInTheDocument();
  });

  it("creates a project from the project list", async () => {
    let projects = [] as Array<Record<string, unknown>>;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (url.endsWith("/api/projects") && init?.method === "POST") {
        const body = JSON.parse(String(init.body));
        projects = [
          {
            id: 8,
            name: body.name,
            description: body.description,
            current_user_role: "owner",
            member_count: 1,
            updated_at: "2026-06-26T11:00:00Z",
          },
        ];
        return { ok: true, json: async () => projects[0] };
      }
      if (url.endsWith("/api/projects")) {
        return { ok: true, json: async () => projects };
      }
      throw new Error(`Unhandled fetch: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter>
        <ProjectsPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText(/暂无项目/)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "创建新项目" }));
    expect(screen.getByRole("dialog", { name: "创建新项目" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("项目名称"), { target: { value: "New Film" } });
    fireEvent.change(screen.getByLabelText("项目描述"), { target: { value: "Storyboard exploration" } });
    fireEvent.click(screen.getByRole("button", { name: "创建项目" }));

    await waitFor(() => {
      expect(screen.getByText("New Film")).toBeInTheDocument();
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ name: "New Film", description: "Storyboard exploration", members: [] }),
      })
    );
  });

  it("opens a project from the list row actions", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
        if (url.endsWith("/api/projects")) {
          return {
            ok: true,
            json: async () => [
              {
                id: 7,
                name: "Campaign",
                description: "Launch work",
                current_user_role: "owner",
                member_count: 3,
                updated_at: "2026-06-26T10:00:00Z",
              },
            ],
          };
        }
        throw new Error(`Unhandled fetch: ${url}`);
      })
    );

    render(
      <MemoryRouter initialEntries={["/projects"]}>
        <Routes>
          <Route path="/projects" element={<ProjectsPage />} />
          <Route path="/projects/:projectId" element={<div>project detail page</div>} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText("Campaign")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "打开项目 Campaign" }));

    await waitFor(() => {
      expect(screen.getByText("project detail page")).toBeInTheDocument();
    });
  });
});
