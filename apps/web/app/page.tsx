"use client";

import { FormEvent, useEffect, useState } from "react";
import { signOut, useSession } from "next-auth/react";

type View = "search" | "ask" | "compare" | "documents";
type Citation = { document_number: string; title?: string; heading?: string | null; article_number: string | null; page_start: number | null; page_end: number | null; source_url: string | null };
type SearchHit = { chunk_id: string; snippet: string; content: string; fused_score: number; citation: Citation };
type Document = { id: string; document_number: string; title: string; document_type: string; issuing_agency: string | null; source_name: string | null };
type DocumentDetail = Document & { id: string; versions: { id: string; issue_date: string | null; effective_date: string | null; legal_status: string; raw_artifact_key: string; source_url: string | null; processing_status: string | null; processing_error_code: string | null; chunk_count: number }[] };
type Chunk = { id: string; version_id: string; article_number: string | null; clause_number: string | null; heading: string | null; page_start: number | null; page_end: number | null; content: string };
type Claim = { text: string; citation_numbers: number[] };
type Answer = { status: string; answer: string | null; interpretation: string | null; uncertainties: string[]; citations: Citation[]; confirmed_facts: Claim[]; review_actions: string[]; disclaimer: string };
type Change = { key: string; change_type: string; before_content: string | null; after_content: string | null; before_citation: Citation | null; after_citation: Citation | null };

type SearchDocumentGroup = { document_number: string; title: string; hits: SearchHit[] };

function groupSearchResults(results: SearchHit[]): SearchDocumentGroup[] {
  const groups = new Map<string, SearchDocumentGroup>();
  for (const hit of results) {
    const key = hit.citation.document_number;
    const group = groups.get(key) || {
      document_number: key,
      title: hit.citation.title || key,
      hits: [],
    };
    if (group.hits.length < 3) group.hits.push(hit);
    groups.set(key, group);
  }
  return Array.from(groups.values());
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, { headers: { "Content-Type": "application/json" }, ...options });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || "The request could not be completed.");
  return body as T;
}

function escapeText(value: string | null | undefined) {
  return value || "";
}

function CitationLine({ citation, language = "en" }: { citation: Citation; language?: "en" | "vi" }) {
  const location = [citation.article_number ? `${language === "vi" ? "Điều" : "Article"} ${citation.article_number}` : null, citation.page_start ? `${language === "vi" ? "tr." : "p."} ${citation.page_start}${citation.page_end && citation.page_end !== citation.page_start ? `–${citation.page_end}` : ""}` : null].filter(Boolean).join(" · ");
  return <div className="citation"><span className="tag">{citation.document_number}</span><span>{location || (language === "vi" ? "Đoạn trích nguồn" : "Source passage")}</span>{citation.source_url && <a href={citation.source_url} target="_blank" rel="noreferrer">{language === "vi" ? "Nguồn chính thức ↗" : "Official source ↗"}</a>}</div>;
}

