import type { ApiClient, Page } from "./api";

export type PageAction = {
  action: string;
  label: string;
  payload: Record<string, unknown>;
};

export function extractActionButtons(html: string): PageAction[] {
  const doc = new DOMParser().parseFromString(html, "text/html");
  return Array.from(doc.querySelectorAll<HTMLButtonElement>("button[data-action]")).map((button) => {
    const payloadRaw = button.getAttribute("data-payload") || "{}";
    let payload: Record<string, unknown>;
    try {
      payload = JSON.parse(payloadRaw);
    } catch {
      payload = {};
    }
    return {
      action: button.dataset.action || "",
      label: button.textContent?.trim() || "run",
      payload
    };
  });
}

export function renderGeneratedPage(
  page: Page,
  api: ApiClient,
  onActionComplete: () => void,
  onOpenJob?: (jobId: string) => void
): HTMLElement {
  const root = document.createElement("section");
  root.className = "generated-page turnstile";

  const meta = document.createElement("div");
  meta.className = "page-meta";
  const title = document.createElement("div");
  title.textContent = page.title;
  const pin = document.createElement("button");
  pin.type = "button";
  pin.className = "inline-action";
  pin.textContent = page.pinned_at ? "unpin" : "pin";
  pin.addEventListener("click", async () => {
    pin.disabled = true;
    try {
      const result = page.pinned_at ? await api.unpinPage(page.id) : await api.pinPage(page.id);
      page.pinned_at = result.page.pinned_at;
      pin.textContent = page.pinned_at ? "unpin" : "pin";
    } finally {
      pin.disabled = false;
    }
  });
  meta.append(title, pin);
  if (page.job_id && onOpenJob) {
    const job = document.createElement("button");
    job.type = "button";
    job.className = "inline-action";
    job.textContent = "source job";
    job.addEventListener("click", () => onOpenJob(page.job_id!));
    meta.append(job);
  }

  const frame = document.createElement("iframe");
  frame.className = "page-frame";
  frame.srcdoc = page.html;
  frame.title = page.title;
  frame.setAttribute("sandbox", "");
  frame.referrerPolicy = "no-referrer";
  frame.loading = "lazy";

  const actions = document.createElement("div");
  actions.className = "page-actions";
  const status = document.createElement("p");
  status.className = "action-status";
  for (const item of extractActionButtons(page.html)) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "page-action";
    const originalLabel = item.label.toLowerCase();
    button.textContent = originalLabel;

    const doRun = async () => {
      button.disabled = true;
      button.classList.remove("armed");
      button.textContent = originalLabel;
      status.textContent = "running action...";
      try {
        await api.runAction(item.action, { ...item.payload, page_id: page.id, job_id: page.job_id });
        status.textContent = "action complete";
        onActionComplete();
      } catch (error) {
        status.textContent = error instanceof Error ? error.message : "action failed";
        button.disabled = false;
      }
    };

    let armedTimer: number | undefined;
    const disarm = () => {
      button.classList.remove("armed");
      button.textContent = originalLabel;
      clearTimeout(armedTimer);
    };

    button.addEventListener("click", async () => {
      if (button.classList.contains("armed")) {
        clearTimeout(armedTimer);
        disarm();
        await doRun();
        return;
      }
      const meta = await actionMeta(api, item.action);
      if (meta?.requires_confirmation) {
        button.textContent = `tap again to ${originalLabel}`;
        button.classList.add("armed");
        armedTimer = window.setTimeout(disarm, 3000);
        return;
      }
      await doRun();
    });

    button.addEventListener("blur", () => {
      if (button.classList.contains("armed")) {
        disarm();
      }
    });

    actions.append(button);
  }

  if (actions.childElementCount === 0) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "no direct actions on this page.";
    actions.append(empty);
  }

  root.append(meta, frame, actions, status);
  return root;
}

async function actionMeta(api: ApiClient, action: string) {
  try {
    const { actions } = await api.getActions();
    return actions.find((item) => item.name === action);
  } catch {
    return undefined;
  }
}
