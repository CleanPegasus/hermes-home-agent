import type { CodexEffort, CodexRun, CodexState } from "./api";
import { addFact, block, factsList, shortDate } from "./ui";

type CodexActions = {
  submit: (prompt: string, effort: CodexEffort, confirmDangerousMode: boolean) => void;
  openRun: (runId: string) => void;
  refresh?: () => void;
  cancel?: (runId: string) => void;
};

const FALLBACK_EFFORT_OPTIONS: CodexEffort[] = ["low", "medium", "high", "xhigh"];

export function renderCodexSurface(state: CodexState, runs: CodexRun[], actions: CodexActions): HTMLElement {
  const root = document.createElement("section");
  root.className = "list-screen detail-screen";
  root.innerHTML = '<p class="eyebrow">codex</p><h1>codex</h1>';

  const form = document.createElement("form");
  form.className = "codex-form";
  const promptLabel = document.createElement("label");
  promptLabel.textContent = "prompt";
  const promptInput = document.createElement("textarea");
  promptInput.name = "prompt";
  promptInput.rows = 5;
  promptInput.setAttribute("autocomplete", "off");
  promptLabel.append(promptInput);

  const effortOptions = codexEffortOptions(state);
  let selectedEffort = normalizeEffort(state.effort, effortOptions);
  const effortField = document.createElement("fieldset");
  effortField.className = "effort-field";
  const effortLegend = document.createElement("legend");
  effortLegend.textContent = "session effort";
  const effortToggle = document.createElement("div");
  effortToggle.className = "effort-toggle";
  effortToggle.setAttribute("role", "group");
  effortToggle.setAttribute("aria-label", "session effort");
  const effortButtons = effortOptions.map((effort) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = effort;
    button.dataset.effort = effort;
    button.addEventListener("click", () => {
      selectedEffort = effort;
      syncEffortButtons(effortButtons, selectedEffort);
    });
    return button;
  });
  effortToggle.append(...effortButtons);
  effortField.append(effortLegend, effortToggle);
  syncEffortButtons(effortButtons, selectedEffort);

  const confirmation = document.createElement("label");
  confirmation.className = "codex-confirm";
  const confirmationInput = document.createElement("input");
  confirmationInput.type = "checkbox";
  confirmationInput.name = "confirmDangerousMode";
  const confirmationText = document.createElement("span");
  confirmationText.textContent = "i understand this runs Codex with bypassed approvals and must review the diff before deploy";
  confirmation.append(confirmationInput, confirmationText);

  const status = document.createElement("p");
  status.className = "action-status";

  const submit = document.createElement("button");
  submit.type = "submit";
  submit.textContent = "create chat";
  submit.disabled = !state.enabled || !state.binary_available;
  form.append(promptLabel, effortField, confirmation, submit, status);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const prompt = promptInput.value.trim();
    if (!prompt) {
      return;
    }
    if (!state.enabled) {
      status.textContent = state.disabled_reason || "codex execution is disabled.";
      return;
    }
    if (!state.binary_available) {
      status.textContent = "codex binary is not available.";
      return;
    }
    if (state.requires_confirmation && !confirmationInput.checked) {
      status.textContent = "confirm dangerous mode before creating a chat.";
      return;
    }
    actions.submit(prompt, selectedEffort, confirmationInput.checked);
  });

  root.append(
    factsList([
      ["enabled", state.enabled ? "yes" : "no"],
      ["available", state.available ? "yes" : "no"],
      ["binary", state.binary_available ? "yes" : "no"],
      ["workdir", state.workdir],
      ["mode", state.mode],
      ["default effort", state.effort],
      ["dirty", state.dirty ? "yes" : "no"],
      ["review", "inspect before and after status plus diff stat before deploy"],
    ]),
    diagnosticBlock("worktree status", state.status_short || "clean"),
    diagnosticBlock("diff stat", state.diff_stat || "empty"),
    form,
    codexRunList(runs, actions.openRun)
  );
  return root;
}

