import type { Clarification, Job } from "./api";
import { el, emptyState, relativeDate } from "./ui";

type AskItem = Clarification & { job: Job | null };

type AskActions = {
  answer: (clarificationId: string, answer: string) => void | Promise<void>;
  openJob?: (jobId: string) => void;
};

export function renderAskSurface(items: AskItem[], actions: AskActions): HTMLElement {
  const root = document.createElement("section");
  root.className = "list-screen detail-screen";
  root.innerHTML = '<p class="eyebrow">your agents are asking</p>';

  if (items.length === 0) {
    root.append(emptyState("❓", "no open questions", "agents surface questions here when they need you"));
    return root;
  }

  for (const item of items) {
    root.append(renderQuestion(item, actions));
  }
  return root;
}

function renderQuestion(item: AskItem, actions: AskActions): HTMLElement {
  const card = el("article", "ask-card detail-card");
  const profile = item.job?.profile;
  const eyebrow = el("p", "ask-meta", `${profile ? `${profile.emoji} ${profile.name}` : "agent"} · ${relativeDate(item.created_at)}`);
  const question = el("h2", "ask-question", item.question);
  card.append(eyebrow, question);

  if (item.job) {
    const context = el("button", "ask-context link-button", item.job.command);
    context.addEventListener("click", () => actions.openJob?.(item.job!.id));
    card.append(context);
  }

  let submitting = false;
  const submit = (answer: string) => {
    const trimmed = answer.trim();
    if (!trimmed || submitting) {
      return;
    }
    submitting = true;
    card.classList.add("is-submitting");
    void Promise.resolve(actions.answer(item.id, trimmed));
  };

  if (item.choices.length > 0) {
    const choiceRow = el("div", "ask-choices");
    for (const choice of item.choices) {
      const button = el("button", "ask-choice chip");
      button.type = "button";
      button.textContent = choice;
      button.addEventListener("click", () => submit(choice));
      choiceRow.append(button);
    }
    card.append(choiceRow);
  }

  const form = el("form", "ask-form");
  const input = el("input", "ask-input");
  input.type = "text";
  input.placeholder = item.choices.length > 0 ? "or type your own answer" : "type your answer";
  const send = el("button", "ask-send", "send");
  send.type = "submit";
  form.append(input, send);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    submit(input.value);
  });
  card.append(form);
  return card;
}
