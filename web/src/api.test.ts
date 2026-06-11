import { describe, expect, it, vi } from "vitest";

import { createApiClient, getHomeApiToken } from "./api";

describe("api client", () => {
  it("uses localStorage token when building authenticated requests", async () => {
    localStorage.setItem("HOME_API_TOKEN", "test-token");
    const fetchImpl = vi.fn(async () => {
      return new Response(JSON.stringify({ tiles: [] }), {
        headers: { "content-type": "application/json" }
      });
    });
    const client = createApiClient({ baseUrl: "http://home.test", fetchImpl });

    await client.getTiles();

    expect(getHomeApiToken()).toBe("test-token");
    expect(fetchImpl).toHaveBeenCalledWith(
      "http://home.test/api/tiles",
      expect.objectContaining({
        headers: expect.objectContaining({
          accept: "application/json",
          authorization: "Bearer test-token"
        })
      })
    );
  });

  it("falls back to dev-token when localStorage has no token", async () => {
    localStorage.removeItem("HOME_API_TOKEN");
    const fetchImpl = vi.fn(async () => {
      return new Response(JSON.stringify({ todos: [] }), {
        headers: { "content-type": "application/json" }
      });
    });
    const client = createApiClient({ baseUrl: "http://home.test/", fetchImpl });

    await client.getTodos();

    expect(fetchImpl).toHaveBeenCalledWith(
      "http://home.test/api/todos",
      expect.objectContaining({
        headers: expect.objectContaining({
          authorization: "Bearer dev-token"
        })
      })
    );
  });
});
