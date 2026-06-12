import { describe, expect, it, vi } from "vitest";

import { renderNotes } from "./notes";
import type { Category, Note } from "./api";

describe("notes rendering", () => {
  it("renders a vault setup state when notes are unconfigured", () => {
    const root = renderNotes([], [], undefined, {
      configured: false,
      warning: "Set OBSIDIAN_VAULT_PATH to enable notes."
    });

    expect(root.textContent).toContain("connect your obsidian vault");
    expect(root.textContent).toContain("OBSIDIAN_VAULT_PATH");
    expect(root.querySelector(".empty-state")).not.toBeNull();
  });

  it("filters notes by category slug and renders tag chips", () => {
    const onOpen = vi.fn();
    const root = renderNotes([
      note("1", "hallway filter", "home", ["hvac"]),
      note("2", "bike pump", "errands", ["garage"])
    ], categories, onOpen);

    expect(root.textContent).toContain("hallway filter");
    expect(root.textContent).toContain("bike pump");
    expect(root.querySelector(".note-tags .chip")?.textContent).toBe("hvac");

    root.querySelector<HTMLButtonElement>('[data-category="errands"]')!.click();
    expect(root.textContent).toContain("bike pump");
    expect(root.textContent).not.toContain("hallway filter");

    root.querySelector<HTMLButtonElement>(".note-row")!.click();
    expect(onOpen).toHaveBeenCalledWith("2");
  });
});

const categories: Category[] = [
  { id: "cat-1", slug: "home", name: "home", color: "#1BA1E2", created_by: "seed", created_at: null },
  { id: "cat-2", slug: "errands", name: "errands", color: "#4CAF50", created_by: "seed", created_at: null }
];

function note(id: string, title: string, category: string, tags: string[]): Note {
  return {
    id,
    title,
    category,
    tags,
    body_md: `${title} body`,
    source_job_id: null,
    archived: false,
    created_at: null,
    updated_at: null
  };
}
