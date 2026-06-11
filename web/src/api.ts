export type TileSize = "s" | "m" | "w";

export type TileFace = {
  count?: number;
  glyph?: string;
  line?: string;
  meta?: string;
  sub?: string;
};

export type Tile = {
  key: string;
  size: TileSize;
  color: string;
  sort: number;
  front: TileFace;
  back: TileFace;
  updated_at: string | null;
};

export type Todo = {
  id: string;
  title: string;
  notes: string | null;
  status: "open" | "done" | "dropped";
  source: string;
  created_at: string | null;
  completed_at: string | null;
};

export type Note = {
  id: string;
  category_id: string | null;
  title: string;
  body_md: string;
  updated_at: string | null;
};

export type Job = {
  id: string;
  command: string;
  status: "queued" | "running" | "done" | "failed" | "needs_approval";
  page_id: string | null;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
};

export type Page = {
  id: string;
  job_id: string;
  title: string;
  html: string;
  created_at: string | null;
};

export type ApiClient = ReturnType<typeof createApiClient>;

type FetchLike = typeof fetch;

type ClientOptions = {
  baseUrl?: string;
  fetchImpl?: FetchLike;
};

const DEFAULT_BASE_URL = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";

export function getHomeApiToken(): string {
  return localStorage.getItem("HOME_API_TOKEN") || "dev-token";
}

export function createApiClient(options: ClientOptions = {}) {
  const baseUrl = (options.baseUrl || DEFAULT_BASE_URL).replace(/\/$/, "");
  const fetchImpl = options.fetchImpl || fetch;

  async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const headers = {
      accept: "application/json",
      authorization: `Bearer ${getHomeApiToken()}`,
      ...(init.body ? { "content-type": "application/json" } : {}),
      ...(init.headers || {})
    };
    const response = await fetchImpl(`${baseUrl}${path}`, { ...init, headers });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || `request failed: ${response.status}`);
    }
    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      return (await response.json()) as T;
    }
    return (await response.text()) as T;
  }

  return {
    getTiles: () => request<{ tiles: Tile[] }>("/api/tiles"),
    getTodos: () => request<{ todos: Todo[] }>("/api/todos"),
    getNotes: () => request<{ notes: Note[] }>("/api/notes"),
    getJobs: () => request<{ jobs: Job[] }>("/api/jobs"),
    getJob: (jobId: string) => request<{ job: Job }>(`/api/jobs/${jobId}`),
    getJobEvents: (jobId: string) => request<string>(`/api/jobs/${jobId}/events`, { headers: { accept: "text/event-stream" } }),
    getPage: (pageId: string) => request<{ page: Page }>(`/api/pages/${pageId}`),
    sendCommand: (text: string) =>
      request<{ job_id: string }>("/api/command", { method: "POST", body: JSON.stringify({ text }) }),
    runAction: (action: string, payload: Record<string, unknown>) =>
      request<{ ok: boolean; tile?: string }>("/api/actions", {
        method: "POST",
        body: JSON.stringify({ action, payload })
      })
  };
}
