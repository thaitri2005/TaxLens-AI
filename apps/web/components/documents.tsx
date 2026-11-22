import { Empty, Heading } from "./layout";
import { EndingTag, StatusTag } from "./tags";
import type { Copy } from "../lib/copy";
import { DOCUMENT_PAGE_SIZE, formatDate, labelFor, pageRange } from "../lib/format";
import type { Chunk, CountByValue, DocumentDetail, DocumentFilters, DocumentOverview, FacetFilters } from "../lib/types";
export function OverviewPanel({ overview, filters, copy, numberFormat, onFilter }: {
  overview: DocumentOverview | null;
  filters: DocumentFilters;
  copy: Copy;
  numberFormat: Intl.NumberFormat;
  onFilter: (change: Partial<DocumentFilters>) => void;
}) {
  if (overview === null) {
    return <div className="stat-grid" aria-busy="true">{[copy.statDocuments, copy.statSearchable, copy.statPassages, copy.statAttention].map(label =>
      <div className="stat-card placeholder" key={label}><span>{label}</span><strong>…</strong><small>&nbsp;</small></div>)}</div>;
  }
  const format = (value: number) => numberFormat.format(value);
  const percent = (part: number, whole: number) => `${whole ? Math.round((part / whole) * 100) : 0}%`;
  const inForce = overview.by_status.find(item => item.value === "EFFECTIVE")?.count ?? 0;
  return <>
    <div className="stat-grid">
      <StatCard label={copy.statDocuments} value={format(overview.total_documents)} note={`${format(inForce)} ${copy.statInForce}`} />
      <StatCard label={copy.statSearchable} value={format(overview.searchable_documents)} note={`${percent(overview.searchable_documents, overview.total_documents)} ${copy.statOfLibrary}`} />
      <StatCard label={copy.statPassages} value={format(overview.passages)} note={`${percent(overview.embedded_passages, overview.passages)} ${copy.statEmbedded}`} />
      <StatCard label={copy.statAttention} value={format(overview.failed_versions)} note={copy.statAttentionNote} warn={overview.failed_versions > 0} />
    </div>
    <FacetGroups overview={overview} filters={filters} copy={copy} numberFormat={numberFormat} onFilter={onFilter} />
  </>;
}

export function FacetGroups({ overview, filters, copy, numberFormat, onFilter }: {
  overview: DocumentOverview;
  filters: FacetFilters;
  copy: Copy;
  numberFormat: Intl.NumberFormat;
  onFilter: (change: Partial<FacetFilters>) => void;
}) {
  const format = (value: number) => numberFormat.format(value);
  return <div className="facet-groups">
    <FacetRow label={copy.bySource} items={overview.by_source} active={filters.source} labels={copy.sourceNames} format={format} onSelect={source => onFilter({ source })} />
    <FacetRow label={copy.byKind} items={overview.by_kind} active={filters.kind} labels={copy.kinds} format={format} onSelect={kind => onFilter({ kind })} />
    <FacetRow label={copy.byStatus} items={overview.by_status} active={filters.status} labels={copy.legalStatuses} format={format} onSelect={status => onFilter({ status })} />
  </div>;
}

export function StatCard({ label, value, note, warn = false }: { label: string; value: string; note: string; warn?: boolean }) {
  return <div className={`stat-card ${warn ? "warn" : ""}`}><span>{label}</span><strong>{value}</strong><small>{note}</small></div>;
}

export function FacetRow({ label, items, active, labels, format, onSelect }: {
  label: string;
  items: CountByValue[];
  active: string;
  labels: Record<string, string>;
  format: (value: number) => string;
  onSelect: (value: string) => void;
}) {
  if (!items.length) return null;
  return <div className="facet-row">
    <span className="facet-label">{label}</span>
    <div className="facet-chips">{items.map(item => <button
      key={item.value}
      type="button"
      className={`facet-chip ${active === item.value ? "active" : ""}`}
      aria-pressed={active === item.value}
      onClick={() => onSelect(active === item.value ? "" : item.value)}
    >{labelFor(labels, item.value)}<span>{format(item.count)}</span></button>)}</div>
  </div>;
}

