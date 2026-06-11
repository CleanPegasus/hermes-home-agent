import type { Todo } from "./api";

export function renderTodos(todos: Todo[]): HTMLElement {
  const root = document.createElement("section");
  root.className = "list-screen";
  root.innerHTML = '<p class="eyebrow">agent canonical</p><h1>todos</h1>';
  const tabs = document.createElement("div");
  tabs.className = "pivot-tabs";
  tabs.innerHTML = "<span>today</span><span>upcoming</span>";
  const list = document.createElement("div");
  list.className = "metro-list";

  if (todos.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "nothing due - hermes will add work here when it belongs.";
    list.append(empty);
  }

  for (const todo of todos) {
    const row = document.createElement("div");
    row.className = `list-row todo-row ${todo.status}`;
    const box = document.createElement("span");
    box.className = "wp-checkbox";
    box.textContent = todo.status === "done" ? "x" : "";
    const text = document.createElement("span");
    text.textContent = todo.title;
    const source = document.createElement("small");
    source.textContent = `added by ${todo.source}`;
    row.append(box, text, source);
    list.append(row);
  }
  root.append(tabs, list);
  return root;
}
