import { expect, test } from "@playwright/test";

const session = {
  ok: true,
  agent: { configured: false, state: "listening" },
  database: "sqlite",
  mcp: { configured: true },
  auth: { valid: true },
  approvals: { pending: false },
  connectors: {},
  todos: { configured: true, url: null, default_project_configured: false, provider: "vikunja" }
};

test("generated pages render in a sandboxed no-referrer iframe", async ({ page }) => {
  await page.route("**/api/pages/page-1", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        page: {
          id: "page-1",
          job_id: "job-1",
          title: "malicious page",
          html: "<article><h1>safe</h1><script>window.top.evil = true</script><button data-action=\"todos.complete\" data-payload=\"{}\">mark done</button></article>",
          provenance: {},
          created_at: "2026-06-12T00:00:00+00:00",
          pinned_at: null
        }
      })
    })
  );

  await page.goto("/page/page-1");

  const frame = page.locator("iframe.page-frame");
  await expect(frame).toHaveAttribute("sandbox", "");
  await expect(frame).toHaveAttribute("referrerpolicy", "no-referrer");
  await expect(frame).toHaveAttribute("title", "malicious page");
  await expect(page.frameLocator("iframe.page-frame").locator("h1")).toHaveText("safe");
  await expect(page.locator(".page-action")).toContainText("mark done");
});

test("todo tabs filter open done and dropped tasks", async ({ page }) => {
  await page.route("**/api/todos", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        todos: [
          todo("todo-open", "replace filter", "open"),
          todo("todo-done", "buy oat milk", "done"),
          todo("todo-dropped", "old errand", "dropped")
        ],
        configured: true,
        provider: "vikunja",
        status: session.todos,
        warning: null
      })
    })
  );

  await page.goto("/tile/todos");

  await expect(page.getByText("replace filter")).toBeVisible();
  await expect(page.getByText("buy oat milk")).toHaveCount(0);

  await page.getByRole("tab", { name: /done 1/ }).click();
  await expect(page.getByText("buy oat milk")).toBeVisible();
  await expect(page.getByText("replace filter")).toHaveCount(0);

  await page.getByRole("tab", { name: /dropped 1/ }).click();
  await expect(page.getByText("old errand")).toBeVisible();
  await expect(page.getByText("buy oat milk")).toHaveCount(0);
});

function todo(id: string, title: string, status: "open" | "done" | "dropped") {
  return {
    id,
    external_id: id,
    provider: "vikunja",
    title,
    notes: null,
    due_at: null,
    scheduled_for: null,
    tags: [],
    status,
    source: "user",
    project_id: "1",
    project: "home",
    list: "home",
    created_at: "2026-06-12T00:00:00+00:00",
    updated_at: "2026-06-12T00:00:00+00:00",
    completed_at: status === "done" ? "2026-06-12T00:00:00+00:00" : null
  };
}
