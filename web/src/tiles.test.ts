import { describe, expect, it } from "vitest";

import type { Tile, TileSize } from "./api";
import { tileIcon } from "./icons";
import { extractActionButtons } from "./pages";
import { getTileShape, packTiles, renderTileFace, renderTile, renderTileGrid, trimLastWord } from "./tiles";

function makeTile(key: string, size: TileSize, sort: number): Tile {
  return {
    key,
    size,
    color: "#0050EF",
    sort,
    front: { count: 1, emoji: "✅", line: key, sub: "front meta" },
    back: { glyph: ">", line: "back", sub: "back meta" },
    updated_at: null
  };
}

describe("tile rendering", () => {
  it("renders a tile face count, line, and meta without unsafe html", () => {
    // Front face: count is rendered
    const front = renderTileFace(
      { count: 3 },
      { iconName: "todos", shape: "tall", isFront: true }
    );
    expect(front.className).toContain("tile-face");
    expect(front.textContent).toContain("3");

    // Back face: line and meta rendered without unsafe html injection
    const back = renderTileFace(
      {
        line: "ready",
        meta: "<strong>today</strong>"
      },
      { shape: "tall", isFront: false }
    );
    expect(back.textContent).toContain("ready");
    expect(back.textContent).toContain("<strong>today</strong>");
    expect(back.querySelector("strong")).toBeNull();
  });

  it("never renders emoji on a tile face", () => {
    const frontFace = renderTileFace(
      { emoji: "🛠️", count: 5, line: "codex" },
      { iconName: "codex", shape: "wide", isFront: true }
    );
    // No emoji text node should appear
    expect(frontFace.textContent).not.toContain("🛠️");

    const backFace = renderTileFace(
      { emoji: "🛠️", line: "codex back" },
      { shape: "wide", isFront: false }
    );
    expect(backFace.textContent).not.toContain("🛠️");
  });

  it("renders an SVG icon for a known tile key", () => {
    const icon = tileIcon("todos");
    expect(icon.tagName.toLowerCase()).toBe("svg");
    expect(icon.getAttribute("aria-hidden")).toBe("true");
    expect(icon.getAttribute("viewBox")).toBe("0 0 24 24");
    expect(icon.querySelectorAll("path").length).toBeGreaterThan(0);
  });

  it("renders a fallback square-outline icon for an unknown key", () => {
    const icon = tileIcon("unknown-future-key");
    expect(icon.tagName.toLowerCase()).toBe("svg");
    // Fallback is a single path (square)
    expect(icon.querySelectorAll("path").length).toBeGreaterThanOrEqual(1);
  });

  it("small tiles always have tile-static class (never flip)", () => {
    // Tile with a back that has content: still static because shape is small
    const tile = makeTile("approvals", "s", 50);
    // Force key-based shape override to small
    tile.size = "s";
    const button = renderTile(tile, () => undefined, 0);
    expect(button.dataset.shape).toBe("small");
    expect(button.classList.contains("tile-static")).toBe(true);
  });

  it("maps tile sizes and sort slots to metro shapes", () => {
    expect(getTileShape(makeTile("jobs", "w", 10))).toBe("wide");
    expect(getTileShape(makeTile("todos", "m", 20))).toBe("large");
    expect(getTileShape(makeTile("calendar", "m", 30))).toBe("tall");
    expect(getTileShape(makeTile("notes", "m", 50))).toBe("wide");
    expect(getTileShape(makeTile("approvals", "s", 50))).toBe("small");
    expect(getTileShape(makeTile("future-tall", "t", 100))).toBe("tall");
    expect(getTileShape(makeTile("future-large", "l", 110))).toBe("large");
  });

  it("gives the live homepage tiles mixed metro shapes even when the API marks them small", () => {
    expect(getTileShape(makeTile("jobs", "s", 10))).toBe("wide");
    expect(getTileShape(makeTile("todos", "s", 70))).toBe("large");
    expect(getTileShape(makeTile("calendar", "s", 80))).toBe("wide");
    expect(getTileShape(makeTile("notes", "s", 90))).toBe("large");
    expect(getTileShape(makeTile("codex", "s", 60))).toBe("tall");
    expect(getTileShape(makeTile("history", "s", 95))).toBe("wide");
    expect(getTileShape(makeTile("profiles", "s", 85))).toBe("wide");
    expect(getTileShape(makeTile("custom", "s", 20))).toBe("wide");
  });

  it("packs seeded tiles without holes at mobile and desktop columns", () => {
    const tiles = [
      makeTile("jobs", "w", 10),
      makeTile("todos", "m", 20),
      makeTile("calendar", "m", 30),
      makeTile("notes", "m", 40),
      makeTile("approvals", "s", 50),
      makeTile("spend", "s", 60),
      makeTile("channels", "s", 70),
      makeTile("vitals", "s", 80),
      makeTile("codex", "s", 90)
    ];

    expect(assertNoPackedHoles(packTiles(tiles, 4), 4)).toBe(true);
    expect(assertNoPackedHoles(packTiles(tiles, 6), 6)).toBe(true);
  });

  it("packs randomized shape sequences without covered-cell holes", () => {
    const sizes: TileSize[] = ["s", "w", "t", "l"];
    for (let seed = 0; seed < 50; seed += 1) {
      const tiles = Array.from({ length: 16 }, (_, index) => makeTile(`random-${seed}-${index}`, sizes[(seed + index * 3) % sizes.length], index * 10));

      expect(assertNoPackedHoles(packTiles(tiles, 4), 4)).toBe(true);
      expect(assertNoPackedHoles(packTiles(tiles, 6), 6)).toBe(true);
    }
  });

  it("renders metro shape classes, explicit positions, and stable tile animation indexes", () => {
    const grid = renderTileGrid(
      [makeTile("jobs", "w", 10), makeTile("todos", "m", 20), makeTile("calendar", "m", 30)],
      () => undefined
    );

    const buttons = Array.from(grid.querySelectorAll<HTMLButtonElement>(".tile"));
    expect(buttons.map((button) => button.dataset.shape)).toEqual(["wide", "large", "tall"]);
    expect(buttons[0].className).toContain("tile-shape-wide");
    expect(buttons[1].className).toContain("tile-shape-large");
    expect(buttons[2].className).toContain("tile-shape-tall");
    expect(buttons[0].style.gridColumn).toMatch(/span 2/);
    expect(buttons[0].style.gridRow).toMatch(/span 1/);
    expect(buttons.map((button) => button.style.getPropertyValue("--tile-index"))).toEqual(["0", "1", "2"]);
  });

  it("renders a watermark svg icon on tiles", () => {
    const tile = makeTile("todos", "s", 10);
    const button = renderTile(tile, () => undefined, 0);
    const watermark = button.querySelector(".tile-watermark");
    expect(watermark).not.toBeNull();
    expect(watermark?.querySelector("svg")).not.toBeNull();
  });
});

