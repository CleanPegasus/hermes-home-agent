import "./styles.css";

import {
  ApiError,
  createApiClient,
  getHomeApiBase,
  getHomeApiToken,
  setHomeApiBase,
  setHomeApiToken,
  type ActionRunFilters,
  type ApiClient,
  type CodexEffort,
  type Profile,
  type SessionInfo
} from "./api";
import { renderApprovalDetail, renderApprovals } from "./approvals";
import { renderCodexRunDetail, renderCodexSurface } from "./codex";
import { renderHistory } from "./history";
import { renderJobDetail, renderJobsList, renderWorkingScreen, updateStepLog, waitForJob } from "./jobs";
import { renderNoteDetail, renderNotes } from "./notes";
import { renderGeneratedPage } from "./pages";
import { renderProfileEditor, renderProfileFocus, renderProfilesPage } from "./profiles";
import { renderActionRunDetail, renderCalendarSurface, renderChannelsSurface, renderDiagnosticsBundle, renderSpendSurface, renderVitalsSurface } from "./surfaces";
import { renderTileGrid } from "./tiles";
import { renderTodos } from "./todos";
import { addFact, toast } from "./ui";

let api: ApiClient = createApiClient();
let sessionState: SessionInfo | null = null;
let navDepth = 0;
const COMMAND_SUGGESTIONS = ["add buy oat milk to my todos", "summarize today", "file a note"];
const PROFILE_STORAGE_KEY = "HERMES_PROFILE_ID";
const app = document.querySelector<HTMLDivElement>("#app");

if (!app) {
  throw new Error("missing #app root");
}

const rootElement: HTMLDivElement = app;

function setScreen(node: HTMLElement): void {
  rootElement.replaceChildren(node);
}

function visit(path: string): void {
  const current = `${window.location.pathname}${window.location.search}`;
  if (current !== path) {
    history.pushState({}, "", path);
    navDepth += 1;
  }
  void renderRoute(path);
}

async function renderRoute(path = `${window.location.pathname}${window.location.search}`): Promise<void> {
  const url = new URL(path, window.location.origin);
  const parts = url.pathname.split("/").filter(Boolean).map((part) => decodeURIComponent(part));
  let loadingTimer: number | undefined;
  if (parts[0] !== "settings") {
    loadingTimer = window.setTimeout(() => {
      renderLoading(parts[0] || "start");
    }, 200);
  }
  try {
    if (parts.length === 0) {
      await showStart();
      return;
    }
    if (parts[0] === "tile" && parts[1]) {
      if (parts[1] === "vitals") {
        await showVitals(auditFiltersFromParams(url.searchParams));
        return;
      }
      await openTile(parts[1]);
      return;
    }
    if (parts[0] === "history") {
      await showHistory();
      return;
    }
    if (parts[0] === "profiles") {
      if (parts[1] === "new") {
        await showProfileEditor(null);
      } else {
        await showProfiles();
      }
      return;
    }
    if (parts[0] === "profile" && parts[1]) {
      if (parts[2] === "edit") {
        await showProfileEditor(parts[1]);
      } else {
        await showProfileFocus(parts[1]);
      }
      return;
    }
    if (parts[0] === "job" && parts[1]) {
      await showJobDetail(parts[1]);
      return;
    }
    if (parts[0] === "page" && parts[1]) {
      await showPage(parts[1]);
      return;
    }
    if (parts[0] === "approval" && parts[1]) {
      await showApprovalDetail(parts[1]);
      return;
    }
    if (parts[0] === "note" && parts[1]) {
      await showNoteDetail(parts[1]);
      return;
    }
    if (parts[0] === "action" && parts[1]) {
      await showActionRunDetail(parts[1]);
      return;
    }
    if (parts[0] === "codex" && parts[1]) {
      await showCodexRun(parts[1]);
      return;
    }
    if (parts[0] === "diagnostics" && parts[1]) {
      await showDiagnostics(parts[1]);
      return;
    }
    if (parts[0] === "settings") {
      renderSetup("connection settings");
      return;
    }
    renderNotFound(url.pathname);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      renderSetup(error.message);
      return;
    }
    if (error instanceof ApiError && error.status === 404) {
      renderNotFound(url.pathname);
      return;
    }
    renderRouteError(error instanceof Error ? error.message : "couldn't load this screen.");
  } finally {
    window.clearTimeout(loadingTimer);
  }
}

