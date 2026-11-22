import type { Copy } from "../lib/copy";
import { CONFIRMED_ENDINGS, formatDate, hasConfirmedlyEnded, labelFor, locationLabel, todayInVietnam } from "../lib/format";
import type { Citation, Ending } from "../lib/types";
export function EndingTag({ ending, copy }: { ending: Ending; copy: Copy }) {
  if (!ending.ended_on || !ending.end_basis) return null;
  const date = formatDate(ending.ended_on);
  const later = ending.ended_on > todayInVietnam();
  const confirmed = CONFIRMED_ENDINGS.includes(ending.end_basis);
  const label = later ? copy.endings.endsLater(date) : confirmed ? copy.endings.ended(date) : copy.endings.mayHaveEnded(date);
  const detail = ending.end_basis === "ministry" ? copy.endings.ministryRecord
    : !ending.ended_by ? null
    : ending.end_basis === "explicit" ? copy.endings.by(ending.ended_by)
    : later ? null
    : ending.end_basis === "guidance" ? copy.endings.guides(ending.ended_by) : copy.endings.amends(ending.ended_by);
  return <span className={`status-tag ${confirmed && !later ? "status-expired" : "status-partially_expired"}`}>
    {label}{detail ? ` · ${detail}` : ""}
  </span>;
}

// The ministry still lists some ended documents as in force; a confirmed ending that has
// passed wins over that status, so the two tags never contradict each other.
export function StatusTag({ status, ending, copy }: { status: string; ending?: Ending; copy: Copy }) {
  if (status === "EFFECTIVE" && ending && hasConfirmedlyEnded(ending)) return null;
  return <span className={`status-tag status-${status.toLowerCase()}`}>{labelFor(copy.legalStatuses, status)}</span>;
}

export function CitationLine({ citation, copy, number }: { citation: Citation; copy: Copy; number?: number }) {
  return (
    <div className="citation">
      {number !== undefined && <span className="source-number">[{number}]</span>}
      <span className="tag">{citation.document_number}</span>
      <EndingTag ending={citation} copy={copy} />
      <span>{locationLabel(citation, copy) || copy.sourcePassage}</span>
      {citation.heading && <span>{citation.heading}</span>}
      {citation.source_url && <a href={citation.source_url} target="_blank" rel="noreferrer">{copy.officialSource}</a>}
    </div>
  );
}
