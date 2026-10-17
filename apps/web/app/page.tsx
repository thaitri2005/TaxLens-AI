"use client";

import { FormEvent, useEffect, useState } from "react";
import { signOut, useSession } from "next-auth/react";

type View = "search" | "ask" | "documents";
type Language = "en" | "vi";
type Citation = {
  document_number: string;
  title?: string;
  heading?: string | null;
  legal_status?: string;
  article_number: string | null;
  clause_number?: string | null;
  page_start: number | null;
  page_end: number | null;
  source_url: string | null;
};
type SearchHit = { chunk_id: string; snippet: string; content: string; fused_score: number; citation: Citation };
type Document = { id: string; document_number: string; title: string; document_type: string; issuing_agency: string | null; source_name: string | null };
type Version = {
  id: string;
  issue_date: string | null;
  effective_date: string | null;
  legal_status: string;
  raw_artifact_key: string;
  source_url: string | null;
  processing_status: string | null;
  processing_error_code: string | null;
  chunk_count: number;
};
type DocumentDetail = Document & { versions: Version[] };
type Chunk = { id: string; version_id: string; article_number: string | null; clause_number: string | null; heading: string | null; page_start: number | null; page_end: number | null; content: string };
type Claim = { text: string; citation_numbers: number[] };
type AnswerStatus = "ANSWERED" | "UNSUPPORTED" | "INSUFFICIENT_EVIDENCE" | "PROVIDER_UNAVAILABLE" | "INVALID_MODEL_OUTPUT";
type Answer = {
  status: AnswerStatus;
  answer: string | null;
  interpretation: string | null;
  uncertainties: string[];
  citations: Citation[];
  confirmed_facts: Claim[];
  review_actions: string[];
  disclaimer: string;
};
type SearchDocumentGroup = { document_number: string; title: string; hits: SearchHit[] };

const DOCUMENT_PAGE_SIZE = 100;

