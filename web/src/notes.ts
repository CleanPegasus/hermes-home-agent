import type { Category, Note } from "./api";
import { armConfirm, chip, emptyState, stripMarkdown } from "./ui";

type NotesSurfaceState = {
  configured?: boolean;
  warning?: string | null;
  onSearch?: (filters: { q?: string; category?: string }) => Promise<Note[]>;
};

export function renderNotes(notes: Note[], categories: Category[] = [], onOpen?: (noteId: string) => void, state: NotesSurfaceState = {}): HTMLElement {
  const openNote = onOpen;
  const root = document.createElement("section");
  root.className = "list-screen";
  root.innerHTML = '<p class="eyebrow">hermes native</p>';
  if (state.configured === false) {
    root.append(emptyState("📂", "connect your obsidian vault", state.warning || undefined));
    return root;
  }

  const search = document.createElement("input");
  search.className = "search";
  search.placeholder = "search notes";
  search.type = "search";

  const pivots = document.createElement("div");
  pivots.className = "pivot-tabs scroll";
  const all = document.createElement("button");
  all.type = "button";
  all.className = "pivot-button active";
  all.textContent = "all";
  pivots.append(all);
  for (const category of categories) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "pivot-button";
    button.textContent = category.slug;
    button.dataset.category = category.slug;
    pivots.append(button);
  }

  const list = document.createElement("div");
  list.className = "metro-list";

  let activeCategory: string | null = null;
  let visibleNotes = notes;
  let searchTimer: number | null = null;
  const renderList = () => {
    const query = search.value.trim().toLowerCase();
    const visible = visibleNotes.filter((note) => {
      const matchesCategory = !activeCategory || note.category === activeCategory;
      const haystack = `${note.title} ${note.body_md}`.toLowerCase();
      return matchesCategory && (!query || haystack.includes(query));
    });
    list.replaceChildren();
    if (visible.length === 0) {
      const empty = document.createElement("p");
      empty.className = "empty";
      empty.textContent = "nothing filed here yet - hermes will use it when something fits.";
      list.append(empty);
      return;
    }

    for (const note of visible) {
      const row = document.createElement(openNote ? "button" : "div");
      row.className = "list-row note-row";
      if (row instanceof HTMLButtonElement) {
        row.type = "button";
        row.addEventListener("click", () => openNote?.(note.id));
      }
      const title = document.createElement("span");
      title.textContent = note.title;
      const snippet = document.createElement("small");
      snippet.textContent = stripMarkdown(note.body_md).slice(0, 140);
      const tags = document.createElement("div");
      tags.className = "note-tags";
      for (const tag of note.tags) {
        tags.append(chip(tag));
      }
      row.append(title, snippet, tags);
      list.append(row);
    }
  };

  const refreshFromServer = () => {
    if (!state.onSearch) {
      renderList();
      return;
    }
    const filters = {
      q: search.value.trim() || undefined,
      category: activeCategory || undefined
    };
    void state.onSearch(filters).then((nextNotes) => {
      visibleNotes = nextNotes;
      renderList();
    });
  };

  search.addEventListener("input", () => {
    if (searchTimer) {
      window.clearTimeout(searchTimer);
    }
    searchTimer = window.setTimeout(refreshFromServer, 250);
  });
  pivots.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLButtonElement)) {
      return;
    }
    for (const button of pivots.querySelectorAll("button")) {
      button.classList.toggle("active", button === target);
    }
    activeCategory = target.dataset.category || null;
    refreshFromServer();
  });

  if (categories.length === 0) {
    const emptyCategory = document.createElement("small");
    emptyCategory.textContent = "categories unavailable";
    pivots.append(emptyCategory);
  }

  renderList();
  root.append(search, pivots, list);
  return root;
}

type NoteDetailActions = {
  save: (noteId: string, changes: { title: string; body_md: string; category: string; tags: string[] }) => void;
  archive: (noteId: string) => void;
  merge: (noteId: string, targetNoteId: string) => void;
  openJob?: (jobId: string) => void;
};

export function renderNoteDetail(note: Note, categories: Category[], allNotes: Note[], actions: NoteDetailActions): HTMLElement {
  const root = document.createElement("section");
  root.className = "list-screen detail-screen";
  root.innerHTML = '<p class="eyebrow">memory</p><h1>note</h1>';

  const form = document.createElement("form");
  form.className = "note-form";
  form.innerHTML = `
    <label>title<input name="title" autocomplete="off"></label>
    <label>category<select name="category"></select></label>
    <label>tags<input name="tags" autocomplete="off"></label>
    <label>body<textarea name="body" rows="12"></textarea></label>
    <div class="page-actions">
      <button type="submit" class="page-action">save</button>
      <button type="button" class="page-action danger" data-action="archive">archive</button>
    </div>
  `;
  const title = form.elements.namedItem("title") as HTMLInputElement;
  const category = form.elements.namedItem("category") as HTMLSelectElement;
  const tags = form.elements.namedItem("tags") as HTMLInputElement;
  const body = form.elements.namedItem("body") as HTMLTextAreaElement;
  title.value = note.title;
  body.value = note.body_md;
  tags.value = note.tags.join(", ");

  const empty = document.createElement("option");
  empty.value = "inbox";
  empty.textContent = "inbox";
  category.append(empty);
  for (const item of categories) {
    const option = document.createElement("option");
    option.value = item.slug;
    option.textContent = item.slug;
    option.selected = item.slug === note.category;
    category.append(option);
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    actions.save(note.id, {
      title: title.value,
      body_md: body.value,
      category: category.value || "inbox",
      tags: tags.value.split(",").map((tag) => tag.trim()).filter(Boolean)
    });
  });
  const archiveButton = form.querySelector<HTMLButtonElement>('[data-action="archive"]');
  if (archiveButton) {
    armConfirm(archiveButton, "tap again to archive", () => {
      actions.archive(note.id);
    });
  }

  const merge = document.createElement("form");
  merge.className = "merge-form";
  merge.innerHTML = `
    <p class="eyebrow">merge into</p>
    <select name="target"></select>
    <button type="button" class="inline-action">merge</button>
  `;
  const target = merge.elements.namedItem("target") as HTMLSelectElement;
  for (const other of allNotes.filter((item) => item.id !== note.id)) {
    const option = document.createElement("option");
    option.value = other.id;
    option.textContent = other.title;
    target.append(option);
  }
  const mergeButton = merge.querySelector<HTMLButtonElement>("button[type='button']")!;
  armConfirm(mergeButton, "tap again to merge", () => {
    if (target.value) {
      actions.merge(note.id, target.value);
    }
  });

  root.append(form);
  if (note.source_job_id && actions.openJob) {
    const source = document.createElement("button");
    source.type = "button";
    source.className = "page-action secondary";
    source.textContent = "source job";
    source.addEventListener("click", () => actions.openJob?.(note.source_job_id!));
    root.append(source);
  }
  if (target.options.length > 0) {
    root.append(merge);
  }
  return root;
}