function shell(title: string, body: HTMLElement, opts?: { commandBar?: boolean }): HTMLElement {
  const showCommandBar = opts?.commandBar !== false;
  const root = document.createElement("main");
  root.className = "shell";
  const top = document.createElement("div");
  top.className = "panorama-row";
  const agentLabel = sessionState
    ? `hermes-01-${sessionState.agent.state}${sessionState.agent.configured ? "" : "-fallback"}`
    : "hermes-01-setup";
  const h1 = document.createElement("h1");
  h1.textContent = title;
  const agentSpan = document.createElement("span");
  agentSpan.className = "agent-state";
  agentSpan.textContent = agentLabel;
  top.append(h1, agentSpan);
  const nav = document.createElement("nav");
  nav.className = "nav-bar";
  nav.innerHTML = '<button type="button" data-nav="back" aria-label="back">‹</button><button type="button" data-nav="home" aria-label="start">⊞</button><button type="button" data-nav="settings" aria-label="settings">⚙</button>';
  nav.querySelector('[data-nav="back"]')?.addEventListener("click", () => {
    if (navDepth > 0) {
      history.back();
    } else {
      visit("/");
    }
  });
  nav.querySelector('[data-nav="home"]')?.addEventListener("click", () => visit("/"));
  nav.querySelector('[data-nav="settings"]')?.addEventListener("click", () => visit("/settings"));
  if (showCommandBar) {
    const globalBar = document.createElement("form");
    globalBar.className = "command-bar global-command-bar";
    globalBar.innerHTML = '<input class="command-input" name="command" autocomplete="off" placeholder="tell hermes what to do..." /><button type="submit" aria-label="send">›</button>';
    globalBar.addEventListener("submit", async (event) => {
      event.preventDefault();
      const input = globalBar.querySelector<HTMLInputElement>(".command-input");
      const button = globalBar.querySelector<HTMLButtonElement>('button[type="submit"]');
      const text = input?.value.trim() || "";
      if (!text) {
        return;
      }
      globalBar.classList.add("is-submitting");
      input?.setAttribute("disabled", "true");
      button?.setAttribute("disabled", "true");
      try {
        await runCommand(text, localStorage.getItem(PROFILE_STORAGE_KEY) || null);
      } finally {
        globalBar.classList.remove("is-submitting");
        input?.removeAttribute("disabled");
        button?.removeAttribute("disabled");
      }
    });
    root.append(top, body, globalBar, nav);
  } else {
    root.append(top, body, nav);
  }
  return root;
}

async function showStart(prefillCommand?: string): Promise<void> {
  history.replaceState({}, "", "/");
  const [session, { tiles }, profileState, activity, pinned] = await Promise.all([
    api.getSession(),
    api.getTiles(),
    api.getProfiles(),
    renderRecentActivity(),
    renderPinnedPages()
  ]);
  sessionState = session;
  const selectedProfileId = selectedProfile(profileState.profiles, profileState.default_id);
  const body = document.createElement("section");
  body.className = "start-screen";
  body.append(renderTileGrid(tiles, (key) => visit(`/tile/${encodeURIComponent(key)}`)));
  body.append(renderProfilePicker(profileState.profiles, selectedProfileId));
  body.append(activity);
  body.append(pinned);

  const chips = document.createElement("div");
  chips.className = "chips";
  for (const suggestion of COMMAND_SUGGESTIONS) {
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
    const button = form.querySelector<HTMLButtonElement>('button[type="submit"]');
    const text = input?.value.trim() || "";
    if (!text) {
      return;
    }
    form.classList.add("is-submitting");
    input?.setAttribute("disabled", "true");
    button?.setAttribute("disabled", "true");
    try {
      await runCommand(text, selectedProfile(profileState.profiles, profileState.default_id));
    } finally {
      form.classList.remove("is-submitting");
      input?.removeAttribute("disabled");
      button?.removeAttribute("disabled");
    }
  });

  body.append(chips, form);
  setScreen(shell("start", body, { commandBar: false }));

  if (prefillCommand) {
    const input = body.querySelector<HTMLInputElement>(".command-input");
    if (input) {
      input.value = prefillCommand;
      input.focus();
      input.setSelectionRange(prefillCommand.length, prefillCommand.length);
    }
  }
}