const COPY = {
  en: {
    search: "Search", ask: "Ask TaxLens", documents: "Documents",
    heroEyebrow: "Vietnamese tax intelligence", heroTitleOne: "Find the rule.", heroTitleTwo: "See the evidence.",
    heroCopy: "Search official regulations and ask grounded questions with article-level citations.",
    retrievalEyebrow: "Retrieval workspace", searchTitle: "Search regulations", hybrid: "Hybrid search", searchButton: "Search",
    searchPlaceholder: "Try: thời điểm lập hóa đơn", mode: "Mode", modes: { hybrid: "Hybrid", keyword: "Keyword", semantic: "Semantic" },
    askEyebrow: "Evidence-grounded answers", askTitle: "Ask TaxLens", citedResponse: "Cited response",
    askPlaceholder: "Ask a question about Vietnamese tax regulations…", askButton: "Ask question", pressEnter: "Press Enter to ask",
    askEmptyTitle: "Ask a focused question", askEmptyText: "TaxLens will show its evidence status, uncertainties, and citations.",
    confirmedFacts: "Confirmed facts", uncertainties: "Uncertainties", reviewActions: "Review actions", sources: "Sources",
    statusMessages: {
      ANSWERED: "",
      UNSUPPORTED: "This request is outside the supported regulatory-question scope.",
      INSUFFICIENT_EVIDENCE: "TaxLens did not find enough current, citable evidence to answer. The closest passages are listed below.",
      PROVIDER_UNAVAILABLE: "The language model is unavailable right now. Review the retrieved sources directly.",
      INVALID_MODEL_OUTPUT: "The model response could not be validated, so no answer is shown. The relevant passages are listed below.",
    },
    documentsEyebrow: "Source library", documentsTitle: "Documents", source: "Source", type: "Type",
    allSources: "All sources", allTypes: "All types", noMatch: "No matching documents",
    adjustFilters: "Adjust the source or document type filters.", indexed: "indexed", loadMoreDocuments: "Load more documents",
    working: "Working…", evidencePassage: "evidence passage", evidencePassages: "evidence passages", relevantPassage: "Relevant passage",
    noResults: "No matching passages", broaden: "Try a broader Vietnamese or English query.", loadMore: "Load more results",
    searchCorpus: "Search the corpus", searchHelp: "Each document appears once with its strongest evidence passages.",
    article: "Article", clause: "clause", page: "p.", sourcePassage: "Source passage", officialSource: "Official source ↗",
    back: "Back to documents", readingDocument: "Reading versions and indexed passages.", readingLibrary: "Reading the indexed legal documents.",
    indexedSource: "Indexed source", sourceUnavailable: "Source unavailable", agencyUnavailable: "Issuing agency not recorded",
    version: "Version", dateUnavailable: "date unavailable", effective: "Effective: ", notRecorded: "not recorded", chunks: "chunks",
    indexedPassages: "Indexed passages", documentPassage: "Document passage", pageLabel: "Page", pageUnavailable: "Page unavailable",
    readPassage: "Read indexed passage", noChunks: "No indexed chunks", noChunksText: "This document has not produced searchable passages yet.",
    openDetails: "Open details →", admin: "Admin", signOut: "Sign out", brandTagline: "Regulatory intelligence",
  },
  vi: {
    search: "Tìm kiếm", ask: "Hỏi TaxLens", documents: "Văn bản",
    heroEyebrow: "Trợ lý tra cứu thuế Việt Nam", heroTitleOne: "Tìm đúng quy định.", heroTitleTwo: "Nắm rõ thông tin.",
    heroCopy: "Tra cứu và hỏi đáp văn bản pháp luật với trích dẫn đến từng điều, khoản.",
    retrievalEyebrow: "Tra cứu văn bản", searchTitle: "Tìm kiếm quy định", hybrid: "Tìm kiếm kết hợp", searchButton: "Tìm kiếm",
    searchPlaceholder: "Ví dụ: thời điểm lập hóa đơn", mode: "Chế độ", modes: { hybrid: "Kết hợp", keyword: "Từ khóa", semantic: "Ngữ nghĩa" },
    askEyebrow: "Hỏi đáp có trích dẫn", askTitle: "Hỏi TaxLens", citedResponse: "Câu trả lời có dẫn nguồn",
    askPlaceholder: "Đặt câu hỏi về quy định thuế Việt Nam…", askButton: "Gửi câu hỏi", pressEnter: "Nhấn Enter để gửi câu hỏi",
    askEmptyTitle: "Đặt câu hỏi về văn bản pháp luật", askEmptyText: "TaxLens sẽ hiển thị câu trả lời, nguồn trích dẫn và những điểm cần kiểm tra.",
    confirmedFacts: "Thông tin đã xác nhận", uncertainties: "Điểm cần lưu ý", reviewActions: "Đề xuất kiểm tra", sources: "Nguồn dẫn",
    statusMessages: {
      ANSWERED: "",
      UNSUPPORTED: "Yêu cầu nằm ngoài phạm vi hỏi đáp về quy định pháp luật.",
      INSUFFICIENT_EVIDENCE: "TaxLens chưa tìm thấy đủ căn cứ hiện hành để trả lời. Các đoạn trích gần nhất được liệt kê bên dưới.",
      PROVIDER_UNAVAILABLE: "Mô hình ngôn ngữ hiện không khả dụng. Vui lòng xem trực tiếp các nguồn đã truy xuất.",
      INVALID_MODEL_OUTPUT: "Không thể kiểm chứng câu trả lời của mô hình nên câu trả lời không được hiển thị. Các đoạn trích liên quan được liệt kê bên dưới.",
    },
    documentsEyebrow: "Thư viện văn bản", documentsTitle: "Văn bản pháp luật", source: "Nguồn", type: "Loại văn bản",
    allSources: "Tất cả nguồn", allTypes: "Tất cả loại", noMatch: "Không có văn bản phù hợp",
    adjustFilters: "Hãy điều chỉnh bộ lọc nguồn hoặc loại văn bản.", indexed: "văn bản đã xử lý", loadMoreDocuments: "Tải thêm văn bản",
    working: "Đang xử lý…", evidencePassage: "đoạn trích", evidencePassages: "đoạn trích", relevantPassage: "Đoạn trích liên quan",
    noResults: "Không tìm thấy đoạn phù hợp", broaden: "Hãy thử câu hỏi rộng hơn bằng tiếng Việt hoặc tiếng Anh.", loadMore: "Tải thêm kết quả",
    searchCorpus: "Tìm kiếm trong kho văn bản", searchHelp: "Các văn bản phù hợp kèm đoạn trích liên quan.",
    article: "Điều", clause: "khoản", page: "tr.", sourcePassage: "Đoạn trích nguồn", officialSource: "Nguồn chính thức ↗",
    back: "Quay lại danh sách", readingDocument: "Đang đọc thông tin văn bản và các đoạn trích.", readingLibrary: "Đang đọc thư viện văn bản pháp luật.",
    indexedSource: "Văn bản đã xử lý", sourceUnavailable: "Nguồn chưa được ghi nhận", agencyUnavailable: "Cơ quan ban hành chưa được ghi nhận",
    version: "Ngày ban hành", dateUnavailable: "chưa ghi nhận", effective: "Hiệu lực: ", notRecorded: "chưa ghi nhận", chunks: "đoạn trích",
    indexedPassages: "Các đoạn trích đã xử lý", documentPassage: "Đoạn trích văn bản", pageLabel: "Trang", pageUnavailable: "Chưa ghi nhận số trang",
    readPassage: "Xem đoạn trích", noChunks: "Chưa có đoạn trích", noChunksText: "Văn bản này chưa có đoạn trích để tìm kiếm.",
    openDetails: "Chi tiết →", admin: "Quản trị", signOut: "Đăng xuất", brandTagline: "Thông tin pháp lý",
  },
};
type Copy = (typeof COPY)["en"];

