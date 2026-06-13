import type { Job, Profile } from "./api";
import { relativeDate } from "./ui";

type ProfilesPageActions = {
  openProfile: (profileId: string) => void;
  createProfile: () => void;
};

type ProfileEditorActions = {
  save: (payload: Pick<Profile, "name" | "emoji" | "color" | "persona" | "is_default">) => void;
  deleteProfile: () => void;
};

type ProfileFocusActions = {
  runCommand: (text: string, profileId: string) => void;
  editProfile: (profileId: string) => void;
  openJob: (jobId: string) => void;
};

const SUGGESTED_EMOJI = ["🪄", "🧠", "💻", "💰", "🏠", "📝", "🔎", "📅", "✅", "🛠️", "🎭", "⚡"];
const COLORS = ["#1BA1E2", "#0050EF", "#008A00", "#A20025", "#D80073", "#FA6800", "#647687"];

export function renderProfilesPage(profiles: Profile[], defaultId: string | null, actions: ProfilesPageActions): HTMLElement {
  const root = document.createElement("section");
  root.className = "list-screen profiles-screen";
  root.innerHTML = '<p class="eyebrow">profiles</p>';
  const grid = document.createElement("section");
  grid.className = "profile-grid";
  for (const profile of profiles) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "profile-tile";
    button.dataset.profileId = profile.id;
    button.style.setProperty("--profile-color", profile.color);
    button.innerHTML = "<strong></strong><span></span><small></small>";
    button.querySelector("strong")!.textContent = profile.emoji;
    button.querySelector("span")!.textContent = profile.name;
    button.querySelector("small")!.textContent = profile.id === defaultId ? "default" : profile.slug;
    button.addEventListener("click", () => actions.openProfile(profile.id));
    grid.append(button);
  }
  const create = document.createElement("button");
  create.type = "button";
  create.className = "profile-tile new";
  create.dataset.newProfile = "true";
  create.textContent = "➕ new profile";
  create.addEventListener("click", () => actions.createProfile());
  grid.append(create);
  root.append(grid);
  return root;
}

export function renderProfileFocus(profile: Profile, jobs: Job[], actions: ProfileFocusActions): HTMLElement {
  const root = document.createElement("section");
  root.className = "list-screen profile-focus";
  root.innerHTML = '<p class="eyebrow">profile</p><h1></h1>';
  root.querySelector("h1")!.textContent = `${profile.emoji} ${profile.name}`;
  const persona = document.createElement("p");
  persona.className = "profile-persona";
  persona.textContent = profile.persona || "no persona yet.";
  const edit = document.createElement("button");
  edit.type = "button";
  edit.className = "page-action secondary";
  edit.textContent = "edit";
  edit.addEventListener("click", () => actions.editProfile(profile.id));
  const form = document.createElement("form");
  form.className = "command-bar profile-command";
  form.innerHTML = '<input class="command-input" name="command" autocomplete="off" placeholder="run with this profile..." /><button type="submit" aria-label="send">›</button>';
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const input = form.elements.namedItem("command") as HTMLInputElement;
    const text = input.value.trim();
    if (text) {
      actions.runCommand(text, profile.id);
    }
  });
  root.append(persona, edit, form, renderProfileJobs(jobs, actions.openJob));
  return root;
}

export function renderProfileEditor(profile: Profile | null, actions: ProfileEditorActions): HTMLElement {
  const root = document.createElement("section");
  root.className = "list-screen detail-screen profile-editor";
  root.innerHTML = '<p class="eyebrow">profile</p><h1></h1>';
  root.querySelector("h1")!.textContent = profile ? "edit profile" : "new profile";
  const form = document.createElement("form");
  form.className = "profile-form";
  form.innerHTML = `
    <label>name<input name="name" autocomplete="off"></label>
    <label>emoji<input name="emoji" autocomplete="off"></label>
    <div class="emoji-row"></div>
    <label>color<input name="color" autocomplete="off"></label>
    <div class="swatch-row"></div>
    <label>persona<textarea name="persona" rows="8"></textarea></label>
    <label class="check-row"><input name="is_default" type="checkbox"> make default</label>
    <div class="page-actions"><button type="submit" class="page-action">save</button></div>
  `;
  const name = form.elements.namedItem("name") as HTMLInputElement;
  const emoji = form.elements.namedItem("emoji") as HTMLInputElement;
  const color = form.elements.namedItem("color") as HTMLInputElement;
  const persona = form.elements.namedItem("persona") as HTMLTextAreaElement;
  const isDefault = form.elements.namedItem("is_default") as HTMLInputElement;
  name.value = profile?.name || "";
  emoji.value = profile?.emoji || "🤖";
  color.value = profile?.color || "#1BA1E2";
  persona.value = profile?.persona || "";
  isDefault.checked = profile?.is_default || false;
  const emojiRow = form.querySelector(".emoji-row")!;
  for (const option of SUGGESTED_EMOJI) {
    emojiRow.append(optionButton(option, () => {
      emoji.value = option;
    }));
  }
  const swatchRow = form.querySelector(".swatch-row")!;
  for (const option of COLORS) {
    const button = optionButton("", () => {
      color.value = option;
    });
    button.className = "swatch";
    button.style.setProperty("--profile-color", option);
    swatchRow.append(button);
  }
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    actions.save({
      name: name.value.trim(),
      emoji: emoji.value.trim() || "🤖",
      color: color.value.trim() || "#1BA1E2",
      persona: persona.value.trim(),
      is_default: isDefault.checked
    });
  });
  root.append(form);
  if (profile && !profile.is_default) {
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "page-action danger";
    remove.textContent = "delete";
    remove.addEventListener("click", () => actions.deleteProfile());
    root.append(remove);
  }
  return root;
}

function renderProfileJobs(jobs: Job[], openJob: (jobId: string) => void): HTMLElement {
  const root = document.createElement("section");
  root.className = "surface-list";
  const heading = document.createElement("h2");
  heading.textContent = "recent jobs";
  const rows = document.createElement("div");
  rows.className = "metro-list compact-list";
  if (jobs.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "no jobs yet.";
    rows.append(empty);
  }
  for (const job of jobs) {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "list-row";
    row.innerHTML = "<span></span><small></small>";
    row.querySelector("span")!.textContent = job.summary || job.command;
    row.querySelector("small")!.textContent = relativeDate(job.started_at || job.finished_at);
    row.addEventListener("click", () => openJob(job.id));
    rows.append(row);
  }
  root.append(heading, rows);
  return root;
}

function optionButton(label: string, onClick: () => void): HTMLButtonElement {
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = label;
  button.addEventListener("click", onClick);
  return button;
}
