"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
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
type Document = { id: string; document_number: string; title: string; document_type: string; kind: string; issuing_agency: string | null; source_name: string | null };
type DocumentListItem = Document & { legal_status: string | null; issue_date: string | null };
type DocumentPage = { total: number; items: DocumentListItem[] };
type CountByValue = { value: string; count: number };
type DocumentOverview = {
  total_documents: number;
  searchable_documents: number;
  passages: number;
  embedded_passages: number;
  failed_versions: number;
  by_status: CountByValue[];
  by_source: CountByValue[];
  by_kind: CountByValue[];
};
type DocumentFilters = { q: string; source: string; kind: string; status: string };
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

const DOCUMENT_PAGE_SIZE = 20;
const CHUNK_PAGE_SIZE = 50;
const NO_FILTERS: DocumentFilters = { q: "", source: "", kind: "", status: "" };
// A scaled-to-zero API answers 502-504 while it starts; reads are retried instead of failing.
const RETRY_DELAYS_MS = [3000, 8000];
const SLOW_REQUEST_MS = 4000;

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
    documentsEyebrow: "Source library", documentsTitle: "Documents", libraryDocuments: "documents",
    statDocuments: "Documents", statInForce: "in force",
    statSearchable: "Searchable", statOfLibrary: "of the library",
    statPassages: "Passages", statEmbedded: "ready for semantic search",
    statAttention: "Need attention", statAttentionNote: "failed processing",
    bySource: "Source", byKind: "Kind", byStatus: "Status",
    searchDocuments: "Find a document by number or title, e.g. 219/2013 or hóa đơn", searchDocumentsButton: "Find",
    filteredBy: "Filtered by", clearFilters: "Clear filters", removeFilter: "Remove filter",
    showing: (from: number, to: number, total: string) => `${from}–${to} of ${total}`,
    pageOf: (page: number, pages: number) => `Page ${page} of ${pages}`,
    previous: "← Previous", next: "Next →",
    noMatch: "No matching documents", adjustFilters: "Try another number or title, or clear the filters.",
    slowService: "The service is starting up after a quiet period. This can take a minute.",
    loadFailed: "The library could not be loaded:", retry: "Try again",
    loadMorePassages: "Load more passages",
    kinds: {
      law: "Law", ordinance: "Ordinance", resolution: "Resolution", decree: "Decree", decision: "Decision",
      circular: "Circular", joint_circular: "Joint circular", consolidated: "Consolidated text", directive: "Directive", other: "Other",
    } as Record<string, string>,
    legalStatuses: {
      EFFECTIVE: "In force", PARTIALLY_EXPIRED: "Partly expired", EXPIRED: "Expired",
      NOT_YET_EFFECTIVE: "Not yet in force", DISCOVERED: "Status not recorded", UNKNOWN: "Status unknown",
    } as Record<string, string>,
    sourceNames: { "government-portal": "Government portal", "mof-vbpq": "Ministry of Finance" } as Record<string, string>,
    working: "Working…", evidencePassage: "evidence passage", evidencePassages: "evidence passages", relevantPassage: "Relevant passage",
    noResults: "No matching passages", broaden: "Try a broader Vietnamese or English query.", loadMore: "Load more results",
    searchCorpus: "Search the corpus", searchHelp: "Each document appears once with its strongest evidence passages.",
    article: "Article", clause: "clause", page: "p.", sourcePassage: "Source passage", officialSource: "Official source ↗",
    back: "Back to documents", readingDocument: "Reading versions and indexed passages.",
    indexedSource: "Indexed source", sourceUnavailable: "Source unavailable", agencyUnavailable: "Issuing agency not recorded",
    version: "Version", dateUnavailable: "date unavailable", effective: "Effective: ", notRecorded: "not recorded", chunks: "passages",
    indexedPassages: "Indexed passages", documentPassage: "Document passage", pageLabel: "Page", pageUnavailable: "Page unavailable",
    readPassage: "Read indexed passage", noChunks: "No indexed passages", noChunksText: "This document has not produced searchable passages yet.",
    admin: "Admin", signOut: "Sign out", brandTagline: "Regulatory intelligence",
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
    documentsEyebrow: "Thư viện văn bản", documentsTitle: "Văn bản pháp luật", libraryDocuments: "văn bản",
    statDocuments: "Văn bản", statInForce: "còn hiệu lực",
    statSearchable: "Tra cứu được", statOfLibrary: "tổng số văn bản",
    statPassages: "Đoạn trích", statEmbedded: "sẵn sàng tìm kiếm ngữ nghĩa",
    statAttention: "Cần xử lý", statAttentionNote: "xử lý không thành công",
    bySource: "Nguồn", byKind: "Loại", byStatus: "Hiệu lực",
    searchDocuments: "Tìm theo số hiệu hoặc trích yếu, ví dụ 219/2013 hoặc hóa đơn", searchDocumentsButton: "Tìm",
    filteredBy: "Đang lọc theo", clearFilters: "Xóa bộ lọc", removeFilter: "Bỏ bộ lọc",
    showing: (from: number, to: number, total: string) => `${from}–${to} trên ${total}`,
    pageOf: (page: number, pages: number) => `Trang ${page}/${pages}`,
    previous: "← Trang trước", next: "Trang sau →",
    noMatch: "Không có văn bản phù hợp", adjustFilters: "Hãy thử số hiệu hoặc trích yếu khác, hoặc xóa bộ lọc.",
    slowService: "Hệ thống đang khởi động lại sau một thời gian không hoạt động. Việc này có thể mất khoảng một phút.",
    loadFailed: "Không tải được thư viện văn bản:", retry: "Thử lại",
    loadMorePassages: "Tải thêm đoạn trích",
    kinds: {
      law: "Luật", ordinance: "Pháp lệnh", resolution: "Nghị quyết", decree: "Nghị định", decision: "Quyết định",
      circular: "Thông tư", joint_circular: "Thông tư liên tịch", consolidated: "Văn bản hợp nhất", directive: "Chỉ thị", other: "Khác",
    } as Record<string, string>,
    legalStatuses: {
      EFFECTIVE: "Còn hiệu lực", PARTIALLY_EXPIRED: "Hết hiệu lực một phần", EXPIRED: "Hết hiệu lực",
      NOT_YET_EFFECTIVE: "Chưa có hiệu lực", DISCOVERED: "Chưa ghi nhận hiệu lực", UNKNOWN: "Không xác định",
    } as Record<string, string>,
    sourceNames: { "government-portal": "Cổng TTĐT Chính phủ", "mof-vbpq": "Bộ Tài chính" } as Record<string, string>,
    working: "Đang xử lý…", evidencePassage: "đoạn trích", evidencePassages: "đoạn trích", relevantPassage: "Đoạn trích liên quan",
    noResults: "Không tìm thấy đoạn phù hợp", broaden: "Hãy thử câu hỏi rộng hơn bằng tiếng Việt hoặc tiếng Anh.", loadMore: "Tải thêm kết quả",
    searchCorpus: "Tìm kiếm trong kho văn bản", searchHelp: "Các văn bản phù hợp kèm đoạn trích liên quan.",
    article: "Điều", clause: "khoản", page: "tr.", sourcePassage: "Đoạn trích nguồn", officialSource: "Nguồn chính thức ↗",
    back: "Quay lại danh sách", readingDocument: "Đang đọc thông tin văn bản và các đoạn trích.",
    indexedSource: "Văn bản đã xử lý", sourceUnavailable: "Nguồn chưa được ghi nhận", agencyUnavailable: "Cơ quan ban hành chưa được ghi nhận",
    version: "Ngày ban hành", dateUnavailable: "chưa ghi nhận", effective: "Hiệu lực: ", notRecorded: "chưa ghi nhận", chunks: "đoạn trích",
    indexedPassages: "Các đoạn trích đã xử lý", documentPassage: "Đoạn trích văn bản", pageLabel: "Trang", pageUnavailable: "Chưa ghi nhận số trang",
    readPassage: "Xem đoạn trích", noChunks: "Chưa có đoạn trích", noChunksText: "Văn bản này chưa có đoạn trích để tìm kiếm.",
    admin: "Quản trị", signOut: "Đăng xuất", brandTagline: "Thông tin pháp lý",
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