function groupSearchResults(results: SearchHit[]): SearchDocumentGroup[] {
  const groups = new Map<string, SearchDocumentGroup>();
  for (const hit of results) {
    const key = hit.citation.document_number;
    const group = groups.get(key) || { document_number: key, title: hit.citation.title || key, hits: [] };
    if (group.hits.length < 3) group.hits.push(hit);
    groups.set(key, group);
  }
  return Array.from(groups.values());
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, { headers: { "Content-Type": "application/json" }, ...options });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "The request could not be completed.");
  return body as T;
}

function pageRange(start: number | null, end: number | null, prefix: string) {
  if (!start) return null;
  return `${prefix} ${start}${end && end !== start ? `–${end}` : ""}`;
}

function locationLabel(citation: Citation, copy: Copy) {
  const article = citation.article_number
    ? `${copy.article} ${citation.article_number}${citation.clause_number ? ` ${copy.clause} ${citation.clause_number}` : ""}`
    : null;
  return [article, pageRange(citation.page_start, citation.page_end, copy.page)].filter(Boolean).join(" · ");
}

function CitationLine({ citation, copy, number }: { citation: Citation; copy: Copy; number?: number }) {
  return (
    <div className="citation">
      {number !== undefined && <span className="source-number">[{number}]</span>}
      <span className="tag">{citation.document_number}</span>
      <span>{locationLabel(citation, copy) || copy.sourcePassage}</span>
      {citation.heading && <span>{citation.heading}</span>}
      {citation.source_url && <a href={citation.source_url} target="_blank" rel="noreferrer">{copy.officialSource}</a>}
    </div>
  );
}

