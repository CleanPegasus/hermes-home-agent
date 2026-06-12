import type { Todo, TodoLabel, TodoProject } from "./api";
import { chip, emptyState } from "./ui";

type TodoActions = {
  complete: (todoId: string) => Promise<void>;
  reopen: (todoId: string) => Promise<void>;
  drop: (todoId: string) => Promise<void>;
};

type TodoSurfaceState = {
  configured?: boolean;
  warning?: string | null;
  projects?: TodoProject[];
  labels?: TodoLabel[];
};

type TodoFilter = Todo["status"];
const FILTERS: TodoFilter[] = ["open", "done", "dropped"];

export function renderTodos(todos: Todo[], actions?: TodoActions, state: TodoSurfaceState = {}): HTMLElement {
  const root = document.createElement("section");
  root.className = "list-screen";
  root.innerHTML = '<p class="eyebrow">agent canonical</p>';
  const tabs = document.createElement("div");
  tabs.className = "pivot-tabs";
  tabs.setAttribute("role", "tablist");
  const list = document.createElement("div");
  list.className = "metro-list";
  let activeFilter: TodoFilter = "open";
  let activeProjectId = "all";
  let activeLabel = "";

  for (const filter of FILTERS) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "pivot-button";
    button.dataset.filter = filter;
    button.setAttribute("role", "tab");
    button.textContent = `${filter} ${todos.filter((todo) => todo.status === filter).length}`;
    button.addEventListener("click", () => {
      activeFilter = filter;
      renderFilteredTodos();
    });
    tabs.append(button);
  }

  if (state.configured === false) {
    const setup = document.createElement("div");
    setup.className = "todo-setup";
    setup.append(emptyState("🔗", "connect Vikunja to sync todos. Set VIKUNJA_URL and VIKUNJA_TOKEN on the server.", state.warning || undefined));
    list.append(setup);
    root.append(tabs, list);
    return root;
  }

  const projectTabs = renderProjectTabs(state.projects || [], (projectId) => {
    activeProjectId = projectId;
    renderFilteredTodos();
  });
  const labelTabs = renderLabelTabs(state.labels || [], (label) => {
    activeLabel = label;
    renderFilteredTodos();
  });

  function updateCounts(): void {
    for (const button of tabs.querySelectorAll<HTMLButtonElement>(".pivot-button[data-filter]")) {
      const filter = button.dataset.filter as TodoFilter;
      button.textContent = `${filter} ${todos.filter((todo) => todo.status === filter).length}`;
    }
  }

  function renderFilteredTodos(): void {
    list.replaceChildren();
    for (const button of tabs.querySelectorAll<HTMLButtonElement>(".pivot-button")) {
      const active = button.dataset.filter === activeFilter;
      button.classList.toggle("active", active);
      button.setAttribute("aria-selected", String(active));
    }
    syncFilterButtons(projectTabs, "[data-project-id]", activeProjectId);
    syncFilterButtons(labelTabs, "[data-label]", activeLabel);
    const filtered = filterTodos(todos, activeFilter, activeProjectId, activeLabel);
    if (filtered.length === 0) {
      const empty = document.createElement("p");
      empty.className = "empty";
      empty.textContent = emptyMessage(activeFilter);
      list.append(empty);
      return;
    }
    for (const todo of filtered) {
      list.append(renderTodoRow(todo, actions ? makeActionHandler(todo) : undefined));
    }
  }

  function makeActionHandler(todo: Todo) {
    return async (kind: "complete" | "reopen" | "drop", _todo: Todo, controls: HTMLElement): Promise<void> => {
      const scope = controls.parentElement ?? controls;
      const buttons = scope.querySelectorAll<HTMLButtonElement>("button");
      for (const btn of buttons) {
        btn.disabled = true;
      }
      try {
        if (kind === "complete") {
          await actions!.complete(todo.id);
          todo.status = "done";
        } else if (kind === "reopen") {
          await actions!.reopen(todo.id);
          todo.status = "open";
        } else {
          await actions!.drop(todo.id);
          todo.status = "dropped";
        }
        updateCounts();
        renderFilteredTodos();
      } catch {
        // main.ts already toasted the error — just re-enable the buttons
        for (const btn of buttons) {
          btn.disabled = false;
        }
      }
    };
  }

  renderFilteredTodos();
  root.append(tabs, projectTabs, labelTabs, list);
  return root;
}

export function filterTodos(todos: Todo[], status: TodoFilter, projectId = "all", label = ""): Todo[] {
  return todos.filter((todo) => {
    const matchesStatus = todo.status === status;
    const matchesProject = projectId === "all" || todo.project_id === projectId;
    const matchesLabel = !label || todo.tags.some((tag) => tag.toLowerCase() === label.toLowerCase());
    return matchesStatus && matchesProject && matchesLabel;
  });
}