export function renderCodexRunDetail(run: CodexRun, actions: Pick<CodexActions, "refresh" | "cancel"> = {}): HTMLElement {
  const root = document.createElement("section");
  root.className = "list-screen detail-screen";
  root.innerHTML = '<p class="eyebrow">codex run</p><h1></h1>';
  root.querySelector("h1")!.textContent = run.status;

  const controls = document.createElement("div");
  controls.className = "page-actions";
  if (actions.refresh) {
    const refresh = document.createElement("button");
    refresh.type = "button";
    refresh.className = "page-action";
    refresh.textContent = "refresh";
    refresh.addEventListener("click", () => actions.refresh?.());
    controls.append(refresh);
  }
  if (actions.cancel && ["queued", "running"].includes(run.status)) {
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "page-action danger";
    cancel.textContent = "cancel";
    cancel.addEventListener("click", () => actions.cancel?.(run.id));
    controls.append(cancel);
  }

  const facts = document.createElement("dl");
  facts.className = "fact-list";
  addFact(facts, "workdir", run.workdir);
  addFact(facts, "mode", "yolo");
  addFact(facts, "effort", run.effort);
  addFact(facts, "pid", run.process_id === null ? "none" : String(run.process_id));
  addFact(facts, "cancel requested", run.cancel_requested ? "yes" : "no");
  addFact(facts, "started", run.started_at || "not started");
  addFact(facts, "finished", run.finished_at || "not finished");
  if (run.exit_code !== null) {
    addFact(facts, "exit", String(run.exit_code));
  }
  if (run.error) {
    addFact(facts, "error", run.error);
  }

  const prompt = diagnosticBlock("prompt", run.prompt);
  const before = diagnosticBlock("before status", run.before_status || "clean");
  const after = diagnosticBlock("after status", run.after_status || "not captured yet");
  const diff = diagnosticBlock("diff stat", run.diff_stat || "empty");
  const stdout = diagnosticBlock("stdout", run.stdout_tail || "");
  const stderr = diagnosticBlock("stderr", run.stderr_tail || "");
  root.append(controls, facts, prompt, before, after, diff, stdout, stderr);
  return root;
}

function codexRunList(runs: CodexRun[], openRun: (runId: string) => void): HTMLElement {
  const root = document.createElement("section");
  root.className = "surface-list";
  const title = document.createElement("h2");
  title.textContent = "previous prompts";
  const list = document.createElement("div");
  list.className = "metro-list compact-list";
  if (runs.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "nothing here yet.";
    list.append(empty);
  }
  for (const run of runs) {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "list-row";
    row.innerHTML = "<span></span><small></small>";
    row.querySelector("span")!.textContent = run.prompt;
    row.querySelector("small")!.textContent = `${run.effort} · ${run.status}${run.started_at ? ` · ${shortDate(run.started_at)}` : ""}`;
    row.addEventListener("click", () => openRun(run.id));
    list.append(row);
  }
  root.append(title, list);
  return root;
}

function diagnosticBlock(label: string, value: string): HTMLElement {
  const pre = document.createElement("pre");
  pre.className = "scope-preview diagnostic-json";
  pre.textContent = value || "empty";
  return block(label, pre);
}

function codexEffortOptions(state: CodexState): CodexEffort[] {
  const options = (state.effort_options || []).filter(isCodexEffort);
  return options.length > 0 ? options : FALLBACK_EFFORT_OPTIONS;
}

function normalizeEffort(value: CodexEffort, options: CodexEffort[]): CodexEffort {
  return options.includes(value) ? value : options[0] || "xhigh";
}

function isCodexEffort(value: string): value is CodexEffort {
  return FALLBACK_EFFORT_OPTIONS.includes(value as CodexEffort);
}

function syncEffortButtons(buttons: HTMLButtonElement[], selectedEffort: CodexEffort): void {
  for (const button of buttons) {
    const active = button.dataset.effort === selectedEffort;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  }
}