export default function Home() {
  const { data: session } = useSession();
  const [view, setView] = useState<View>("search");
  const [language, setLanguage] = useState<Language>("en");
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
  const [documents, setDocuments] = useState<Document[] | null>(null);
  const [documentsHasMore, setDocumentsHasMore] = useState(false);
  const [documentSourceFilter, setDocumentSourceFilter] = useState("all");
  const [documentTypeFilter, setDocumentTypeFilter] = useState("all");
  const [selectedDocument, setSelectedDocument] = useState<Document | null>(null);
  const [documentDetail, setDocumentDetail] = useState<DocumentDetail | null>(null);
  const [documentChunks, setDocumentChunks] = useState<Chunk[]>([]);
  const [documentBusy, setDocumentBusy] = useState(false);
  const [documentError, setDocumentError] = useState("");
  const copy = COPY[language];

  const visibleDocuments = documents?.filter(document =>
    (documentSourceFilter === "all" || document.source_name === documentSourceFilter) &&
    (documentTypeFilter === "all" || document.document_type === documentTypeFilter)
  );

  async function loadDocuments(offset: number) {
    setDocumentError("");
    try {
      const page = await request<Document[]>(`/documents?limit=${DOCUMENT_PAGE_SIZE}&offset=${offset}`);
      setDocuments(previous => (offset === 0 ? page : [...(previous || []), ...page]));
      setDocumentsHasMore(page.length === DOCUMENT_PAGE_SIZE);
    } catch (error) {
      setDocumentError((error as Error).message);
    }
  }

  useEffect(() => {
    if (view === "documents" && documents === null) void loadDocuments(0);
  }, [view, documents]);

  async function openDocument(document: Document) {
    setSelectedDocument(document); setDocumentDetail(null); setDocumentChunks([]); setDocumentError(""); setDocumentBusy(true);
    try {
      const detail = await request<DocumentDetail>(`/documents/${document.id}`);
      setDocumentDetail(detail);
      setDocumentChunks(await request<Chunk[]>(`/documents/${detail.id}/chunks`));
    } catch (error) {
      setDocumentError((error as Error).message);
    } finally {
      setDocumentBusy(false);
    }
  }

  async function runSearch(limit: number) {
    setSearchBusy(true); setSearchError("");
    try {
      const params = new URLSearchParams({ q: searchQuery, mode: searchMode, limit: String(limit + 1) });
      const results = await request<SearchHit[]>(`/search?${params}`);
      setSearchLimit(limit);
      setSearchHasMore(results.length > limit);
      setSearchResults(results.slice(0, limit));
    } catch (error) {
      setSearchError((error as Error).message);
    } finally {
      setSearchBusy(false);
    }
  }

  async function search(event: FormEvent) {
    event.preventDefault();
    await runSearch(10);
  }

  async function ask(event: FormEvent) {
    event.preventDefault(); setAnswerBusy(true); setAnswerError(""); setAnswer(null);
    try {
      setAnswer(await request<Answer>("/questions", { method: "POST", body: JSON.stringify({ question }) }));
    } catch (error) {
      setAnswerError((error as Error).message);
    } finally {
      setAnswerBusy(false);
    }
  }

  const tabs: [View, string][] = [["search", copy.search], ["ask", copy.ask], ["documents", copy.documents]];

  return <>
    <header className="topbar">
      <a className="brand" href="#search"><span className="brand-mark">TL</span><span><strong>TaxLens</strong><small>{copy.brandTagline}</small></span></a>
      <div className="topbar-actions">
        <div className="language-toggle" aria-label="Language">
          <button className={language === "en" ? "active" : ""} onClick={() => setLanguage("en")}>EN</button>
          <button className={language === "vi" ? "active" : ""} onClick={() => setLanguage("vi")}>VI</button>
        </div>
        {session?.user.role === "admin" && <a className="topbar-link" href="/admin">{copy.admin}</a>}
        <button className="sign-out-button" type="button" onClick={() => signOut({ callbackUrl: "/login" })}>{copy.signOut}</button>
      </div>
    </header>
    <main className={`shell ${language === "vi" ? "language-vi" : ""}`}>
      <section className="hero"><p className="eyebrow">{copy.heroEyebrow}</p><h1>{copy.heroTitleOne}<br /><em>{copy.heroTitleTwo}</em></h1><p className="hero-copy">{copy.heroCopy}</p></section>
      <nav className="tabs" aria-label="Workspace views">
        {tabs.map(([key, label]) => <button key={key} className={`tab ${view === key ? "active" : ""}`} onClick={() => setView(key)}>{label}</button>)}
      </nav>

      {view === "search" && <section className="view">
        <Heading eyebrow={copy.retrievalEyebrow} title={copy.searchTitle} chip={copy.hybrid} />
        <form onSubmit={search} className="search-form">
          <label className="search-box">
            <span>⌕</span>
            <input value={searchQuery} onChange={event => setSearchQuery(event.target.value)} required maxLength={500} placeholder={copy.searchPlaceholder} />
            <button type="submit">{searchBusy ? "…" : copy.searchButton}</button>
          </label>
          <div className="form-row">
            <label>{copy.mode}
              <select value={searchMode} onChange={event => setSearchMode(event.target.value)}>
                <option value="hybrid">{copy.modes.hybrid}</option>
                <option value="keyword">{copy.modes.keyword}</option>
                <option value="semantic">{copy.modes.semantic}</option>
              </select>
            </label>
          </div>
        </form>
        <ResultState error={searchError} hasResults={searchResults !== null} emptyTitle={copy.searchCorpus} emptyText={copy.searchHelp} />
        {searchResults && <div className="result-list">
          {searchResults.length ? groupSearchResults(searchResults).map(group => <article className="result-card" key={group.document_number}>
            <div className="result-top"><span className="result-number">{group.document_number}</span><span className="score">{group.hits.length} {group.hits.length === 1 ? copy.evidencePassage : copy.evidencePassages}</span></div>
            <h3 className="result-title">{group.title}</h3>
            <div className="evidence-list">{group.hits.map(hit => <div className="evidence-item" key={hit.chunk_id}>
              <p className="result-heading">{hit.citation.heading || (hit.citation.article_number ? `${copy.article} ${hit.citation.article_number}` : copy.relevantPassage)}</p>
              <p className="result-snippet">{hit.snippet}</p>
              <CitationLine citation={hit.citation} copy={copy} />
            </div>)}</div>
          </article>) : <Empty title={copy.noResults} text={copy.broaden} />}
        </div>}
        {searchHasMore && <button className="load-more" type="button" onClick={() => runSearch(searchLimit + 10)} disabled={searchBusy}>{searchBusy ? "…" : copy.loadMore}</button>}
      </section>}

      {view === "ask" && <section className="view">
        <Heading eyebrow={copy.askEyebrow} title={copy.askTitle} chip={copy.citedResponse} />
        <form onSubmit={ask} className="chat-form">
          <div className="chat-bar">
            <input type="text" value={question} onChange={event => setQuestion(event.target.value)} required maxLength={1000} placeholder={copy.askPlaceholder} aria-label={copy.askPlaceholder} />
            <button type="submit" aria-label={copy.askButton} disabled={answerBusy}>{answerBusy ? "…" : "↑"}</button>
          </div>
          <div className="chat-hint">{copy.pressEnter}</div>
        </form>
        <ResultState error={answerError} hasResults={answer !== null || answerBusy} emptyTitle={copy.askEmptyTitle} emptyText={copy.askEmptyText} />
        {answerBusy && <Empty title={copy.working} text="" />}
        {answer && <AnswerCard answer={answer} copy={copy} />}
      </section>}

      {view === "documents" && <section className="view">
        {selectedDocument ? <>
          <button className="back-button" onClick={() => setSelectedDocument(null)}>← {copy.back}</button>
          {documentBusy ? <Empty title={copy.working} text={copy.readingDocument} />
            : documentError ? <div className="error-state">{documentError}</div>
            : documentDetail && <DocumentDetailView detail={documentDetail} chunks={documentChunks} copy={copy} />}
        </> : <>
          <Heading eyebrow={copy.documentsEyebrow} title={copy.documentsTitle} chip={`${visibleDocuments?.length || 0} ${copy.indexed}`} />
          <div className="form-row">
            <label>{copy.source}
              <select value={documentSourceFilter} onChange={event => setDocumentSourceFilter(event.target.value)}>
                <option value="all">{copy.allSources}</option>
                {Array.from(new Set(documents?.map(document => document.source_name).filter(Boolean))).map(source => <option key={source} value={source || ""}>{source}</option>)}
              </select>
            </label>
            <label>{copy.type}
              <select value={documentTypeFilter} onChange={event => setDocumentTypeFilter(event.target.value)}>
                <option value="all">{copy.allTypes}</option>
                {Array.from(new Set(documents?.map(document => document.document_type))).map(type => <option key={type} value={type}>{type}</option>)}
              </select>
            </label>
          </div>
          {documentError ? <div className="error-state">{documentError}</div>
            : documents === null ? <Empty title={copy.working} text={copy.readingLibrary} />
            : <div className="document-list">
              {visibleDocuments?.length ? visibleDocuments.map(document => <button className="document-card document-button" key={document.id} onClick={() => openDocument(document)}>
                <div className="doc-top"><span className="doc-number">{document.document_number}</span><span className="tag">{document.document_type}</span></div>
                <strong>{document.title}</strong>
                <div className="doc-meta">{document.issuing_agency || copy.agencyUnavailable}<span>{document.source_name || copy.sourceUnavailable} · {copy.openDetails}</span></div>
              </button>) : <Empty title={copy.noMatch} text={copy.adjustFilters} />}
            </div>}
          {documentsHasMore && <button className="load-more" type="button" onClick={() => loadDocuments(documents?.length || 0)}>{copy.loadMoreDocuments}</button>}
        </>}
      </section>}
    </main>
    <footer><span>TaxLens AI</span><span>Evidence first</span></footer>
  </>;
}