function renderTodoRow(todo: Todo, onAction?: (kind: "complete" | "reopen" | "drop", todo: Todo, controls: HTMLElement) => Promise<void>): HTMLElement {
  const row = document.createElement("div");
  row.className = `list-row todo-row ${todo.status}`;
  const box = document.createElement("button");
  box.type = "button";
  box.className = "wp-checkbox";
  box.textContent = todo.status === "done" ? "x" : "";
  const text = document.createElement("span");
  text.textContent = todo.title;
  const meta = document.createElement("small");
  meta.className = "todo-meta";
  const metaLine = document.createElement("span");
  metaLine.textContent = todoMeta(todo);
  meta.append(metaLine, renderTodoChips(todo), renderPriority(todo), renderDue(todo));
  row.append(box, text, meta);
  if (onAction) {
    const controls = document.createElement("div");
    controls.className = "row-actions";
    if (todo.status === "open") {
      box.setAttribute("aria-label", "mark done");
      box.addEventListener("click", () => void onAction("complete", todo, controls));
      controls.append(
        actionButton("done", () => void onAction("complete", todo, controls)),
        actionButton("drop", () => void onAction("drop", todo, controls), "danger")
      );
    } else {
      box.setAttribute("aria-label", "reopen");
      box.addEventListener("click", () => void onAction("reopen", todo, controls));
      controls.append(actionButton("reopen", () => void onAction("reopen", todo, controls)));
    }
    row.append(controls);
  } else {
    box.setAttribute("aria-label", todo.status === "done" ? "done" : "open");
    box.disabled = true;
  }
  return row;
}

function renderProjectTabs(projects: TodoProject[], onSelect: (projectId: string) => void): HTMLElement {
  const root = document.createElement("div");
  root.className = "pivot-tabs secondary";
  const all = document.createElement("button");
  all.type = "button";
  all.className = "pivot-button active";
  all.dataset.projectId = "all";
  all.textContent = "all";
  all.addEventListener("click", () => onSelect("all"));
  root.append(all);
  for (const project of projects) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "pivot-button";
    button.dataset.projectId = project.id;
    button.textContent = project.title;
    button.addEventListener("click", () => onSelect(project.id));
    root.append(button);
  }
  return root;
}

function renderLabelTabs(labels: TodoLabel[], onSelect: (label: string) => void): HTMLElement {
  const root = document.createElement("div");
  root.className = "label-filter-strip";
  const all = document.createElement("button");
  all.type = "button";
  all.className = "chip active";
  all.dataset.label = "";
  all.textContent = "all labels";
  all.addEventListener("click", () => onSelect(""));
  root.append(all);
  for (const label of labels) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "chip";
    button.dataset.label = label.title;
    button.style.setProperty("--chip-color", label.hex_color);
    button.textContent = label.title;
    button.addEventListener("click", () => onSelect(label.title));
    root.append(button);
  }
  return root;
}

function syncFilterButtons(root: HTMLElement, selector: string, activeValue: string): void {
  for (const button of root.querySelectorAll<HTMLButtonElement>(selector)) {
    const value = button.dataset.projectId ?? button.dataset.label ?? "";
    button.classList.toggle("active", value === activeValue);
  }
}

function renderTodoChips(todo: Todo): HTMLElement {
  const root = document.createElement("span");
  root.className = "todo-chips";
  if (todo.project) {
    root.append(chip(todo.project));
  }
  for (const tag of todo.tags) {
    root.append(chip(tag));
  }
  return root;
}

function renderPriority(todo: Todo): HTMLElement {
  const root = document.createElement("span");
  root.className = "todo-priority";
  const value = todo.priority || 0;
  root.textContent = value >= 3 ? "!".repeat(Math.min(3, value - 2)) : "";
  return root;
}

function renderDue(todo: Todo): HTMLElement {
  const root = document.createElement("span");
  root.className = "todo-due";
  if (!todo.due_at) {
    return root;
  }
  const overdue = todo.status === "open" && new Date(todo.due_at).getTime() < Date.now();
  root.classList.toggle("overdue", overdue);
  root.textContent = `📅 ${formatDate(todo.due_at)}`;
  return root;
}

function emptyMessage(filter: TodoFilter): string {
  if (filter === "open") {
    return "nothing due - hermes will add work here when it belongs.";
  }
  if (filter === "done") {
    return "nothing completed yet.";
  }
  return "nothing dropped.";
}

function actionButton(label: string, onClick: () => void, className = ""): HTMLButtonElement {
  const button = document.createElement("button");
  button.type = "button";
  button.className = `inline-action ${className}`.trim();
  button.textContent = label;
  button.addEventListener("click", onClick);
  return button;
}

function todoMeta(todo: Todo): string {
  const parts = [todo.provider ? `${todo.provider} · ${todo.source}` : `added by ${todo.source}`];
  if (todo.project) {
    parts.push(todo.project);
  }
  if (todo.scheduled_for) {
    parts.push(`scheduled ${formatDate(todo.scheduled_for)}`);
  }
  return parts.join(" · ");
}

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleDateString([], { month: "short", day: "numeric" }).toLowerCase();
}
