import type { Note } from "./api";

export function renderNotes(notes: Note[]): HTMLElement {
  const root = document.createElement("section");
  root.className = "list-screen";
  root.innerHTML = '<p class="eyebrow">hermes native</p><h1>notes</h1>';

  const search = document.createElement("input");
  search.className = "search";
  search.placeholder = "search notes";
  search.type = "search";

  const pivots = document.createElement("div");
  pivots.className = "pivot-tabs scroll";
  for (const label of ["work", "ideas", "home", "personal", "health"]) {
    const span = document.createElement("span");
    span.textContent = label;
    pivots.append(span);
  }

  const list = document.createElement("div");
  list.className = "metro-list";
  if (notes.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "nothing filed here yet - hermes will use it when something fits.";
    list.append(empty);
  }

  for (const note of notes) {
    const row = document.createElement("div");
    row.className = "list-row note-row";
    const title = document.createElement("span");
    title.textContent = note.title;
    const snippet = document.createElement("small");
    snippet.textContent = note.body_md.slice(0, 96);
    row.append(title, snippet);
    list.append(row);
  }

  root.append(search, pivots, list);
  return root;
}