function AnswerCard({ answer, copy }: { answer: Answer; copy: Copy }) {
  const statusMessage = copy.statusMessages[answer.status];
  const body = answer.answer || answer.interpretation;
  return <div className="answer-card">
    <span className="answer-status">{answer.status}</span>
    {statusMessage && <p className="answer-note">{statusMessage}</p>}
    {body && <div className="answer-text">{body}</div>}
    {answer.confirmed_facts.length > 0 && <div className="confirmed-facts">
      <p className="eyebrow">{copy.confirmedFacts}</p>
      {answer.confirmed_facts.map((fact, index) => <p key={`${index}-${fact.text}`}>{fact.text} <span className="fact-citations">[{fact.citation_numbers.join(", ")}]</span></p>)}
    </div>}
    {answer.uncertainties.length > 0 && <div className="uncertainties">
      <strong>{copy.uncertainties}</strong><br />
      {answer.uncertainties.map(item => <span key={item}>{item}<br /></span>)}
    </div>}
    {answer.review_actions.length > 0 && <div className="review-actions">
      <strong>{copy.reviewActions}</strong>
      {answer.review_actions.map(action => <span key={action}>• {action}</span>)}
    </div>}
    {answer.citations.length > 0 && <div className="answer-citations">
      <p className="eyebrow">{copy.sources}</p>
      {answer.citations.map((citation, index) => <CitationLine key={`${citation.document_number}-${index}`} citation={citation} copy={copy} number={index + 1} />)}
    </div>}
    <p className="disclaimer">{answer.disclaimer}</p>
  </div>;
}

