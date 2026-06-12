import { describe, expect, it } from "vitest";

import type { Tile, TileSize } from "./api";
import { extractActionButtons } from "./pages";
import { getTileShape, packTiles, renderTileFace, renderTileGrid } from "./tiles";

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
    const face = renderTileFace({
      count: 3,
      line: "ready",
      meta: "<strong>today</strong>"
    });

    expect(face.className).toContain("tile-face");
    expect(face.textContent).toContain("3");
    expect(face.textContent).toContain("ready");
    expect(face.textContent).toContain("<strong>today</strong>");
    expect(face.querySelector("strong")).toBeNull();
  });

  it("renders tile face emoji before text", () => {
    const face = renderTileFace({ emoji: "🛠️", line: "codex" });

    expect(face.querySelector(".tile-emoji")?.textContent).toBe("🛠️");
    expect(face.textContent).toContain("codex");
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