async function openTile(key: string): Promise<void> {
  if (key === "todos") {
    const todoState = await api.getTodos();
    setScreen(shell("todos", renderTodos(todoState.todos, {
      complete: (todoId) => runTodoAction("todos.complete", todoId),
      reopen: (todoId) => runTodoAction("todos.reopen", todoId),
      drop: (todoId) => runTodoAction("todos.drop", todoId)
    }, {
      configured: todoState.configured,
      warning: todoState.warning,
      projects: todoState.projects,
      labels: todoState.labels
    })));
    return;
  }
  if (key === "notes") {
    const [{ notes, configured, warning }, { categories }] = await Promise.all([api.getNotes(), api.getCategories()]);
    setScreen(shell("notes", renderNotes(notes, categories, (noteId) => visit(`/note/${encodeURIComponent(noteId)}`), {
      configured,
      warning,
      onSearch: async (filters) => (await api.getNotes(filters)).notes
    })));
    return;
  }
  if (key === "jobs") {
    const { jobs } = await api.getJobs();
    setScreen(shell("jobs", renderJobsList(jobs, (jobId) => visit(`/job/${encodeURIComponent(jobId)}`))));
    return;
  }
  if (key === "history") {
    await showHistory();
    return;
  }
  if (key === "profiles") {
    await showProfiles();
    return;
  }
  if (key === "approvals") {
    const { approvals } = await api.getApprovals();
    setScreen(shell("approvals", renderApprovals(approvals, {
      approve: (approvalId) => void decideApproval(approvalId, "approve"),
      reject: (approvalId) => void decideApproval(approvalId, "reject"),
      openJob: (jobId) => visit(`/job/${encodeURIComponent(jobId)}`),
      openApproval: (approvalId) => visit(`/approval/${encodeURIComponent(approvalId)}`)
    })));
    return;
  }
  if (key === "calendar") {
    setScreen(shell("calendar", renderCalendarSurface(await api.getCalendar(), { sync: () => void syncConnectorsAndReload("calendar") })));
    return;
  }
  if (key === "channels") {
    setScreen(shell("channels", renderChannelsSurface(await api.getChannels(), { sync: () => void syncConnectorsAndReload("channels") })));
    return;
  }
  if (key === "spend") {
    setScreen(shell("spend", renderSpendSurface(await api.getSpend(), { sync: () => void syncConnectorsAndReload("spend") })));
    return;
  }
  if (key === "vitals") {
    await showVitals();
    return;
  }
  if (key === "codex") {
    await showCodex();
    return;
  }
  setScreen(shell(key, await renderCapabilityStatus(key)));
}

async function renderCapabilityStatus(key: string): Promise<HTMLElement> {
  const capabilities = await api.getCapabilities();
  const root = document.createElement("section");
  root.className = "list-screen detail-screen";
  root.innerHTML = '<p class="eyebrow">capability</p><h1></h1>';
  root.querySelector("h1")!.textContent = key;
  const facts = document.createElement("dl");
  facts.className = "fact-list";
  const status = capabilityStatus(key, capabilities.features);
  addFact(facts, "state", status.state);
  addFact(facts, "configured", status.configured ? "yes" : "no");
  addFact(facts, "what hermes can do", status.description);
  root.append(facts);
  return root;
}

