import { describe, expect, it, vi } from "vitest";

import { parseSseSteps, waitForJob } from "./jobs";
import type { ApiClient, Job } from "./api";

function job(status: Job["status"], extra: Partial<Job> = {}): Job {
  return {
    id: "job-1",
    command: "test command",
    status,
    page_id: null,
    error: null,
    stdout_tail: null,
    stderr_tail: null,
    exit_code: null,
    emoji: null,
    summary: null,
    profile_id: null,
    profile: null,
    started_at: null,
    finished_at: null,
    ...extra
  };
}

describe("parseSseSteps", () => {
  it("extracts step text from server-sent event lines", () => {
    expect(parseSseSteps('data: {"text":"queued"}\n\ndata: {"text":"running"}\n')).toEqual(["queued", "running"]);
  });
});

describe("waitForJob", () => {
  it("waits beyond the old 12 second ceiling and returns the completed job", async () => {
    vi.useFakeTimers();
    const states = [job("running"), job("running"), job("done", { page_id: "page-1" })];
    const getJob = vi.fn(async () => ({ job: states.shift() ?? job("done", { page_id: "page-1" }) }));
    const api = {
      getJob,
      getJobEvents: vi.fn(async () => 'data: {"text":"working"}\n')
    } as unknown as ApiClient;
    const statuses: string[] = [];

    const pending = waitForJob(api, "job-1", () => undefined, {
      intervalMs: 12_000,
      maxAttempts: 3,
      onStatus: (message) => statuses.push(message)
    });

    await vi.advanceTimersByTimeAsync(24_000);
    await expect(pending).resolves.toMatchObject({ status: "done", page_id: "page-1" });
    expect(getJob).toHaveBeenCalledTimes(3);
    expect(statuses).toContain("still working... 24s");
    vi.useRealTimers();
  });

  it("returns a helpful message instead of spinning forever when it times out", async () => {
    vi.useFakeTimers();
    const api = {
      getJob: vi.fn(async () => ({ job: job("running") })),
      getJobEvents: vi.fn(async () => "")
    } as unknown as ApiClient;

    const pending = waitForJob(api, "job-1", () => undefined, { intervalMs: 1000, maxAttempts: 2 });
    await vi.advanceTimersByTimeAsync(2000);
    await expect(pending).resolves.toMatchObject({
      status: "running",
      error: "Hermes is still working after 10 minutes. Check the jobs tile for the latest status."
    });
    vi.useRealTimers();
  });
});
