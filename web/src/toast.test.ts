import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { toast } from "./ui";

describe("toast", () => {
  beforeEach(() => {
    document.getElementById("toast-root")?.remove();
    vi.useFakeTimers();
  });

  afterEach(() => {
    document.getElementById("toast-root")?.remove();
    vi.useRealTimers();
  });

  it("creates #toast-root on first call and appends a toast", () => {
    toast("hello world");
    const root = document.getElementById("toast-root");
    expect(root).not.toBeNull();
    expect(root!.children.length).toBe(1);
    expect(root!.children[0].textContent).toBe("hello world");
  });

  it("info toast has role=status and info class", () => {
    toast("saved", "info");
    const item = document.getElementById("toast-root")!.children[0];
    expect(item.getAttribute("role")).toBe("status");
    expect(item.classList.contains("toast-info")).toBe(true);
  });

  it("error toast has role=alert and error class", () => {
    toast("something broke", "error");
    const item = document.getElementById("toast-root")!.children[0];
    expect(item.getAttribute("role")).toBe("alert");
    expect(item.classList.contains("toast-error")).toBe(true);
  });

  it("defaults to info kind", () => {
    toast("default kind");
    const item = document.getElementById("toast-root")!.children[0];
    expect(item.getAttribute("role")).toBe("status");
    expect(item.classList.contains("toast-info")).toBe(true);
  });

  it("stacks multiple toasts", () => {
    toast("first");
    toast("second");
    toast("third");
    const root = document.getElementById("toast-root")!;
    expect(root.children.length).toBe(3);
  });

  it("reuses existing #toast-root on subsequent calls", () => {
    toast("one");
    toast("two");
    expect(document.querySelectorAll("#toast-root").length).toBe(1);
  });

  it("dismisses info toast after 4s", () => {
    toast("brief");
    const root = document.getElementById("toast-root")!;
    expect(root.children.length).toBe(1);
    vi.advanceTimersByTime(3999);
    expect(root.children.length).toBe(1);
    vi.advanceTimersByTime(1);
    expect(root.children.length).toBe(0);
  });

  it("dismisses error toast after 6s", () => {
    toast("oops", "error");
    const root = document.getElementById("toast-root")!;
    expect(root.children.length).toBe(1);
    vi.advanceTimersByTime(5999);
    expect(root.children.length).toBe(1);
    vi.advanceTimersByTime(1);
    expect(root.children.length).toBe(0);
  });

  it("does not dismiss error toast early at 4s", () => {
    toast("lingering error", "error");
    const root = document.getElementById("toast-root")!;
    vi.advanceTimersByTime(4000);
    expect(root.children.length).toBe(1);
  });
});