async function runCommand(text: string, profileId?: string | null): Promise<void> {
  const working = renderWorkingScreen(text);
  setScreen(shell("working", working, { commandBar: false }));
  const status = working.querySelector<HTMLElement>(".working-status");
  const bgButton = working.querySelector<HTMLButtonElement>('[data-action="background"]');
  const cancelButton = working.querySelector<HTMLButtonElement>('[data-action="cancel"]');

  let job_id: string;
  try {
    ({ job_id } = await api.sendCommand(text, profileId));
  } catch (error) {
    toast(error instanceof Error ? error.message : "couldn't send command", "error");
    await showStart(text);
    return;
  }

  const aborter = new AbortController();

  if (bgButton) {
    bgButton.removeAttribute("disabled");
    bgButton.addEventListener("click", () => {
      aborter.abort();
      toast("still running - check jobs for the result");
      visit("/");
    });
  }
  if (cancelButton) {
    cancelButton.removeAttribute("disabled");
    cancelButton.addEventListener("click", async () => {
      aborter.abort();
      try {
        await api.cancelJob(job_id);
      } catch (error) {
        toast(error instanceof Error ? error.message : "couldn't cancel job", "error");
      }
      visit(`/job/${encodeURIComponent(job_id)}`);
    });
  }

  let job;
  try {
    job = await waitForJob(api, job_id, (steps) => updateStepLog(working, steps), {
      signal: aborter.signal,
      onStatus: (message) => {
        if (status) {
          status.textContent = message;
        }
      }
    });
  } catch (error) {
    if (aborter.signal.aborted) {
      return;
    }
    throw error;
  }

  if (aborter.signal.aborted) {
    return;
  }

  if (job.status === "done" && job.page_id) {
    visit(`/page/${encodeURIComponent(job.page_id)}`);
    return;
  }
  if (job.status === "done" || job.status === "needs_approval" || job.status === "needs_clarification") {
    visit(`/job/${encodeURIComponent(job.id)}`);
    return;
  }
  const error = document.createElement("section");
  error.className = "list-screen";
  error.innerHTML = `<p class="eyebrow">jobs</p><h1>didn't finish</h1><p class="empty"></p><div class="page-actions"></div>`;
  error.querySelector(".empty")!.textContent = job.error || "the steps it took are in jobs";
  const openJobBtn = document.createElement("button");
  openJobBtn.type = "button";
  openJobBtn.className = "page-action secondary";
  openJobBtn.textContent = "open job";
  openJobBtn.addEventListener("click", () => visit(`/job/${encodeURIComponent(job.id)}`));
  const editCommandBtn = document.createElement("button");
  editCommandBtn.type = "button";
  editCommandBtn.className = "page-action secondary";
  editCommandBtn.textContent = "edit command";
  editCommandBtn.addEventListener("click", () => void showStart(text));
  error.querySelector(".page-actions")!.append(openJobBtn, editCommandBtn);
  setScreen(shell("failed", error));
}

function renderLoading(label: string): void {
  const root = document.createElement("section");
  root.className = "list-screen";
  root.innerHTML = '<p class="eyebrow">loading</p><h1></h1><p class="empty">fetching current state...</p>';
  root.querySelector("h1")!.textContent = label;
  setScreen(shell("loading", root));
}

function renderNotFound(path: string): void {
  const root = document.createElement("section");
  root.className = "list-screen";
  root.innerHTML = '<p class="eyebrow">route</p><h1>not found</h1><p class="empty"></p><div class="page-actions"></div>';
  root.querySelector(".empty")!.textContent = path;
  const home = document.createElement("button");
  home.type = "button";
  home.className = "page-action";
  home.textContent = "start";
  home.addEventListener("click", () => visit("/"));
  root.querySelector(".page-actions")!.append(home);
  setScreen(shell("not found", root));
}

function renderRouteError(message: string): void {
  const root = document.createElement("section");
  root.className = "list-screen";
  root.innerHTML = '<p class="eyebrow">route</p><h1>couldn\'t load</h1><p class="empty"></p><div class="page-actions"></div>';
  root.querySelector(".empty")!.textContent = message;
  const retry = document.createElement("button");
  retry.type = "button";
  retry.className = "page-action";
  retry.textContent = "retry";
  retry.addEventListener("click", () => void renderRoute());
  root.querySelector(".page-actions")!.append(retry);
  setScreen(shell("error", root));
}

async function showPage(pageId: string): Promise<void> {
  const { page } = await api.getPage(pageId);
  const pageView = renderGeneratedPage(page, api, () => visit("/"), (jobId) => visit(`/job/${encodeURIComponent(jobId)}`));
  pageView.append(renderFollowUpForm("page", `follow up on page ${page.id}: `));
  setScreen(shell("page", pageView));
}

