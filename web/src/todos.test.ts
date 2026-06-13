import { describe, expect, it, vi } from "vitest";

import { renderTodos } from "./todos";

describe("todo rendering", () => {
  it("renders a Vikunja setup hint when todos are unconfigured", () => {
    const root = renderTodos([], undefined, {
      configured: false,
      warning: "Vikunja todo integration is not configured. Set VIKUNJA_URL, VIKUNJA_TOKEN to use todos."
    });

    expect(root.textContent).toContain("connect Vikunja to sync todos");
    expect(root.textContent).toContain("VIKUNJA_URL");
    expect(root.textContent).not.toContain("nothing due - hermes will add work here");
  });

  it("filters todos by tab status", () => {
    const root = renderTodos([
      todo("open-task", "open"),
      todo("done-task", "done"),
      todo("dropped-task", "dropped")
    ]);

    expect(root.textContent).toContain("open-task");
    expect(root.textContent).not.toContain("done-task");
    expect(root.querySelector<HTMLButtonElement>('[data-filter="open"]')?.getAttribute("aria-selected")).toBe("true");

    root.querySelector<HTMLButtonElement>('[data-filter="done"]')!.click();
    expect(root.textContent).toContain("done-task");
    expect(root.textContent).not.toContain("open-task");
    expect(root.querySelector<HTMLButtonElement>('[data-filter="done"]')?.getAttribute("aria-selected")).toBe("true");

    root.querySelector<HTMLButtonElement>('[data-filter="dropped"]')!.click();
    expect(root.textContent).toContain("dropped-task");
    expect(root.textContent).not.toContain("done-task");
  });

  it("completing a todo keeps the active project filter and updates counts", async () => {
    const complete = vi.fn().mockResolvedValue(undefined);
    const root = renderTodos([
      todo("task-a", "open", { project_id: "10", project: "alpha" }),
      todo("task-b", "open", { project_id: "20", project: "beta" })
    ], {
      complete,
      reopen: vi.fn().mockResolvedValue(undefined),
      drop: vi.fn().mockResolvedValue(undefined)
    }, {
      projects: [
        { id: "10", title: "alpha", hex_color: "#aaa" },
        { id: "20", title: "beta", hex_color: "#bbb" }
      ],
      labels: []
    });

    // Switch to project "alpha" filter
    root.querySelector<HTMLButtonElement>('[data-project-id="10"]')!.click();
    expect(root.textContent).toContain("task-a");
    expect(root.textContent).not.toContain("task-b");

    // Complete the visible task
    const doneButton = root.querySelector<HTMLButtonElement>(".inline-action")!;
    doneButton.click();

    // Flush the microtask queue so the async handler resolves
    await new Promise((resolve) => setTimeout(resolve));

    // Filter still on alpha project tab — task-a should be gone (now done), task-b not shown
    expect(complete).toHaveBeenCalledWith("task-a");
    expect(root.textContent).not.toContain("task-a");
    expect(root.textContent).not.toContain("task-b");

    // Project filter buttons still present and alpha still active
    const alphaButton = root.querySelector<HTMLButtonElement>('[data-project-id="10"]')!;
    expect(alphaButton.classList.contains("active")).toBe(true);

    // Status tab count for "open" decremented from 2 to 1
    const openTab = root.querySelector<HTMLButtonElement>('[data-filter="open"]')!;
    expect(openTab.textContent).toBe("open 1");
  });

  it("filters by project and label while rendering due dates and priority", () => {
    const root = renderTodos([
      todo("buy oat milk", "open", {
        project_id: "8",
        project: "errands",
        tags: ["groceries"],
        priority: 5,
        due_at: "2020-01-01T00:00:00Z"
      }),
      todo("write memo", "open", {
        project_id: "7",
        project: "work",
        tags: ["writing"],
        priority: 1
      })
    ], undefined, {
      projects: [
        { id: "8", title: "errands", hex_color: "#4CAF50" },
        { id: "7", title: "work", hex_color: "#1BA1E2" }
      ],
      labels: [
        { id: "3", title: "groceries", hex_color: "#4CAF50" },
        { id: "4", title: "writing", hex_color: "#1BA1E2" }
      ]
    });

    expect(root.textContent).toContain("buy oat milk");
    expect(root.textContent).toContain("!!!");
    expect(root.querySelector(".overdue")).not.toBeNull();
    expect(root.querySelector(".todo-row .chip")?.textContent).toContain("errands");

    root.querySelector<HTMLButtonElement>('[data-project-id="7"]')!.click();
    expect(root.textContent).toContain("write memo");
    expect(root.textContent).not.toContain("buy oat milk");

    root.querySelector<HTMLButtonElement>('[data-label="writing"]')!.click();
    expect(root.textContent).toContain("write memo");
    expect(root.textContent).not.toContain("buy oat milk");
  });
});

function todo(title: string, status: "open" | "done" | "dropped", extra = {}) {
  return {
    id: title,
    external_id: title,
    provider: "vikunja",
    title,
    notes: null,
    due_at: null,
    scheduled_for: null,
    tags: [],
    priority: null,
    status,
    source: "user",
    project_id: "1",
    project: "home",
    list: "home",
    created_at: null,
    updated_at: null,
    completed_at: null,
    ...extra
  };
}