export default function Home() {
  const { data: session } = useSession();
  const [view, setView] = useState<View>("search");
  const [language, setLanguage] = useState<"en" | "vi">("en");
  const [searchQuery, setSearchQuery] = useState("");
  const [searchMode, setSearchMode] = useState("hybrid");
  const [searchResults, setSearchResults] = useState<SearchHit[] | null>(null);
  const [searchLimit, setSearchLimit] = useState(10);
  const [searchHasMore, setSearchHasMore] = useState(false);
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
  const [documentSourceFilter, setDocumentSourceFilter] = useState("all");
  const [documentTypeFilter, setDocumentTypeFilter] = useState("all");
  const [selectedDocument, setSelectedDocument] = useState<Document | null>(null);
  const [documentDetail, setDocumentDetail] = useState<DocumentDetail | null>(null);
  const [documentChunks, setDocumentChunks] = useState<Chunk[]>([]);
  const [documentBusy, setDocumentBusy] = useState(false);
  const [documentError, setDocumentError] = useState("");

  const visibleDocuments = documents?.filter(document =>
    (documentSourceFilter === "all" || document.source_name === documentSourceFilter) &&
    (documentTypeFilter === "all" || document.document_type === documentTypeFilter)
  );
  const copy = language === "vi" ? {
    search: "Tìm kiếm", ask: "Hỏi TaxLens", compare: "Đối chiếu văn bản", documents: "Văn bản",
    heroEyebrow: "Trợ lý tra cứu thuế Việt Nam", heroTitleOne: "Tìm đúng quy định.", heroTitleTwo: "Nắm rõ thông tin.",
    heroCopy: "Tra cứu, hỏi đáp và đối chiếu văn bản pháp luật với trích dẫn rõ ràng.",
    retrievalEyebrow: "Tra cứu văn bản", searchTitle: "Tìm kiếm quy định", hybrid: "Tìm kiếm kết hợp", searchButton: "Tìm kiếm", searchPlaceholder: "Ví dụ: thời điểm lập hóa đơn",
    askEyebrow: "Hỏi đáp có trích dẫn", askTitle: "Hỏi TaxLens", citedResponse: "Câu trả lời có dẫn nguồn",
    askPlaceholder: "Đặt câu hỏi về quy định thuế Việt Nam…", askButton: "Gửi câu hỏi →", pressEnter: "Nhấn Enter để gửi câu hỏi",
    compareEyebrow: "Thông tin văn bản", compareTitle: "Đối chiếu văn bản", compareChip: "Đối chiếu",
    before: "Văn bản gốc", after: "Văn bản hiện hành", compareButton: "Đối chiếu →",
    documentsEyebrow: "Thư viện văn bản", documentsTitle: "Văn bản pháp luật", source: "Nguồn", type: "Loại văn bản",
    mode: "Chế độ", allSources: "Tất cả nguồn", allTypes: "Tất cả loại", noMatch: "Không có văn bản phù hợp",
    adjustFilters: "Hãy điều chỉnh bộ lọc nguồn hoặc loại văn bản.", noDocs: "Chưa có văn bản được xử lý",
    noDocsText: "Nạp văn bản chính thức để xây dựng thư viện nguồn.", working: "Đang xử lý…",
    evidencePassage: "đoạn trích", evidencePassages: "đoạn trích", relevantPassage: "Đoạn trích liên quan",
    noResults: "Không tìm thấy đoạn phù hợp", broaden: "Hãy thử câu hỏi rộng hơn bằng tiếng Việt hoặc tiếng Anh.",
    searchCorpus: "Tìm kiếm trong kho văn bản", searchHelp: "Các văn bản phù hợp kèm đoạn trích liên quan.",
    chooseVersions: "Chọn hai văn bản để đối chiếu.", chooseVersionsText: "Đối chiếu hai văn bản để xem những quy định được bổ sung, sửa đổi hoặc bãi bỏ.",
    noChanges: "Không phát hiện thay đổi", noChangesText: "Hai văn bản được chọn không có khác biệt rõ ràng.",
  } : {
    search: "Search", ask: "Ask TaxLens", compare: "Compare versions", documents: "Documents",
    heroEyebrow: "Vietnamese tax intelligence", heroTitleOne: "Find the rule.", heroTitleTwo: "See the evidence.",
    heroCopy: "Search official regulations, ask grounded questions, and compare document versions from one focused workspace.",
    retrievalEyebrow: "Retrieval workspace", searchTitle: "Search regulations", hybrid: "Hybrid search", searchButton: "Search", searchPlaceholder: "Try: thời điểm lập hóa đơn",
    askEyebrow: "Evidence-grounded answers", askTitle: "Ask TaxLens", citedResponse: "Cited response",
    askPlaceholder: "Ask a question about Vietnamese tax regulations…", askButton: "Ask question →", pressEnter: "Press Enter to ask",
    compareEyebrow: "Version intelligence", compareTitle: "Compare regulations", compareChip: "Article diff",
    before: "Before document", after: "After document", compareButton: "Compare versions →",
    documentsEyebrow: "Source library", documentsTitle: "Documents", source: "Source", type: "Type",
    mode: "Mode", allSources: "All sources", allTypes: "All types", noMatch: "No matching documents",
    adjustFilters: "Adjust the source or document type filters.", noDocs: "No documents indexed yet",
    noDocsText: "Ingest official documents to populate the source library.", working: "Working…",
    evidencePassage: "evidence passage", evidencePassages: "evidence passages", relevantPassage: "Relevant passage",
    noResults: "No matching passages", broaden: "Try a broader Vietnamese or English query.",
    searchCorpus: "Search the corpus", searchHelp: "Each document appears once with its strongest evidence passages.",
    chooseVersions: "Choose two document versions", chooseVersionsText: "Use document numbers from the Documents tab to see added, removed, and modified articles.",
    noChanges: "No article changes found", noChangesText: "The selected versions did not produce a detected article difference.",
  };

  useEffect(() => {
    if ((view === "documents" || view === "compare") && documents === null) request<Document[]>("/documents?limit=100").then(setDocuments).catch(error => setDocumentError(error.message));
  }, [view, documents]);

  async function openDocument(document: Document) {
    setSelectedDocument(document); setDocumentDetail(null); setDocumentChunks([]); setDocumentError(""); setDocumentBusy(true);
    try {
      const detail = await request<DocumentDetail>(`/documents/${document.id}`);
      setDocumentDetail(detail);
      setDocumentChunks(await request<Chunk[]>(`/documents/${detail.id}/chunks`));
    } catch (error) { setDocumentError((error as Error).message); } finally { setDocumentBusy(false); }
  }

  async function search(event: FormEvent) {
    event.preventDefault(); setSearchBusy(true); setSearchError("");
    try { const limit = 10; const params = new URLSearchParams({ q: searchQuery, mode: searchMode, limit: String(limit + 1) }); const results = await request<SearchHit[]>(`/search?${params}`); setSearchLimit(limit); setSearchHasMore(results.length > limit); setSearchResults(results.slice(0, limit)); } catch (error) { setSearchError((error as Error).message); } finally { setSearchBusy(false); }
  }

  async function loadMoreSearchResults() {
    const nextLimit = searchLimit + 10; setSearchBusy(true); setSearchError("");
    try { const params = new URLSearchParams({ q: searchQuery, mode: searchMode, limit: String(nextLimit + 1) }); const results = await request<SearchHit[]>(`/search?${params}`); setSearchLimit(nextLimit); setSearchHasMore(results.length > nextLimit); setSearchResults(results.slice(0, nextLimit)); } catch (error) { setSearchError((error as Error).message); } finally { setSearchBusy(false); }
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
    <header className="topbar"><a className="brand" href="#search"><span className="brand-mark">TL</span><span><strong>TaxLens</strong><small>Regulatory intelligence</small></span></a><div className="topbar-actions"><div className="language-toggle" aria-label="Language"><button className={language === "en" ? "active" : ""} onClick={() => setLanguage("en")}>EN</button><button className={language === "vi" ? "active" : ""} onClick={() => setLanguage("vi")}>VI</button></div>{session?.user.role === "admin" && <a href="/admin">Admin</a>}<button type="button" onClick={() => signOut({ callbackUrl: "/login" })}>Sign out</button><div className="status"><span className="status-dot" />Local workspace</div></div></header>
    <main className={`shell ${language === "vi" ? "language-vi" : ""}`}>
      <section className="hero"><p className="eyebrow">{copy.heroEyebrow}</p><h1>{copy.heroTitleOne}<br /><em>{copy.heroTitleTwo}</em></h1><p className="hero-copy">{copy.heroCopy}</p></section>
      <nav className="tabs" aria-label="Workspace views">{([["search", copy.search], ["ask", copy.ask], ["compare", copy.compare], ["documents", copy.documents]] as [View, string][]).map(([key, label]) => <button key={key} className={`tab ${view === key ? "active" : ""}`} onClick={() => setView(key)}>{label}</button>)}</nav>
      {view === "search" && <section className="view"><Heading eyebrow={copy.retrievalEyebrow} title={copy.searchTitle} chip={copy.hybrid} /><form onSubmit={search} className="search-form"><label className="search-box"><span>⌕</span><input value={searchQuery} onChange={event => setSearchQuery(event.target.value)} required maxLength={500} placeholder={copy.searchPlaceholder} /><button type="submit">{searchBusy ? "…" : copy.searchButton}</button></label><div className="form-row"><label>{copy.mode}<select value={searchMode} onChange={event => setSearchMode(event.target.value)}><option value="hybrid">{language === "vi" ? "Kết hợp" : "Hybrid"}</option><option value="keyword">{language === "vi" ? "Từ khóa" : "Keyword"}</option><option value="semantic">{language === "vi" ? "Ngữ nghĩa" : "Semantic"}</option></select></label></div></form><ResultState error={searchError} hasResults={searchResults !== null} emptyTitle={copy.searchCorpus} emptyText={copy.searchHelp} />{searchResults && <div className="result-list">{searchResults.length ? groupSearchResults(searchResults).map(group => <article className="result-card" key={group.document_number}><div className="result-top"><span className="result-number">{group.document_number}</span><span className="score">{group.hits.length} {group.hits.length === 1 ? copy.evidencePassage : copy.evidencePassages}</span></div><h3 className="result-title">{group.title}</h3><div className="evidence-list">{group.hits.map(hit => <div className="evidence-item" key={hit.chunk_id}><p className="result-heading">{hit.citation.heading || (hit.citation.article_number ? `${language === "vi" ? "Điều" : "Article"} ${hit.citation.article_number}` : copy.relevantPassage)}</p><p className="result-snippet">{hit.snippet}</p><CitationLine citation={hit.citation} language={language} /></div>)}</div></article>) : <Empty title={copy.noResults} text={copy.broaden} />}</div>}{searchHasMore && <button className="load-more" type="button" onClick={loadMoreSearchResults} disabled={searchBusy}>{searchBusy ? "…" : (language === "vi" ? "Tải thêm kết quả" : "Load more results")}</button>}</section>}
      {view === "ask" && <section className="view"><Heading eyebrow={copy.askEyebrow} title={copy.askTitle} chip={copy.citedResponse} /><form onSubmit={ask} className="chat-form"><div className="chat-bar"><input type="text" value={question} onChange={event => setQuestion(event.target.value)} required maxLength={1000} placeholder={copy.askPlaceholder} aria-label={copy.askPlaceholder} /><button type="submit" aria-label={copy.askButton} disabled={answerBusy}>{answerBusy ? "…" : "↑"}</button></div><div className="chat-hint">{copy.pressEnter}</div></form><ResultState error={answerError} hasResults={answer !== null} emptyTitle={language === "vi" ? "Đặt câu hỏi về văn bản pháp luật" : "Ask a focused question"} emptyText={language === "vi" ? "TaxLens sẽ hiển thị câu trả lời, nguồn trích dẫn và những điểm cần kiểm tra." : "TaxLens will show its evidence status, uncertainties, and citations."} />{answer && <div className="answer-card"><span className="answer-status">{answer.status}</span>{answer.confirmed_facts.length > 0 && <div className="confirmed-facts"><p className="eyebrow">{language === "vi" ? "Thông tin đã xác nhận" : "Confirmed facts"}</p>{answer.confirmed_facts.map(fact => <p key={fact.text}>{fact.text} <span className="fact-citations">[{fact.citation_numbers.join(", ")}]</span></p>)}</div>}<div className="answer-text">{escapeText(answer.answer || answer.interpretation)}</div>{answer.uncertainties.length > 0 && <div className="uncertainties"><strong>{language === "vi" ? "Điểm cần lưu ý" : "Uncertainties"}</strong><br />{answer.uncertainties.map(item => <span key={item}>{item}<br /></span>)}</div>}{answer.review_actions.length > 0 && <div className="review-actions"><strong>{language === "vi" ? "Đề xuất kiểm tra" : "Review actions"}</strong>{answer.review_actions.map(action => <span key={action}>• {action}</span>)}</div>}<div className="answer-citations"><p className="eyebrow">{language === "vi" ? "Nguồn dẫn" : "Sources"}</p>{answer.citations.map((citation, index) => <CitationLine key={`${citation.document_number}-${index}`} citation={citation} language={language} />)}</div><p className="disclaimer">{answer.disclaimer}</p></div>}</section>}
      {view === "compare" && <section className="view"><Heading eyebrow={copy.compareEyebrow} title={copy.compareTitle} chip={copy.compareChip} /><form onSubmit={compare} className="compare-form"><label>{copy.before}<input value={before} onChange={event => setBefore(event.target.value)} list="document-options" required placeholder="e.g. 02/2024/TT-BTC" /></label><span className="swap">→</span><label>{copy.after}<input value={after} onChange={event => setAfter(event.target.value)} list="document-options" required placeholder="e.g. 31/2025/TT-BTC" /></label><button type="submit">{compareBusy ? copy.working : copy.compareButton}</button><datalist id="document-options">{documents?.map(document => <option key={document.document_number} value={document.document_number}>{document.title}</option>)}</datalist></form><ResultState error={compareError} hasResults={changes !== null} emptyTitle={copy.chooseVersions} emptyText={copy.chooseVersionsText} />{changes && <div className="comparison-list">{changes.length ? changes.map(change => <article className={`change-card ${change.change_type.toLowerCase()}`} key={change.key}><div className="change-top"><strong>{change.key}</strong><span className="change-type">{change.change_type}</span></div><div className="change-content"><div><strong>{copy.before}</strong>{change.before_content || "—"}{change.before_citation && <CitationLine citation={change.before_citation} language={language} />}</div><div><strong>{copy.after}</strong>{change.after_content || "—"}{change.after_citation && <CitationLine citation={change.after_citation} language={language} />}</div></div></article>) : <Empty title={copy.noChanges} text={copy.noChangesText} />}</div>}</section>}
      {view === "documents" && <section className="view">{selectedDocument ? <><button className="back-button" onClick={() => setSelectedDocument(null)}>← {language === "vi" ? "Quay lại danh sách" : "Back to documents"}</button>{documentBusy ? <Empty title={copy.working} text={language === "vi" ? "Đang đọc thông tin văn bản và các đoạn trích." : "Reading versions and indexed passages."} /> : documentError ? <div className="error-state">{documentError}</div> : documentDetail && <DocumentDetailView detail={documentDetail} chunks={documentChunks} language={language} />}</> : <><Heading eyebrow={copy.documentsEyebrow} title={copy.documentsTitle} chip={`${visibleDocuments?.length || 0} ${language === "vi" ? "văn bản đã xử lý" : "indexed"}`} /><div className="form-row"><label>{copy.source}<select value={documentSourceFilter} onChange={event => setDocumentSourceFilter(event.target.value)}><option value="all">{copy.allSources}</option>{Array.from(new Set(documents?.map(document => document.source_name).filter(Boolean))).map(source => <option key={source} value={source || ""}>{source}</option>)}</select></label><label>{copy.type}<select value={documentTypeFilter} onChange={event => setDocumentTypeFilter(event.target.value)}><option value="all">{copy.allTypes}</option>{Array.from(new Set(documents?.map(document => document.document_type))).map(type => <option key={type} value={type}>{type}</option>)}</select></label></div>{documentError ? <div className="error-state">{documentError}</div> : documents === null ? <Empty title={copy.working} text={language === "vi" ? "Đang đọc thư viện văn bản pháp luật." : "Reading the indexed legal documents."} /> : <div className="document-list">{visibleDocuments?.length ? visibleDocuments.map(document => <button className="document-card document-button" key={document.document_number} onClick={() => openDocument(document)}><div className="doc-top"><span className="doc-number">{document.document_number}</span><span className="tag">{document.document_type}</span></div><strong>{document.title}</strong><div className="doc-meta">{document.issuing_agency || (language === "vi" ? "Chưa có cơ quan ban hành" : "Cơ quan ban hành chưa được ghi nhận")}<span>{document.source_name || (language === "vi" ? "Nguồn chưa được ghi nhận" : "Source unavailable")} · {language === "vi" ? "Chi tiết" : "Open details →"}</span></div></button>) : <Empty title={copy.noMatch} text={copy.adjustFilters} />}</div>}</>}</section>}
    </main><footer><span>TaxLens AI</span><span>Evidence first · Local development</span></footer>
  </>;
}

function Heading({ eyebrow, title, chip }: { eyebrow: string; title: string; chip: string }) { return <div className="section-heading"><div><p className="eyebrow">{eyebrow}</p><h2>{title}</h2></div><span className="chip">{chip}</span></div>; }
function Empty({ title, text }: { title: string; text: string }) { return <div className="empty-state"><span className="empty-icon">⌁</span><h3>{title}</h3><p>{text}</p></div>; }
function ResultState({ error, hasResults, emptyTitle, emptyText }: { error: string; hasResults: boolean; emptyTitle: string; emptyText: string }) { if (error) return <div className="error-state">{error}</div>; return hasResults ? null : <Empty title={emptyTitle} text={emptyText} />; }
function DocumentDetailView({ detail, chunks, language }: { detail: DocumentDetail; chunks: Chunk[]; language: "en" | "vi" }) {
  return <>
    <Heading eyebrow={language === "vi" ? "Văn bản đã xử lý" : "Indexed source"} title={detail.document_number} chip={detail.document_type} />
    <p className="document-title">{detail.title}</p>
    <p className="document-source">{detail.source_name || (language === "vi" ? "Nguồn chưa được ghi nhận" : "Source unavailable")} · {detail.issuing_agency || (language === "vi" ? "Cơ quan ban hành chưa được ghi nhận" : "Agency unavailable")} {detail.versions[0]?.source_url && <a href={detail.versions[0].source_url} target="_blank" rel="noreferrer">{language === "vi" ? "Nguồn chính thức ↗" : "Open official source ↗"}</a>}</p>
    <div className="version-grid">{detail.versions.map(version => <div className="version-card" key={version.id}><span className="tag">{version.legal_status}</span><strong>{language === "vi" ? "Ngày ban hành" : "Version"} {version.issue_date || (language === "vi" ? "chưa ghi nhận" : "date unavailable")}</strong><small>{language === "vi" ? "Hiệu lực: " : "Effective: "}{version.effective_date || (language === "vi" ? "chưa ghi nhận" : "not recorded")}</small><small>{version.processing_status || "NOT_PROCESSED"} · {version.chunk_count} {language === "vi" ? "đoạn trích" : "chunks"}</small>{version.processing_error_code && <small>{version.processing_error_code}</small>}</div>)}</div>
    <div className="chunk-heading"><p className="eyebrow">{language === "vi" ? "Các đoạn trích đã xử lý" : "Indexed passages"}</p><span>{chunks.length} {language === "vi" ? "đoạn trích" : "chunks"}</span></div>
    {chunks.length ? <div className="chunk-list">{chunks.map(chunk => <article className="chunk-card" key={chunk.id}><div className="chunk-top"><strong>{chunk.article_number ? `${language === "vi" ? "Điều" : "Article"} ${chunk.article_number}` : (language === "vi" ? "Đoạn trích văn bản" : "Document passage")}</strong><span>{chunk.page_start ? `${language === "vi" ? "Trang" : "Page"} ${chunk.page_start}${chunk.page_end && chunk.page_end !== chunk.page_start ? `–${chunk.page_end}` : ""}` : (language === "vi" ? "Chưa ghi nhận số trang" : "Page unavailable")}</span></div>{chunk.heading && <h3>{chunk.heading}</h3>}<details><summary>{language === "vi" ? "Xem đoạn trích" : "Read indexed passage"}</summary><p>{chunk.content}</p></details></article>)}</div> : <Empty title={language === "vi" ? "Chưa có đoạn trích" : "No indexed chunks"} text={language === "vi" ? "Văn bản này chưa có đoạn trích để tìm kiếm." : "This document has not produced searchable passages yet."} />}
  </>;
}