async function showNoteDetail(noteId: string): Promise<void> {
  const [{ note }, { categories }, { notes }] = await Promise.all([api.getNote(noteId), api.getCategories(), api.getNotes()]);
  setScreen(shell("note", renderNoteDetail(note, categories, notes, {
    save: (targetNoteId, changes) => void saveNote(targetNoteId, changes),
    archive: (targetNoteId) => void archiveNote(targetNoteId),
    merge: (targetNoteId, target) => void mergeNote(targetNoteId, target),
    openJob: (jobId) => visit(`/job/${encodeURIComponent(jobId)}`)
  })));
  rootElement.querySelector(".detail-screen")?.append(renderFollowUpForm("note", `use note ${note.id}: `));
}

async function saveNote(noteId: string, changes: { title: string; body_md: string; category: string; tags: string[] }): Promise<void> {
  try {
    await api.updateNote(noteId, changes);
    toast("note saved");
    await showNoteDetail(noteId);
  } catch (error) {
    toast(error instanceof Error ? error.message : "couldn't save note", "error");
  }
}

async function archiveNote(noteId: string): Promise<void> {
  try {
    await api.archiveNote(noteId);
    toast("note archived");
    visit("/tile/notes");
  } catch (error) {
    toast(error instanceof Error ? error.message : "couldn't archive note", "error");
  }
}

async function mergeNote(noteId: string, targetNoteId: string): Promise<void> {
  try {
    const { note } = await api.mergeNote(noteId, targetNoteId);
    visit(`/note/${encodeURIComponent(note.id)}`);
  } catch (error) {
    toast(error instanceof Error ? error.message : "couldn't merge note", "error");
  }
}

async function showJobDetail(jobId: string): Promise<void> {
  const detail = await api.getJobTimeline(jobId);
  setScreen(shell("job", renderJobDetail(detail, {
    openPage: (pageId) => visit(`/page/${encodeURIComponent(pageId)}`),
    retry: (targetJobId) => void retryJob(targetJobId),
    cancel: (targetJobId) => void cancelJob(targetJobId),
    diagnostics: (targetJobId) => visit(`/diagnostics/${encodeURIComponent(targetJobId)}`),
    answerClarification: (clarificationId, answer) => void answerClarification(clarificationId, answer)
  })));
  rootElement.querySelector(".detail-screen")?.append(renderFollowUpForm("job", `continue job ${jobId}: `));
}

async function showDiagnostics(jobId: string): Promise<void> {
  const diagnostics = await api.getJobDiagnostics(jobId);
  setScreen(shell("diagnostics", renderDiagnosticsBundle(diagnostics)));
}

async function showApprovalDetail(approvalId: string): Promise<void> {
  const { approval, job } = await api.getApproval(approvalId);
  setScreen(shell("approval", renderApprovalDetail(approval, job, {
    approve: (targetApprovalId) => void decideApproval(targetApprovalId, "approve"),
    reject: (targetApprovalId) => void decideApproval(targetApprovalId, "reject"),
    openJob: (jobId) => visit(`/job/${encodeURIComponent(jobId)}`)
  })));
}

async function showActionRunDetail(actionRunId: string): Promise<void> {
  const { action_run } = await api.getActionRun(actionRunId);
  setScreen(shell("action", renderActionRunDetail(action_run, {
    openJob: (jobId) => visit(`/job/${encodeURIComponent(jobId)}`),
    openPage: (pageId) => visit(`/page/${encodeURIComponent(pageId)}`)
  })));
}

async function showCodex(): Promise<void> {
  const [state, { codex_runs }] = await Promise.all([api.getCodexState(), api.getCodexRuns()]);
  setScreen(shell("codex", renderCodexSurface(state, codex_runs, {
    submit: (prompt, effort, confirmDangerousMode) => void submitCodexPrompt(prompt, effort, confirmDangerousMode),
    openRun: (runId) => visit(`/codex/${encodeURIComponent(runId)}`)
  })));
}

