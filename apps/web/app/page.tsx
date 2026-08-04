"use client";

import { FormEvent, useEffect, useState } from "react";

type View = "search" | "ask" | "compare" | "documents";
type Citation = { document_number: string; article_number: string | null; page_start: number | null; page_end: number | null; source_url: string | null };
type SearchHit = { chunk_id: string; content: string; fused_score: number; citation: Citation };
type Document = { document_number: string; title: string; document_type: string; issuing_agency: string | null };
type Answer = { status: string; answer: string | null; interpretation: string | null; uncertainties: string[]; citations: Citation[] };
type Change = { key: string; change_type: string; before_content: string | null; after_content: string | null };

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, { headers: { "Content-Type": "application/json" }, ...options });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || "The request could not be completed.");
  return body as T;
}

function escapeText(value: string | null | undefined) {
  return value || "";
}

function CitationLine({ citation }: { citation: Citation }) {
  const location = [citation.article_number ? `Article ${citation.article_number}` : null, citation.page_start ? `p. ${citation.page_start}${citation.page_end && citation.page_end !== citation.page_start ? `–${citation.page_end}` : ""}` : null].filter(Boolean).join(" · ");
  return <div className="citation"><span className="tag">{citation.document_number}</span><span>{location || "Source passage"}</span>{citation.source_url && <a href={citation.source_url} target="_blank" rel="noreferrer">Official source ↗</a>}</div>;
}

