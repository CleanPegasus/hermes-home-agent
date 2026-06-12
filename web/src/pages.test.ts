import { describe, expect, it, vi } from "vitest";

import type { ApiClient, Page } from "./api";
import { renderGeneratedPage } from "./pages";

describe("renderGeneratedPage", () => {
  it("isolates generated HTML in a sandboxed no-referrer iframe", () => {
    const page = generatedPage();
    const root = renderGeneratedPage(page, fakeApi(), vi.fn());
    const frame = root.querySelector<HTMLIFrameElement>("iframe.page-frame")!;

    expect(frame.getAttribute("sandbox")).toBe("");
    expect(frame.getAttribute("referrerpolicy")).toBe("no-referrer");
    expect(frame.srcdoc).toContain("<h1>safe</h1>");
  });
});

function generatedPage(): Page {
  return {
    id: "page-1",
    job_id: "job-1",
    title: "safe",
    html: '<article><h1>safe</h1><button data-action="todos.complete" data-payload="{}">mark done</button></article>',
    provenance: {},
    created_at: "2026-06-12T00:00:00+00:00",
    pinned_at: null
  };
}

function fakeApi(): ApiClient {
  return {
    pinPage: vi.fn(),
    unpinPage: vi.fn(),
    getActions: vi.fn(async () => ({ actions: [] })),
    runAction: vi.fn()
  } as unknown as ApiClient;
}