async function showHistory(): Promise<void> {
  const { jobs } = await api.getJobs(200);
  const body = document.createElement("section");
  renderHistory(body, jobs, (job) => visit(`/job/${encodeURIComponent(job.id)}`));
  setScreen(shell("history", body));
}

async function showProfiles(): Promise<void> {
  const { profiles, default_id } = await api.getProfiles();
  setScreen(shell("profiles", renderProfilesPage(profiles, default_id, {
    openProfile: (profileId) => visit(`/profile/${encodeURIComponent(profileId)}`),
    createProfile: () => visit("/profiles/new")
  })));
}

async function showProfileFocus(profileId: string): Promise<void> {
  const [{ profiles }, { jobs }] = await Promise.all([api.getProfiles(), api.getJobs(50, profileId)]);
  const profile = profiles.find((item) => item.id === profileId);
  if (!profile) {
    renderNotFound(`/profile/${profileId}`);
    return;
  }
  setScreen(shell("profile", renderProfileFocus(profile, jobs, {
    runCommand: (text, selectedId) => void runCommand(text, selectedId),
    editProfile: (selectedId) => visit(`/profile/${encodeURIComponent(selectedId)}/edit`),
    openJob: (jobId) => visit(`/job/${encodeURIComponent(jobId)}`)
  })));
}

async function showProfileEditor(profileId: string | null): Promise<void> {
  const { profiles } = await api.getProfiles();
  const profile = profileId ? profiles.find((item) => item.id === profileId) || null : null;
  setScreen(shell("profile", renderProfileEditor(profile, {
    save: async (payload) => {
      const response = profile ? await api.updateProfile(profile.id, payload) : await api.createProfile(payload);
      localStorage.setItem(PROFILE_STORAGE_KEY, response.profile.id);
      visit(`/profile/${encodeURIComponent(response.profile.id)}`);
    },
    deleteProfile: async () => {
      if (profile) {
        await api.deleteProfile(profile.id);
      }
      visit("/profiles");
    }
  })));
}

function renderProfilePicker(profiles: Profile[], selectedId: string | null): HTMLElement {
  const wrapper = document.createElement("div");
  wrapper.className = "profile-picker-wrapper";

  const root = document.createElement("div");
  root.className = "profile-strip";

  const nameLabel = document.createElement("span");
  nameLabel.className = "profile-selected-name";
  nameLabel.style.cssText = "font-size:12px;color:rgba(255,255,255,0.65);margin-top:4px;display:block;";
  const initialProfile = profiles.find((p) => p.id === selectedId) || profiles[0];
  nameLabel.textContent = initialProfile?.name ?? "";

  for (const profile of profiles) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "profile-pick";
    button.dataset.profileId = profile.id;
    button.style.setProperty("--profile-color", profile.color);
    button.textContent = profile.emoji;
    button.title = profile.name;
    const isActive = profile.id === selectedId;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-pressed", String(isActive));
    button.addEventListener("click", () => {
      localStorage.setItem(PROFILE_STORAGE_KEY, profile.id);
      for (const item of root.querySelectorAll<HTMLButtonElement>(".profile-pick")) {
        const active = item === button;
        item.classList.toggle("active", active);
        item.setAttribute("aria-pressed", String(active));
      }
      nameLabel.textContent = profile.name;
    });
    root.append(button);
  }
  wrapper.append(root, nameLabel);
  return wrapper;
}

function selectedProfile(profiles: Profile[], defaultId: string | null): string | null {
  const stored = localStorage.getItem(PROFILE_STORAGE_KEY);
  if (stored && profiles.some((profile) => profile.id === stored)) {
    return stored;
  }
  return defaultId || profiles[0]?.id || null;
}

async function submitCodexPrompt(prompt: string, effort: CodexEffort, confirmDangerousMode: boolean): Promise<void> {
  try {
    const { codex_run } = await api.createCodexRun(prompt, effort, confirmDangerousMode);
    visit(`/codex/${encodeURIComponent(codex_run.id)}`);
  } catch (error) {
    toast(error instanceof Error ? error.message : "couldn't submit codex run", "error");
  }
}

