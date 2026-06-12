export function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  className?: string,
  text?: string
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (className) {
    node.className = className;
  }
  if (text !== undefined) {
    node.textContent = text;
  }
  return node;
}

export function addFact(list: HTMLElement, label: string, value: string): void {
  const term = document.createElement("dt");
  term.textContent = label;
  const description = document.createElement("dd");
  description.textContent = value;
  list.append(term, description);
}

export function factsList(facts: Array<[string, string]>): HTMLDListElement {
  const root = document.createElement("dl");
  root.className = "fact-list";
  for (const [label, value] of facts) {
    addFact(root, label, value);
  }
  return root;
}

export function block(title: string, ...children: HTMLElement[]): HTMLElement {
  const root = document.createElement("section");
  root.className = "surface-list";
  const heading = document.createElement("h2");
  heading.textContent = title;
  root.append(heading, ...children);
  return root;
}

export function shortDate(iso: string | null): string {
  if (!iso) {
    return "unknown";
  }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return iso;
  }
  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  }).toLowerCase();
}

export function relativeDate(iso: string | null): string {
  if (!iso) {
    return "unknown";
  }
  const date = new Date(iso);
  const timestamp = date.getTime();
  if (Number.isNaN(timestamp)) {
    return iso;
  }
  const deltaSeconds = Math.round((Date.now() - timestamp) / 1000);
  if (deltaSeconds < -60) {
    const futureMinutes = Math.round(Math.abs(deltaSeconds) / 60);
    return `in ${futureMinutes}m`;
  }
  if (deltaSeconds < 60) {
    return "now";
  }
  const minutes = Math.floor(deltaSeconds / 60);
  if (minutes < 60) {
    return `${minutes}m ago`;
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 48) {
    return `${hours}h ago`;
  }
  const days = Math.floor(hours / 24);
  if (days < 7) {
    return `${days}d ago`;
  }
  return shortDate(iso);
}

export function emptyState(emoji: string, line: string, hint?: string): HTMLElement {
  const root = document.createElement("div");
  root.className = "empty-state";
  const mark = document.createElement("span");
  mark.className = "empty-state-emoji";
  mark.textContent = emoji;
  const message = document.createElement("p");
  message.className = "empty";
  message.textContent = line;
  root.append(mark, message);
  if (hint) {
    const detail = document.createElement("small");
    detail.textContent = hint;
    root.append(detail);
  }
  return root;
}

export function chip(text: string, color?: string): HTMLElement {
  const root = document.createElement("span");
  root.className = "chip";
  root.textContent = text;
  if (color) {
    root.style.setProperty("--chip-color", color);
  }
  return root;
}

export function statusEmoji(status: string): string {
  return {
    queued: "⏳",
    running: "⚙️",
    done: "✅",
    failed: "❌",
    cancelled: "🛑",
    needs_approval: "🛡️"
  }[status] || "•";
}

export function armConfirm(button: HTMLButtonElement, armedLabel: string, onConfirm: () => void): void {
  let armedTimer: number | undefined;

  const disarm = () => {
    button.textContent = button.dataset.originalLabel ?? button.textContent ?? "";
    button.classList.remove("armed");
    clearTimeout(armedTimer);
  };

  button.dataset.originalLabel = button.textContent ?? "";

  button.addEventListener("click", (event) => {
    event.stopPropagation();
    if (button.classList.contains("armed")) {
      clearTimeout(armedTimer);
      button.classList.remove("armed");
      onConfirm();
      return;
    }
    button.dataset.originalLabel = button.textContent ?? "";
    button.textContent = armedLabel;
    button.classList.add("armed");
    armedTimer = window.setTimeout(disarm, 3000);
  });

  button.addEventListener("blur", () => {
    if (button.classList.contains("armed")) {
      disarm();
    }
  });
}

export function stripMarkdown(text: string): string {
  return text
    // links [text](url) -> text
    .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1")
    // bold **text** or __text__
    .replace(/\*\*([^*]*)\*\*/g, "$1")
    .replace(/__([^_]*)__/g, "$1")
    // italic *text* or _text_
    .replace(/\*([^*]*)\*/g, "$1")
    .replace(/_([^_]*)_/g, "$1")
    // inline code
    .replace(/`([^`]*)`/g, "$1")
    // blockquote markers
    .replace(/^>\s?/gm, "")
    // heading markers
    .replace(/^#{1,6}\s+/gm, "")
    .trim();
}

export function toast(message: string, kind: "info" | "error" = "info"): void {
  let root = document.getElementById("toast-root");
  if (!root) {
    root = document.createElement("div");
    root.id = "toast-root";
    document.body.append(root);
  }
  const item = document.createElement("div");
  item.className = `toast toast-${kind}`;
  item.setAttribute("role", kind === "error" ? "alert" : "status");
  item.textContent = message;
  root.append(item);
  const delay = kind === "error" ? 6000 : 4000;
  window.setTimeout(() => {
    item.remove();
  }, delay);
}
