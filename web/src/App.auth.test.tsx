import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

describe("App auth flow", () => {
  beforeEach(() => {
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
    vi.unstubAllGlobals();
  });

  it("keeps the auth form mounted and shows duplicate username errors from the real register flow", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      if (url.endsWith("/api/auth/register")) {
        return {
          ok: false,
          status: 409,
          headers: new Headers({ "Content-Type": "application/json" }),
          json: async () => ({ error: "conflict", message: "Username 'alice' is already taken" }),
          text: async () => JSON.stringify({ error: "conflict", message: "Username 'alice' is already taken" }),
        };
      }

      throw new Error(`Unhandled fetch: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <MemoryRouter initialEntries={["/login"]}>
        <App />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "去注册" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "去注册" }));
    fireEvent.change(screen.getByLabelText("用户名"), { target: { value: "alice" } });
    fireEvent.change(screen.getByLabelText("密码"), { target: { value: "secret123" } });
    fireEvent.click(screen.getByRole("button", { name: "注册并进入" }));

    await waitFor(() => {
      expect(screen.getByText("用户名已存在")).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: "注册并进入" })).toBeInTheDocument();
  });
});
