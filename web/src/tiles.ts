import type { Tile, TileFace } from "./api";

export type TileShape = "small" | "wide" | "tall" | "large";
export interface PackedTile {
  tile: Tile;
  shape: TileShape;
  col: number;
  row: number;
}

const METRO_TILE_SHAPES_BY_KEY: Record<string, TileShape> = {
  jobs: "wide",
  todos: "large",
  calendar: "wide",
  notes: "large",
  approvals: "small",
  spend: "small",
  channels: "wide",
  vitals: "small",
  codex: "tall",
  profiles: "wide",
  history: "wide"
};
const METRO_FALLBACK_SHAPES: TileShape[] = ["small", "wide", "small", "tall", "large", "small", "wide"];
const MEDIUM_TILE_SHAPES: TileShape[] = ["large", "tall", "large", "wide"];

export function getTileShape(tile: Tile): TileShape {
  if (tile.size === "w") {
    return "wide";
  }

  if (tile.size === "t") {
    return "tall";
  }

  if (tile.size === "l") {
    return "large";
  }

  if (tile.size === "m") {
    const slot = Math.max(0, Math.floor(tile.sort / 10) - 2);
    return MEDIUM_TILE_SHAPES[slot % MEDIUM_TILE_SHAPES.length];
  }

  const keyShape = METRO_TILE_SHAPES_BY_KEY[tile.key];
  if (keyShape) {
    return keyShape;
  }

  const slot = Math.max(0, Math.floor(tile.sort / 10) - 1);
  return METRO_FALLBACK_SHAPES[slot % METRO_FALLBACK_SHAPES.length];
}

export function packTiles(tiles: Tile[], columns: number): PackedTile[] {
  const safeColumns = Math.max(1, Math.floor(columns));
  const remaining = tiles.map((tile, index) => ({ tile, index, shape: getTileShape(tile) }));
  const heights = Array(safeColumns).fill(0) as number[];
  const packed: PackedTile[] = [];

  while (remaining.length > 0) {
    let best: { remainingIndex: number; col: number; row: number } | null = null;
    for (let remainingIndex = 0; remainingIndex < remaining.length; remainingIndex += 1) {
      const candidate = remaining[remainingIndex];
      const [colSpan] = shapeSize(candidate.shape);
      if (colSpan > safeColumns) {
        continue;
      }
      const position = findFlatPosition(heights, colSpan);
      if (!position) {
        continue;
      }
      if (
        !best ||
        position.row < best.row ||
        (position.row === best.row && position.col < best.col) ||
        (position.row === best.row && position.col === best.col && candidate.index < remaining[best.remainingIndex].index)
      ) {
        best = { remainingIndex, col: position.col, row: position.row };
      }
    }

    const picked = best ? remaining.splice(best.remainingIndex, 1)[0] : remaining.shift()!;
    const [colSpan, rowSpan] = shapeSize(picked.shape);
    const col = best?.col ?? 0;
    const row = best?.row ?? Math.max(...heights);
    for (let offset = 0; offset < Math.min(colSpan, safeColumns); offset += 1) {
      heights[col + offset] = row + rowSpan;
    }
    packed.push({ tile: picked.tile, shape: picked.shape, col, row });
  }

  return packed;
}

function findFlatPosition(heights: number[], colSpan: number): { col: number; row: number } | null {
  let best: { col: number; row: number } | null = null;
  for (let col = 0; col <= heights.length - colSpan; col += 1) {
    const row = heights[col];
    let flat = true;
    for (let offset = 1; offset < colSpan; offset += 1) {
      if (heights[col + offset] !== row) {
        flat = false;
        break;
      }
    }
    if (flat && (!best || row < best.row || (row === best.row && col < best.col))) {
      best = { col, row };
    }
  }
  return best;
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

export function renderTileFace(face: TileFace): HTMLDivElement {
  const root = document.createElement("div");
  const hasMark = face.count !== undefined || Boolean(face.glyph) || Boolean(face.emoji);
  root.className = hasMark ? "tile-face tile-face-has-mark" : "tile-face tile-face-text-only";

  if (face.count !== undefined) {
    const count = document.createElement("div");
    count.className = "tile-count";
    count.textContent = String(face.count);
    root.append(count);
  } else if (face.glyph) {
    const glyph = document.createElement("div");
    glyph.className = "tile-glyph";
    glyph.textContent = face.glyph;
    root.append(glyph);
  }

  if (face.emoji) {
    const emoji = document.createElement("span");
    emoji.className = "tile-emoji";
    emoji.textContent = face.emoji;
    root.append(emoji);
  }

  const line = document.createElement("div");
  line.className = "tile-line";
  line.textContent = face.line || "";
  root.append(line);

  const meta = document.createElement("div");
  meta.className = "tile-meta";
  meta.textContent = face.sub || face.meta || "";
  root.append(meta);

  return root;
}

function backHasContent(face: TileFace): boolean {
  return face.count !== undefined || Boolean(face.glyph) || Boolean(face.emoji) || Boolean(face.line) || Boolean(face.sub) || Boolean(face.meta);
}

export function renderTile(tile: Tile, onOpen: (key: string) => void, index = 0, packed?: Pick<PackedTile, "shape" | "col" | "row">): HTMLButtonElement {
  const shape = packed?.shape ?? getTileShape(tile);
  const [colSpan, rowSpan] = shapeSize(shape);
  const button = document.createElement("button");
  button.className = `tile tile-${tile.size} tile-shape-${shape}`;
  button.style.setProperty("--tile-color", tile.color);
  button.style.setProperty("--tile-index", String(index));
  button.style.setProperty("--tile-col-span", String(colSpan));
  button.style.setProperty("--tile-row-span", String(rowSpan));
  if (packed) {
    button.style.gridColumn = `${packed.col + 1} / span ${colSpan}`;
    button.style.gridRow = `${packed.row + 1} / span ${rowSpan}`;
  }
  button.type = "button";
  button.dataset.key = tile.key;
  button.dataset.shape = shape;
  button.addEventListener("click", () => onOpen(tile.key));

  const label = document.createElement("span");
  label.className = "tile-label";
  label.textContent = tile.key;

  const inner = document.createElement("span");
  inner.className = "tile-inner";
  const front = renderTileFace(tile.front);
  front.classList.add("tile-front");
  const back = renderTileFace(tile.back);
  back.classList.add("tile-back");
  inner.append(front, back);

  if (!backHasContent(tile.back)) {
    button.classList.add("tile-static");
  }

  button.append(inner, label);
  return button;
}

export function renderTileGrid(tiles: Tile[], onOpen: (key: string) => void): HTMLElement {
  const grid = document.createElement("section");
  grid.className = "tile-grid";
  const renderPackedTiles = () => {
    grid.replaceChildren();
    for (const [index, packed] of packTiles(tiles, gridColumnCount()).entries()) {
      grid.append(renderTile(packed.tile, onOpen, index, packed));
    }
  };
  renderPackedTiles();
  const media = typeof window !== "undefined" && "matchMedia" in window ? window.matchMedia("(min-width: 760px)") : null;
  media?.addEventListener?.("change", renderPackedTiles);
  return grid;
}

function gridColumnCount(): number {
  if (typeof window !== "undefined" && "matchMedia" in window && window.matchMedia("(min-width: 760px)").matches) {
    return 6;
  }
  return 4;
}

if (typeof document !== "undefined") {
  document.addEventListener("visibilitychange", () => {
    document.documentElement.classList.toggle("tiles-paused", document.hidden);
  });
}
