export type TileSize = "s" | "m" | "w" | "t" | "l";

export type TileFace = {
  count?: number;
  emoji?: string;
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
  external_id: string | null;
  provider: string;
  title: string;
  notes: string | null;
  due_at: string | null;
  scheduled_for: string | null;
  tags: string[];
  priority: number | null;
  status: "open" | "done" | "dropped";
  source: string;
  project_id: string | null;
  project: string | null;
  list: string | null;
  created_at: string | null;
  updated_at: string | null;
  completed_at: string | null;
};

export type TodoProject = {
  id: string;
  title: string;
  hex_color: string;
};

export type TodoLabel = {
  id: string;
  title: string;
  hex_color: string;
};

export type VikunjaStatus = {
  configured: boolean;
  url: string | null;
  default_project_configured: boolean;
  provider: string;
};

export type TodosResponse = {
  todos: Todo[];
  projects: TodoProject[];
  labels: TodoLabel[];
  configured: boolean;
  provider: string;
  status: VikunjaStatus;
  warning: string | null;
};

export type Category = {
  id: string;
  slug: string;
  name: string;
  color: string;
  created_by: "seed" | "agent" | "user" | string;
  created_at: string | null;
};

export type Note = {
  id: string;
  title: string;
  body_md: string;
  category: string;
  tags: string[];
  source_job_id: string | null;
  archived: boolean;
  created_at: string | null;
  updated_at: string | null;
};

export type NotesResponse = {
  notes: Note[];
  configured: boolean;
  warning: string | null;
};

export type Job = {
  id: string;
  command: string;
  status: "queued" | "running" | "done" | "failed" | "needs_approval" | "needs_clarification" | "cancelled";
  page_id: string | null;
  error: string | null;
  stdout_tail: string | null;
  stderr_tail: string | null;
  exit_code: number | null;
  emoji: string | null;
  summary: string | null;
  profile_id: string | null;
  profile: null | {
    id: string;
    name: string;
    emoji: string;
    color: string;
  };
  started_at: string | null;
  finished_at: string | null;
};

export type Clarification = {
  id: string;
  job_id: string;
  question: string;
  choices: string[];
  draft: Record<string, unknown>;
  answer: string | null;
  status: "pending" | "answered" | string;
  follow_up_job_id: string | null;
  created_at: string | null;
  answered_at: string | null;
};

export type Profile = {
  id: string;
  slug: string;
  name: string;
  emoji: string;
  color: string;
  persona: string;
  is_default: boolean;
  created_at: string | null;
  updated_at: string | null;
};

export type Page = {
  id: string;
  job_id: string | null;
  title: string;
  html: string;
  provenance: Record<string, unknown>;
  created_at: string | null;
  pinned_at: string | null;
};

export type Approval = {
  id: string;
  job_id: string | null;
  action: string;
  scope: Record<string, unknown>;
  status: "pending" | "approved" | "rejected" | "expired" | string;
  expires_at: string | null;
  decided_at: string | null;
  result: Record<string, unknown>;
  error: string | null;
};

export type JobEvent = {
  id: string;
  job_id: string;
  ts: string | null;
  kind: "step" | "tool" | "warn" | string;
  text: string;
};

export type ActionMeta = {
  name: string;
  label: string;
  danger: "low" | "medium" | "high" | string;
  requires_confirmation: boolean;
  required_payload: string[];
  refresh: string[];
};

export type ActionRun = {
  id: string;
  idempotency_key: string;
  action: string;
  payload: Record<string, unknown>;
  source_job_id: string | null;
  source_page_id: string | null;
  status: "running" | "done" | "failed" | string;
  result: Record<string, unknown>;
  error: string | null;
  summary: string;
  created_at: string | null;
};

export type ActionRunFilters = {
  action?: string;
  status?: string;
  source_job_id?: string;
  source_page_id?: string;
  limit?: number;
};

export type ConnectorSyncRun = {
  id: string;
  connector: string;
  adapter: string;
  source: string | null;
  status: "running" | "success" | "skipped" | "error" | string;
  imported: number;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
};

export type ConnectorStatus = {
  configured: boolean;
  source: string | null;
  available: boolean;
  adapter: string;
  state: "not_configured" | "local_adapter" | "source_missing" | "provider_connected" | string;
  last_sync: ConnectorSyncRun | null;
};