export default function Home() {
  const [view, setView] = useState<View>("search");
  const [searchQuery, setSearchQuery] = useState("");
  const [searchMode, setSearchMode] = useState("hybrid");
  const [searchResults, setSearchResults] = useState<SearchHit[] | null>(null);
  const [searchBusy, setSearchBusy] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [answerBusy, setAnswerBusy] = useState(false);
  const [answerError, setAnswerError] = useState("");
  const [before, setBefore] = useState("");
  const [after, setAfter] = useState("");
  const [changes, setChanges] = useState<Change[] | null>(null);
  const [compareBusy, setCompareBusy] = useState(false);
  const [compareError, setCompareError] = useState("");
  const [documents, setDocuments] = useState<Document[] | null>(null);

  useEffect(() => {
    if (view === "documents" && documents === null) request<Document[]>("/documents?limit=100").then(setDocuments).catch(error => setCompareError(error.message));
  }, [view, documents]);

  async function search(event: FormEvent) {
    event.preventDefault(); setSearchBusy(true); setSearchError("");
    try { const params = new URLSearchParams({ q: searchQuery, mode: searchMode, limit: "5" }); setSearchResults(await request<SearchHit[]>(`/search?${params}`)); } catch (error) { setSearchError((error as Error).message); } finally { setSearchBusy(false); }
  }

  async function ask(event: FormEvent) {
    event.preventDefault(); setAnswerBusy(true); setAnswerError("");
    try { setAnswer(await request<Answer>("/questions", { method: "POST", body: JSON.stringify({ question }) })); } catch (error) { setAnswerError((error as Error).message); } finally { setAnswerBusy(false); }
  }

  async function compare(event: FormEvent) {
    event.preventDefault(); setCompareBusy(true); setCompareError("");
    try { const result = await request<{ changes: Change[] }>("/comparisons", { method: "POST", body: JSON.stringify({ before_document_number: before, after_document_number: after }) }); setChanges(result.changes); } catch (error) { setCompareError((error as Error).message); } finally { setCompareBusy(false); }
  }

  return <>
    <header className="topbar"><a className="brand" href="#search"><span className="brand-mark">TL</span><span><strong>TaxLens</strong><small>Regulatory intelligence</small></span></a><div className="status"><span className="status-dot" />Local workspace</div></header>
    <main className="shell">
      <section className="hero"><p className="eyebrow">Vietnamese tax intelligence</p><h1>Find the rule.<br /><em>See the evidence.</em></h1><p className="hero-copy">Search official regulations, ask grounded questions, and compare document versions from one focused workspace.</p></section>
      <nav className="tabs" aria-label="Workspace views">{([["search", "Search"], ["ask", "Ask TaxLens"], ["compare", "Compare versions"], ["documents", "Documents"]] as [View, string][]).map(([key, label]) => <button key={key} className={`tab ${view === key ? "active" : ""}`} onClick={() => setView(key)}>{label}</button>)}</nav>
      {view === "search" && <section className="view"><Heading eyebrow="Retrieval workspace" title="Search regulations" chip="Hybrid search" /><form onSubmit={search} className="search-form"><label className="search-box"><span>⌕</span><input value={searchQuery} onChange={event => setSearchQuery(event.target.value)} required maxLength={500} placeholder="Try: thời điểm lập hóa đơn" /><button type="submit">{searchBusy ? "Searching…" : "Search"}</button></label><div className="form-row"><label>Mode<select value={searchMode} onChange={event => setSearchMode(event.target.value)}><option value="hybrid">Hybrid</option><option value="keyword">Keyword</option><option value="semantic">Semantic</option></select></label></div></form><ResultState error={searchError} hasResults={searchResults !== null} emptyTitle="Search the corpus" emptyText="Results will show the matched passage and its source document, article, page, and official URL." />{searchResults && <div className="result-list">{searchResults.length ? searchResults.map(hit => <article className="result-card" key={hit.chunk_id}><div className="result-top"><span className="result-number">{hit.citation.document_number}</span><span className="score">fused score {hit.fused_score.toFixed(4)}</span></div><p>{hit.content}</p><CitationLine citation={hit.citation} /></article>) : <Empty title="No matching passages" text="Try a broader Vietnamese or English query." />}</div>}</section>}
      {view === "ask" && <section className="view"><Heading eyebrow="Evidence-grounded answers" title="Ask TaxLens" chip="Cited response" /><form onSubmit={ask} className="question-form"><textarea value={question} onChange={event => setQuestion(event.target.value)} required maxLength={1000} placeholder="Ask a question about Vietnamese tax regulations…" /><div className="form-actions"><span>Answers are generated from retrieved legal passages.</span><button type="submit">{answerBusy ? "Working…" : "Ask question →"}</button></div></form><ResultState error={answerError} hasResults={answer !== null} emptyTitle="Ask a focused question" emptyText="TaxLens will show its evidence status, answer, uncertainties, and citations." />{answer && <div className="answer-card"><span className="answer-status">{answer.status}</span><div className="answer-text">{escapeText(answer.answer || answer.interpretation)}</div>{answer.uncertainties.length > 0 && <div className="uncertainties"><strong>Uncertainties</strong><br />{answer.uncertainties.map(item => <span key={item}>{item}<br /></span>)}</div>}<div className="answer-citations"><p className="eyebrow">Sources</p>{answer.citations.map((citation, index) => <CitationLine key={`${citation.document_number}-${index}`} citation={citation} />)}</div></div>}</section>}
      {view === "compare" && <section className="view"><Heading eyebrow="Version intelligence" title="Compare regulations" chip="Article diff" /><form onSubmit={compare} className="compare-form"><label>Before document<input value={before} onChange={event => setBefore(event.target.value)} list="document-options" required placeholder="e.g. 02/2024/TT-BTC" /></label><span className="swap">→</span><label>After document<input value={after} onChange={event => setAfter(event.target.value)} list="document-options" required placeholder="e.g. 31/2025/TT-BTC" /></label><button type="submit">{compareBusy ? "Comparing…" : "Compare versions →"}</button><datalist id="document-options">{documents?.map(document => <option key={document.document_number} value={document.document_number}>{document.title}</option>)}</datalist></form><ResultState error={compareError} hasResults={changes !== null} emptyTitle="Choose two document versions" emptyText="Use document numbers from the Documents tab to see added, removed, and modified articles." />{changes && <div className="comparison-list">{changes.length ? changes.map(change => <article className={`change-card ${change.change_type.toLowerCase()}`} key={change.key}><div className="change-top"><strong>{change.key}</strong><span className="change-type">{change.change_type}</span></div><div className="change-content"><div><strong>Before</strong>{change.before_content || "—"}</div><div><strong>After</strong>{change.after_content || "—"}</div></div></article>) : <Empty title="No article changes found" text="The selected versions did not produce a detected article difference." />}</div>}</section>}
      {view === "documents" && <section className="view"><Heading eyebrow="Source library" title="Documents" chip={`${documents?.length || 0} indexed`} />{documents === null ? <Empty title="Loading source library" text="Reading the indexed legal documents." /> : <div className="document-list">{documents.length ? documents.map(document => <article className="document-card" key={document.document_number}><div className="doc-top"><span className="doc-number">{document.document_number}</span><span className="tag">{document.document_type}</span></div><strong>{document.title}</strong><div className="doc-meta">{document.issuing_agency || "Agency unavailable"}</div></article>) : <Empty title="No documents indexed yet" text="Ingest official documents to populate the source library." />}</div>}</section>}
    </main><footer><span>TaxLens AI</span><span>Evidence first · Local development</span></footer>
  </>;
}

function Heading({ eyebrow, title, chip }: { eyebrow: string; title: string; chip: string }) { return <div className="section-heading"><div><p className="eyebrow">{eyebrow}</p><h2>{title}</h2></div><span className="chip">{chip}</span></div>; }
function Empty({ title, text }: { title: string; text: string }) { return <div className="empty-state"><span className="empty-icon">⌁</span><h3>{title}</h3><p>{text}</p></div>; }
function ResultState({ error, hasResults, emptyTitle, emptyText }: { error: string; hasResults: boolean; emptyTitle: string; emptyText: string }) { if (error) return <div className="error-state">{error}</div>; return hasResults ? null : <Empty title={emptyTitle} text={emptyText} />; }
