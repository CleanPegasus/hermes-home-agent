import type { SavedItem } from "./api";
import { armConfirm, el, emptyState, relativeDate } from "./ui";

type ForYouActions = {
  archive: (savedItemId: string) => void | Promise<void>;
};

export function renderForYouSurface(items: SavedItem[], actions: ForYouActions): HTMLElement {
  const root = document.createElement("section");
  root.className = "list-screen detail-screen";
  root.innerHTML = '<p class="eyebrow">things you saved</p>';

  const active = items.filter((item) => item.status !== "archived");
  if (active.length === 0) {
    root.append(emptyState("✨", "nothing here yet", "share links or text to Hermes and they show up here"));
    return root;
  }

  for (const item of active) {
    root.append(renderSavedItem(item, actions));
  }
  return root;
}

function renderSavedItem(item: SavedItem, actions: ForYouActions): HTMLElement {
  const card = el("article", "foryou-card detail-card");
  const meta = el("p", "foryou-meta", `${item.status === "new" ? "enriching…" : "saved"} · ${relativeDate(item.created_at)}`);
  card.append(meta);

  if (item.url) {
    const link = el("a", "foryou-title", item.title || item.url);
    link.href = item.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    card.append(link);
  } else {
    card.append(el("h2", "foryou-title", item.title));
  }

  if (item.summary) {
    card.append(el("p", "foryou-summary", item.summary));
  }

  const archive = el("button", "foryou-archive link-button", "archive");
  armConfirm(archive, "tap to confirm", () => void Promise.resolve(actions.archive(item.id)));
  card.append(archive);
  return card;
}