function assertNoPackedHoles(packed: ReturnType<typeof packTiles>, columns: number): boolean {
  const occupied = new Set<string>();
  const heights = Array(columns).fill(0) as number[];
  for (const item of packed) {
    const [colSpan, rowSpan] = shapeSize(item.shape);
    for (let col = item.col; col < item.col + colSpan; col += 1) {
      for (let row = item.row; row < item.row + rowSpan; row += 1) {
        occupied.add(`${col}:${row}`);
      }
      heights[col] = Math.max(heights[col], item.row + rowSpan);
    }
  }
  for (let col = 0; col < columns; col += 1) {
    for (let row = 0; row < heights[col]; row += 1) {
      if (!occupied.has(`${col}:${row}`)) {
        return false;
      }
    }
  }
  return true;
}

function shapeSize(shape: string): [number, number] {
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

describe("trimLastWord", () => {
  it("drops the last word from a multi-word string", () => {
    expect(trimLastWord("review the quarterly insurance paperwork")).toBe("review the quarterly insurance");
  });

  it("returns null for a single-word string", () => {
    expect(trimLastWord("hello")).toBeNull();
  });

  it("handles trailing punctuation and strips it", () => {
    expect(trimLastWord("review the paperwork,")).toBe("review the");
    expect(trimLastWord("buy milk.")).toBe("buy");
  });

  it("handles trailing ellipsis from previous trim", () => {
    expect(trimLastWord("review the quarterly…")).toBe("review the");
  });

  it("returns null when only whitespace remains after trim", () => {
    expect(trimLastWord("one")).toBeNull();
  });
});

describe("generated page action parsing", () => {
  it("extracts data-action buttons and parses payload json", () => {
    const actions = extractActionButtons(`
      <article>
        <button data-action="todos.complete" data-payload='{"todo_id":42}'>
          done
        </button>
      </article>
    `);

    expect(actions).toEqual([
      {
        action: "todos.complete",
        label: "done",
        payload: { todo_id: 42 }
      }
    ]);
  });
});