const UNAVAILABLE_STATUSES = new Set([502, 503, 504]);

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  // Reads are retried while the API starts; a question (POST) is never sent twice.
  const retries = !options?.method || options.method === "GET" ? RETRY_DELAYS_MS.length : 0;
  for (let attempt = 0; ; attempt += 1) {
    let response: Response | null = null;
    try {
      response = await fetch(`/api${path}`, { headers: { "Content-Type": "application/json" }, ...options });
    } catch {
      response = null;
    }
    if ((response === null || UNAVAILABLE_STATUSES.has(response.status)) && attempt < retries) {
      await new Promise(resolve => setTimeout(resolve, RETRY_DELAYS_MS[attempt]));
      continue;
    }
    if (response === null) throw new Error("The service could not be reached.");
    const body = await response.json().catch(() => ({}));
    // The sign-in session (8 hours) has ended: go back to the login page.
    if (response.status === 401 && body.detail === "Authentication required") window.location.assign("/login");
    if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "The request could not be completed.");
    return body as T;
  }
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

function labelFor(labels: Record<string, string>, value: string) {
  return labels[value] ?? value;
}

function formatDate(isoDate: string) {
  return isoDate.split("-").reverse().join("/");
}

function documentListQuery(filters: DocumentFilters, pageIndex: number) {
  const params = new URLSearchParams({ limit: String(DOCUMENT_PAGE_SIZE), offset: String(pageIndex * DOCUMENT_PAGE_SIZE) });
  if (filters.q) params.set("q", filters.q);
  if (filters.source) params.set("source_name", filters.source);
  if (filters.kind) params.set("kind", filters.kind);
  if (filters.status) params.set("legal_status", filters.status);
  return params.toString();
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
  const [overview, setOverview] = useState<DocumentOverview | null>(null);
  const [overviewError, setOverviewError] = useState("");
  const [documentFilters, setDocumentFilters] = useState<DocumentFilters>(NO_FILTERS);
  const [documentQueryInput, setDocumentQueryInput] = useState("");
  const [documentPageIndex, setDocumentPageIndex] = useState(0);
  const [documentPage, setDocumentPage] = useState<DocumentPage | null>(null);
  const [documentListBusy, setDocumentListBusy] = useState(false);
  const [documentListError, setDocumentListError] = useState("");
  const [documentsSlow, setDocumentsSlow] = useState(false);
  const [selectedDocument, setSelectedDocument] = useState<Document | null>(null);
  const [documentDetail, setDocumentDetail] = useState<DocumentDetail | null>(null);
  const [documentChunks, setDocumentChunks] = useState<Chunk[]>([]);
  const [documentBusy, setDocumentBusy] = useState(false);
  const [chunksBusy, setChunksBusy] = useState(false);
  const [documentError, setDocumentError] = useState("");
  const loadedListQuery = useRef("");
  const latestListRequest = useRef(0);
  const listTop = useRef<HTMLDivElement>(null);
  const copy = COPY[language];
  const numberFormat = new Intl.NumberFormat(language === "vi" ? "vi-VN" : "en-US");
  const listQuery = documentListQuery(documentFilters, documentPageIndex);

  // The Documents tab loads a small summary and one page of 20 documents; the list is
  // never loaded whole. Both requests start together so the summary shows first.
  async function loadOverview() {
    setOverviewError("");
    try {
      setOverview(await request<DocumentOverview>("/documents/overview"));
    } catch (error) {
      setOverviewError((error as Error).message);
    }
  }

  async function loadDocumentPage(query: string) {
    const requestId = ++latestListRequest.current;
    loadedListQuery.current = query;
    setDocumentListBusy(true); setDocumentListError("");
    const slowTimer = setTimeout(() => setDocumentsSlow(true), SLOW_REQUEST_MS);
    try {
      const page = await request<DocumentPage>(`/documents?${query}`);
      if (requestId === latestListRequest.current) setDocumentPage(page);
    } catch (error) {
      if (requestId === latestListRequest.current) {
        loadedListQuery.current = "";
        setDocumentListError((error as Error).message);
      }
    } finally {
      clearTimeout(slowTimer);
      if (requestId === latestListRequest.current) { setDocumentListBusy(false); setDocumentsSlow(false); }
    }
  }

  useEffect(() => {
    if (view === "documents" && overview === null && !overviewError) void loadOverview();
  }, [view, overview, overviewError]);

  useEffect(() => {
    // Returning to the tab keeps the page already shown; only a new page or filter loads.
    if (view === "documents" && listQuery !== loadedListQuery.current) void loadDocumentPage(listQuery);
  }, [view, listQuery]);

  function updateDocumentFilters(change: Partial<DocumentFilters>) {
    setDocumentFilters(previous => ({ ...previous, ...change }));
    setDocumentPageIndex(0);
  }

  function clearDocumentFilters() {
    setDocumentQueryInput("");
    setDocumentFilters(NO_FILTERS);
    setDocumentPageIndex(0);
  }

  function goToDocumentPage(pageIndex: number) {
    setDocumentPageIndex(pageIndex);
    listTop.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function openDocument(document: Document) {
    setSelectedDocument(document); setDocumentDetail(null); setDocumentChunks([]); setDocumentError(""); setDocumentBusy(true);
    try {
      const [detail, chunks] = await Promise.all([
        request<DocumentDetail>(`/documents/${document.id}`),
        request<Chunk[]>(`/documents/${document.id}/chunks?limit=${CHUNK_PAGE_SIZE}&offset=0`),
      ]);
      setDocumentDetail(detail);
      setDocumentChunks(chunks);
    } catch (error) {
      setDocumentError((error as Error).message);
    } finally {
      setDocumentBusy(false);
    }
  }

  async function loadMoreChunks() {
    if (!documentDetail) return;
    setChunksBusy(true);
    try {
      const more = await request<Chunk[]>(`/documents/${documentDetail.id}/chunks?limit=${CHUNK_PAGE_SIZE}&offset=${documentChunks.length}`);
      setDocumentChunks(previous => [...previous, ...more]);
    } catch (error) {
      setDocumentError((error as Error).message);
    } finally {
      setChunksBusy(false);
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

  function findDocuments(event: FormEvent) {
    event.preventDefault();
    updateDocumentFilters({ q: documentQueryInput.trim() });
  }

  const tabs: [View, string][] = [["search", copy.search], ["ask", copy.ask], ["documents", copy.documents]];
  const activeFilters: [keyof DocumentFilters, string][] = [
    ["q", documentFilters.q ? `“${documentFilters.q}”` : ""],
    ["source", documentFilters.source && labelFor(copy.sourceNames, documentFilters.source)],
    ["kind", documentFilters.kind && labelFor(copy.kinds, documentFilters.kind)],
    ["status", documentFilters.status && labelFor(copy.legalStatuses, documentFilters.status)],
  ];
  const shownFilters = activeFilters.filter(([, label]) => label);

  return <>
    <header className="topbar">
      <a className="brand" href="#search"><img className="brand-mark" src="/logo.svg" alt="" width={34} height={34} /><span><strong>TaxLens</strong><small>{copy.brandTagline}</small></span></a>
      <div className="topbar-actions">
        <div className="language-toggle" aria-label="Language">
          <button className={language === "en" ? "active" : ""} onClick={() => setLanguage("en")}>EN</button>
          <button className={language === "vi" ? "active" : ""} onClick={() => setLanguage("vi")}>VI</button>
        </div>
        {session?.user.role === "admin" && <a className="topbar-link" href="/admin">{copy.admin}</a>}
        <button className="sign-out-button" type="button" onClick={() => signOut({ redirect: false }).then(() => window.location.assign("/login"))}>{copy.signOut}</button>
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
            : documentDetail && <DocumentDetailView detail={documentDetail} chunks={documentChunks} copy={copy} numberFormat={numberFormat} onLoadMore={loadMoreChunks} loadingMore={chunksBusy} />}
        </> : <>
          <Heading eyebrow={copy.documentsEyebrow} title={copy.documentsTitle} chip={overview ? `${numberFormat.format(overview.total_documents)} ${copy.libraryDocuments}` : "…"} />
          {overviewError
            ? <div className="error-state">{copy.loadFailed} {overviewError} <button className="link-button" type="button" onClick={() => setOverviewError("")}>{copy.retry}</button></div>
            : <OverviewPanel overview={overview} filters={documentFilters} copy={copy} numberFormat={numberFormat} onFilter={updateDocumentFilters} />}

          <form className="library-search" onSubmit={findDocuments}>
            <label className="search-box">
              <span>⌕</span>
              <input value={documentQueryInput} onChange={event => setDocumentQueryInput(event.target.value)} maxLength={200} placeholder={copy.searchDocuments} aria-label={copy.searchDocuments} />
              <button type="submit">{copy.searchDocumentsButton}</button>
            </label>
          </form>
          {shownFilters.length > 0 && <div className="active-filters">
            <span>{copy.filteredBy}</span>
            {shownFilters.map(([key, label]) => <button key={key} className="facet-chip active" type="button" aria-label={`${copy.removeFilter}: ${label}`} onClick={() => { if (key === "q") setDocumentQueryInput(""); updateDocumentFilters({ [key]: "" } as Partial<DocumentFilters>); }}>{label} ×</button>)}
            <button className="link-button" type="button" onClick={clearDocumentFilters}>{copy.clearFilters}</button>
          </div>}

          <div ref={listTop} className="list-anchor" />
          {documentsSlow && <p className="slow-note">{copy.slowService}</p>}
          {documentListError
            ? <div className="error-state">{copy.loadFailed} {documentListError} <button className="link-button" type="button" onClick={() => loadDocumentPage(listQuery)}>{copy.retry}</button></div>
            : documentPage === null ? <div className="document-table" aria-busy="true">{Array.from({ length: 6 }, (_, index) => <div className="skeleton-row" key={index} />)}</div>
            : documentPage.items.length === 0 ? <Empty title={copy.noMatch} text={copy.adjustFilters} />
            : <div className={`document-table ${documentListBusy ? "is-busy" : ""}`} aria-busy={documentListBusy}>
              {documentPage.items.map(document => <button className="document-row" type="button" key={document.id} onClick={() => openDocument(document)}>
                <span className="document-row-number">{document.document_number}</span>
                <span className="document-row-title">{document.title}</span>
                <span className="document-row-meta">
                  <span className="tag">{labelFor(copy.kinds, document.kind)}</span>
                  {document.legal_status && <StatusTag status={document.legal_status} copy={copy} />}
                  <span className="document-row-date">{document.issue_date ? formatDate(document.issue_date) : "—"}</span>
                </span>
              </button>)}
            </div>}
          {documentPage && documentPage.total > 0 && <Pager
            pageIndex={documentPageIndex}
            total={documentPage.total}
            copy={copy}
            numberFormat={numberFormat}
            busy={documentListBusy}
            onPage={goToDocumentPage}
          />}
        </>}
      </section>}
    </main>
    <footer><span>TaxLens AI</span><span>Evidence first</span></footer>
  </>;
}

