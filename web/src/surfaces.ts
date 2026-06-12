import type { ActionRun, ActionRunFilters, CalendarEvent, ChannelMessage, ConnectorStatus, SpendItem } from "./api";
import { factsList, shortDate } from "./ui";

type SyncActions = {
  sync?: () => void;
};

export function renderCalendarSurface(
  data: { configured: boolean; adapter: string; connector: ConnectorStatus; write_policy: string; events: CalendarEvent[] },
  actions: SyncActions = {}
): HTMLElement {
  const root = document.createElement("section");
  root.className = "list-screen detail-screen";
  root.innerHTML = '<p class="eyebrow">approval gated</p><h1>calendar</h1>';
  const facts = factsList([
    ["adapter", data.adapter],
    ["writes", data.write_policy],
    ...connectorFacts(data.connector),
    ["events", String(data.events.length)]
  ]);
  root.append(actionBar(actions), facts, list("events", data.events, (event) => [event.summary, `${event.status}${event.starts_at ? ` · ${formatDate(event.starts_at)}` : ""}`]));
  return root;
}

export function renderChannelsSurface(data: { configured: boolean; connectors: ConnectorStatus[]; messages: ChannelMessage[] }, actions: SyncActions = {}): HTMLElement {
  const root = document.createElement("section");
  root.className = "list-screen detail-screen";
  root.innerHTML = '<p class="eyebrow">inbound</p><h1>channels</h1>';
  const connector = data.connectors[0] || nullConnector("channels");
  root.append(
    actionBar(actions),
    factsList([
      ["configured", data.configured ? "yes" : "no"],
      ...connectorFacts(connector),
      ["messages", String(data.messages.length)]
    ]),
    list("messages", data.messages, (message) => [message.subject, `${message.channel}${message.sender ? ` · ${message.sender}` : ""}`])
  );
  return root;
}

export function renderSpendSurface(
  data: { configured: boolean; connector: ConnectorStatus; currency: string; total_cents: number; items: SpendItem[] },
  actions: SyncActions = {}
): HTMLElement {
  const root = document.createElement("section");
  root.className = "list-screen detail-screen";
  root.innerHTML = '<p class="eyebrow">ledger</p><h1>spend</h1>';
  root.append(
    actionBar(actions),
    factsList([
      ["configured", data.configured ? "yes" : "no"],
      ...connectorFacts(data.connector),
      ["total", money(data.total_cents, data.currency)],
      ["items", String(data.items.length)]
    ]),
    list("items", data.items, (item) => [item.merchant, `${money(item.amount_cents, item.currency)}${item.category ? ` · ${item.category}` : ""}`])
  );
  return root;
}

export function renderVitalsSurface(
  data: { session: Record<string, unknown>; counts: Record<string, unknown> },
  actionRuns: ActionRun[],
  openActionRun?: (actionRunId: string) => void,
  auditFilters: ActionRunFilters = {},
  onAuditFilter?: (filters: ActionRunFilters) => void
): HTMLElement {
  const root = document.createElement("section");
  root.className = "list-screen detail-screen";
  root.innerHTML = '<p class="eyebrow">system</p><h1>vitals</h1>';
  const sessionFacts = Object.entries(data.session).map(([key, value]) => [key, String(value)] as [string, string]);
  const countFacts = Object.entries(data.counts).map(([key, value]) => [key, typeof value === "object" ? JSON.stringify(value) : String(value)] as [string, string]);
  root.append(factsList([...sessionFacts, ...countFacts]), renderAuditFilters(auditFilters, onAuditFilter), renderActionRuns(actionRuns, openActionRun));
  return root;
}

export function renderActionRuns(actionRuns: ActionRun[], openActionRun?: (actionRunId: string) => void): HTMLElement {
  return list(
    "action audit",
    actionRuns,
    (run) => [run.action, `${run.summary || run.status}${run.created_at ? ` · ${formatDate(run.created_at)}` : ""}`],
    openActionRun ? (run) => openActionRun(run.id) : undefined
  );
}

export function renderActionRunDetail(
  actionRun: ActionRun,
  actions: { openJob?: (jobId: string) => void; openPage?: (pageId: string) => void }
): HTMLElement {
  const root = document.createElement("section");
  root.className = "list-screen detail-screen";
  root.innerHTML = '<p class="eyebrow">action audit</p><h1>run</h1>';
  root.append(
    factsList([
      ["action", actionRun.action],
      ["status", actionRun.status],
      ["summary", actionRun.summary || actionRun.status],
      ["created", actionRun.created_at || "unknown"],
      ["key", actionRun.idempotency_key]
    ])
  );
  const buttons = document.createElement("div");
  buttons.className = "page-actions";
  if (actionRun.source_job_id && actions.openJob) {
    const job = document.createElement("button");
    job.type = "button";
    job.className = "page-action secondary";
    job.textContent = "source job";
    job.addEventListener("click", () => actions.openJob?.(actionRun.source_job_id!));
    buttons.append(job);
  }
  if (actionRun.source_page_id && actions.openPage) {
    const page = document.createElement("button");
    page.type = "button";
    page.className = "page-action secondary";
    page.textContent = "source page";
    page.addEventListener("click", () => actions.openPage?.(actionRun.source_page_id!));
    buttons.append(page);
  }
  const body = JSON.stringify({ action_run: actionRun }, null, 2);
  const copy = document.createElement("button");
  copy.type = "button";
  copy.className = "page-action";
  copy.textContent = "copy json";
  copy.addEventListener("click", async () => {
    await navigator.clipboard?.writeText(body);
  });
  const download = document.createElement("button");
  download.type = "button";
  download.className = "page-action secondary";
  download.textContent = "download json";
  download.addEventListener("click", () => downloadJson(`action-run-${actionRun.id}.json`, body));
  buttons.append(copy, download);
  const payload = document.createElement("pre");
  payload.className = "scope-preview diagnostic-json";
  payload.textContent = body;
  root.append(buttons, payload);
  return root;
}

