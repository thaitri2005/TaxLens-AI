"use client";
import { FormEvent, useEffect, useRef, useState } from "react";
import { signOut, useSession } from "next-auth/react";
import { AnswerCard } from "../components/answer";
import { DocumentDetailView, FacetGroups, OverviewPanel, Pager } from "../components/documents";
import { Empty, Heading, ResultState } from "../components/layout";
import { CitationLine, EndingTag, StatusTag } from "../components/tags";
import { SLOW_REQUEST_MS, request } from "../lib/api";
import { COPY } from "../lib/copy";
import { CHUNK_PAGE_SIZE, NO_FACETS, NO_FILTERS, SEARCH_DOCUMENT_MATCHES, SEARCH_MAX_OFFSET, SEARCH_PAGE_SIZE, documentListQuery, formatDate, groupSearchResults, labelFor } from "../lib/format";
import type { Answer, Chunk, Document, DocumentDetail, DocumentFilters, DocumentOverview, DocumentPage, FacetFilters, Language, SearchHit, View } from "../lib/types";

export default function Home() {
  const { data: session } = useSession();
  const isAdmin = session?.user.role === "admin";
  const [view, setView] = useState<View>("search");
  const [language, setLanguage] = useState<Language>("en");
  const [searchQuery, setSearchQuery] = useState("");
  const [searchMode, setSearchMode] = useState("hybrid");
  const [searchResults, setSearchResults] = useState<SearchHit[] | null>(null);
  const [searchedQuery, setSearchedQuery] = useState("");
  const [searchPageIndex, setSearchPageIndex] = useState(0);
  const [searchHasMore, setSearchHasMore] = useState(false);
  const [searchDocuments, setSearchDocuments] = useState<DocumentPage | null>(null);
  const [searchFilters, setSearchFilters] = useState<FacetFilters>(NO_FACETS);
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
  const searchTop = useRef<HTMLDivElement>(null);
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
    // The overview supplies the filter chips on both the Search and Documents tabs.
    if ((view === "search" || view === "documents") && overview === null && !overviewError) void loadOverview();
  }, [view, overview, overviewError]);

  useEffect(() => {
    // Returning to the tab keeps the page already shown; only a new page or filter loads.
    if (view === "documents" && isAdmin && listQuery !== loadedListQuery.current) void loadDocumentPage(listQuery);
  }, [view, isAdmin, listQuery]);

  useEffect(() => {
    // The library is for administrators; other users only see a document opened from search.
    if (view === "documents" && !isAdmin && !selectedDocument) setView("search");
  }, [view, isAdmin, selectedDocument]);

  useEffect(() => {
    // A changed filter reruns the current search from its first page.
    if (searchedQuery) void runSearch(searchedQuery, 0);
  }, [searchFilters]);

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

  // One page of passages at a time. The first page also looks up documents whose number or
  // title matches, the same lookup as the Documents tab, so "219/2013" finds the circular
  // itself and not only passages that mention it.
  async function runSearch(query: string, pageIndex: number) {
    setSearchBusy(true); setSearchError("");
    const offset = pageIndex * SEARCH_PAGE_SIZE;
    try {
      const params = new URLSearchParams({ q: query, mode: searchMode, limit: String(SEARCH_PAGE_SIZE + 1), offset: String(offset) });
      const documentParams = new URLSearchParams({ q: query, limit: String(SEARCH_DOCUMENT_MATCHES) });
      for (const target of [params, documentParams]) {
        if (searchFilters.source) target.set("source_name", searchFilters.source);
        if (searchFilters.kind) target.set("kind", searchFilters.kind);
        if (searchFilters.status) target.set("legal_status", searchFilters.status);
      }
      const [results, documents] = await Promise.all([
        request<SearchHit[]>(`/search?${params}`),
        pageIndex === 0
          ? request<DocumentPage>(`/documents?${documentParams}`).catch(() => null)
          : Promise.resolve(undefined),
      ]);
      setSearchedQuery(query);
      setSearchPageIndex(pageIndex);
      setSearchHasMore(results.length > SEARCH_PAGE_SIZE && offset + SEARCH_PAGE_SIZE < SEARCH_MAX_OFFSET);
      setSearchResults(results.slice(0, SEARCH_PAGE_SIZE));
      if (documents !== undefined) setSearchDocuments(documents);
      if (pageIndex > 0) searchTop.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (error) {
      setSearchError((error as Error).message);
    } finally {
      setSearchBusy(false);
    }
  }

  async function search(event: FormEvent) {
    event.preventDefault();
    await runSearch(searchQuery.trim(), 0);
  }

  function openFromSearch(document: Document) {
    setView("documents");
    void openDocument(document);
  }

  function updateSearchFilters(change: Partial<FacetFilters>) {
    setSearchFilters(previous => ({ ...previous, ...change }));
  }

  function closeDocument() {
    setSelectedDocument(null);
    // Without the library, a document opened from search returns to the search results.
    if (!isAdmin) setView("search");
  }

  function showDocumentsFor(query: string) {
    setDocumentQueryInput(query);
    updateDocumentFilters({ ...searchFilters, q: query });
    setSelectedDocument(null);
    setView("documents");
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

  const tabs: [View, string][] = [["search", copy.search], ["ask", copy.ask], ...(isAdmin ? [["documents", copy.documents] as [View, string]] : [])];
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
        {overview && <FacetGroups overview={overview} filters={searchFilters} copy={copy} numberFormat={numberFormat} onFilter={updateSearchFilters} />}
        {(searchFilters.source || searchFilters.kind || searchFilters.status) && <div className="active-filters">
          <button className="link-button" type="button" onClick={() => setSearchFilters(NO_FACETS)}>{copy.clearFilters}</button>
        </div>}
        <ResultState error={searchError} hasResults={searchResults !== null} emptyTitle={copy.searchCorpus} emptyText={copy.searchHelp} />
        {searchPageIndex === 0 && searchDocuments && searchDocuments.items.length > 0 && <div className="search-documents">
          <p className="eyebrow">{copy.matchingDocuments}</p>
          <div className="document-table">{searchDocuments.items.map(document => <button className="document-row" type="button" key={document.id} onClick={() => openFromSearch(document)}>
            <span className="document-row-number">{document.document_number}</span>
            <span className="document-row-title">{document.title}</span>
            <span className="document-row-meta">
              <span className="tag">{labelFor(copy.kinds, document.kind)}</span>
              {document.legal_status && <StatusTag status={document.legal_status} ending={document} copy={copy} />}
              <EndingTag ending={document} copy={copy} />
            </span>
            {document.preview && <span className="document-row-preview">{document.preview}</span>}
          </button>)}</div>
          {isAdmin && searchDocuments.total > searchDocuments.items.length && <button className="link-button" type="button" onClick={() => showDocumentsFor(searchedQuery)}>{copy.showAllDocuments(numberFormat.format(searchDocuments.total))} →</button>}
        </div>}
        <div ref={searchTop} className="list-anchor" />
        {searchResults && searchResults.length > 0 && <p className="eyebrow">{copy.matchingPassages}</p>}
        {searchResults && <div className={`result-list ${searchBusy ? "is-busy" : ""}`}>
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
        {searchResults && (searchPageIndex > 0 || searchHasMore) && <nav className="pager" aria-label={copy.searchPage(searchPageIndex + 1)}>
          <button type="button" disabled={searchBusy || searchPageIndex === 0} onClick={() => runSearch(searchedQuery, searchPageIndex - 1)}>{copy.previous}</button>
          <span>{copy.searchPage(searchPageIndex + 1)}</span>
          <button type="button" disabled={searchBusy || !searchHasMore} onClick={() => runSearch(searchedQuery, searchPageIndex + 1)}>{copy.next}</button>
        </nav>}
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
        {answer && <AnswerCard key={answer.question_id ?? "answer"} answer={answer} copy={copy} />}
      </section>}

      {view === "documents" && <section className="view">
        {selectedDocument ? <>
          <button className="back-button" onClick={closeDocument}>← {isAdmin ? copy.back : copy.backToSearch}</button>
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
                  {document.legal_status && <StatusTag status={document.legal_status} ending={document} copy={copy} />}
                  <EndingTag ending={document} copy={copy} />
                  <span className="document-row-date">{document.issue_date ? formatDate(document.issue_date) : "—"}</span>
                </span>
                {document.preview && <span className="document-row-preview">{document.preview}</span>}
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
