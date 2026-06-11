import type { ApiClient, Job } from "./api";

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
    <ol class="step-log"></ol>
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

export async function waitForJob(api: ApiClient, jobId: string, onSteps: (steps: string[]) => void): Promise<Job> {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    const [jobResponse, eventText] = await Promise.all([api.getJob(jobId), api.getJobEvents(jobId)]);
    onSteps(parseSseSteps(eventText));
    if (["done", "failed", "needs_approval"].includes(jobResponse.job.status)) {
      return jobResponse.job;
    }
    await new Promise((resolve) => window.setTimeout(resolve, 600));
  }
  return (await api.getJob(jobId)).job;
}

export function renderJobsList(jobs: Job[], openPage: (pageId: string) => void): HTMLElement {
  const root = document.createElement("section");
  root.className = "list-screen";
  root.innerHTML = '<p class="eyebrow">jobs - live ledger</p><h1>jobs</h1>';
  const list = document.createElement("div");
  list.className = "metro-list";
  for (const job of jobs) {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "list-row";
    row.disabled = !job.page_id;
    row.innerHTML = `<span>${job.command}</span><small>${job.status}</small>`;
    if (job.page_id) {
      row.addEventListener("click", () => openPage(job.page_id!));
    }
    list.append(row);
  }
  root.append(list);
  return root;
}
