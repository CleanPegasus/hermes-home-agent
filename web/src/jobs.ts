import type { ApiClient, Approval, Job, JobEvent, Page } from "./api";
import { addFact, statusEmoji } from "./ui";

export function parseSseSteps(text: string): string[] {
  return text
    .split("\n")
    .filter((line) => line.startsWith("data: "))
    .map((line) => {
      try {
        const payload = JSON.parse(line.slice(6)) as { text?: string };
        return payload.text || "";
      } catch {
        return "";
      }
    })
    .filter(Boolean);
}

export function renderWorkingScreen(command: string): HTMLElement {
  const root = document.createElement("section");
  root.className = "screen working-screen";
  root.innerHTML = `
    <div class="panorama-row">
      <h1>working on it</h1>
      <span class="agent-state">hermes-01-running</span>
    </div>
    <div class="dot-track" aria-hidden="true">
      <span></span><span></span><span></span><span></span><span></span>
    </div>
    <p class="working-command"></p>
    <p class="working-status">starting job...</p>
    <ol class="step-log"></ol>
    <div class="page-actions working-actions">
      <button type="button" class="page-action secondary" data-action="background" disabled>run in background</button>
      <button type="button" class="page-action danger" data-action="cancel" disabled>cancel</button>
    </div>
  `;
  root.querySelector(".working-command")!.textContent = command.toLowerCase();
  return root;
}

export function updateStepLog(root: HTMLElement, steps: string[]): void {
  const log = root.querySelector(".step-log");
  if (!log) {
    return;
  }
  log.replaceChildren(
    ...steps.map((step) => {
      const li = document.createElement("li");
      li.textContent = step;
      return li;
    })
  );
}

type WaitForJobOptions = {
  intervalMs?: number;
  maxAttempts?: number;
  onStatus?: (message: string) => void;
  signal?: AbortSignal;
};

export async function waitForJob(
  api: ApiClient,
  jobId: string,
  onSteps: (steps: string[]) => void,
  options: WaitForJobOptions = {}
): Promise<Job> {
  const intervalMs = options.intervalMs ?? 1000;
  const maxAttempts = options.maxAttempts ?? 600;
  let lastJob: Job | null = null;
  const startedAt = Date.now();
  const streamApi = api as ApiClient & {
    streamJobEvents?: (jobId: string, onEvent: (event: JobEvent) => void, signal?: AbortSignal) => Promise<void>;
  };
  const streamedSteps: string[] = [];
  const abortController = typeof AbortController !== "undefined" ? new AbortController() : null;
  let streamStarted = false;

  if (streamApi.streamJobEvents && abortController) {
    streamStarted = true;
    streamApi
      .streamJobEvents(
        jobId,
        (event) => {
          if (!event.text) {
            return;
          }
          streamedSteps.push(event.text);
          onSteps([...streamedSteps]);
        },
        abortController.signal
      )
      .catch(() => {
        streamStarted = false;
      });
  }

  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    if (options.signal?.aborted) {
      abortController?.abort();
      return lastJob || (await api.getJob(jobId)).job;
    }
    const [jobResponse, eventText] = await Promise.all([
      api.getJob(jobId),
      streamStarted ? Promise.resolve("") : api.getJobEvents(jobId)
    ]);
    lastJob = jobResponse.job;
    if (!streamStarted) {
      onSteps(parseSseSteps(eventText));
    }
    const elapsedSeconds = Math.max(1, Math.round((Date.now() - startedAt) / 1000));
    options.onStatus?.(`still working... ${elapsedSeconds}s`);
    if (["done", "failed", "needs_approval", "cancelled"].includes(jobResponse.job.status)) {
      abortController?.abort();
      return jobResponse.job;
    }
    await new Promise((resolve) => window.setTimeout(resolve, intervalMs));
  }
  abortController?.abort();

  const job = lastJob || (await api.getJob(jobId)).job;
  return {
    ...job,
    error: job.error || "Hermes is still working after 10 minutes. Check the jobs tile for the latest status."
  };
}

export function renderJobsList(jobs: Job[], openJob: (jobId: string) => void): HTMLElement {
  const root = document.createElement("section");
  root.className = "list-screen";
  root.innerHTML = '<p class="eyebrow">jobs - live ledger</p><h1>jobs</h1>';
  const list = document.createElement("div");
  list.className = "metro-list";
  for (const job of jobs) {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "list-row";
    row.innerHTML = "<span></span><small></small>";
    row.querySelector("span")!.textContent = job.command;
    row.querySelector("small")!.textContent = `${statusEmoji(job.status)} ${job.status}`;
    row.addEventListener("click", () => openJob(job.id));
    list.append(row);
  }
  if (jobs.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "no jobs yet.";
    list.append(empty);
  }
  root.append(list);
  return root;
}

