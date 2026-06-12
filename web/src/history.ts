import type { Job, Tile, TileSize } from "./api";
import { tileIcon } from "./icons";
import { packTiles, renderTileFace, type TileShape } from "./tiles";
import { emptyState, relativeDate } from "./ui";

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
    root.append(emptyState("📋", "no jobs yet.", "send hermes a command to get started"));
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
  button.setAttribute("aria-label", `${job.summary || job.command} · ${job.status} · ${relativeDate(job.started_at || job.finished_at)}`);
  button.addEventListener("click", () => onOpen(job));

  // Watermark: status icon, low-opacity, bottom-right
  const watermark = document.createElement("span");
  watermark.className = "tile-watermark";
  watermark.setAttribute("aria-hidden", "true");
  watermark.append(tileIcon(job.status));

  const inner = document.createElement("span");
  inner.className = "tile-inner";

  // Front face: status icon + line (command/summary)
  const frontFace = document.createElement("div");
  frontFace.className = "tile-face tile-front";

  const iconWrap = document.createElement("div");
  iconWrap.className = "tile-icon";
  iconWrap.append(tileIcon(job.status));

  if (packed.shape === "wide") {
    const row = document.createElement("div");
    row.className = "tile-front-row";
    row.append(iconWrap);
    frontFace.append(row);
  } else {
    frontFace.append(iconWrap);
  }

  const lineText = job.summary || job.command;
  if (lineText && packed.shape !== "small") {
    const line = document.createElement("div");
    line.className = "tile-line";
    line.textContent = lineText;
    frontFace.append(line);
  }

  // Back face: empty (history tiles don't flip)
  const backFace = renderTileFace({}, { shape: packed.shape, isFront: false });
  backFace.classList.add("tile-back");

  inner.append(frontFace, backFace);

  // History tiles always static (no back content)
  button.classList.add("tile-static");

  const label = document.createElement("span");
  label.className = "tile-label";
  label.textContent = job.status;

  button.append(watermark, inner, label);
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

