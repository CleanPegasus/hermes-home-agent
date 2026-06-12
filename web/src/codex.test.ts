import { describe, expect, it, vi } from "vitest";

import type { CodexRun, CodexState } from "./api";
import { renderCodexSurface } from "./codex";

const state: CodexState = {
  available: true,
  enabled: true,
  binary_available: true,
  workdir: "/opt/hermes-home/web",
  mode: "dangerously-bypass-approvals-and-sandbox",
  effort: "medium",
  effort_options: ["low", "medium", "high", "xhigh"],
  requires_confirmation: true,
  disabled_reason: null,
  dirty: false,
  status_short: "",
  diff_stat: ""
};

function codexRun(extra: Partial<CodexRun> = {}): CodexRun {
  return {
    id: "run-1",
    prompt: "previous prompt",
    effort: "high",
    workdir: "/opt/hermes-home/web",
    command: [],
    status: "done",
    process_id: null,
    cancel_requested: false,
    before_status: null,
    after_status: null,
    diff_stat: null,
    stdout_tail: null,
    stderr_tail: null,
    exit_code: 0,
    error: null,
    started_at: "2026-06-12T08:00:00+00:00",
    finished_at: "2026-06-12T08:01:00+00:00",
    ...extra
  };
}

describe("renderCodexSurface", () => {
  it("creates chats with an effort toggle and shows previous prompts", () => {
    const submit = vi.fn();
    const openRun = vi.fn();
    const root = renderCodexSurface(state, [codexRun()], { submit, openRun });

    expect(root.querySelector(".eyebrow")?.textContent).toBe("codex");
    expect(root.querySelector("h1")?.textContent).toBe("codex");
    expect(root.textContent).toContain("previous prompts");
    expect(root.textContent).toContain("previous prompt");
    expect(root.textContent).toContain("high · done");

    const medium = root.querySelector<HTMLButtonElement>('button[data-effort="medium"]')!;
    const high = root.querySelector<HTMLButtonElement>('button[data-effort="high"]')!;
    expect(medium.getAttribute("aria-pressed")).toBe("true");

    high.click();
    expect(high.getAttribute("aria-pressed")).toBe("true");
    expect(medium.getAttribute("aria-pressed")).toBe("false");

    root.querySelector<HTMLTextAreaElement>('textarea[name="prompt"]')!.value = "start a new chat";
    root.querySelector<HTMLInputElement>('input[name="confirmDangerousMode"]')!.checked = true;
    root.querySelector<HTMLFormElement>("form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));

    expect(submit).toHaveBeenCalledWith("start a new chat", "high", true);

    root.querySelector<HTMLButtonElement>(".list-row")!.click();
    expect(openRun).toHaveBeenCalledWith("run-1");
  });
});
