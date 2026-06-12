import { describe, expect, it, vi } from "vitest";

import type { Job } from "./api";
import { renderHistory } from "./history";

function job(id: string, command: string, extra: Partial<Job> = {}): Job {
  return {
    id,
    command,
    status: "done",
    page_id: `page-${id}`,
    error: null,
    stdout_tail: null,
    stderr_tail: null,
    exit_code: 0,
    started_at: "2026-06-12T08:00:00Z",
    finished_at: "2026-06-12T08:01:00Z",
    emoji: "✅",
    summary: command,
    profile_id: null,
    profile: null,
    ...extra
  };
}

describe("renderHistory", () => {
  it("renders one tile per job with emoji summary status and day groups", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-06-12T12:00:00Z"));
    const open = vi.fn();
    const root = document.createElement("section");
    const jobs = [
      job("1", "added oat milk"),
      job("2", "failed research", {
        status: "failed",
        emoji: "⚠️",
        summary: "could not research",
        started_at: "2026-06-11T08:00:00Z"
      })
    ];

    renderHistory(root, jobs, open);

    expect(root.querySelectorAll(".history-tile")).toHaveLength(2);
    expect(root.textContent).toContain("today");
    expect(root.textContent).toContain("yesterday");
    expect(root.textContent).toContain("✅");
    expect(root.textContent).toContain("added oat milk");
    expect(root.querySelector(".history-tile.failed")).not.toBeNull();

    root.querySelector<HTMLButtonElement>(".history-tile")!.click();
    expect(open).toHaveBeenCalledWith(jobs[0]);
    vi.useRealTimers();
  });
});
