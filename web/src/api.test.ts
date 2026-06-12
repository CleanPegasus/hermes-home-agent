import { beforeEach, describe, expect, it, vi } from "vitest";

import { createApiClient, getHomeApiBase, getHomeApiToken, setHomeApiBase } from "./api";

const sessionInfo = {
  ok: true,
  agent: { configured: false, state: "listening" },
  database: "sqlite",
  mcp: { configured: true },
  auth: { valid: true },
  approvals: { pending: false },
  connectors: {}
};

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    headers: { "content-type": "application/json" }
  });
}

describe("api client", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("uses localStorage token when building authenticated requests", async () => {
    localStorage.setItem("HOME_API_TOKEN", "test-token");
    const fetchImpl = vi.fn(async () => {
      return jsonResponse({ tiles: [] });
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

  it("does not send a bearer token when localStorage has no token", async () => {
    const fetchImpl = vi.fn(async () => {
      return jsonResponse({ todos: [] });
    });
    const client = createApiClient({ baseUrl: "http://home.test/", fetchImpl });

    await client.getTodos();

    expect(getHomeApiToken()).toBeNull();
    expect(fetchImpl).toHaveBeenCalledWith(
      "http://home.test/api/todos",
      expect.objectContaining({
        headers: expect.not.objectContaining({
          authorization: expect.any(String)
        })
      })
    );
  });

  it("uses same-origin paths by default without leaking a stored bearer token", async () => {
    localStorage.setItem("HOME_API_TOKEN", "stale-token-from-setup");
    const fetchImpl = vi.fn(async () => {
      return jsonResponse({ tiles: [] });
    });
    const client = createApiClient({ fetchImpl });

    await client.getTiles();

    expect(fetchImpl).toHaveBeenCalledWith(
      `${window.location.origin}/api/tiles`,
      expect.objectContaining({
        credentials: "same-origin",
        headers: expect.not.objectContaining({
          authorization: expect.any(String)
        })
      })
    );
  });

  it("uses the stored API base when no explicit base is passed", async () => {
    setHomeApiBase("http://127.0.0.1:8000/");
    const fetchImpl = vi.fn(async () => {
      return jsonResponse(sessionInfo);
    });
    const client = createApiClient({ fetchImpl });

    await client.getSession();

    expect(getHomeApiBase()).toBe("http://127.0.0.1:8000");
    expect(fetchImpl).toHaveBeenCalledWith("http://127.0.0.1:8000/api/session", expect.any(Object));
  });

  it("uses same-origin Basic Auth behavior on a public host with stale localStorage", async () => {
    vi.stubGlobal("location", { origin: "http://187.127.175.14", hostname: "187.127.175.14" });
    localStorage.setItem("HOME_API_TOKEN", "stale-token-from-setup");
    setHomeApiBase("http://127.0.0.1:8001/");
    const fetchImpl = vi.fn(async () => {
      return jsonResponse(sessionInfo);
    });
    const client = createApiClient({ fetchImpl });

    await client.getSession();

    expect(getHomeApiBase()).toBe("");
    expect(fetchImpl).toHaveBeenCalledWith(
      "http://187.127.175.14/api/session",
      expect.objectContaining({
        credentials: "same-origin",
        headers: expect.not.objectContaining({
          authorization: expect.any(String)
        })
      })
    );
  });

  it("drops a stored non-same-origin API base on a public same-origin deployment", async () => {
    vi.stubGlobal("location", { origin: "http://203.0.113.10", hostname: "203.0.113.10" });
    localStorage.setItem("HOME_API_TOKEN", "stale-token-from-setup");
    setHomeApiBase("https://vps-server.tail4754d5.ts.net");
    const fetchImpl = vi.fn(async () => {
      return jsonResponse(sessionInfo);
    });
    const client = createApiClient({ fetchImpl });

    await client.getSession();

    expect(getHomeApiBase()).toBe("");
    expect(fetchImpl).toHaveBeenCalledWith(
      "http://203.0.113.10/api/session",
      expect.objectContaining({
        credentials: "same-origin",
        headers: expect.not.objectContaining({
          authorization: expect.any(String)
        })
      })
    );
  });

  it("ignores a loopback VITE_API_BASE baked into a public build", async () => {
    vi.resetModules();
    vi.stubEnv("VITE_API_BASE", "http://127.0.0.1:8001");
    vi.stubGlobal("location", { origin: "http://187.127.175.14", hostname: "187.127.175.14" });
    localStorage.setItem("HOME_API_TOKEN", "stale-token-from-setup");
    const apiModule = await import("./api");
    const fetchImpl = vi.fn(async () => {
      return jsonResponse(sessionInfo);
    });
    const client = apiModule.createApiClient({ fetchImpl });

    await client.getSession();

    expect(apiModule.getHomeApiBase()).toBe("");
    expect(fetchImpl).toHaveBeenCalledWith(
      "http://187.127.175.14/api/session",
      expect.objectContaining({
        credentials: "same-origin",
        headers: expect.not.objectContaining({
          authorization: expect.any(String)
        })
      })
    );
  });

  it("ignores a non-same-origin VITE_API_BASE baked into a public same-origin build", async () => {
    vi.resetModules();
    vi.stubEnv("VITE_API_BASE", "https://vps-server.tail4754d5.ts.net");
    vi.stubGlobal("location", { origin: "http://203.0.113.10", hostname: "203.0.113.10" });
    localStorage.setItem("HOME_API_TOKEN", "stale-token-from-setup");
    const apiModule = await import("./api");
    const fetchImpl = vi.fn(async () => {
      return jsonResponse(sessionInfo);
    });
    const client = apiModule.createApiClient({ fetchImpl });

    await client.getSession();

    expect(apiModule.getHomeApiBase()).toBe("");
    expect(fetchImpl).toHaveBeenCalledWith(
      "http://203.0.113.10/api/session",
      expect.objectContaining({
        credentials: "same-origin",
        headers: expect.not.objectContaining({
          authorization: expect.any(String)
        })
      })
    );
  });

  it("uses same-origin credentials for public job streams without a bearer header", async () => {
    vi.stubGlobal("location", { origin: "http://187.127.175.14", hostname: "187.127.175.14" });
    localStorage.setItem("HOME_API_TOKEN", "stale-token-from-setup");
    const fetchImpl = vi.fn(async () => {
      return new Response('data: {"id":"event-1","job_id":"job-1","ts":null,"kind":"step","text":"started"}\n\n', {
        headers: { "content-type": "text/event-stream" }
      });
    });
    const events: unknown[] = [];
    const client = createApiClient({ fetchImpl });

    await client.streamJobEvents("job-1", (event) => events.push(event));

    expect(events).toHaveLength(1);
    expect(fetchImpl).toHaveBeenCalledWith(
      "http://187.127.175.14/api/jobs/job-1/stream",
      expect.objectContaining({
        credentials: "same-origin",
        headers: expect.not.objectContaining({
          authorization: expect.any(String)
        })
      })
    );
  });

  it("surfaces nginx gateway errors without raw html", async () => {
    const fetchImpl = vi.fn(async () => {
      return new Response("<html><head><title>504 Gateway Time-out</title></head><body>nginx</body></html>", {
        status: 504,
        headers: { "content-type": "text/html" }
      });
    });
    const client = createApiClient({ fetchImpl });

    await expect(client.sendCommand("add test todo")).rejects.toMatchObject({
      status: 504,
      message: "api gateway error (504): 504 Gateway Time-out"
    });
  });

  it("sends codex chat prompts with a constrained effort value", async () => {
    const fetchImpl = vi.fn(async () => {
      return jsonResponse({ codex_run: { id: "run-1" } });
    });
    const client = createApiClient({ baseUrl: "http://home.test", fetchImpl });

    await client.createCodexRun("wire the settings tile", "high", true);

    expect(fetchImpl).toHaveBeenCalledWith(
      "http://home.test/api/codex-runs",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ prompt: "wire the settings tile", effort: "high", confirm_dangerous_mode: true })
      })
    );
  });
});
