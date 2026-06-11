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
  onActionComplete: () => void
): HTMLElement {
  const root = document.createElement("section");
  root.className = "generated-page turnstile";

  const frame = document.createElement("iframe");
  frame.className = "page-frame";
  frame.sandbox.add("allow-same-origin");
  frame.srcdoc = page.html;
  frame.title = page.title;

  const actions = document.createElement("div");
  actions.className = "page-actions";
  for (const item of extractActionButtons(page.html)) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "page-action";
    button.textContent = item.label.toLowerCase();
    button.addEventListener("click", async () => {
      await api.runAction(item.action, item.payload);
      onActionComplete();
    });
    actions.append(button);
  }

  root.append(frame, actions);
  return root;
}
