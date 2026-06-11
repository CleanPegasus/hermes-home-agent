import type { Tile, TileFace } from "./api";

export function renderTileFace(face: TileFace): HTMLDivElement {
  const root = document.createElement("div");
  root.className = "tile-face";

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

export function renderTile(tile: Tile, onOpen: (key: string) => void): HTMLButtonElement {
  const button = document.createElement("button");
  button.className = `tile tile-${tile.size}`;
  button.style.setProperty("--tile-color", tile.color);
  button.type = "button";
  button.dataset.key = tile.key;
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

  button.append(inner, label);
  return button;
}

export function renderTileGrid(tiles: Tile[], onOpen: (key: string) => void): HTMLElement {
  const grid = document.createElement("section");
  grid.className = "tile-grid";
  for (const tile of tiles) {
    grid.append(renderTile(tile, onOpen));
  }
  return grid;
}