function OverviewPanel({ overview, filters, copy, numberFormat, onFilter }: {
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
    <div className="facet-groups">
      <FacetRow label={copy.bySource} items={overview.by_source} active={filters.source} labels={copy.sourceNames} format={format} onSelect={source => onFilter({ source })} />
      <FacetRow label={copy.byKind} items={overview.by_kind} active={filters.kind} labels={copy.kinds} format={format} onSelect={kind => onFilter({ kind })} />
      <FacetRow label={copy.byStatus} items={overview.by_status} active={filters.status} labels={copy.legalStatuses} format={format} onSelect={status => onFilter({ status })} />
    </div>
  </>;
}

function StatCard({ label, value, note, warn = false }: { label: string; value: string; note: string; warn?: boolean }) {
  return <div className={`stat-card ${warn ? "warn" : ""}`}><span>{label}</span><strong>{value}</strong><small>{note}</small></div>;
}

function FacetRow({ label, items, active, labels, format, onSelect }: {
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

function StatusTag({ status, copy }: { status: string; copy: Copy }) {
  return <span className={`status-tag status-${status.toLowerCase()}`}>{labelFor(copy.legalStatuses, status)}</span>;
}

function Pager({ pageIndex, total, copy, numberFormat, busy, onPage }: {
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

function DocumentDetailView({ detail, chunks, copy, numberFormat, onLoadMore, loadingMore }: {
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
    <p className="document-source">
      {labelFor(copy.sourceNames, detail.source_name || "") || copy.sourceUnavailable} · {detail.issuing_agency || copy.agencyUnavailable}{" "}
      {detail.versions[0]?.source_url && <a href={detail.versions[0].source_url} target="_blank" rel="noreferrer">{copy.officialSource}</a>}
    </p>
    <div className="version-grid">{detail.versions.map(version => <div className="version-card" key={version.id}>
      <StatusTag status={version.legal_status} copy={copy} />
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
