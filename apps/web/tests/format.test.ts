import { afterEach, describe, expect, it, vi } from "vitest";
import { COPY } from "../lib/copy";
import { NO_FILTERS, documentListQuery, formatDate, groupSearchResults, hasConfirmedlyEnded, labelFor, locationLabel, pageRange, todayInVietnam } from "../lib/format";
import type { SearchHit } from "../lib/types";

function hit(documentNumber: string, chunkId: string): SearchHit {
  return {
    chunk_id: chunkId, snippet: "", content: "", fused_score: 0,
    citation: { document_number: documentNumber, title: `Title ${documentNumber}`, article_number: "1", page_start: null, page_end: null, source_url: null },
  };
}

afterEach(() => vi.useRealTimers());

describe("format helpers", () => {
  it("formats ISO dates the Vietnamese way", () => {
    expect(formatDate("2025-07-01")).toBe("01/07/2025");
  });

  it("shows a page or a page range", () => {
    expect(pageRange(null, null, "p.")).toBeNull();
    expect(pageRange(3, 3, "p.")).toBe("p. 3");
    expect(pageRange(3, 5, "p.")).toBe("p. 3–5");
  });

  it("labels a citation by article, clause, and pages", () => {
    const citation = { document_number: "48/2024/QH15", article_number: "9", clause_number: "3", page_start: 4, page_end: 5, source_url: null };
    expect(locationLabel(citation, COPY.en)).toBe("Article 9 clause 3 · p. 4–5");
  });

  it("falls back to the raw value without a label", () => {
    expect(labelFor({ law: "Law" }, "law")).toBe("Law");
    expect(labelFor({ law: "Law" }, "other_kind")).toBe("other_kind");
  });

  it("keeps each document once with at most three passages", () => {
    const groups = groupSearchResults([hit("A", "1"), hit("B", "2"), hit("A", "3"), hit("A", "4"), hit("A", "5")]);
    expect(groups.map(group => [group.document_number, group.hits.length])).toEqual([["A", 3], ["B", 1]]);
  });

  it("builds the document list query from the filters and page", () => {
    expect(documentListQuery({ ...NO_FILTERS, q: "hóa đơn", status: "EFFECTIVE" }, 2)).toBe("limit=20&offset=40&q=h%C3%B3a+%C4%91%C6%A1n&legal_status=EFFECTIVE");
  });
});

describe("document endings", () => {
  it("uses Vietnam's date, seven hours ahead of UTC", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-06-30T18:00:00Z"));
    expect(todayInVietnam()).toBe("2026-07-01");
  });

  it("counts only confirmed endings that have passed", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-11-23T03:00:00Z"));
    expect(hasConfirmedlyEnded({ ended_on: "2025-07-01", end_basis: "explicit" })).toBe(true);
    expect(hasConfirmedlyEnded({ ended_on: "2025-07-01", end_basis: "ministry" })).toBe(true);
    expect(hasConfirmedlyEnded({ ended_on: "2025-07-01", end_basis: "guidance" })).toBe(false);
    expect(hasConfirmedlyEnded({ ended_on: "2027-01-01", end_basis: "explicit" })).toBe(false);
    expect(hasConfirmedlyEnded({})).toBe(false);
  });
});
