import { describe, expect, it, vi } from "vitest";

import type { Job, Profile } from "./api";
import { renderProfileEditor, renderProfileFocus, renderProfilesPage } from "./profiles";

const profile: Profile = {
  id: "profile-1",
  slug: "coding-agent",
  name: "coding agent",
  emoji: "💻",
  color: "#1BA1E2",
  persona: "Use repo context.",
  is_default: true,
  created_at: null,
  updated_at: null
};

function job(extra: Partial<Job> = {}): Job {
  return {
    id: "job-1",
    command: "write tests",
    status: "done",
    page_id: null,
    error: null,
    stdout_tail: null,
    stderr_tail: null,
    exit_code: 0,
    emoji: "💻",
    summary: "wrote tests",
    profile_id: profile.id,
    profile: { id: profile.id, name: profile.name, emoji: profile.emoji, color: profile.color },
    parent_job_id: null,
    started_at: "2026-06-12T08:00:00Z",
    finished_at: "2026-06-12T08:01:00Z",
    ...extra
  };
}

describe("profiles UI", () => {
  it("renders profile tiles and opens the new-profile tile", () => {
    const open = vi.fn();
    const create = vi.fn();
    const root = renderProfilesPage([profile], profile.id, { openProfile: open, createProfile: create });

    expect(root.textContent).toContain("coding agent");
    expect(root.textContent).toContain("new profile");

    root.querySelector<HTMLButtonElement>('[data-profile-id="profile-1"]')!.click();
    expect(open).toHaveBeenCalledWith(profile.id);

    root.querySelector<HTMLButtonElement>("[data-new-profile]")!.click();
    expect(create).toHaveBeenCalled();
  });

  it("submits profile editor payloads", () => {
    const save = vi.fn();
    const root = renderProfileEditor(profile, { save, deleteProfile: vi.fn() });

    root.querySelector<HTMLInputElement>('input[name="name"]')!.value = "Research";
    root.querySelector<HTMLTextAreaElement>('textarea[name="persona"]')!.value = "Find sources.";
    root.querySelector<HTMLInputElement>('input[name="is_default"]')!.checked = true;
    root.querySelector<HTMLFormElement>("form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));

    expect(save).toHaveBeenCalledWith({
      name: "Research",
      emoji: "💻",
      color: "#1BA1E2",
      persona: "Find sources.",
      is_default: true
    });
  });

  it("renders focus command form and profile jobs", () => {
    const run = vi.fn();
    const root = renderProfileFocus(profile, [job()], { runCommand: run, editProfile: vi.fn(), openJob: vi.fn() });

    expect(root.textContent).toContain("Use repo context.");
    expect(root.textContent).toContain("wrote tests");
    root.querySelector<HTMLInputElement>('input[name="command"]')!.value = "summarize repo";
    root.querySelector<HTMLFormElement>("form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));

    expect(run).toHaveBeenCalledWith("summarize repo", profile.id);
  });
});