export function renderDiagnosticsBundle(bundle: Record<string, unknown>): HTMLElement {
  const root = document.createElement("section");
  root.className = "list-screen detail-screen";
  root.innerHTML = '<p class="eyebrow">diagnostics</p><h1>bundle</h1>';
  const pre = document.createElement("pre");
  pre.className = "scope-preview diagnostic-json";
  pre.textContent = JSON.stringify(bundle, null, 2);
  const copy = document.createElement("button");
  copy.type = "button";
  copy.className = "page-action";
  copy.textContent = "copy";
  copy.addEventListener("click", async () => {
    await navigator.clipboard?.writeText(pre.textContent || "");
  });
  root.append(copy, pre);
  return root;
}

function actionBar(actions: SyncActions): HTMLElement {
  const root = document.createElement("div");
  root.className = "page-actions";
  if (actions.sync) {
    const sync = document.createElement("button");
    sync.type = "button";
    sync.className = "page-action secondary";
    sync.textContent = "sync";
    sync.addEventListener("click", () => actions.sync?.());
    root.append(sync);
  }
  return root;
}

function connectorFacts(connector: ConnectorStatus): Array<[string, string]> {
  const last = connector.last_sync;
  return [
    ["connector", connector.state],
    ["source", connector.source || "not configured"],
    ["available", connector.available ? "yes" : "no"],
    ["last sync", last ? `${last.status}${last.finished_at ? ` · ${shortDate(last.finished_at)}` : ""}` : "never"],
    ["last imported", last ? String(last.imported) : "0"],
    ["last error", last?.error || "none"]
  ];
}

function nullConnector(name: string): ConnectorStatus {
  return {
    configured: false,
    source: null,
    available: false,
    adapter: "json_file",
    state: "not_configured",
    last_sync: {
      id: `${name}-none`,
      connector: name,
      adapter: "json_file",
      source: null,
      status: "skipped",
      imported: 0,
      error: "connector is not configured",
      started_at: null,
      finished_at: null
    }
  };
}

function renderAuditFilters(filters: ActionRunFilters, onFilter?: (filters: ActionRunFilters) => void): HTMLElement {
  const form = document.createElement("form");
  form.className = "audit-filter-form";
  form.innerHTML = `
    <label>action<input name="action" autocomplete="off"></label>
    <label>status<select name="status"><option value="">any</option><option value="done">done</option><option value="failed">failed</option><option value="running">running</option></select></label>
    <label>job<input name="source_job_id" autocomplete="off"></label>
    <label>page<input name="source_page_id" autocomplete="off"></label>
    <button type="submit">filter</button>
    <button type="button" data-clear>clear</button>
  `;
  (form.elements.namedItem("action") as HTMLInputElement).value = filters.action || "";
  (form.elements.namedItem("status") as HTMLSelectElement).value = filters.status || "";
  (form.elements.namedItem("source_job_id") as HTMLInputElement).value = filters.source_job_id || "";
  (form.elements.namedItem("source_page_id") as HTMLInputElement).value = filters.source_page_id || "";
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    onFilter?.({
      action: (form.elements.namedItem("action") as HTMLInputElement).value.trim() || undefined,
      status: (form.elements.namedItem("status") as HTMLSelectElement).value || undefined,
      source_job_id: (form.elements.namedItem("source_job_id") as HTMLInputElement).value.trim() || undefined,
      source_page_id: (form.elements.namedItem("source_page_id") as HTMLInputElement).value.trim() || undefined
    });
  });
  form.querySelector("[data-clear]")?.addEventListener("click", () => onFilter?.({}));
  return form;
}

function list<T>(heading: string, items: T[], describe: (item: T) => [string, string], open?: (item: T) => void): HTMLElement {
  const root = document.createElement("section");
  root.className = "surface-list";
  const title = document.createElement("h2");
  title.textContent = heading;
  const rows = document.createElement("div");
  rows.className = "metro-list compact-list";
  if (items.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "nothing here yet.";
    rows.append(empty);
  }
  for (const item of items) {
    const [primary, secondary] = describe(item);
    const row = document.createElement(open ? "button" : "div");
    row.className = "list-row";
    if (row instanceof HTMLButtonElement && open) {
      row.type = "button";
      row.addEventListener("click", () => open(item));
    }
    row.innerHTML = "<span></span><small></small>";
    row.querySelector("span")!.textContent = primary;
    row.querySelector("small")!.textContent = secondary;
    rows.append(row);
  }
  root.append(title, rows);
  return root;
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }).toLowerCase();
}

function money(cents: number, currency: string): string {
  return new Intl.NumberFormat([], { style: "currency", currency }).format(cents / 100);
}

function downloadJson(filename: string, body: string): void {
  const url = URL.createObjectURL(new Blob([body], { type: "application/json" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
