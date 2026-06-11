import "./styles.css";

import { createApiClient, type ApiClient, type Tile } from "./api";
import { renderJobsList, renderWorkingScreen, updateStepLog, waitForJob } from "./jobs";
import { renderNotes } from "./notes";
import { renderGeneratedPage } from "./pages";
import { renderTileGrid } from "./tiles";
import { renderTodos } from "./todos";

const api = createApiClient();
const app = document.querySelector<HTMLDivElement>("#app");

if (!app) {
  throw new Error("missing #app root");
}

const rootElement: HTMLDivElement = app;

function setScreen(node: HTMLElement): void {
  rootElement.replaceChildren(node);
}

function shell(title: string, body: HTMLElement): HTMLElement {
  const root = document.createElement("main");
  root.className = "shell";
  const top = document.createElement("div");
  top.className = "panorama-row";
  top.innerHTML = `<h1>${title}</h1><span class="agent-state">hermes-01-listening</span>`;
  const nav = document.createElement("nav");
  nav.className = "nav-bar";
  nav.innerHTML = '<button type="button" data-nav="back" aria-label="back">‹</button><button type="button" data-nav="home" aria-label="start">⊞</button>';
  nav.querySelector('[data-nav="back"]')?.addEventListener("click", () => history.back());
  nav.querySelector('[data-nav="home"]')?.addEventListener("click", () => void showStart());
  root.append(top, body, nav);
  return root;
}

async function showStart(): Promise<void> {
  const { tiles } = await api.getTiles();
  const body = document.createElement("section");
  body.className = "start-screen";
  body.append(renderTileGrid(tiles, (key) => void openTile(key)));

  const chips = document.createElement("div");
  chips.className = "chips";
  for (const suggestion of ["add buy oat milk to my todos", "summarize today", "file a note"]) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.textContent = suggestion;
    chip.addEventListener("click", () => {
      const input = body.querySelector<HTMLInputElement>(".command-input");
      if (input) {
        input.value = suggestion;
        input.focus();
      }
    });
    chips.append(chip);
  }

  const form = document.createElement("form");
  form.className = "command-bar";
  form.innerHTML = '<input class="command-input" name="command" autocomplete="off" placeholder="tell hermes what to do..." /><button type="submit" aria-label="send">›</button>';
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = form.querySelector<HTMLInputElement>(".command-input");
    const text = input?.value.trim() || "";
    if (!text) {
      return;
    }
    await runCommand(text);
  });

  body.append(chips, form);
  setScreen(shell("start", body));
}

async function openTile(key: string): Promise<void> {
  if (key === "todos") {
    const { todos } = await api.getTodos();
    setScreen(shell("todos", renderTodos(todos)));
    return;
  }
  if (key === "notes") {
    const { notes } = await api.getNotes();
    setScreen(shell("notes", renderNotes(notes)));
    return;
  }
  if (key === "jobs") {
    const { jobs } = await api.getJobs();
    setScreen(shell("jobs", renderJobsList(jobs, (pageId) => void showPage(pageId))));
    return;
  }
  setScreen(shell(key, renderPlaceholder(key)));
}

function renderPlaceholder(key: string): HTMLElement {
  const root = document.createElement("section");
  root.className = "list-screen";
  root.innerHTML = `<p class="eyebrow">server defined</p><h1>${key}</h1><p class="empty">nothing to show here yet.</p>`;
  return root;
}

async function runCommand(text: string): Promise<void> {
  const working = renderWorkingScreen(text);
  setScreen(shell("working", working));
  const { job_id } = await api.sendCommand(text);
  const job = await waitForJob(api, job_id, (steps) => updateStepLog(working, steps));
  if (job.status === "done" && job.page_id) {
    await showPage(job.page_id);
    return;
  }
  const error = document.createElement("section");
  error.className = "list-screen";
  error.innerHTML = `<p class="eyebrow">jobs</p><h1>didn't finish</h1><p class="empty">${job.error || "the steps it took are in jobs"}</p>`;
  setScreen(shell("failed", error));
}

async function showPage(pageId: string): Promise<void> {
  const { page } = await api.getPage(pageId);
  const pageView = renderGeneratedPage(page, api, () => void showStart());
  setScreen(shell("page", pageView));
}

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => undefined);
  });
}

showStart().catch((error) => {
  const root = document.createElement("main");
  root.className = "shell";
  root.innerHTML = `<section class="list-screen"><p class="eyebrow">offline</p><h1>didn't load</h1><p class="empty">${String(error.message || error)}</p></section>`;
  setScreen(root);
});
