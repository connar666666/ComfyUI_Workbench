import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AssetsPage } from "./AssetsPage";

describe("AssetsPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    window.localStorage?.clear?.();
  });

  it("creates a folder from a dialog with an optional description", async () => {
    let folders = [] as Array<Record<string, unknown>>;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;

      if (url.includes("/api/assets")) {
        return { ok: true, json: async () => [] };
      }

      if (url.endsWith("/api/folders") && init?.method === "POST") {
        const body = JSON.parse(String(init.body));
        folders = [
          {
            id: "folder-1",
            name: body.name,
            description: body.description,
            scope: body.scope,
            parent_id: body.parent_id,
            asset_count: 0,
            created_at: "2026-06-27T10:00:00Z",
          },
        ];
        return { ok: true, json: async () => folders[0] };
      }

      if (url.includes("/api/folders?")) {
        return { ok: true, json: async () => folders };
      }

      throw new Error(`Unhandled fetch: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<AssetsPage />);

    await waitFor(() => {
      expect(screen.getByText("创建第一个文件夹")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "新建文件夹" }));
    expect(screen.getByRole("dialog", { name: "新建文件夹" })).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("文件夹名称"), { target: { value: "角色设定" } });
    fireEvent.change(screen.getByLabelText("文件夹描述"), { target: { value: "用于存放角色立绘和设定图" } });
    fireEvent.click(screen.getByRole("button", { name: "创建文件夹" }));

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "角色设定" })).toBeInTheDocument();
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/folders",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          scope: "assets",
          name: "角色设定",
          description: "用于存放角色立绘和设定图",
          parent_id: null,
          project_id: null,
        }),
      }),
    );
  });
});
