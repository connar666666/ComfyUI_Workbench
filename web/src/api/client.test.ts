import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

describe("auth API errors", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.unstubAllGlobals();
    const storage = new Map<string, string>();
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
  });

  it("surfaces backend login error messages", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 403,
      headers: new Headers({ "Content-Type": "application/json" }),
      json: async () => ({ message: "Invalid username or password" }),
      text: async () => JSON.stringify({ message: "Invalid username or password" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const client = await import("./client");

    await expect(client.login("alice", "wrong-password")).rejects.toThrow("Invalid username or password");
  });

  it("falls back to a helpful register conflict message", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 409,
      headers: new Headers({ "Content-Type": "text/plain" }),
      json: async () => {
        throw new Error("not json");
      },
      text: async () => "",
    });
    vi.stubGlobal("fetch", fetchMock);

    const client = await import("./client");

    await expect(client.register("alice", "secret")).rejects.toThrow("Username is already taken");
  });

  it("lists remote workflows through the authenticated API client", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        workflows: [{ id: "wf-1", name: "Portrait Workflow", run_count: 2 }],
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const client = await import("./client");
    client.setAuthToken("demo-token");

    await expect(client.listRemoteWorkflows()).resolves.toEqual([
      { id: "wf-1", name: "Portrait Workflow", run_count: 2 },
    ]);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/remote-workflows",
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer demo-token",
        }),
      })
    );
  });

  it("uploads a file for a remote workflow field", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        name: "uploaded.png",
        type: "input",
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const client = await import("./client");
    client.setAuthToken("demo-token");

    const file = new File(["hello"], "uploaded.png", { type: "image/png" });
    await expect(client.uploadRemoteWorkflowFile(file)).resolves.toEqual({
      name: "uploaded.png",
      type: "input",
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/remote-workflows/uploads",
      expect.objectContaining({
        method: "POST",
      })
    );
  });

  it("uses UUID project ids in project-scoped URLs", async () => {
    const projectId = "0765e635-f4c0-4176-a292-1bed4837c0ab";
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ id: projectId, name: "Campaign" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const client = await import("./client");
    await client.getProject(projectId);

    expect(fetchMock).toHaveBeenCalledWith(
      `/api/projects/${projectId}`,
      expect.any(Object)
    );
  });

  it("passes project ids to folder and project asset APIs", async () => {
    const projectId = "0765e635-f4c0-4176-a292-1bed4837c0ab";
    const folderId = "9feb0927-8652-4a92-a51e-ca403f3b900f";
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [],
    });
    vi.stubGlobal("fetch", fetchMock);

    const client = await import("./client");
    await client.listAssetFolders("assets", null, projectId);
    await client.listProjectAssets(projectId, undefined, folderId);
    await client.createAssetFolder("References", "assets", null, projectId, "Shot references");

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      `/api/folders?scope=assets&project_id=${projectId}`,
      expect.any(Object)
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      `/api/projects/${projectId}/assets?folder_id=${folderId}`,
      expect.any(Object)
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "/api/folders",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          scope: "assets",
          name: "References",
          description: "Shot references",
          parent_id: null,
          project_id: projectId,
        }),
      })
    );
  });

  it("deletes assets through the authenticated API client", async () => {
    const assetId = "938f13b9-03ca-4129-897c-4452254932a6";
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const client = await import("./client");
    await client.deleteAsset(assetId);

    expect(fetchMock).toHaveBeenCalledWith(
      `/api/assets/${assetId}`,
      expect.objectContaining({ method: "DELETE" })
    );
  });
});
