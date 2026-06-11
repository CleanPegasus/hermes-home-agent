import { describe, expect, it } from "vitest";

import { extractActionButtons } from "./pages";
import { renderTileFace } from "./tiles";

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
