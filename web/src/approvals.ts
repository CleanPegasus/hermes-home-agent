import type { Approval, Job } from "./api";
import { addFact, statusEmoji } from "./ui";

type ApprovalActions = {
  approve: (approvalId: string) => void;
  reject: (approvalId: string) => void;
  openJob: (jobId: string) => void;
  openApproval?: (approvalId: string) => void;
};

export function renderApprovals(approvals: Approval[], actions: ApprovalActions): HTMLElement {
  const root = document.createElement("section");
  root.className = "list-screen";
  root.innerHTML = '<p class="eyebrow">trust inbox</p><h1>approvals</h1>';

  const list = document.createElement("div");
  list.className = "metro-list";
  const pending = approvals.filter((approval) => approval.status === "pending");
  const rest = approvals.filter((approval) => approval.status !== "pending");

  if (approvals.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "nothing needs approval.";
    list.append(empty);
  }

  for (const approval of [...pending, ...rest]) {
    list.append(renderApprovalRow(approval, actions));
  }

  root.append(list);
  return root;
}

function renderApprovalRow(approval: Approval, actions: ApprovalActions): HTMLElement {
  const row = document.createElement("article");
  row.className = `approval-card ${approval.status}`;

  const header = document.createElement("div");
  header.className = "approval-header";
  const title = document.createElement("h2");
  title.textContent = approval.action;
  const status = document.createElement("small");
  status.textContent = `${statusEmoji(approval.status)} ${approval.status}`;
  header.append(title, status);

  const scope = document.createElement("pre");
  scope.className = "scope-preview";
  scope.textContent = JSON.stringify(approval.scope || {}, null, 2);

  const buttons = document.createElement("div");
  buttons.className = "page-actions";
  if (approval.status === "pending") {
    const approve = document.createElement("button");
    approve.type = "button";
    approve.className = "page-action";
    approve.textContent = "approve";
    approve.addEventListener("click", () => actions.approve(approval.id));

    const reject = document.createElement("button");
    reject.type = "button";
    reject.className = "page-action danger";
    reject.textContent = "reject";
    reject.addEventListener("click", () => actions.reject(approval.id));

    buttons.append(approve, reject);
  }
  if (actions.openApproval) {
    const detail = document.createElement("button");
    detail.type = "button";
    detail.className = "page-action secondary";
    detail.textContent = "details";
    detail.addEventListener("click", () => actions.openApproval?.(approval.id));
    buttons.append(detail);
  }
  if (approval.job_id) {
    const job = document.createElement("button");
    job.type = "button";
    job.className = "page-action secondary";
    job.textContent = "source job";
    job.addEventListener("click", () => actions.openJob(approval.job_id!));
    buttons.append(job);
  }

  row.append(header, scope, buttons);
  return row;
}

export function renderApprovalDetail(approval: Approval, job: Job | null, actions: ApprovalActions): HTMLElement {
  const root = document.createElement("section");
  root.className = "list-screen detail-screen";
  root.innerHTML = '<p class="eyebrow">approval detail</p><h1></h1>';
  root.querySelector("h1")!.textContent = approval.action;

  const facts = document.createElement("dl");
  facts.className = "fact-list";
  addFact(facts, "status", approval.status);
  addFact(facts, "expires", approval.expires_at || "not set");
  addFact(facts, "decided", approval.decided_at || "not decided");
  addFact(facts, "source job", approval.job_id || "none");
  if (job) {
    addFact(facts, "command", job.command);
  }

  const scope = document.createElement("pre");
  scope.className = "scope-preview diagnostic-json";
  scope.textContent = JSON.stringify({ scope: approval.scope, result: approval.result, error: approval.error }, null, 2);

  const buttons = document.createElement("div");
  buttons.className = "page-actions";
  if (approval.status === "pending") {
    const approve = document.createElement("button");
    approve.type = "button";
    approve.className = "page-action";
    approve.textContent = "approve";
    approve.addEventListener("click", () => actions.approve(approval.id));

    const reject = document.createElement("button");
    reject.type = "button";
    reject.className = "page-action danger";
    reject.textContent = "reject";
    reject.addEventListener("click", () => actions.reject(approval.id));
    buttons.append(approve, reject);
  }
  if (approval.job_id) {
    const source = document.createElement("button");
    source.type = "button";
    source.className = "page-action secondary";
    source.textContent = "source job";
    source.addEventListener("click", () => actions.openJob(approval.job_id!));
    buttons.append(source);
  }

  root.append(facts, buttons, scope);
  return root;
}