function Heading({ eyebrow, title, chip }: { eyebrow: string; title: string; chip: string }) {
  return <div className="section-heading"><div><p className="eyebrow">{eyebrow}</p><h2>{title}</h2></div><span className="chip">{chip}</span></div>;
}

function Empty({ title, text }: { title: string; text: string }) {
  return <div className="empty-state"><span className="empty-icon">⌁</span><h3>{title}</h3>{text && <p>{text}</p>}</div>;
}

function ResultState({ error, hasResults, emptyTitle, emptyText }: { error: string; hasResults: boolean; emptyTitle: string; emptyText: string }) {
  if (error) return <div className="error-state">{error}</div>;
  return hasResults ? null : <Empty title={emptyTitle} text={emptyText} />;
}

function DocumentDetailView({ detail, chunks, copy }: { detail: DocumentDetail; chunks: Chunk[]; copy: Copy }) {
  return <>
    <Heading eyebrow={copy.indexedSource} title={detail.document_number} chip={detail.document_type} />
    <p className="document-title">{detail.title}</p>
    <p className="document-source">
      {detail.source_name || copy.sourceUnavailable} · {detail.issuing_agency || copy.agencyUnavailable}{" "}
      {detail.versions[0]?.source_url && <a href={detail.versions[0].source_url} target="_blank" rel="noreferrer">{copy.officialSource}</a>}
    </p>
    <div className="version-grid">{detail.versions.map(version => <div className="version-card" key={version.id}>
      <span className="tag">{version.legal_status}</span>
      <strong>{copy.version} {version.issue_date || copy.dateUnavailable}</strong>
      <small>{copy.effective}{version.effective_date || copy.notRecorded}</small>
      <small>{version.processing_status || "NOT_PROCESSED"} · {version.chunk_count} {copy.chunks}</small>
      {version.processing_error_code && <small>{version.processing_error_code}</small>}
    </div>)}</div>
    <div className="chunk-heading"><p className="eyebrow">{copy.indexedPassages}</p><span>{chunks.length} {copy.chunks}</span></div>
    {chunks.length ? <div className="chunk-list">{chunks.map(chunk => <article className="chunk-card" key={chunk.id}>
      <div className="chunk-top">
        <strong>{chunk.article_number ? `${copy.article} ${chunk.article_number}${chunk.clause_number ? ` ${copy.clause} ${chunk.clause_number}` : ""}` : copy.documentPassage}</strong>
        <span>{pageRange(chunk.page_start, chunk.page_end, copy.pageLabel) || copy.pageUnavailable}</span>
      </div>
      {chunk.heading && <h3>{chunk.heading}</h3>}
      <details><summary>{copy.readPassage}</summary><p>{chunk.content}</p></details>
    </article>)}</div> : <Empty title={copy.noChunks} text={copy.noChunksText} />}
  </>;
}
