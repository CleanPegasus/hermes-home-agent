import { afterEach, describe, expect, it, vi } from "vitest";

import { chip, emptyState, factsList, relativeDate, shortDate, statusEmoji, stripMarkdown } from "./ui";

describe("ui helpers", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("formats short and relative dates", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-06-12T12:00:00Z"));

    expect(shortDate("2026-06-12T10:03:00Z")).toContain("jun");
    expect(relativeDate("2026-06-12T10:00:00Z")).toBe("2h ago");
    expect(relativeDate("2026-06-12T11:59:20Z")).toBe("now");
    expect(relativeDate(null)).toBe("unknown");
  });

  it("renders facts, chips, and empty states with escaped text", () => {
    const facts = factsList([["unsafe", "<img src=x>"]]);
    expect(facts.querySelector("dt")?.textContent).toBe("unsafe");
    expect(facts.querySelector("dd")?.textContent).toBe("<img src=x>");
    expect(facts.innerHTML).not.toContain("<img");

    const renderedChip = chip("<script>label</script>", "#e51400");
    expect(renderedChip.className).toBe("chip");
    expect(renderedChip.textContent).toBe("<script>label</script>");
    expect(renderedChip.innerHTML).not.toContain("<script>");
    expect(renderedChip.style.getPropertyValue("--chip-color")).toBe("#e51400");

    const empty = emptyState("📂", "connect your vault", "set OBSIDIAN_VAULT_PATH");
    expect(empty.textContent).toContain("📂");
    expect(empty.textContent).toContain("connect your vault");
    expect(empty.textContent).toContain("set OBSIDIAN_VAULT_PATH");
  });

  it("maps statuses to stable emoji", () => {
    expect(statusEmoji("queued")).toBe("⏳");
    expect(statusEmoji("running")).toBe("⚙️");
    expect(statusEmoji("done")).toBe("✅");
    expect(statusEmoji("failed")).toBe("❌");
    expect(statusEmoji("cancelled")).toBe("🛑");
    expect(statusEmoji("needs_approval")).toBe("🛡️");
    expect(statusEmoji("needs_clarification")).toBe("?");
    expect(statusEmoji("mystery")).toBe("•");
  });

  it("stripMarkdown removes headings, bold, italic, code, links, and blockquotes", () => {
    expect(stripMarkdown("## Shopping List")).toBe("Shopping List");
    expect(stripMarkdown("**bold** and *italic* text")).toBe("bold and italic text");
    expect(stripMarkdown("`inline code` here")).toBe("inline code here");
    expect(stripMarkdown("[link text](https://example.com) end")).toBe("link text end");
    expect(stripMarkdown("> quoted line")).toBe("quoted line");
    expect(stripMarkdown("**bold** before *italic* and `code`")).toBe("bold before italic and code");
    expect(stripMarkdown("# Title\n**bold** [link](url)\n> quote")).toBe("Title\nbold link\nquote");
  });
});
