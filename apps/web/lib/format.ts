import type { Copy } from "./copy";
import type { Citation, DocumentFilters, Ending, FacetFilters, SearchDocumentGroup, SearchHit } from "./types";
export const DOCUMENT_PAGE_SIZE = 20;

export const SEARCH_PAGE_SIZE = 10;

// The search API ranks at most 200 passages ahead of a page.
export const SEARCH_MAX_OFFSET = 200;

export const SEARCH_DOCUMENT_MATCHES = 5;

export const CHUNK_PAGE_SIZE = 50;

export const NO_FILTERS: DocumentFilters = { q: "", source: "", kind: "", status: "" };

export const NO_FACETS: FacetFilters = { source: "", kind: "", status: "" };

export function groupSearchResults(results: SearchHit[]): SearchDocumentGroup[] {
  const groups = new Map<string, SearchDocumentGroup>();
  for (const hit of results) {
    const key = hit.citation.document_number;
    const group = groups.get(key) || { document_number: key, title: hit.citation.title || key, hits: [] };
    if (group.hits.length < 3) group.hits.push(hit);
    groups.set(key, group);
  }
  return Array.from(groups.values());
}

export function pageRange(start: number | null, end: number | null, prefix: string) {
  if (!start) return null;
  return `${prefix} ${start}${end && end !== start ? `–${end}` : ""}`;
}

export function locationLabel(citation: Citation, copy: Copy) {
  const article = citation.article_number
    ? `${copy.article} ${citation.article_number}${citation.clause_number ? ` ${copy.clause} ${citation.clause_number}` : ""}`
    : null;
  return [article, pageRange(citation.page_start, citation.page_end, copy.page)].filter(Boolean).join(" · ");
}

export function labelFor(labels: Record<string, string>, value: string) {
  return labels[value] ?? value;
}

export function formatDate(isoDate: string) {
  return isoDate.split("-").reverse().join("/");
}

export const CONFIRMED_ENDINGS = ["explicit", "ministry"];

export function todayInVietnam() {
  return new Date(Date.now() + 7 * 3600 * 1000).toISOString().slice(0, 10);
}

export function hasConfirmedlyEnded(ending: Ending) {
  return Boolean(ending.ended_on && ending.end_basis && CONFIRMED_ENDINGS.includes(ending.end_basis) && ending.ended_on <= todayInVietnam());
}

export function documentListQuery(filters: DocumentFilters, pageIndex: number) {
  const params = new URLSearchParams({ limit: String(DOCUMENT_PAGE_SIZE), offset: String(pageIndex * DOCUMENT_PAGE_SIZE) });
  if (filters.q) params.set("q", filters.q);
  if (filters.source) params.set("source_name", filters.source);
  if (filters.kind) params.set("kind", filters.kind);
  if (filters.status) params.set("legal_status", filters.status);
  return params.toString();
}