async function showCodexRun(runId: string): Promise<void> {
  const { codex_run } = await api.getCodexRun(runId);
  setScreen(shell("codex", renderCodexRunDetail(codex_run, {
    refresh: () => void showCodexRun(runId),
    cancel: (targetRunId) => void cancelCodexRun(targetRunId)
  })));
  if (["queued", "running"].includes(codex_run.status)) {
    window.setTimeout(() => {
      if (window.location.pathname === `/codex/${runId}`) {
        void showCodexRun(runId);
      }
    }, 2000);
  }
}

async function cancelCodexRun(runId: string): Promise<void> {
  try {
    await api.cancelCodexRun(runId);
    await showCodexRun(runId);
  } catch (error) {
    toast(error instanceof Error ? error.message : "couldn't cancel run", "error");
  }
}

async function showVitals(filters: ActionRunFilters = {}): Promise<void> {
  const [vitals, actionRuns] = await Promise.all([api.getVitals(), api.getActionRuns(filters)]);
  setScreen(shell("vitals", renderVitalsSurface(
    vitals,
    actionRuns.action_runs,
    (actionRunId) => visit(`/action/${encodeURIComponent(actionRunId)}`),
    filters,
    (nextFilters) => visit(`/tile/vitals${auditFilterQuery(nextFilters)}`)
  )));
}

async function syncConnectorsAndReload(tile: "calendar" | "channels" | "spend"): Promise<void> {
  try {
    await api.syncConnectors();
    await openTile(tile);
  } catch (error) {
    toast(error instanceof Error ? error.message : "sync failed", "error");
  }
}

async function retryJob(jobId: string): Promise<void> {
  try {
    const { job_id } = await api.retryJob(jobId);
    visit(`/job/${encodeURIComponent(job_id)}`);
  } catch (error) {
    toast(error instanceof Error ? error.message : "couldn't retry job", "error");
  }
}

async function cancelJob(jobId: string): Promise<void> {
  try {
    await api.cancelJob(jobId);
    await showJobDetail(jobId);
  } catch (error) {
    toast(error instanceof Error ? error.message : "couldn't cancel job", "error");
  }
}

async function answerClarification(clarificationId: string, answer: string): Promise<void> {
  try {
    const { job_id } = await api.answerClarification(clarificationId, answer);
    visit(`/job/${encodeURIComponent(job_id)}`);
  } catch (error) {
    toast(error instanceof Error ? error.message : "couldn't answer clarification", "error");
  }
}

async function runTodoAction(action: string, todoId: string): Promise<void> {
  try {
    await api.runAction(action, { todo_id: todoId });
  } catch (error) {
    toast(error instanceof Error ? error.message : "action failed", "error");
    throw error;
  }
}

async function decideApproval(approvalId: string, decision: "approve" | "reject"): Promise<void> {
  try {
    if (decision === "approve") {
      await api.approveApproval(approvalId);
      toast("approved");
    } else {
      await api.rejectApproval(approvalId);
      toast("rejected");
    }
    await renderRoute();
  } catch (error) {
    toast(error instanceof Error ? error.message : "couldn't decide approval", "error");
  }
}

async function renderRecentActivity(): Promise<HTMLElement> {
  const root = document.createElement("section");
  root.className = "recent-activity";
  const { jobs } = await api.getJobs();
  const recent = jobs.slice(0, 3);
  if (recent.length === 0) {
    root.innerHTML = '<p class="eyebrow">recent</p><p class="empty">no jobs yet.</p>';
    return root;
  }
  root.innerHTML = '<p class="eyebrow">recent</p>';
  const list = document.createElement("div");
  list.className = "compact-list";
  for (const job of recent) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "activity-row";
    button.innerHTML = "<span></span><small></small>";
    button.querySelector("span")!.textContent = job.command;
    button.querySelector("small")!.textContent = job.status;
    button.addEventListener("click", () => visit(`/job/${encodeURIComponent(job.id)}`));
    list.append(button);
  }
  root.append(list);
  return root;
}

