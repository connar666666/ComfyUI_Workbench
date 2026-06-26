import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
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
    expect(screen.getByText("owner")).toBeInTheDocument();
    expect(screen.getByText("3 members")).toBeInTheDocument();
  });
});
