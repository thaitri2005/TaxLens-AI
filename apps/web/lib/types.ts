export type View = "search" | "ask" | "documents";

export type Language = "en" | "vi";

// A document's recorded ending (see taxlens.retrieval.repeals): explicit and ministry
// endings are confirmed, guidance and amendment endings are only inferred.
export type Ending = { ended_on?: string | null; end_basis?: string | null; ended_by?: string | null };

export type Citation = Ending & {
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

export type SearchHit = { chunk_id: string; snippet: string; content: string; fused_score: number; citation: Citation };

export type Document = Ending & { id: string; document_number: string; title: string; document_type: string; kind: string; issuing_agency: string | null; source_name: string | null };

export type DocumentListItem = Document & { legal_status: string | null; issue_date: string | null; preview: string | null };

export type DocumentPage = { total: number; items: DocumentListItem[] };

export type CountByValue = { value: string; count: number };

export type DocumentOverview = {
  total_documents: number;
  searchable_documents: number;
  passages: number;
  embedded_passages: number;
  failed_versions: number;
  by_status: CountByValue[];
  by_source: CountByValue[];
  by_kind: CountByValue[];
};

export type DocumentFilters = { q: string; source: string; kind: string; status: string };

export type Version = {
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

export type DocumentDetail = Document & { versions: Version[] };

export type Chunk = { id: string; version_id: string; article_number: string | null; clause_number: string | null; heading: string | null; page_start: number | null; page_end: number | null; content: string };

export type Claim = { text: string; citation_numbers: number[] };

export type AnswerStatus = "ANSWERED" | "UNSUPPORTED" | "INSUFFICIENT_EVIDENCE" | "PROVIDER_UNAVAILABLE" | "INVALID_MODEL_OUTPUT";

export type Answer = {
  status: AnswerStatus;
  answer: string | null;
  interpretation: string | null;
  uncertainties: string[];
  citations: Citation[];
  confirmed_facts: Claim[];
  review_actions: string[];
  practical_advice?: string[];
  disclaimer: string;
  question_id?: string | null;
};

export type SearchDocumentGroup = { document_number: string; title: string; hits: SearchHit[] };

export type FacetFilters = Omit<DocumentFilters, "q">;