async function renderPinnedPages(): Promise<HTMLElement> {
  const root = document.createElement("section");
  root.className = "recent-activity";
  const { pages } = await api.getPages();
  const pinned = pages.filter((page) => page.pinned_at).slice(0, 3);
  if (pinned.length === 0) {
    return root;
  }
  root.innerHTML = '<p class="eyebrow">pinned</p>';
  const list = document.createElement("div");
  list.className = "compact-list";
  for (const page of pinned) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "activity-row";
    button.innerHTML = "<span></span><small></small>";
    button.querySelector("span")!.textContent = page.title;
    button.querySelector("small")!.textContent = "page";
    button.addEventListener("click", () => visit(`/page/${encodeURIComponent(page.id)}`));
    list.append(button);
  }
  root.append(list);
  return root;
}

function capabilityStatus(key: string, features: Record<string, unknown>): { configured: boolean; state: string; description: string } {
  if (key === "calendar") {
    return {
      configured: Boolean(features.calendar_writes),
      state: "approval gated",
      description: "calendar writes execute into the local hermes calendar after approval"
    };
  }
  if (key === "vitals") {
    return {
      configured: true,
      state: "available",
      description: "session, database, auth, action registry, job retry, and job cancel status are exposed"
    };
  }
  if (key === "spend") {
    return { configured: false, state: "not configured", description: "no spend data source is connected" };
  }
  if (key === "channels") {
    return { configured: false, state: "not configured", description: "no inbound channel connectors are configured" };
  }
  return { configured: false, state: "not configured", description: "this surface is not implemented yet" };
}

function renderSetup(message: string): void {
  const root = document.createElement("main");
  root.className = "shell setup-shell";
  const body = document.createElement("section");
  body.className = "list-screen setup-screen";
  body.innerHTML = `
    <p class="eyebrow">setup</p>
    <h1>connect</h1>
    <p class="empty"></p>
    <form class="setup-form">
      <label>api base<input name="base" autocomplete="off" placeholder="same origin or http://127.0.0.1:8000"></label>
      <label>token<input name="token" autocomplete="off" type="password" placeholder="home api token"></label>
      <button type="submit">save</button>
    </form>
    <p class="action-status"></p>
  `;
  body.querySelector(".empty")!.textContent = message;
  const form = body.querySelector<HTMLFormElement>(".setup-form")!;
  const base = form.elements.namedItem("base") as HTMLInputElement;
  const token = form.elements.namedItem("token") as HTMLInputElement;
  base.value = getHomeApiBase();
  token.value = getHomeApiToken() || "";
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const status = body.querySelector<HTMLElement>(".action-status")!;
    status.textContent = "checking connection...";
    setHomeApiBase(base.value);
    setHomeApiToken(token.value);
    api = createApiClient();
    try {
      sessionState = await api.getSession();
      visit("/");
    } catch (error) {
      status.textContent = error instanceof Error ? error.message : "connection failed";
    }
  });
  root.append(body);
  setScreen(root);
}

function renderFollowUpForm(label: string, prefix: string): HTMLElement {
  const form = document.createElement("form");
  form.className = "followup-form";
  form.innerHTML = `<label>${label} follow-up<input name="command" autocomplete="off"></label><button type="submit">send</button>`;
  const input = form.elements.namedItem("command") as HTMLInputElement;
  input.value = prefix;
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const text = input.value.trim();
    if (text) {
      await runCommand(text);
    }
  });
  return form;
}

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => undefined);
  });
}

window.addEventListener("popstate", () => {
  navDepth = Math.max(0, navDepth - 1);
  void renderRoute();
});

function auditFiltersFromParams(params: URLSearchParams): ActionRunFilters {
  return {
    action: params.get("action") || undefined,
    status: params.get("status") || undefined,
    source_job_id: params.get("source_job_id") || undefined,
    source_page_id: params.get("source_page_id") || undefined
  };
}

function auditFilterQuery(filters: ActionRunFilters): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value === undefined || value === "") {
      continue;
    }
    params.set(key, String(value));
  }
  const text = params.toString();
  return text ? `?${text}` : "";
}

async function boot(): Promise<void> {
  try {
    await renderRoute();
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      renderSetup("sign in with the site password, or enter the local api token to connect hermes home.");
      return;
    }
    renderSetup(error instanceof Error ? error.message : "couldn't reach hermes home api.");
  }
}

void boot();