export function Pager({ pageIndex, total, copy, numberFormat, busy, onPage }: {
  pageIndex: number;
  total: number;
  copy: Copy;
  numberFormat: Intl.NumberFormat;
  busy: boolean;
  onPage: (pageIndex: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / DOCUMENT_PAGE_SIZE));
  const from = pageIndex * DOCUMENT_PAGE_SIZE + 1;
  const to = Math.min(total, from + DOCUMENT_PAGE_SIZE - 1);
  return <nav className="pager" aria-label={copy.pageOf(pageIndex + 1, pages)}>
    <button type="button" disabled={busy || pageIndex === 0} onClick={() => onPage(pageIndex - 1)}>{copy.previous}</button>
    <span>{copy.pageOf(pageIndex + 1, pages)} · {copy.showing(from, to, numberFormat.format(total))}</span>
    <button type="button" disabled={busy || pageIndex >= pages - 1} onClick={() => onPage(pageIndex + 1)}>{copy.next}</button>
  </nav>;
}

export function DocumentDetailView({ detail, chunks, copy, numberFormat, onLoadMore, loadingMore }: {
  detail: DocumentDetail;
  chunks: Chunk[];
  copy: Copy;
  numberFormat: Intl.NumberFormat;
  onLoadMore: () => void;
  loadingMore: boolean;
}) {
  const totalChunks = detail.versions.reduce((sum, version) => sum + version.chunk_count, 0);
  return <>
    <Heading eyebrow={copy.indexedSource} title={detail.document_number} chip={labelFor(copy.kinds, detail.kind)} />
    <p className="document-title">{detail.title}</p>
    {detail.ended_on && <p className="document-ending"><EndingTag ending={detail} copy={copy} /></p>}
    <p className="document-source">
      {labelFor(copy.sourceNames, detail.source_name || "") || copy.sourceUnavailable} · {detail.issuing_agency || copy.agencyUnavailable}{" "}
      {detail.versions[0]?.source_url && <a href={detail.versions[0].source_url} target="_blank" rel="noreferrer">{copy.officialSource}</a>}
    </p>
    <div className="version-grid">{detail.versions.map(version => <div className="version-card" key={version.id}>
      <StatusTag status={version.legal_status} ending={detail} copy={copy} />
      <strong>{copy.version} {version.issue_date ? formatDate(version.issue_date) : copy.dateUnavailable}</strong>
      <small>{copy.effective}{version.effective_date ? formatDate(version.effective_date) : copy.notRecorded}</small>
      <small>{version.processing_status || "NOT_PROCESSED"} · {numberFormat.format(version.chunk_count)} {copy.chunks}</small>
      {version.processing_error_code && <small>{version.processing_error_code}</small>}
    </div>)}</div>
    <div className="chunk-heading"><p className="eyebrow">{copy.indexedPassages}</p><span>{numberFormat.format(totalChunks)} {copy.chunks}</span></div>
    {chunks.length ? <div className="chunk-list">{chunks.map(chunk => <article className="chunk-card" key={chunk.id}>
      <div className="chunk-top">
        <strong>{chunk.article_number ? `${copy.article} ${chunk.article_number}${chunk.clause_number ? ` ${copy.clause} ${chunk.clause_number}` : ""}` : copy.documentPassage}</strong>
        <span>{pageRange(chunk.page_start, chunk.page_end, copy.pageLabel) || copy.pageUnavailable}</span>
      </div>
      {chunk.heading && <h3>{chunk.heading}</h3>}
      <details><summary>{copy.readPassage}</summary><p>{chunk.content}</p></details>
    </article>)}</div> : <Empty title={copy.noChunks} text={copy.noChunksText} />}
    {chunks.length < totalChunks && chunks.length > 0 && <button className="load-more" type="button" onClick={onLoadMore} disabled={loadingMore}>
      {loadingMore ? "…" : `${copy.loadMorePassages} (${numberFormat.format(chunks.length)}/${numberFormat.format(totalChunks)})`}
    </button>}
  </>;
}