type JobDetail = {
  job: Job;
  events: JobEvent[];
  page: Page | null;
  approvals: Approval[];
};

type JobDetailActions = {
  openPage: (pageId: string) => void;
  retry: (jobId: string) => void;
  cancel: (jobId: string) => void;
  diagnostics: (jobId: string) => void;
};

export function renderJobDetail(detail: JobDetail, actions: JobDetailActions): HTMLElement {
  const root = document.createElement("section");
  root.className = "list-screen detail-screen";
  root.innerHTML = '<p class="eyebrow">job detail</p>';

  const title = document.createElement("h1");
  title.textContent = `${statusEmoji(detail.job.status)} ${detail.job.status}`;

  const command = document.createElement("p");
  command.className = "working-command";
  command.textContent = detail.job.command;

  const controls = document.createElement("div");
  controls.className = "page-actions";
  if (detail.page) {
    const pageButton = document.createElement("button");
    pageButton.type = "button";
    pageButton.className = "page-action";
    pageButton.textContent = "open page";
    pageButton.addEventListener("click", () => actions.openPage(detail.page!.id));
    controls.append(pageButton);
  }
  const retryButton = document.createElement("button");
  retryButton.type = "button";
  retryButton.className = "page-action";
  retryButton.textContent = "retry";
  retryButton.addEventListener("click", () => actions.retry(detail.job.id));
  controls.append(retryButton);
  const diagnosticsButton = document.createElement("button");
  diagnosticsButton.type = "button";
  diagnosticsButton.className = "page-action secondary";
  diagnosticsButton.textContent = "diagnostics";
  diagnosticsButton.addEventListener("click", () => actions.diagnostics(detail.job.id));
  controls.append(diagnosticsButton);
  if (["queued", "running", "needs_approval"].includes(detail.job.status)) {
    const cancelButton = document.createElement("button");
    cancelButton.type = "button";
    cancelButton.className = "page-action danger";
    cancelButton.textContent = "cancel";
    cancelButton.addEventListener("click", () => actions.cancel(detail.job.id));
    controls.append(cancelButton);
  }

  const facts = document.createElement("dl");
  facts.className = "fact-list";
  addFact(facts, "started", detail.job.started_at || "not started");
  addFact(facts, "finished", detail.job.finished_at || "not finished");
  if (detail.job.error) {
    addFact(facts, "error", detail.job.error);
  }
  if (detail.job.exit_code !== null) {
    addFact(facts, "exit", String(detail.job.exit_code));
  }
  if (detail.job.stdout_tail) {
    addFact(facts, "stdout", detail.job.stdout_tail);
  }
  if (detail.job.stderr_tail) {
    addFact(facts, "stderr", detail.job.stderr_tail);
  }

  const eventList = document.createElement("ol");
  eventList.className = "step-log timeline";
  for (const event of detail.events) {
    const item = document.createElement("li");
    item.innerHTML = `<span></span><small></small>`;
    item.querySelector("span")!.textContent = event.text;
    item.querySelector("small")!.textContent = `${event.kind}${event.ts ? ` · ${formatShortTime(event.ts)}` : ""}`;
    eventList.append(item);
  }
  if (detail.events.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "no events recorded for this job.";
    eventList.append(empty);
  }

  const approvals = document.createElement("div");
  approvals.className = "metro-list compact-list";
  for (const approval of detail.approvals) {
    const row = document.createElement("div");
    row.className = `list-row approval-row ${approval.status}`;
    row.innerHTML = `<span></span><small></small>`;
    row.querySelector("span")!.textContent = approval.action;
    row.querySelector("small")!.textContent = `${statusEmoji(approval.status)} ${approval.status}`;
    approvals.append(row);
  }

  root.append(title, command, controls, facts);
  const timelineHeading = document.createElement("h2");
  timelineHeading.textContent = "timeline";
  root.append(timelineHeading, eventList);
  if (detail.approvals.length > 0) {
    const approvalHeading = document.createElement("h2");
    approvalHeading.textContent = "approvals";
    root.append(approvalHeading, approvals);
  }
  return root;
}

function formatShortTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}
