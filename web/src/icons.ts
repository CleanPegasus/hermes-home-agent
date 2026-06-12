function svg(paths: string[]): SVGSVGElement {
  const ns = "http://www.w3.org/2000/svg";
  const el = document.createElementNS(ns, "svg") as SVGSVGElement;
  el.setAttribute("viewBox", "0 0 24 24");
  el.setAttribute("fill", "none");
  el.setAttribute("stroke", "currentColor");
  el.setAttribute("stroke-width", "1.6");
  el.setAttribute("stroke-linecap", "round");
  el.setAttribute("stroke-linejoin", "round");
  el.setAttribute("aria-hidden", "true");
  for (const d of paths) {
    const path = document.createElementNS(ns, "path");
    path.setAttribute("d", d);
    el.append(path);
  }
  return el;
}

function polyline(points: string): SVGSVGElement {
  const ns = "http://www.w3.org/2000/svg";
  const el = document.createElementNS(ns, "svg") as SVGSVGElement;
  el.setAttribute("viewBox", "0 0 24 24");
  el.setAttribute("fill", "none");
  el.setAttribute("stroke", "currentColor");
  el.setAttribute("stroke-width", "1.6");
  el.setAttribute("stroke-linecap", "round");
  el.setAttribute("stroke-linejoin", "round");
  el.setAttribute("aria-hidden", "true");
  const pl = document.createElementNS(ns, "polyline");
  pl.setAttribute("points", points);
  el.append(pl);
  return el;
}

const ICONS: Record<string, () => SVGSVGElement> = {
  // checkmark inside a square outline
  todos: () =>
    svg([
      "M3 3h18v18H3z",
      "M7 12l3.5 3.5L17 9"
    ]),

  // page outline with folded corner + two short rule lines
  notes: () =>
    svg([
      "M4 4h11l5 5v11H4z",
      "M15 4v5h5",
      "M8 13h8",
      "M8 17h5"
    ]),

  // lightning bolt
  jobs: () =>
    svg(["M13 2L4.5 13.5H11L10 22L19.5 10.5H13L13 2z"]),

  // calendar outline with binding ticks and one day dot
  calendar: () =>
    svg([
      "M3 6h18v15H3z",
      "M3 10h18",
      "M8 3v3",
      "M16 3v3",
      "M8 14h.01"
    ]),

  // shield outline with small check
  approvals: () =>
    svg([
      "M12 3L4 7v5c0 5 3.6 9.1 8 10 4.4-.9 8-5 8-10V7L12 3z",
      "M9 12l2 2 4-4"
    ]),

  // rounded-square chat bubble with tail
  channels: () =>
    svg([
      "M4 4h16a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H8l-4 3V6a2 2 0 0 1 2-2z"
    ]),

  // banknote: rounded rectangle with center circle
  spend: () => {
    const ns = "http://www.w3.org/2000/svg";
    const el = document.createElementNS(ns, "svg") as SVGSVGElement;
    el.setAttribute("viewBox", "0 0 24 24");
    el.setAttribute("fill", "none");
    el.setAttribute("stroke", "currentColor");
    el.setAttribute("stroke-width", "1.6");
    el.setAttribute("stroke-linecap", "round");
    el.setAttribute("stroke-linejoin", "round");
    el.setAttribute("aria-hidden", "true");
    const rect = document.createElementNS(ns, "rect");
    rect.setAttribute("x", "3");
    rect.setAttribute("y", "7");
    rect.setAttribute("width", "18");
    rect.setAttribute("height", "10");
    rect.setAttribute("rx", "1");
    const circle = document.createElementNS(ns, "circle");
    circle.setAttribute("cx", "12");
    circle.setAttribute("cy", "12");
    circle.setAttribute("r", "2.5");
    el.append(rect, circle);
    return el;
  },

  // pulse / heartbeat polyline
  vitals: () => {
    const el = polyline("2 12 6 12 8 6 10 18 13 8 15 14 17 12 22 12");
    return el;
  },

  // terminal prompt: > chevron + underscore cursor
  codex: () =>
    svg([
      "M5 9l5 3-5 3",
      "M13 18h6"
    ]),

  // head-and-shoulders outline
  profiles: () =>
    svg([
      "M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z",
      "M3 21c0-4.4 4-8 9-8s9 3.6 9 8"
    ]),

  // circle with clock hands
  history: () =>
    svg([
      "M12 2a10 10 0 1 0 0 20A10 10 0 0 0 12 2z",
      "M12 6v6l3.5 2"
    ]),

  // status: done — simple check
  done: () =>
    svg(["M4 12l5.5 5.5L20 7"]),

  // status: failed — X
  failed: () =>
    svg(["M6 6l12 12", "M18 6L6 18"]),

  // status: running — play triangle inside circle
  running: () =>
    svg([
      "M12 2a10 10 0 1 0 0 20A10 10 0 0 0 12 2z",
      "M10 8l6 4-6 4z"
    ]),

  // status: queued — clock
  queued: () =>
    svg([
      "M12 2a10 10 0 1 0 0 20A10 10 0 0 0 12 2z",
      "M12 6v6l4 2"
    ]),

  // status: cancelled — slashed circle
  cancelled: () =>
    svg([
      "M12 2a10 10 0 1 0 0 20A10 10 0 0 0 12 2z",
      "M4.9 4.9l14.2 14.2"
    ]),

  // status: needs_approval — shield
  needs_approval: () =>
    svg([
      "M12 3L4 7v5c0 5 3.6 9.1 8 10 4.4-.9 8-5 8-10V7L12 3z",
      "M12 10v4",
      "M12 17h.01"
    ])
};

// Plain square-outline fallback
function fallbackIcon(): SVGSVGElement {
  return svg(["M3 3h18v18H3z"]);
}

export function tileIcon(name: string): SVGSVGElement {
  const factory = ICONS[name];
  return factory ? factory() : fallbackIcon();
}