export type CodexEffort = "low" | "medium" | "high" | "xhigh";

export type CodexRun = {
  id: string;
  prompt: string;
  effort: CodexEffort;
  workdir: string;
  command: string[];
  status: "queued" | "running" | "done" | "failed" | string;
  process_id: number | null;
  cancel_requested: boolean;
  before_status: string | null;
  after_status: string | null;
  diff_stat: string | null;
  stdout_tail: string | null;
  stderr_tail: string | null;
  exit_code: number | null;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
};

export type CodexState = {
  available: boolean;
  enabled: boolean;
  binary_available: boolean;
  workdir: string;
  mode: string;
  effort: CodexEffort;
  effort_options: CodexEffort[];
  requires_confirmation: boolean;
  disabled_reason: string | null;
  dirty: boolean;
  status_short: string;
  diff_stat: string;
};

export type CalendarEvent = {
  id: string;
  calendar_id: string;
  summary: string;
  starts_at: string | null;
  ends_at: string | null;
  status: string;
  source_approval_id: string | null;
  created_at: string | null;
  updated_at: string | null;
};

export type ChannelMessage = {
  id: string;
  channel: string;
  sender: string | null;
  subject: string;
  body: string;
  status: string;
  received_at: string | null;
};

export type SpendItem = {
  id: string;
  merchant: string;
  amount_cents: number;
  currency: string;
  category: string | null;
  spent_at: string | null;
};

export type SessionInfo = {
  ok: boolean;
  agent: {
    configured: boolean;
    state: "listening" | "running" | string;
  };
  database: string;
  mcp: {
    configured: boolean;
  };
  auth: {
    valid: boolean;
  };
  approvals: {
    pending: boolean;
  };
  connectors: Record<string, ConnectorStatus>;
  todos: VikunjaStatus;
};

export type ApiClient = ReturnType<typeof createApiClient>;

type FetchLike = typeof fetch;

type ClientOptions = {
  baseUrl?: string;
  fetchImpl?: FetchLike;
};

const API_TOKEN_KEY = "HOME_API_TOKEN";
const API_BASE_KEY = "HOME_API_BASE";
const ENV_API_BASE = import.meta.env.VITE_API_BASE || "";

export class ApiError extends Error {
  status: number;
  body: string;

