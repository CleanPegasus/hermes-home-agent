import type { Job, Tile, TileSize } from "./api";
import { packTiles, renderTileFace, type TileShape } from "./tiles";
import { relativeDate, statusEmoji } from "./ui";

const HISTORY_SHAPES: TileShape[] = ["wide", "small", "small", "tall", "wide", "small"];

export function renderHistory(root: HTMLElement, jobs: Job[], onOpen: (job: Job) => void): void {
  root.className = "list-screen history-screen";
  root.replaceChildren();
  const eyebrow = document.createElement("p");
  eyebrow.className = "eyebrow";
  eyebrow.textContent = "history";
  const title = document.createElement("h1");
  title.textContent = "history";
  root.append(eyebrow, title);

  if (jobs.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "no chats yet.";
    root.append(empty);
    return;
  }

  for (const group of groupJobsByDay(jobs)) {
    const heading = document.createElement("h2");
    heading.className = "history-day";
    heading.textContent = group.label;
    const grid = document.createElement("section");
    grid.className = "tile-grid history-grid";
    const jobsByTileKey = new Map(group.jobs.map((job) => [`history-${job.id}`, job]));
    for (const [index, packed] of packTiles(group.jobs.map(historyTile), columnCount()).entries()) {
      const job = jobsByTileKey.get(packed.tile.key);
      if (job) {
        grid.append(renderHistoryTile(job, packed, index, onOpen));
      }
    }
    root.append(heading, grid);
  }
}

function renderHistoryTile(job: Job, packed: ReturnType<typeof packTiles>[number], index: number, onOpen: (job: Job) => void): HTMLButtonElement {
  const [colSpan, rowSpan] = shapeSize(packed.shape);
  const button = document.createElement("button");
  button.type = "button";
  button.className = `tile history-tile ${job.status} tile-shape-${packed.shape}`;
  button.style.setProperty("--tile-color", historyColor(job.status));
  button.style.setProperty("--tile-index", String(index));
  button.style.setProperty("--tile-col-span", String(colSpan));
  button.style.setProperty("--tile-row-span", String(rowSpan));
  button.style.gridColumn = `${packed.col + 1} / span ${colSpan}`;
  button.style.gridRow = `${packed.row + 1} / span ${rowSpan}`;
  button.addEventListener("click", () => onOpen(job));

  const inner = document.createElement("span");
  inner.className = "tile-inner";
  const face = renderTileFace({
    emoji: job.emoji || statusEmoji(job.status),
    line: job.summary || job.command,
    meta: historyMeta(job)
  });
  face.classList.add("tile-front");
  inner.append(face);
  const label = document.createElement("span");
  label.className = "tile-label";
  label.textContent = job.status;
  button.append(inner, label);
  return button;
}

function groupJobsByDay(jobs: Job[]): Array<{ label: string; jobs: Job[] }> {
  const groups = new Map<string, Job[]>();
  for (const job of jobs) {
    const label = dayLabel(job.started_at || job.finished_at);
    groups.set(label, [...(groups.get(label) || []), job]);
  }
  return ["today", "yesterday", "earlier"].flatMap((label) => {
    const rows = groups.get(label) || [];
    return rows.length ? [{ label, jobs: rows }] : [];
  });
}

function dayLabel(value: string | null): string {
  if (!value) {
    return "earlier";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "earlier";
  }
  const today = new Date();
  const startToday = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime();
  const startValue = new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
  const diffDays = Math.round((startToday - startValue) / 86_400_000);
  if (diffDays === 0) {
    return "today";
  }
  if (diffDays === 1) {
    return "yesterday";
  }
  return "earlier";
}

function historyTile(job: Job, index: number): Tile {
  return {
    key: `history-${job.id}`,
    size: tileSizeForShape(HISTORY_SHAPES[index % HISTORY_SHAPES.length]),
    color: historyColor(job.status),
    sort: index,
    front: {},
    back: {},
    updated_at: null
  };
}

function historyMeta(job: Job): string {
  const pieces = [relativeDate(job.started_at || job.finished_at)];
  if (job.profile) {
    pieces.push(`${job.profile.emoji} ${job.profile.name}`);
  }
  return pieces.join(" · ");
}

function historyColor(status: Job["status"]): string {
  if (status === "failed") {
    return "#E51400";
  }
  if (status === "running" || status === "queued") {
    return "#FA6800";
  }
  if (status === "cancelled") {
    return "#647687";
  }
  return "#0050EF";
}

function tileSizeForShape(shape: TileShape): TileSize {
  if (shape === "wide") {
    return "w";
  }
  if (shape === "tall") {
    return "t";
  }
  if (shape === "large") {
    return "l";
  }
  return "s";
}

function shapeSize(shape: TileShape): [number, number] {
  if (shape === "wide") {
    return [2, 1];
  }
  if (shape === "tall") {
    return [1, 2];
  }
  if (shape === "large") {
    return [2, 2];
  }
  return [1, 1];
}

function columnCount(): number {
  if (typeof window !== "undefined" && "matchMedia" in window && window.matchMedia("(min-width: 760px)").matches) {
    return 6;
  }
  return 4;
}