  constructor(status: number, body: string) {
    super(body || `request failed: ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

export function getHomeApiToken(): string | null {
  return localStorage.getItem(API_TOKEN_KEY);
}

export function setHomeApiToken(token: string): void {
  const trimmed = token.trim();
  if (trimmed) {
    localStorage.setItem(API_TOKEN_KEY, trimmed);
  } else {
    localStorage.removeItem(API_TOKEN_KEY);
  }
}

export function getHomeApiBase(): string {
  const stored = normalizeApiBase(localStorage.getItem(API_BASE_KEY) || "");
  const env = publicSafeEnvApiBase();
  if (stored && shouldIgnoreApiBaseForCurrentHost(stored)) {
    localStorage.removeItem(API_BASE_KEY);
    return env;
  }
  if (stored) {
    return stored;
  }
  return env;
}

export function setHomeApiBase(baseUrl: string): void {
  const trimmed = normalizeApiBase(baseUrl);
  if (trimmed) {
    localStorage.setItem(API_BASE_KEY, trimmed);
  } else {
    localStorage.removeItem(API_BASE_KEY);
  }
}

export function createApiClient(options: ClientOptions = {}) {
  const baseUrl = normalizeApiBase(options.baseUrl ?? getHomeApiBase());
  const fetchImpl = options.fetchImpl || fetch;
  const includeBearerToken = shouldSendBearerToken(baseUrl);
  const credentials = shouldUseSameOriginCredentials(baseUrl) ? "same-origin" : undefined;

  function apiUrl(path: string): string {
    return resolveApiUrl(baseUrl, path);
  }

  async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const token = includeBearerToken ? getHomeApiToken() : null;
    const headers = {
      accept: "application/json",
      ...(token ? { authorization: `Bearer ${token}` } : {}),
      ...(init.body ? { "content-type": "application/json" } : {}),
      ...(init.headers || {})
    };
    const response = await fetchImpl(apiUrl(path), { ...init, headers, credentials: init.credentials ?? credentials });
    if (!response.ok) {
      const text = await response.text();
      throw new ApiError(response.status, readableError(text, response.status));
    }
    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      return (await response.json()) as T;
    }
    return (await response.text()) as T;
  }

  return {
    baseUrl,
    getSession: () => request<SessionInfo>("/api/session"),
    getCapabilities: () => request<{ actions: ActionMeta[]; tiles: string[]; features: Record<string, unknown> }>("/api/capabilities"),
    getTiles: () => request<{ tiles: Tile[] }>("/api/tiles"),
    getCategories: () => request<{ categories: Category[] }>("/api/categories"),
    getTodos: () => request<TodosResponse>("/api/todos"),
    getNotes: (filters: { q?: string; category?: string } = {}) => request<NotesResponse>(`/api/notes${queryString(filters)}`),
    getNote: (noteId: string) => request<{ note: Note }>(`/api/notes/${noteId}`),
    updateNote: (noteId: string, changes: Partial<Pick<Note, "title" | "body_md" | "category" | "tags" | "archived">>) =>
      request<{ note: Note }>(`/api/notes/${noteId}`, { method: "PATCH", body: JSON.stringify(changes) }),
    archiveNote: (noteId: string) => request<{ note: Note }>(`/api/notes/${noteId}/archive`, { method: "POST" }),
    mergeNote: (noteId: string, targetNoteId: string) =>
      request<{ note: Note; archived_note: Note }>(`/api/notes/${noteId}/merge`, {
        method: "POST",
        body: JSON.stringify({ target_note_id: targetNoteId })
      }),
    getJobs: (limit?: number, profileId?: string) => request<{ jobs: Job[] }>(`/api/jobs${queryString({ limit, profile_id: profileId })}`),
    getJob: (jobId: string) => request<{ job: Job }>(`/api/jobs/${jobId}`),
    getJobTimeline: (jobId: string) =>
      request<{ job: Job; events: JobEvent[]; page: Page | null; approvals: Approval[]; clarifications: Clarification[] }>(`/api/jobs/${jobId}/timeline`),
    getJobDiagnostics: (jobId: string) =>
      request<{
        job: Job;
        events: JobEvent[];
        page: Omit<Page, "html"> & { html_bytes: number } | null;
        approvals: Approval[];
        clarifications: Clarification[];
        environment: Record<string, unknown>;
      }>(`/api/jobs/${jobId}/diagnostics`),
    getJobEvents: (jobId: string) => request<string>(`/api/jobs/${jobId}/events`, { headers: { accept: "text/event-stream" } }),
    streamJobEvents: (jobId: string, onEvent: (event: JobEvent) => void, signal?: AbortSignal) =>
      streamEvents(apiUrl(`/api/jobs/${jobId}/stream`), fetchImpl, onEvent, signal, includeBearerToken, credentials),
    cancelJob: (jobId: string) => request<{ ok: boolean; job_id: string; status: Job["status"] }>(`/api/jobs/${jobId}/cancel`, { method: "POST" }),
    retryJob: (jobId: string) => request<{ job_id: string }>(`/api/jobs/${jobId}/retry`, { method: "POST" }),
    answerClarification: (clarificationId: string, answer: string) =>
      request<{ job_id: string; clarification: Clarification; job: Job | null }>(`/api/clarifications/${clarificationId}/answer`, {
        method: "POST",
        body: JSON.stringify({ answer })
      }),
    getPage: (pageId: string) => request<{ page: Page }>(`/api/pages/${pageId}`),
    getPages: () => request<{ pages: Page[] }>("/api/pages"),
    pinPage: (pageId: string) => request<{ page: Page }>(`/api/pages/${pageId}/pin`, { method: "POST" }),
    unpinPage: (pageId: string) => request<{ page: Page }>(`/api/pages/${pageId}/unpin`, { method: "POST" }),
    getApprovals: () => request<{ approvals: Approval[] }>("/api/approvals"),
    getApproval: (approvalId: string) => request<{ approval: Approval; job: Job | null }>(`/api/approvals/${approvalId}`),
    approveApproval: (approvalId: string) => request<{ ok: boolean; tile?: string; approval_id: string; status: string }>(`/api/approvals/${approvalId}/approve`, { method: "POST" }),
    rejectApproval: (approvalId: string) => request<{ ok: boolean; tile?: string; approval_id: string; status: string }>(`/api/approvals/${approvalId}/reject`, { method: "POST" }),
    getActions: () => request<{ actions: ActionMeta[] }>("/api/actions"),
    getActionRuns: (filters: ActionRunFilters = {}) => request<{ action_runs: ActionRun[] }>(`/api/action-runs${queryString(filters)}`),
    getActionRun: (actionRunId: string) => request<{ action_run: ActionRun }>(`/api/action-runs/${actionRunId}`),
    getConnectors: () => request<{ connectors: Record<string, ConnectorStatus>; history: ConnectorSyncRun[] }>("/api/connectors"),
    syncConnectors: () =>
      request<{ ok: boolean; result: Record<string, ConnectorSyncRun>; connectors: Record<string, ConnectorStatus>; history: ConnectorSyncRun[] }>("/api/connectors/sync", {
        method: "POST"
      }),
    getCalendar: () => request<{ configured: boolean; adapter: string; connector: ConnectorStatus; write_policy: string; events: CalendarEvent[] }>("/api/calendar"),
    getChannels: () => request<{ configured: boolean; connectors: ConnectorStatus[]; messages: ChannelMessage[] }>("/api/channels"),
    getSpend: () => request<{ configured: boolean; connector: ConnectorStatus; currency: string; total_cents: number; items: SpendItem[] }>("/api/spend"),
    getVitals: () => request<{ session: Record<string, unknown>; counts: Record<string, unknown> }>("/api/vitals"),
    getCodexRuns: () => request<{ codex_runs: CodexRun[] }>("/api/codex-runs"),
    getCodexState: () => request<CodexState>("/api/codex"),
    getCodexRun: (runId: string) => request<{ codex_run: CodexRun }>(`/api/codex-runs/${runId}`),
    cancelCodexRun: (runId: string) => request<{ codex_run: CodexRun }>(`/api/codex-runs/${runId}/cancel`, { method: "POST" }),
    createCodexRun: (prompt: string, effort: CodexEffort, confirmDangerousMode = false) =>
      request<{ codex_run: CodexRun }>("/api/codex-runs", {
        method: "POST",
        body: JSON.stringify({ prompt, effort, confirm_dangerous_mode: confirmDangerousMode })
      }),
    getProfiles: () => request<{ profiles: Profile[]; default_id: string | null }>("/api/profiles"),
    createProfile: (profile: Pick<Profile, "name" | "emoji" | "color" | "persona"> & { is_default?: boolean }) =>
      request<{ profile: Profile }>("/api/profiles", { method: "POST", body: JSON.stringify(profile) }),
    updateProfile: (profileId: string, changes: Partial<Pick<Profile, "name" | "emoji" | "color" | "persona" | "is_default">>) =>
      request<{ profile: Profile }>(`/api/profiles/${profileId}`, { method: "PATCH", body: JSON.stringify(changes) }),
    deleteProfile: (profileId: string) => request<{ ok: boolean }>(`/api/profiles/${profileId}`, { method: "DELETE" }),
    sendCommand: (text: string, profileId?: string | null) =>
      request<{ job_id: string }>("/api/command", { method: "POST", body: JSON.stringify({ text, profile_id: profileId || undefined }) }),
    runAction: (action: string, payload: Record<string, unknown>, idempotencyKey = newIdempotencyKey()) =>
      request<{ ok: boolean; tile?: string; status?: string }>("/api/actions", {
        method: "POST",
        body: JSON.stringify({ action, payload, idempotency_key: idempotencyKey })
      })
  };
}

function queryString(filters: Record<string, string | number | undefined>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value === undefined || value === "") {
      continue;
    }
    params.set(key, String(value));
  }
  const text = params.toString();
  return text ? `?${text}` : "";
}

function newIdempotencyKey(): string {
  if ("randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `action-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

async function streamEvents(
  url: string,
  fetchImpl: FetchLike,
  onEvent: (event: JobEvent) => void,
  signal?: AbortSignal,
  includeBearerToken = true,
  credentials?: RequestCredentials
): Promise<void> {
  const token = includeBearerToken ? getHomeApiToken() : null;
  const response = await fetchImpl(url, {
    headers: {
      accept: "text/event-stream",
      ...(token ? { authorization: `Bearer ${token}` } : {})
    },
    credentials,
    signal
  });
  if (!response.ok) {
    const text = await response.text();
    throw new ApiError(response.status, readableError(text, response.status));
  }
  if (!response.body) {
    const text = await response.text();
    for (const event of parseSseEvents(text)) {
      onEvent(event);
    }
    return;
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() || "";
    for (const chunk of chunks) {
      for (const event of parseSseEvents(`${chunk}\n\n`)) {
        onEvent(event);
      }
    }
  }
  buffer += decoder.decode();
  for (const event of parseSseEvents(buffer)) {
    onEvent(event);
  }
}

function parseSseEvents(text: string): JobEvent[] {
  return text
    .split("\n\n")
    .map((chunk) => chunk.split("\n").find((line) => line.startsWith("data: ")))
    .filter((line): line is string => Boolean(line))
    .map((line) => {
      try {
        return JSON.parse(line.slice(6)) as JobEvent;
      } catch {
        return null;
      }
    })
    .filter((event): event is JobEvent => Boolean(event));
}

function resolveApiUrl(baseUrl: string, path: string): string {
  if (baseUrl) {
    return `${baseUrl}${path}`;
  }
  const origin = globalThis.location?.origin;
  if (!origin || origin === "null") {
    return path;
  }
  return new URL(path, origin).toString();
}

function shouldSendBearerToken(baseUrl: string): boolean {
  if (!baseUrl) {
    return false;
  }
  const origin = globalThis.location?.origin;
  if (!origin || origin === "null") {
    return true;
  }
  try {
    return new URL(baseUrl, origin).origin !== origin;
  } catch {
    return true;
  }
}

function shouldUseSameOriginCredentials(baseUrl: string): boolean {
  return !shouldSendBearerToken(baseUrl);
}

function shouldIgnoreApiBaseForCurrentHost(baseUrl: string): boolean {
  if (!baseUrl) {
    return false;
  }
  const hostname = globalThis.location?.hostname;
  const origin = globalThis.location?.origin;
  if (!hostname || !origin || origin === "null" || isLoopbackHost(hostname)) {
    return false;
  }
  try {
    const target = new URL(baseUrl, origin);
    return isLoopbackHost(target.hostname) || target.origin !== origin;
  } catch {
    return false;
  }
}

function publicSafeEnvApiBase(): string {
  const env = normalizeApiBase(ENV_API_BASE);
  if (!env || shouldIgnoreApiBaseForCurrentHost(env)) {
    return "";
  }
  return env;
}

function isLoopbackHost(hostname: string): boolean {
  return hostname === "localhost" || hostname === "0.0.0.0" || hostname === "::1" || hostname === "[::1]" || /^127\./.test(hostname);
}

function normalizeApiBase(baseUrl: string): string {
  return baseUrl.trim().replace(/\/+$/, "");
}

function readableError(text: string, status: number): string {
  if (!text) {
    return `request failed: ${status}`;
  }
  try {
    const payload = JSON.parse(text) as { detail?: unknown };
    if (typeof payload.detail === "string") {
      return payload.detail;
    }
    if (Array.isArray(payload.detail)) {
      const validation = payload.detail
        .map((item) => {
          if (!item || typeof item !== "object") {
            return "";
          }
          const detail = item as { loc?: unknown; msg?: unknown };
          const loc = Array.isArray(detail.loc) ? detail.loc.join(".") : "";
          const msg = typeof detail.msg === "string" ? detail.msg : "";
          return [loc, msg].filter(Boolean).join(": ");
        })
        .filter(Boolean)
        .join("; ");
      if (validation) {
        return validation;
      }
    }
  } catch {
    const plain = textFromHtml(text);
    if ([502, 503, 504].includes(status)) {
      return `api gateway error (${status})${plain ? `: ${plain}` : ""}`;
    }
    return plain || text;
  }
  return textFromHtml(text) || text;
}

function textFromHtml(text: string): string {
  const title = text.match(/<title[^>]*>([\s\S]*?)<\/title>/i)?.[1];
  const source = title || text;
  return source
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 220);
}
